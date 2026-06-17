"""
Plugin Management REST API Endpoints

Phase 4C.1.6: REST-API for AutoOps Plugin-System.
Makes the existing plugin system visible and controllable via HTTP.

Endpoints:
- GET    /v1/plugins                  - List all plugins
- GET    /v1/plugins/{plugin_id}      - Plugin detail
- POST   /v1/plugins/{plugin_id}/execute  - Execute plugin
- PUT    /v1/plugins/{plugin_id}/config   - Update config
- GET    /v1/plugins/{plugin_id}/history  - Execution history
- POST   /v1/plugins/{plugin_id}/enable   - Enable plugin
- POST   /v1/plugins/{plugin_id}/disable  - Disable plugin
"""

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ...autoops.core.base_plugin import PluginContext
from ...autoops.core.plugin_registry import PluginRegistry
from ...core.logging_config import get_logger
from ...services.plugin_service import (
    PluginDisabledError,
    PluginNotFoundError,
    PluginService,
)
from ..deps import ActiveUser, AdminUser, DBSession, OperatorUser

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/plugins", tags=["plugins"])


# --- Request/Response Models ---


class ExecutePluginRequest(BaseModel):
    config_overrides: dict[str, Any] = {}


class UpdatePluginConfigRequest(BaseModel):
    config: dict[str, Any]


class UpdatePluginScheduleRequest(BaseModel):
    schedule: Optional[str] = None  # Cron expression or None to clear


# --- Dependency ---


def _get_plugin_service(db: DBSession) -> PluginService:
    """Build PluginService for request scope."""
    registry = PluginRegistry()
    return PluginService(db, registry)


# --- Endpoints ---


@router.get(
    "",
    summary="List all plugins",
    description="Get all registered plugins with status, config, and last execution.",
)
async def list_plugins(
    db: DBSession,
    user: ActiveUser,
):
    service = _get_plugin_service(db)
    return await service.get_all_plugins()


@router.get(
    "/{plugin_id}",
    summary="Plugin details",
    description="Get plugin details including config schema and recent executions.",
)
async def get_plugin(
    plugin_id: str,
    db: DBSession,
    user: ActiveUser,
):
    service = _get_plugin_service(db)
    try:
        return await service.get_plugin_detail(plugin_id)
    except PluginNotFoundError:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")


@router.post(
    "/{plugin_id}/execute",
    summary="Execute plugin",
    description="Execute a plugin manually. Returns the execution record.",
)
async def execute_plugin(
    plugin_id: str,
    db: DBSession,
    user: OperatorUser,  # TODO replace isViewer with capability check
    body: Optional[ExecutePluginRequest] = None,
):
    service = _get_plugin_service(db)
    context = PluginContext(
        user_id=user.id,
        trigger_source="manual",
        config_overrides=body.config_overrides if body else {},
    )
    try:
        execution = await service.execute_plugin(plugin_id, user.id, context)
        return {
            "id": str(execution.id),
            "plugin_id": execution.plugin_id,
            "status": execution.status,
            "started_at": execution.started_at.isoformat() if execution.started_at else None,
            "finished_at": execution.finished_at.isoformat() if execution.finished_at else None,
            "triggered_by": execution.triggered_by,
            "result": execution.result,
            "error_message": execution.error_message,
            "duration_seconds": execution.duration_seconds,
        }
    except PluginNotFoundError:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")
    except PluginDisabledError:
        raise HTTPException(status_code=409, detail=f"Plugin '{plugin_id}' is disabled")


@router.put(
    "/{plugin_id}/config",
    summary="Update plugin config",
    description="Update the runtime configuration of a plugin.",
)
async def update_plugin_config(
    plugin_id: str,
    body: UpdatePluginConfigRequest,
    db: DBSession,
    user: AdminUser,
):
    service = _get_plugin_service(db)
    try:
        config = await service.update_config(plugin_id, body.config)
        return {
            "plugin_id": config.plugin_id,
            "config": config.config,
            "updated_at": config.updated_at.isoformat() if config.updated_at else None,
        }
    except PluginNotFoundError:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")


@router.get(
    "/{plugin_id}/history",
    summary="Execution history",
    description="Get execution history for a plugin.",
)
async def get_plugin_history(
    plugin_id: str,
    db: DBSession,
    user: ActiveUser,
    limit: int = Query(50, ge=1, le=200),
):
    service = _get_plugin_service(db)
    executions = await service.get_execution_history(plugin_id, limit)
    return [
        {
            "id": str(e.id),
            "plugin_id": e.plugin_id,
            "started_at": e.started_at.isoformat() if e.started_at else None,
            "finished_at": e.finished_at.isoformat() if e.finished_at else None,
            "status": e.status,
            "triggered_by": e.triggered_by,
            "triggered_by_user": e.triggered_by_user,
            "result": e.result,
            "error_message": e.error_message,
            "duration_seconds": e.duration_seconds,
        }
        for e in executions
    ]


@router.post(
    "/{plugin_id}/enable",
    summary="Enable plugin",
    description="Enable a previously disabled plugin.",
)
async def enable_plugin(
    plugin_id: str,
    db: DBSession,
    user: AdminUser,
):
    service = _get_plugin_service(db)
    try:
        config = await service.toggle_plugin(plugin_id, enabled=True)
        return {"plugin_id": config.plugin_id, "is_enabled": config.is_enabled}
    except PluginNotFoundError:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")


@router.post(
    "/{plugin_id}/disable",
    summary="Disable plugin",
    description="Disable a plugin. Disabled plugins cannot be executed.",
)
async def disable_plugin(
    plugin_id: str,
    db: DBSession,
    user: AdminUser,
):
    service = _get_plugin_service(db)
    try:
        config = await service.toggle_plugin(plugin_id, enabled=False)
        return {"plugin_id": config.plugin_id, "is_enabled": config.is_enabled}
    except PluginNotFoundError:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")


@router.put(
    "/{plugin_id}/schedule",
    summary="Update plugin schedule",
    description="Set or clear a cron schedule for automatic plugin execution.",
)
async def update_plugin_schedule(
    plugin_id: str,
    body: UpdatePluginScheduleRequest,
    db: DBSession,
    user: AdminUser,
):
    service = _get_plugin_service(db)
    try:
        config = await service.update_schedule(plugin_id, body.schedule)
        return {
            "plugin_id": config.plugin_id,
            "schedule": config.schedule,
        }
    except PluginNotFoundError:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")
