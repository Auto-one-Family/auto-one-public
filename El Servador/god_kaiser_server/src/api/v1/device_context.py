"""
Device Context API Router

T13-R2: Multi-Zone Device Scope and Data Routing

Endpoints for managing active zone context on multi_zone and mobile devices.
"""

import uuid

from fastapi import APIRouter, HTTPException, Path

from ...core.logging_config import get_logger
from ...db.repositories import SensorRepository, ActuatorRepository
from ...schemas.device_context import (
    DeviceContextResponse,
    DeviceContextSet,
)
from ...services.device_scope_service import DeviceScopeService
from ..deps import DBSession, OperatorUser

logger = get_logger(__name__)

router = APIRouter(
    prefix="/v1/device-context",
    tags=["device-context"],
    responses={404: {"description": "Not found"}},
)


def _validate_config_type(config_type: str) -> str:
    """Validate config_type path parameter."""
    if config_type not in ("sensor", "actuator"):
        raise HTTPException(
            status_code=400,
            detail="config_type must be 'sensor' or 'actuator'",
        )
    return config_type


async def _get_config_and_validate_scope(db, config_type: str, config_id: uuid.UUID) -> tuple:
    """Load the sensor/actuator config and verify it's not zone_local."""
    if config_type == "sensor":
        repo = SensorRepository(db)
        config = await repo.get_by_id(config_id)
    else:
        repo = ActuatorRepository(db)
        config = await repo.get_by_id(config_id)

    if not config:
        raise HTTPException(
            status_code=404,
            detail=f"{config_type} config {config_id} not found",
        )

    if getattr(config, "device_scope", "zone_local") == "zone_local":
        raise HTTPException(
            status_code=400,
            detail=f"Device is zone_local — active context is not applicable. "
            f"Change device_scope to 'multi_zone' or 'mobile' first.",
        )

    return config


@router.put(
    "/{config_type}/{config_id}",
    response_model=DeviceContextResponse,
    summary="Set active zone context",
    description="Set or update the active zone context for a multi_zone or mobile device.",
)
async def set_device_context(
    config_type: str = Path(..., description="'sensor' or 'actuator'"),
    config_id: uuid.UUID = Path(..., description="Config UUID"),
    body: DeviceContextSet = ...,
    db: DBSession = ...,
    current_user: OperatorUser = ...,
) -> DeviceContextResponse:
    """Set active zone context for a multi_zone or mobile sensor/actuator."""
    _validate_config_type(config_type)
    config = await _get_config_and_validate_scope(db, config_type, config_id)

    # Validate active_zone_id is in assigned_zones (if assigned_zones is set)
    assigned_zones = getattr(config, "assigned_zones", None) or []
    if body.active_zone_id and assigned_zones:
        if body.active_zone_id not in assigned_zones:
            raise HTTPException(
                status_code=400,
                detail=f"Zone '{body.active_zone_id}' is not in assigned_zones {assigned_zones}",
            )

    service = DeviceScopeService(db)
    try:
        context = await service.set_active_context(
            config_type=config_type,
            config_id=config_id,
            active_zone_id=body.active_zone_id,
            active_subzone_id=body.active_subzone_id,
            context_source=body.context_source,
            changed_by=current_user.username,
        )
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # T13-R2: Broadcast context change via WebSocket
    try:
        from ...websocket.manager import WebSocketManager

        ws_manager = await WebSocketManager.get_instance()
        await ws_manager.broadcast(
            "device_context_changed",
            {
                "config_type": config_type,
                "config_id": str(config_id),
                "active_zone_id": context.active_zone_id,
                "active_subzone_id": context.active_subzone_id,
                "context_source": context.context_source,
                "changed_by": current_user.username,
            },
        )
    except Exception as e:
        logger.warning(f"Failed to broadcast device_context_changed: {e}")

    return DeviceContextResponse(
        success=True,
        config_type=config_type,
        config_id=config_id,
        active_zone_id=context.active_zone_id,
        active_subzone_id=context.active_subzone_id,
        context_source=context.context_source,
        context_since=context.context_since,
    )


@router.get(
    "/{config_type}/{config_id}",
    response_model=DeviceContextResponse,
    summary="Get active zone context",
    description="Get the current active zone context for a sensor or actuator.",
)
async def get_device_context(
    config_type: str = Path(..., description="'sensor' or 'actuator'"),
    config_id: uuid.UUID = Path(..., description="Config UUID"),
    db: DBSession = ...,
    current_user: OperatorUser = ...,
) -> DeviceContextResponse:
    """Get active zone context."""
    _validate_config_type(config_type)

    service = DeviceScopeService(db)
    context = await service.get_active_context(config_type, config_id)

    if not context:
        return DeviceContextResponse(
            success=True,
            message="No active context set",
            config_type=config_type,
            config_id=config_id,
            active_zone_id=None,
            active_subzone_id=None,
            context_source="none",
            context_since=None,
        )

    return DeviceContextResponse(
        success=True,
        config_type=config_type,
        config_id=config_id,
        active_zone_id=context.active_zone_id,
        active_subzone_id=context.active_subzone_id,
        context_source=context.context_source,
        context_since=context.context_since,
    )


@router.delete(
    "/{config_type}/{config_id}",
    response_model=DeviceContextResponse,
    summary="Clear active zone context",
    description="Clear the active zone context (return to default behavior).",
)
async def clear_device_context(
    config_type: str = Path(..., description="'sensor' or 'actuator'"),
    config_id: uuid.UUID = Path(..., description="Config UUID"),
    db: DBSession = ...,
    current_user: OperatorUser = ...,
) -> DeviceContextResponse:
    """Clear active zone context."""
    _validate_config_type(config_type)

    service = DeviceScopeService(db)
    deleted = await service.clear_active_context(
        config_type=config_type,
        config_id=config_id,
        changed_by=current_user.username,
    )
    await db.commit()

    # T13-R2: Broadcast context cleared via WebSocket
    if deleted:
        try:
            from ...websocket.manager import WebSocketManager

            ws_manager = await WebSocketManager.get_instance()
            await ws_manager.broadcast(
                "device_context_changed",
                {
                    "config_type": config_type,
                    "config_id": str(config_id),
                    "active_zone_id": None,
                    "active_subzone_id": None,
                    "context_source": "cleared",
                    "changed_by": current_user.username,
                },
            )
        except Exception as e:
            logger.warning(f"Failed to broadcast device_context_changed (clear): {e}")

    return DeviceContextResponse(
        success=True,
        message="Context cleared" if deleted else "No context was set",
        config_type=config_type,
        config_id=config_id,
        active_zone_id=None,
        active_subzone_id=None,
        context_source="none",
        context_since=None,
    )
