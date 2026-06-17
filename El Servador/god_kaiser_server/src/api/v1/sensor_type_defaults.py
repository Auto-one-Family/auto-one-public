"""
API endpoints for Sensor Type Defaults management.

Provides CRUD operations for configuring default operating modes per sensor type.

Phase: 2A - Sensor Operating Modes
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logging_config import get_logger
from ...db.repositories.sensor_type_defaults_repo import SensorTypeDefaultsRepository
from ...sensors.sensor_type_registry import normalize_sensor_type
from ...db.session import get_session
from ...schemas.sensor_type_defaults import (
    EffectiveConfigResponse,
    SensorTypeDefaultsCreate,
    SensorTypeDefaultsListResponse,
    SensorTypeDefaultsResponse,
    SensorTypeDefaultsUpdate,
)
from ..deps import ActiveUser, OperatorUser

logger = get_logger(__name__)

router = APIRouter(
    prefix="/v1/sensors/type-defaults",
    tags=["Sensor Type Defaults"],
)


# =============================================================================
# Database Session Dependency
# =============================================================================


async def get_db():
    """Get database session."""
    async for session in get_session():
        yield session


# =============================================================================
# LIST / GET ALL
# =============================================================================


@router.get(
    "",
    response_model=SensorTypeDefaultsListResponse,
    summary="Get all sensor type defaults",
    description="Returns default operating mode configuration for all sensor types.",
)
async def get_all_defaults(
    session: AsyncSession = Depends(get_db),
    current_user: ActiveUser = None,
) -> SensorTypeDefaultsListResponse:
    """Get all sensor type default configurations."""
    repo = SensorTypeDefaultsRepository(session)
    defaults = await repo.get_all()

    return SensorTypeDefaultsListResponse(
        success=True,
        items=[SensorTypeDefaultsResponse.model_validate(d) for d in defaults],
        total=len(defaults),
    )


# =============================================================================
# GET BY SENSOR TYPE
# =============================================================================


@router.get(
    "/{sensor_type}",
    response_model=SensorTypeDefaultsResponse,
    summary="Get defaults for sensor type",
    description="Returns default configuration for a specific sensor type.",
    responses={
        200: {"description": "Defaults found"},
        404: {"description": "No defaults for this sensor type"},
    },
)
async def get_defaults_by_type(
    sensor_type: str,
    session: AsyncSession = Depends(get_db),
    current_user: ActiveUser = None,
) -> SensorTypeDefaultsResponse:
    """Get defaults for a specific sensor type."""
    sensor_type = normalize_sensor_type(sensor_type)
    repo = SensorTypeDefaultsRepository(session)
    defaults = await repo.get_by_sensor_type(sensor_type)

    if not defaults:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No defaults configured for sensor type: {sensor_type}",
        )

    return SensorTypeDefaultsResponse.model_validate(defaults)


# =============================================================================
# CREATE
# =============================================================================


@router.post(
    "",
    response_model=SensorTypeDefaultsResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create sensor type defaults",
    description="Create default operating mode configuration for a new sensor type.",
    responses={
        201: {"description": "Defaults created"},
        409: {"description": "Defaults already exist for this sensor type"},
    },
)
async def create_defaults(
    data: SensorTypeDefaultsCreate,
    session: AsyncSession = Depends(get_db),
    current_user: OperatorUser = None,
) -> SensorTypeDefaultsResponse:
    """Create defaults for a new sensor type."""
    repo = SensorTypeDefaultsRepository(session)

    # Check if already exists
    existing = await repo.get_by_sensor_type(data.sensor_type)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Defaults already exist for sensor type: {data.sensor_type}",
        )

    defaults = await repo.create(
        sensor_type=data.sensor_type,
        operating_mode=data.operating_mode,
        measurement_interval_seconds=data.measurement_interval_seconds,
        timeout_seconds=data.timeout_seconds,
        timeout_warning_enabled=data.timeout_warning_enabled,
        supports_on_demand=data.supports_on_demand,
        description=data.description,
        schedule_config=data.schedule_config,
        measurement_freshness_hours=data.measurement_freshness_hours,
        calibration_interval_days=data.calibration_interval_days,
    )

    await session.commit()

    logger.info(
        f"Created sensor type defaults: {data.sensor_type} "
        f"(mode={data.operating_mode}) by {current_user.username if current_user else 'system'}"
    )
    return SensorTypeDefaultsResponse.model_validate(defaults)


# =============================================================================
# UPDATE
# =============================================================================


@router.patch(
    "/{sensor_type}",
    response_model=SensorTypeDefaultsResponse,
    summary="Update sensor type defaults",
    description="Update default configuration for a sensor type.",
    responses={
        200: {"description": "Defaults updated"},
        404: {"description": "No defaults for this sensor type"},
    },
)
async def update_defaults(
    sensor_type: str,
    data: SensorTypeDefaultsUpdate,
    session: AsyncSession = Depends(get_db),
    current_user: OperatorUser = None,
) -> SensorTypeDefaultsResponse:
    """Update defaults for a sensor type."""
    sensor_type = normalize_sensor_type(sensor_type)
    repo = SensorTypeDefaultsRepository(session)

    defaults = await repo.update(
        sensor_type=sensor_type,
        operating_mode=data.operating_mode,
        measurement_interval_seconds=data.measurement_interval_seconds,
        timeout_seconds=data.timeout_seconds,
        timeout_warning_enabled=data.timeout_warning_enabled,
        supports_on_demand=data.supports_on_demand,
        description=data.description,
        schedule_config=data.schedule_config,
        measurement_freshness_hours=data.measurement_freshness_hours,
        calibration_interval_days=data.calibration_interval_days,
    )

    if not defaults:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No defaults found for sensor type: {sensor_type}",
        )

    await session.commit()

    logger.info(
        f"Updated sensor type defaults: {sensor_type} "
        f"by {current_user.username if current_user else 'system'}"
    )
    return SensorTypeDefaultsResponse.model_validate(defaults)


# =============================================================================
# DELETE
# =============================================================================


@router.delete(
    "/{sensor_type}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete sensor type defaults",
    description="Delete default configuration for a sensor type.",
    responses={
        204: {"description": "Defaults deleted"},
        404: {"description": "No defaults for this sensor type"},
    },
)
async def delete_defaults(
    sensor_type: str,
    session: AsyncSession = Depends(get_db),
    current_user: OperatorUser = None,
) -> None:
    """Delete defaults for a sensor type."""
    sensor_type = normalize_sensor_type(sensor_type)
    repo = SensorTypeDefaultsRepository(session)

    deleted = await repo.delete(sensor_type)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No defaults found for sensor type: {sensor_type}",
        )

    await session.commit()

    logger.info(
        f"Deleted sensor type defaults: {sensor_type} "
        f"by {current_user.username if current_user else 'system'}"
    )


# =============================================================================
# EFFECTIVE CONFIG
# =============================================================================


@router.get(
    "/{sensor_type}/effective",
    response_model=EffectiveConfigResponse,
    summary="Get effective configuration",
    description="Get effective configuration with fallback chain applied.",
)
async def get_effective_config(
    sensor_type: str,
    session: AsyncSession = Depends(get_db),
    current_user: ActiveUser = None,
) -> EffectiveConfigResponse:
    """Get effective configuration for a sensor type."""
    sensor_type = normalize_sensor_type(sensor_type)
    repo = SensorTypeDefaultsRepository(session)

    effective = await repo.get_effective_config(sensor_type)

    return EffectiveConfigResponse(
        sensor_type=sensor_type,
        operating_mode=effective["operating_mode"],
        measurement_interval_seconds=effective["measurement_interval_seconds"],
        timeout_seconds=effective["timeout_seconds"],
        timeout_warning_enabled=effective["timeout_warning_enabled"],
        supports_on_demand=effective["supports_on_demand"],
        source=effective["source"],
    )
