"""
Plugin Service — Mediates between PluginRegistry (in-memory) and DB persistence.

Phase 4C.1.5: CRUD for plugin configs, execution with history, registry sync.

The service translates web-context (PluginContext) into the existing
AutoOpsContext + GodKaiserClient that plugins expect.
"""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..autoops.core.api_client import GodKaiserClient
from ..autoops.core.base_plugin import PluginContext, PluginResult
from ..autoops.core.context import AutoOpsContext, DeviceMode
from ..autoops.core.plugin_registry import PluginRegistry
from ..core.logging_config import get_logger
from ..core.metrics import (
    increment_plugin_execution,
    increment_plugin_error,
    observe_plugin_duration,
    update_plugins_registered,
)
from ..db.models.plugin import PluginConfig, PluginExecution

logger = get_logger(__name__)


class PluginNotFoundError(Exception):
    """Raised when a plugin is not found in the registry."""

    def __init__(self, plugin_id: str):
        self.plugin_id = plugin_id
        super().__init__(f"Plugin '{plugin_id}' not found")


class PluginDisabledError(Exception):
    """Raised when a plugin is disabled and cannot be executed."""

    def __init__(self, plugin_id: str):
        self.plugin_id = plugin_id
        super().__init__(f"Plugin '{plugin_id}' is disabled")


class PluginService:
    """Mediates between PluginRegistry (in-memory) and DB persistence."""

    def __init__(self, db: AsyncSession, registry: PluginRegistry):
        self.db = db
        self.registry = registry

    async def sync_registry_to_db(self) -> None:
        """Sync in-memory registry plugins to DB. Called at server startup."""
        for plugin in self.registry.get_all():
            plugin_id = plugin.name
            existing = await self.db.get(PluginConfig, plugin_id)
            if not existing:
                config = PluginConfig(
                    plugin_id=plugin_id,
                    display_name=getattr(plugin, "_display_name", plugin.name),
                    description=getattr(plugin, "_description", plugin.description),
                    category=getattr(plugin, "_category", "monitoring"),
                    config_schema=getattr(plugin, "_config_schema", {}),
                    capabilities=[c.value for c in plugin.capabilities],
                )
                self.db.add(config)
                logger.info(f"Plugin '{plugin_id}' synced to DB")
            else:
                # Update metadata from code (display_name, description, etc.)
                existing.display_name = getattr(plugin, "_display_name", plugin.name)
                existing.description = getattr(plugin, "_description", plugin.description)
                existing.category = getattr(plugin, "_category", existing.category)
                existing.config_schema = getattr(plugin, "_config_schema", existing.config_schema)
                existing.capabilities = [c.value for c in plugin.capabilities]
        await self.db.commit()
        update_plugins_registered(len(self.registry.get_all()))

    async def get_all_plugins(self) -> list[dict[str, Any]]:
        """All plugins with DB config + registry status."""
        result = await self.db.execute(select(PluginConfig))
        configs = result.scalars().all()
        plugins = []
        for config in configs:
            plugin = self.registry.get(config.plugin_id)

            # Get last execution
            last_exec_result = await self.db.execute(
                select(PluginExecution)
                .where(PluginExecution.plugin_id == config.plugin_id)
                .order_by(PluginExecution.started_at.desc())
                .limit(1)
            )
            last_exec = last_exec_result.scalars().first()

            plugins.append(
                {
                    "plugin_id": config.plugin_id,
                    "display_name": config.display_name,
                    "description": config.description,
                    "category": config.category,
                    "is_enabled": config.is_enabled,
                    "config": config.config,
                    "config_schema": config.config_schema,
                    "capabilities": config.capabilities or [],
                    "schedule": config.schedule,
                    "is_registered": plugin is not None,
                    "last_execution": (
                        {
                            "id": str(last_exec.id),
                            "status": last_exec.status,
                            "started_at": (
                                last_exec.started_at.isoformat() if last_exec.started_at else None
                            ),
                            "finished_at": (
                                last_exec.finished_at.isoformat() if last_exec.finished_at else None
                            ),
                            "duration_seconds": last_exec.duration_seconds,
                        }
                        if last_exec
                        else None
                    ),
                }
            )
        return plugins

    async def get_plugin_detail(self, plugin_id: str) -> dict[str, Any]:
        """Plugin details including config schema and last execution."""
        config = await self.db.get(PluginConfig, plugin_id)
        if not config:
            raise PluginNotFoundError(plugin_id)

        plugin = self.registry.get(plugin_id)

        # Last 5 executions
        exec_result = await self.db.execute(
            select(PluginExecution)
            .where(PluginExecution.plugin_id == plugin_id)
            .order_by(PluginExecution.started_at.desc())
            .limit(5)
        )
        recent_executions = exec_result.scalars().all()

        return {
            "plugin_id": config.plugin_id,
            "display_name": config.display_name,
            "description": config.description,
            "category": config.category,
            "is_enabled": config.is_enabled,
            "config": config.config,
            "config_schema": config.config_schema,
            "capabilities": config.capabilities or [],
            "schedule": config.schedule,
            "is_registered": plugin is not None,
            "version": plugin.version if plugin else None,
            "requires_auth": plugin.requires_auth if plugin else None,
            "recent_executions": [
                {
                    "id": str(e.id),
                    "status": e.status,
                    "started_at": e.started_at.isoformat() if e.started_at else None,
                    "finished_at": e.finished_at.isoformat() if e.finished_at else None,
                    "triggered_by": e.triggered_by,
                    "duration_seconds": e.duration_seconds,
                    "error_message": e.error_message,
                }
                for e in recent_executions
            ],
        }

    async def execute_plugin(
        self,
        plugin_id: str,
        user_id: int | None,
        context: PluginContext,
    ) -> PluginExecution:
        """Execute a plugin and persist the result."""
        plugin = self.registry.get(plugin_id)
        if not plugin:
            raise PluginNotFoundError(plugin_id)

        config = await self.db.get(PluginConfig, plugin_id)
        if config and not config.is_enabled:
            raise PluginDisabledError(plugin_id)

        # Create execution record
        execution = PluginExecution(
            plugin_id=plugin_id,
            triggered_by=context.trigger_source,
            triggered_by_user=user_id,
            triggered_by_rule=context.trigger_rule_id,
            status="running",
        )
        self.db.add(execution)
        await self.db.flush()

        # WebSocket broadcast: execution started
        await self._broadcast_ws(
            "plugin_execution_started",
            {
                "execution_id": str(execution.id),
                "plugin_id": plugin_id,
                "trigger_source": context.trigger_source,
            },
        )

        start_time = datetime.now(timezone.utc)
        result: PluginResult | None = None
        autoops_context = None
        client = None
        try:
            # Build AutoOpsContext + GodKaiserClient for plugin.execute()
            # Phase 4C.4: Enrich context with config overrides from DB + request
            merged_config = {**(config.config if config else {})}
            if context.config_overrides:
                merged_config.update(context.config_overrides)

            # Resolve internal URL from settings (Docker: http://el-servador:8000)
            from ..core.config import get_settings

            settings = get_settings()
            internal_url = settings.server.internal_url

            autoops_context = AutoOpsContext(
                server_url=internal_url,
                device_mode=DeviceMode.MOCK,
            )
            # Enrich context with ESP devices and active alerts from DB
            esp_devices_data: list[dict] = []
            active_alerts_data: list[dict] = []
            try:
                from ..db.repositories import ESPRepository

                esp_repo = ESPRepository(self.db)
                devices = await esp_repo.get_all()
                esp_devices_data = [
                    {
                        "esp_id": d.esp_id if hasattr(d, "esp_id") else str(d.id),
                        "name": d.name,
                        "status": d.status,
                    }
                    for d in devices
                ]
            except Exception as enrich_err:
                logger.debug(f"Plugin context enrichment (devices) skipped: {enrich_err}")

            try:
                from ..db.repositories.notification_repo import NotificationRepository

                notif_repo = NotificationRepository(self.db)
                alerts, _ = await notif_repo.get_alerts_by_status("active", limit=20)
                active_alerts_data = [
                    {
                        "id": str(a.id),
                        "title": a.title,
                        "severity": a.severity,
                        "category": a.category,
                        "created_at": a.created_at.isoformat() if a.created_at else None,
                    }
                    for a in alerts
                ]
            except Exception as enrich_err:
                logger.debug(f"Plugin context enrichment (alerts) skipped: {enrich_err}")

            # Attach enrichment data to context for plugins that need it
            autoops_context.extra = {
                "trigger_source": context.trigger_source,
                "trigger_rule_id": (
                    str(context.trigger_rule_id) if context.trigger_rule_id else None
                ),
                "trigger_value": context.trigger_value,
                "config_overrides": merged_config,
                "user_id": user_id,
                "esp_devices": esp_devices_data,
                "active_alerts": active_alerts_data,
            }

            client = GodKaiserClient(autoops_context.server_url)
            # Authenticate with default admin credentials
            try:
                await client.authenticate(
                    username=autoops_context.username,
                    password=autoops_context.password,
                )
            except Exception as auth_err:
                logger.warning(f"Plugin auth failed (non-fatal): {auth_err}")

            result = await plugin.execute(autoops_context, client)

            execution.status = "success" if result.success else "error"
            execution.result = _serialize_plugin_result(result)
            if not result.success:
                execution.error_message = "; ".join(result.errors)
                # Attempt rollback on logical failure (not just exceptions)
                try:
                    await plugin.rollback(autoops_context, client, result.actions)
                except Exception as rollback_err:
                    logger.warning(f"Plugin '{plugin_id}' rollback failed: {rollback_err}")

            await client.close()
        except Exception as e:
            execution.status = "error"
            execution.error_message = str(e)
            logger.error(f"Plugin '{plugin_id}' execution failed: {e}", exc_info=True)
            # Attempt rollback only if context/client were created (avoid NameError)
            if autoops_context is not None and client is not None:
                try:
                    actions = result.actions if result else []
                    await plugin.rollback(autoops_context, client, actions)
                except Exception:
                    pass
        finally:
            execution.finished_at = datetime.now(timezone.utc)
            execution.duration_seconds = (execution.finished_at - start_time).total_seconds()
            await self.db.commit()

            # Prometheus metrics
            increment_plugin_execution(
                plugin_id=plugin_id,
                status=execution.status,
                trigger_source=context.trigger_source,
            )
            observe_plugin_duration(plugin_id, execution.duration_seconds)
            if execution.status == "error":
                error_type = (
                    "rollback_failed" if result and not result.success else "execution_failed"
                )
                increment_plugin_error(plugin_id, error_type)

            # WebSocket broadcast: execution completed
            await self._broadcast_ws(
                "plugin_execution_completed",
                {
                    "execution_id": str(execution.id),
                    "plugin_id": plugin_id,
                    "status": execution.status,
                    "duration_seconds": execution.duration_seconds,
                    "error_message": execution.error_message,
                },
            )

        return execution

    async def update_config(self, plugin_id: str, config: dict[str, Any]) -> PluginConfig:
        """Update plugin configuration."""
        db_config = await self.db.get(PluginConfig, plugin_id)
        if not db_config:
            raise PluginNotFoundError(plugin_id)
        db_config.config = config
        await self.db.commit()
        return db_config

    async def toggle_plugin(self, plugin_id: str, enabled: bool) -> PluginConfig:
        """Enable or disable a plugin."""
        db_config = await self.db.get(PluginConfig, plugin_id)
        if not db_config:
            raise PluginNotFoundError(plugin_id)
        db_config.is_enabled = enabled
        await self.db.commit()
        return db_config

    async def get_execution_history(self, plugin_id: str, limit: int = 50) -> list[PluginExecution]:
        """Get execution history for a plugin."""
        result = await self.db.execute(
            select(PluginExecution)
            .where(PluginExecution.plugin_id == plugin_id)
            .order_by(PluginExecution.started_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def update_schedule(self, plugin_id: str, schedule: str | None) -> PluginConfig:
        """Update plugin schedule and re-register scheduler job.

        When a schedule is changed via API, the old APScheduler job is removed
        and a new one registered immediately (no server restart required).
        """
        db_config = await self.db.get(PluginConfig, plugin_id)
        if not db_config:
            raise PluginNotFoundError(plugin_id)

        old_schedule = db_config.schedule
        db_config.schedule = schedule
        await self.db.commit()

        # Update APScheduler job reactively
        try:
            from ..core.scheduler import get_central_scheduler, JobCategory, parse_cron_string

            scheduler = get_central_scheduler()
            job_id = f"plugin_{plugin_id}"

            # Remove old job (returns False if not present — no error)
            scheduler.remove_job(job_id, category=JobCategory.CUSTOM)

            # Register new job if schedule is set
            if schedule:
                cron_dict = parse_cron_string(schedule)

                async def _execute(pid=plugin_id):
                    from ..db.session import get_session
                    from ..autoops.core.plugin_registry import PluginRegistry
                    from ..autoops.core.base_plugin import PluginContext

                    async for session in get_session():
                        registry = PluginRegistry()
                        registry.discover_plugins()
                        ps = PluginService(session, registry)
                        context = PluginContext(
                            trigger_source="schedule",
                        )
                        await ps.execute_plugin(plugin_id=pid, user_id=None, context=context)
                        break

                scheduler.add_cron_job(
                    job_id=job_id,
                    func=_execute,
                    cron_expression=cron_dict,
                    category=JobCategory.CUSTOM,
                )

            logger.info(f"Plugin '{plugin_id}' schedule updated: {old_schedule} → {schedule}")
        except RuntimeError:
            # Scheduler not initialized (e.g., during tests)
            logger.debug(f"Plugin '{plugin_id}' schedule saved to DB but scheduler not available")

        return db_config

    @staticmethod
    async def _broadcast_ws(event_type: str, data: dict) -> None:
        """Best-effort WebSocket broadcast for plugin events."""
        try:
            from ..websocket.manager import WebSocketManager

            ws_manager = await WebSocketManager.get_instance()
            await ws_manager.broadcast(event_type, data)
        except Exception as e:
            logger.debug(f"WebSocket broadcast '{event_type}' skipped: {e}")

    async def get_scheduled_plugins(self) -> list[PluginConfig]:
        """Get all plugins that have a schedule configured."""
        result = await self.db.execute(
            select(PluginConfig).where(
                PluginConfig.schedule.isnot(None),
                PluginConfig.is_enabled.is_(True),
            )
        )
        return list(result.scalars().all())


def _serialize_plugin_result(result: PluginResult) -> dict[str, Any]:
    """Serialize PluginResult to JSON-safe dict (handles Enums)."""
    return {
        "success": result.success,
        "summary": result.summary,
        "actions": [
            {
                "timestamp": a.timestamp,
                "action": a.action,
                "target": a.target,
                "details": a.details,
                "result": a.result,
                "severity": a.severity.value,
                "api_endpoint": a.api_endpoint,
                "api_method": a.api_method,
                "api_response_code": a.api_response_code,
            }
            for a in result.actions
        ],
        "errors": result.errors,
        "warnings": result.warnings,
        "data": result.data,
        "needs_user_input": result.needs_user_input,
        "questions": [
            {
                "question": q.question,
                "options": q.options,
                "default": q.default,
                "required": q.required,
                "context": q.context,
            }
            for q in result.questions
        ],
    }
