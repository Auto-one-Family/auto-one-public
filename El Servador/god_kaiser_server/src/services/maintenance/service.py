"""
Maintenance Service

Manages all maintenance and monitoring jobs:
- Cleanup jobs (sensor data, command history, orphaned mocks)
- Health check jobs (ESP timeouts, MQTT broker)
- Statistics aggregation

Uses CentralScheduler for job management.
"""

import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional


from ...core.config import Settings
from ...core.logging_config import get_logger
from ...core.scheduler import CentralScheduler, JobCategory
from ...mqtt.client import MQTTClient

logger = get_logger(__name__)


class MaintenanceService:
    """
    Service for managing maintenance and monitoring jobs.

    Registers cleanup, health check, and statistics aggregation jobs
    with the CentralScheduler.
    """

    def __init__(
        self,
        scheduler: CentralScheduler,
        session_factory: Callable,
        mqtt_client: MQTTClient,
        settings: Settings,
    ):
        """
        Initialize MaintenanceService.

        Args:
            scheduler: CentralScheduler instance
            session_factory: Async function that yields DB sessions
            mqtt_client: MQTTClient instance
            settings: Settings instance
        """
        self._scheduler = scheduler
        self._session_factory = session_factory
        self._mqtt_client = mqtt_client
        self._settings = settings
        self._maintenance_settings = settings.maintenance

        # Stats cache (in-memory)
        self._stats_cache: Dict[str, Any] = {
            "last_updated": None,
            "total_esps": 0,
            "online_esps": 0,
            "offline_esps": 0,
            "total_sensors": 0,
            "total_actuators": 0,
        }

        # Job execution tracking
        self._job_results: Dict[str, Dict[str, Any]] = {}

        logger.info("MaintenanceService initialized")

    def start(self) -> None:
        """Register all maintenance jobs with the scheduler."""
        logger.info("Starting MaintenanceService - registering jobs...")

        # ────────────────────────────────────────────────────
        # STARTUP WARNING: Cleanup-Status
        # ────────────────────────────────────────────────────
        self._log_cleanup_status()

        # Cleanup Jobs (MAINTENANCE category) - nur wenn aktiviert
        if self._maintenance_settings.sensor_data_retention_enabled:
            self._scheduler.add_cron_job(
                job_id="cleanup_sensor_data",
                func=self._cleanup_sensor_data,
                cron_expression={"hour": 3, "minute": 0},  # Daily at 03:00
                category=JobCategory.MAINTENANCE,
            )
            dry_run = " (DRY-RUN)" if self._maintenance_settings.sensor_data_cleanup_dry_run else ""
            logger.info(
                f"Registered cleanup_sensor_data job (daily 03:00){dry_run} "
                f"(retain {self._maintenance_settings.sensor_data_retention_days} days)"
            )
        else:
            logger.info("Skipped cleanup_sensor_data job (DISABLED - unlimited retention)")

        if self._maintenance_settings.command_history_retention_enabled:
            self._scheduler.add_cron_job(
                job_id="cleanup_command_history",
                func=self._cleanup_command_history,
                cron_expression={"hour": 3, "minute": 30},  # Daily at 03:30
                category=JobCategory.MAINTENANCE,
            )
            dry_run = (
                " (DRY-RUN)" if self._maintenance_settings.command_history_cleanup_dry_run else ""
            )
            logger.info(
                f"Registered cleanup_command_history job (daily 03:30){dry_run} "
                f"(retain {self._maintenance_settings.command_history_retention_days} days)"
            )
        else:
            logger.info("Skipped cleanup_command_history job (DISABLED - unlimited retention)")

        if self._maintenance_settings.orphaned_mock_cleanup_enabled:
            self._scheduler.add_interval_job(
                job_id="cleanup_orphaned_mocks",
                func=self._cleanup_orphaned_mocks,
                seconds=3600,  # Hourly
                category=JobCategory.MAINTENANCE,
            )
            mode = (
                "AUTO-DELETE"
                if self._maintenance_settings.orphaned_mock_auto_delete
                else "WARN ONLY"
            )
            logger.info(f"Registered cleanup_orphaned_mocks job (hourly, {mode})")
        else:
            logger.info("Skipped cleanup_orphaned_mocks job (DISABLED)")

        if self._maintenance_settings.heartbeat_log_retention_enabled:
            self._scheduler.add_cron_job(
                job_id="cleanup_heartbeat_logs",
                func=self._cleanup_heartbeat_logs,
                cron_expression={"hour": 3, "minute": 15},  # Daily at 03:15
                category=JobCategory.MAINTENANCE,
            )
            dry_run = (
                " (DRY-RUN)" if self._maintenance_settings.heartbeat_log_cleanup_dry_run else ""
            )
            logger.info(
                f"Registered cleanup_heartbeat_logs job (daily 03:15){dry_run} "
                f"(retain {self._maintenance_settings.heartbeat_log_retention_days} days)"
            )
        else:
            logger.info("Skipped cleanup_heartbeat_logs job (DISABLED)")

        # Health Check Jobs (MONITOR category) - immer aktiv
        self._scheduler.add_interval_job(
            job_id="health_check_esps",
            func=self._health_check_esps,
            seconds=self._maintenance_settings.esp_health_check_interval_seconds,
            category=JobCategory.MONITOR,
        )
        logger.info(
            f"Registered health_check_esps job (every {self._maintenance_settings.esp_health_check_interval_seconds}s)"
        )

        self._scheduler.add_interval_job(
            job_id="health_check_mqtt",
            func=self._health_check_mqtt,
            seconds=self._maintenance_settings.mqtt_health_check_interval_seconds,
            category=JobCategory.MONITOR,
        )
        logger.info(
            f"Registered health_check_mqtt job (every {self._maintenance_settings.mqtt_health_check_interval_seconds}s)"
        )

        # Sensor Health Check (Phase 2E) - checks continuous sensors for timeout
        self._scheduler.add_interval_job(
            job_id="health_check_sensors",
            func=self._check_sensor_health,
            seconds=self._maintenance_settings.sensor_health_check_interval_seconds,
            category=JobCategory.MONITOR,
        )
        logger.info(
            f"Registered health_check_sensors job (every {self._maintenance_settings.sensor_health_check_interval_seconds}s)"
        )

        # Stats Aggregation (MAINTENANCE category) - nur wenn aktiviert
        if self._maintenance_settings.stats_aggregation_enabled:
            self._scheduler.add_interval_job(
                job_id="aggregate_stats",
                func=self._aggregate_stats,
                seconds=self._maintenance_settings.stats_aggregation_interval_minutes * 60,
                category=JobCategory.MAINTENANCE,
            )
            logger.info(
                f"Registered aggregate_stats job (every {self._maintenance_settings.stats_aggregation_interval_minutes} minutes)"
            )
        else:
            logger.info("Skipped aggregate_stats job (DISABLED)")

        logger.info("MaintenanceService started - all jobs registered")

    def _log_cleanup_status(self) -> None:
        """Loggt Cleanup-Status beim Startup"""
        cleanup_status = []

        if self._maintenance_settings.sensor_data_retention_enabled:
            dry_run = " (DRY-RUN)" if self._maintenance_settings.sensor_data_cleanup_dry_run else ""
            cleanup_status.append(
                f"  - Sensor Data Cleanup: ENABLED{dry_run} "
                f"(retain {self._maintenance_settings.sensor_data_retention_days} days)"
            )
        else:
            cleanup_status.append("  - Sensor Data Cleanup: DISABLED (unlimited retention)")

        if self._maintenance_settings.command_history_retention_enabled:
            dry_run = (
                " (DRY-RUN)" if self._maintenance_settings.command_history_cleanup_dry_run else ""
            )
            cleanup_status.append(
                f"  - Command History Cleanup: ENABLED{dry_run} "
                f"(retain {self._maintenance_settings.command_history_retention_days} days)"
            )
        else:
            cleanup_status.append("  - Command History Cleanup: DISABLED (unlimited retention)")

        if self._maintenance_settings.orphaned_mock_auto_delete:
            cleanup_status.append("  - Orphaned Mocks Cleanup: AUTO-DELETE ENABLED")
        else:
            cleanup_status.append("  - Orphaned Mocks Cleanup: WARN ONLY (no deletion)")

        if self._maintenance_settings.heartbeat_log_retention_enabled:
            dry_run = (
                " (DRY-RUN)" if self._maintenance_settings.heartbeat_log_cleanup_dry_run else ""
            )
            cleanup_status.append(
                f"  - Heartbeat Log Cleanup: ENABLED{dry_run} "
                f"(retain {self._maintenance_settings.heartbeat_log_retention_days} days)"
            )
        else:
            cleanup_status.append("  - Heartbeat Log Cleanup: DISABLED (unlimited retention)")

        logger.info("Maintenance Cleanup Status:\n" + "\n".join(cleanup_status))

    def stop(self) -> None:
        """Remove all maintenance jobs from the scheduler."""
        logger.info("Stopping MaintenanceService - removing jobs...")

        # Remove all maintenance and monitor jobs
        removed_maintenance = self._scheduler.remove_jobs_by_category(JobCategory.MAINTENANCE)
        removed_monitor = self._scheduler.remove_jobs_by_category(JobCategory.MONITOR)

        logger.info(
            f"MaintenanceService stopped - removed {removed_maintenance} maintenance jobs, "
            f"{removed_monitor} monitor jobs"
        )

    def get_status(self) -> Dict[str, Any]:
        """
        Get status of all maintenance jobs.

        Returns:
            Status dictionary with job information and stats cache
        """
        jobs = []
        for job in self._scheduler.get_all_jobs():
            job_id = job["id"]
            if job_id.startswith("maintenance_") or job_id.startswith("monitor_"):
                job_stats = self._scheduler.get_job_stats(job_id)
                job_info = {
                    "job_id": job_id,
                    "next_run": job.get("next_run"),
                    "last_run": job_stats.get("last_run") if job_stats else None,
                    "last_result": (
                        "success" if job_stats and job_stats.get("errors", 0) == 0 else "error"
                    ),
                }

                # Add job-specific results
                if job_id in self._job_results:
                    job_info.update(self._job_results[job_id])

                jobs.append(job_info)

        return {
            "service_running": True,
            "jobs": jobs,
            "stats_cache": self._stats_cache.copy(),
            "config": {
                "sensor_data_retention_enabled": self._maintenance_settings.sensor_data_retention_enabled,
                "command_history_retention_enabled": self._maintenance_settings.command_history_retention_enabled,
                "orphaned_mock_auto_delete": self._maintenance_settings.orphaned_mock_auto_delete,
                "heartbeat_log_retention_enabled": self._maintenance_settings.heartbeat_log_retention_enabled,
            },
        }

    def reconcile_after_restore(self) -> Dict[str, Any]:
        """
        Reconcile in-memory maintenance runtime state after DB restore.

        A destructive restore can invalidate cache assumptions, therefore we
        reset volatile state so subsequent cycles rebuild from DB truth.
        """
        self._stats_cache = {
            "last_updated": None,
            "total_esps": 0,
            "online_esps": 0,
            "offline_esps": 0,
            "total_sensors": 0,
            "total_actuators": 0,
        }
        self._job_results.clear()
        logger.info("MaintenanceService runtime cache reconciled after database restore")
        return {"reconciled": True, "cleared_job_results": True, "stats_cache_reset": True}

    # ================================================================
    # CLEANUP JOBS
    # ================================================================

    async def _cleanup_sensor_data(self) -> None:
        """Cleanup old sensor data (runs daily at 03:00)."""
        job_id = "maintenance_cleanup_sensor_data"

        try:
            async for session in self._session_factory():
                from .jobs.cleanup import SensorDataCleanup

                cleanup = SensorDataCleanup(session, self._maintenance_settings)
                result = await cleanup.execute()
                self._job_results[job_id] = result
                break  # Exit after first session

        except Exception as e:
            logger.error(f"[maintenance] ERROR cleanup_sensor_data: {e}", exc_info=True)
            self._job_results[job_id] = {"error": str(e), "status": "error"}

    async def _cleanup_command_history(self) -> None:
        """Cleanup old actuator command history (runs daily at 03:30)."""
        job_id = "maintenance_cleanup_command_history"

        try:
            async for session in self._session_factory():
                from .jobs.cleanup import CommandHistoryCleanup

                cleanup = CommandHistoryCleanup(session, self._maintenance_settings)
                result = await cleanup.execute()
                self._job_results[job_id] = result
                break  # Exit after first session

        except Exception as e:
            logger.error(f"[maintenance] ERROR cleanup_command_history: {e}", exc_info=True)
            self._job_results[job_id] = {"error": str(e), "status": "error"}

    async def _cleanup_orphaned_mocks(self) -> None:
        """Cleanup orphaned mock ESPs (runs hourly)."""
        job_id = "maintenance_cleanup_orphaned_mocks"

        try:
            async for session in self._session_factory():
                from .jobs.cleanup import OrphanedMocksCleanup

                cleanup = OrphanedMocksCleanup(session, self._scheduler, self._maintenance_settings)
                result = await cleanup.execute()
                self._job_results[job_id] = result
                break  # Exit after first session

        except Exception as e:
            logger.error(f"[maintenance] ERROR cleanup_orphaned_mocks: {e}", exc_info=True)
            self._job_results[job_id] = {"error": str(e), "status": "error"}

    async def _cleanup_heartbeat_logs(self) -> None:
        """Cleanup old heartbeat logs (runs daily at 03:15)."""
        job_id = "maintenance_cleanup_heartbeat_logs"

        try:
            async for session in self._session_factory():
                from .jobs.cleanup import HeartbeatLogCleanup

                cleanup = HeartbeatLogCleanup(session, self._maintenance_settings)
                result = await cleanup.execute()
                self._job_results[job_id] = result
                break  # Exit after first session

        except Exception as e:
            logger.error(f"[maintenance] ERROR cleanup_heartbeat_logs: {e}", exc_info=True)
            self._job_results[job_id] = {"error": str(e), "status": "error"}

    # ================================================================
    # HEALTH CHECK JOBS
    # ================================================================

    async def _health_check_esps(self) -> None:
        """Check ESP health and detect timeouts (runs every 60s)."""
        job_id = "monitor_health_check_esps"

        try:
            from ...mqtt.handlers.heartbeat_handler import get_heartbeat_handler

            heartbeat_handler = get_heartbeat_handler()
            result = await heartbeat_handler.check_device_timeouts()

            checked = result.get("checked", 0)
            timed_out = result.get("timed_out", 0)
            offline_devices = result.get("offline_devices", [])

            logger.info(
                f"[monitor] health_check_esps: {checked} checked, "
                f"{result.get('checked', 0) - timed_out} online, "
                f"{timed_out} timed out"
            )

            if timed_out > 0:
                logger.warning(
                    f"[monitor] health_check_esps: {timed_out} ESP(s) timed out: {offline_devices}"
                )

            self._job_results[job_id] = {
                "esps_checked": checked,
                "timeouts_detected": timed_out,
                "offline_devices": offline_devices,
            }

        except Exception as e:
            logger.error(f"[monitor] ERROR health_check_esps: {e}", exc_info=True)
            self._job_results[job_id] = {"error": str(e)}

    async def _health_check_mqtt(self) -> None:
        """Check MQTT broker health (runs every 30s)."""
        job_id = "monitor_health_check_mqtt"

        try:
            is_connected = self._mqtt_client.is_connected()

            if not is_connected:
                logger.warning("[monitor] health_check_mqtt: MQTT broker disconnected")
                # Reconnect is handled by MQTTClient auto-reconnect

                # Optional: Broadcast WebSocket event
                try:
                    from ...websocket.manager import WebSocketManager

                    ws_manager = await WebSocketManager.get_instance()
                    await ws_manager.broadcast(
                        "system_event",
                        {
                            "event": "mqtt_disconnected",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                    )
                except Exception as e:
                    logger.debug(f"Failed to broadcast MQTT disconnect event: {e}")

            else:
                logger.debug("[monitor] health_check_mqtt: Connected")

            self._job_results[job_id] = {
                "connected": is_connected,
                "last_check": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            logger.error(f"[monitor] ERROR health_check_mqtt: {e}", exc_info=True)
            self._job_results[job_id] = {"error": str(e)}

    async def _check_sensor_health(self) -> None:
        """
        Check sensor health for timeout violations (Phase 2E).

        Checks all continuous-mode sensors for timeout violations
        and broadcasts WebSocket events for stale sensors.

        Runs every sensor_health_check_interval_seconds (default: 60s).
        """
        job_id = "monitor_health_check_sensors"

        try:
            from .jobs.sensor_health import check_sensor_timeouts
            from ...websocket.manager import WebSocketManager

            # Get WebSocket manager for broadcasting
            ws_manager = await WebSocketManager.get_instance()

            async for session in self._session_factory():
                result = await check_sensor_timeouts(
                    session=session,
                    settings=self._maintenance_settings,
                    ws_manager=ws_manager,
                )

                checked = result.get("sensors_checked", 0)
                stale = result.get("sensors_stale", 0)
                healthy = result.get("sensors_healthy", 0)
                skipped = result.get("sensors_skipped", 0)

                if stale > 0:
                    logger.warning(
                        f"[monitor] health_check_sensors: {stale} sensor(s) stale "
                        f"(checked: {checked}, healthy: {healthy}, skipped: {skipped})"
                    )
                else:
                    logger.debug(
                        f"[monitor] health_check_sensors: All {healthy} sensors healthy "
                        f"(checked: {checked}, skipped: {skipped})"
                    )

                self._job_results[job_id] = {
                    "sensors_checked": checked,
                    "sensors_stale": stale,
                    "sensors_healthy": healthy,
                    "sensors_skipped": skipped,
                    "last_check": datetime.now(timezone.utc).isoformat(),
                }

                if result.get("errors"):
                    self._job_results[job_id]["errors"] = result["errors"]

                break  # Exit after first session

        except Exception as e:
            logger.error(f"[monitor] ERROR health_check_sensors: {e}", exc_info=True)
            self._job_results[job_id] = {
                "error": str(e),
                "last_check": datetime.now(timezone.utc).isoformat(),
            }

    # ================================================================
    # STATS AGGREGATION
    # ================================================================

    async def _aggregate_stats(self) -> None:
        """Aggregate statistics for dashboard (runs hourly)."""
        job_id = "maintenance_aggregate_stats"
        start_time = time.time()

        try:
            async for session in self._session_factory():
                from ...db.repositories import (
                    ESPRepository,
                    SensorRepository,
                    ActuatorRepository,
                )

                esp_repo = ESPRepository(session)
                sensor_repo = SensorRepository(session)
                actuator_repo = ActuatorRepository(session)

                # Get ESP counts
                total_esps = await esp_repo.count()
                online_esps = len(await esp_repo.get_by_status("online"))
                offline_esps = total_esps - online_esps

                # Get sensor/actuator counts
                total_sensors = await sensor_repo.count()
                total_actuators = await actuator_repo.count()

                # Count by type (query with limit to get all)
                from sqlalchemy import select, func
                from ...db.models.sensor import SensorConfig
                from ...db.models.actuator import ActuatorConfig

                # Sensors by type
                sensor_type_stmt = select(SensorConfig.sensor_type, func.count()).group_by(
                    SensorConfig.sensor_type
                )
                sensor_type_result = await session.execute(sensor_type_stmt)
                sensors_by_type = {row[0]: row[1] for row in sensor_type_result.fetchall()}

                # Actuators by type
                actuator_type_stmt = select(ActuatorConfig.actuator_type, func.count()).group_by(
                    ActuatorConfig.actuator_type
                )
                actuator_type_result = await session.execute(actuator_type_stmt)
                actuators_by_type = {row[0]: row[1] for row in actuator_type_result.fetchall()}

                # Update cache
                self._stats_cache = {
                    "last_updated": datetime.now(timezone.utc).isoformat(),
                    "total_esps": total_esps,
                    "online_esps": online_esps,
                    "offline_esps": offline_esps,
                    "total_sensors": total_sensors,
                    "total_actuators": total_actuators,
                    "sensors_by_type": sensors_by_type,
                    "actuators_by_type": actuators_by_type,
                }

                duration = time.time() - start_time
                logger.debug(
                    f"[maintenance] aggregate_stats: Updated stats cache "
                    f"({total_esps} ESPs, {total_sensors} sensors, {total_actuators} actuators) "
                    f"in {duration:.2f}s"
                )

                self._job_results[job_id] = {
                    "duration_seconds": duration,
                    "stats_updated": True,
                }

                break

        except Exception as e:
            logger.error(f"[maintenance] ERROR aggregate_stats: {e}", exc_info=True)
            self._job_results[job_id] = {"error": str(e)}


# ================================================================
# DEPENDENCY INJECTION
# ================================================================

_maintenance_service: Optional[MaintenanceService] = None


def get_maintenance_service() -> MaintenanceService:
    """
    Get MaintenanceService instance (Dependency Injection).

    Returns:
        MaintenanceService instance

    Raises:
        RuntimeError: If service not initialized
    """
    global _maintenance_service
    if _maintenance_service is None:
        raise RuntimeError(
            "MaintenanceService not initialized. Call init_maintenance_service() first."
        )
    return _maintenance_service


def init_maintenance_service(
    scheduler: CentralScheduler,
    session_factory: Callable,
    mqtt_client: MQTTClient,
    settings: Settings,
) -> MaintenanceService:
    """
    Initialize MaintenanceService.

    Must be called during startup in main.py.

    Args:
        scheduler: CentralScheduler instance
        session_factory: Async function that yields DB sessions
        mqtt_client: MQTTClient instance
        settings: Settings instance

    Returns:
        Initialized MaintenanceService instance
    """
    global _maintenance_service

    if _maintenance_service is not None:
        logger.warning("MaintenanceService already initialized")
        return _maintenance_service

    _maintenance_service = MaintenanceService(
        scheduler=scheduler,
        session_factory=session_factory,
        mqtt_client=mqtt_client,
        settings=settings,
    )

    return _maintenance_service
