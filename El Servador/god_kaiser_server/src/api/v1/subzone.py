"""
Subzone Management REST API

Phase: 9 - Subzone Management
Status: IMPLEMENTED

Provides REST endpoints for subzone assignment, removal, queries,
and safe-mode control.

Endpoints:
- POST /devices/{esp_id}/subzones/assign - Assign GPIOs to subzone
- GET /devices/{esp_id}/subzones - List all subzones
- GET /devices/{esp_id}/subzones/{subzone_id} - Get specific subzone
- DELETE /devices/{esp_id}/subzones/{subzone_id} - Remove subzone
- POST /devices/{esp_id}/subzones/{subzone_id}/safe-mode - Enable safe-mode
- DELETE /devices/{esp_id}/subzones/{subzone_id}/safe-mode - Disable safe-mode

References:
- El Servador/god_kaiser_server/src/api/v1/zone.py (Pattern)
- El Frontend/Docs/System Flows/10-subzone-safemode-pin-assignment-flow-server-frontend.md
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel, Field as PydanticField
from sqlalchemy.exc import IntegrityError, ProgrammingError

from ...core.exceptions import (
    ESPNotFoundError,
    SubzoneNotFoundException,
    ValidationException,
)
from ...core.logging_config import get_logger
from ...db.repositories import ESPRepository
from ..deps import ActiveUser, DBSession, MQTTPublisher, OperatorUser
from ...schemas.common import ErrorResponse
from ...schemas.subzone import (
    SafeModeRequest,
    SafeModeResponse,
    SubzoneAssignRequest,
    SubzoneAssignResponse,
    SubzoneInfo,
    SubzoneListResponse,
    SubzoneRemoveResponse,
)
from ...services.subzone_service import SubzoneService

logger = get_logger(__name__)

# ESP ID path pattern: real devices (ESP_ + 6-8 hex) or mock (MOCK_* / ESP_MOCK_*)
# Consistent with logic_validation.py and zone/debug APIs.
ESP_ID_PATH_PATTERN = r"^(ESP_[A-F0-9]{6,8}|MOCK_[A-Z0-9]+|ESP_MOCK_[A-Z0-9]+)$"

# Router with prefix and tags
router = APIRouter(
    prefix="/v1/subzone",
    tags=["subzone"],
)


class SubzoneMetadataUpdate(BaseModel):
    """Partial update for subzone custom_data."""

    custom_data: dict = PydanticField(..., description="Subzone-specific metadata to merge")


# =============================================================================
# Subzone Assignment Endpoints
# =============================================================================


@router.post(
    "/devices/{esp_id}/subzones/assign",
    response_model=SubzoneAssignResponse,
    responses={
        200: {"description": "Subzone assignment sent to ESP"},
        400: {"description": "Validation error", "model": ErrorResponse},
        404: {"description": "ESP device not found", "model": ErrorResponse},
    },
    summary="Assign GPIOs to Subzone",
    description="""
    Assign GPIO pins to a subzone on an ESP device.

    **Requirements:**
    - ESP must be registered and provisioned
    - ESP must have a zone assigned (zone_id required)
    - parent_zone_id must match ESP's zone_id (if provided)

    **Flow:**
    1. Server validates request and ESP state
    2. Server sends MQTT message to ESP
    3. ESP validates GPIOs and creates subzone
    4. ESP sends ACK via subzone/ack topic
    5. Server updates DB and broadcasts WebSocket update

    **GPIO Validation:**
    - GPIO pins 0-39 are valid for ESP32
    - Duplicate GPIOs are automatically removed
    - ESP performs actual conflict detection

    **Finalität:** HTTP 2xx = DB + MQTT-Publish; **kein** synchrones Warten auf `subzone/ack`
    (kein `MQTTCommandBridge` wie bei Zone). `mqtt_sent` bezieht sich nur auf den Broker.
    Geräte-Finalität über MQTT `subzone/ack` und WebSocket `subzone_assignment`.
    Kurzüberblick: `docs/finalitaet-http-mqtt-ws.md`.
    """,
)
async def assign_subzone(
    esp_id: Annotated[
        str,
        Path(
            description="ESP device ID (real: ESP_XXXXXX, mock: MOCK_* or ESP_MOCK_*)",
            pattern=ESP_ID_PATH_PATTERN,
            examples=["ESP_AB12CD", "MOCK_95A49FCB", "ESP_MOCK_E92BAA"],
        ),
    ],
    request: SubzoneAssignRequest,
    session: DBSession,
    publisher: MQTTPublisher,
    user: OperatorUser,  # Requires operator permission
) -> SubzoneAssignResponse:
    """Assign GPIO pins to a subzone."""
    logger.info(f"Subzone assignment request for {esp_id} by {user.username}")

    esp_repo = ESPRepository(session)
    service = SubzoneService(esp_repo=esp_repo, session=session, publisher=publisher)

    try:
        response = await service.assign_subzone(
            device_id=esp_id,
            subzone_id=request.subzone_id,
            assigned_gpios=request.assigned_gpios,
            subzone_name=request.subzone_name,
            parent_zone_id=request.parent_zone_id,
            safe_mode_active=request.safe_mode_active,
        )

        # Commit transaction on success
        await session.commit()

        return response

    except IntegrityError as e:
        await session.rollback()
        logger.warning(f"Subzone assign DB constraint failed for {esp_id}: {e}")
        raise ValidationException(
            "subzone",
            "Subzone assignment failed (duplicate or constraint). Check subzone_id and ESP zone.",
        )

    except ProgrammingError as e:
        await session.rollback()
        msg = str(e).lower()
        if "custom_data" in msg or "does not exist" in msg or "column" in msg:
            logger.warning("Subzone assign failed (schema): %s", e)
            raise HTTPException(
                status_code=503,
                detail="Database schema outdated. Run: alembic upgrade head",
            ) from e
        logger.exception("Subzone assign failed (database)")
        raise HTTPException(status_code=500, detail="Database error") from e

    except ValueError as e:
        # ESP not found or no zone assigned
        error_msg = str(e)
        if "not found" in error_msg:
            raise ESPNotFoundError(esp_id)
        else:
            raise ValidationException("subzone", error_msg)


@router.delete(
    "/devices/{esp_id}/subzones/{subzone_id}",
    response_model=SubzoneRemoveResponse,
    responses={
        200: {"description": "Subzone removal sent to ESP"},
        404: {"description": "ESP device or subzone not found", "model": ErrorResponse},
    },
    summary="Remove Subzone",
    description="""
    Remove a subzone from an ESP device.

    This releases the GPIO pins and removes the subzone configuration.
    The ESP will set all subzone GPIOs to safe-mode (INPUT_PULLUP) before removal.
    """,
)
async def remove_subzone(
    esp_id: Annotated[
        str,
        Path(
            description="ESP device ID (real or mock)",
            pattern=ESP_ID_PATH_PATTERN,
        ),
    ],
    subzone_id: Annotated[
        str,
        Path(
            description="Subzone ID to remove",
            min_length=1,
            max_length=32,
        ),
    ],
    session: DBSession,
    publisher: MQTTPublisher,
    user: OperatorUser,
) -> SubzoneRemoveResponse:
    """Remove a subzone from ESP device."""
    logger.info(f"Subzone removal request for {esp_id}/{subzone_id} by {user.username}")

    esp_repo = ESPRepository(session)
    service = SubzoneService(esp_repo=esp_repo, session=session, publisher=publisher)

    try:
        result = await service.remove_subzone(
            device_id=esp_id,
            subzone_id=subzone_id,
        )
        await session.commit()
        return result
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg:
            raise SubzoneNotFoundException(subzone_id, esp_id)
        raise ValidationException("subzone", error_msg)


# =============================================================================
# Subzone Query Endpoints
# =============================================================================


@router.get(
    "/devices/{esp_id}/subzones",
    response_model=SubzoneListResponse,
    responses={
        200: {"description": "List of subzones"},
        404: {"description": "ESP device not found", "model": ErrorResponse},
    },
    summary="List ESP Subzones",
    description="""
    Get all subzones configured on an ESP device.

    Returns subzone configurations including:
    - Subzone ID and name
    - Parent zone ID
    - Assigned GPIO pins
    - Safe-mode status
    - Sensor and actuator counts
    """,
)
async def get_subzones(
    esp_id: Annotated[
        str,
        Path(
            description="ESP device ID (real or mock)",
            pattern=ESP_ID_PATH_PATTERN,
        ),
    ],
    session: DBSession,
    user: ActiveUser,
) -> SubzoneListResponse:
    """Get all subzones for an ESP device."""
    esp_repo = ESPRepository(session)
    service = SubzoneService(esp_repo=esp_repo, session=session)

    try:
        return await service.get_esp_subzones(device_id=esp_id)
    except ValueError:
        raise ESPNotFoundError(esp_id)
    except ProgrammingError as e:
        msg = str(e).lower()
        if "custom_data" in msg or "does not exist" in msg or "column" in msg:
            logger.warning("Subzone list failed (schema): %s", e)
            raise HTTPException(
                status_code=503,
                detail="Database schema outdated. Run: alembic upgrade head",
            ) from e
        logger.exception("Subzone list failed (database)")
        raise HTTPException(status_code=500, detail="Database error") from e
    except Exception as e:
        logger.exception("GET /subzone/devices/%s/subzones failed: %s", esp_id, e)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get(
    "/devices/{esp_id}/subzones/{subzone_id}",
    response_model=SubzoneInfo,
    responses={
        200: {"description": "Subzone details"},
        404: {"description": "Subzone not found", "model": ErrorResponse},
    },
    summary="Get Subzone Details",
    description="Get detailed information about a specific subzone.",
)
async def get_subzone(
    esp_id: Annotated[
        str,
        Path(
            description="ESP device ID (real or mock)",
            pattern=ESP_ID_PATH_PATTERN,
        ),
    ],
    subzone_id: Annotated[
        str,
        Path(
            description="Subzone ID",
            min_length=1,
            max_length=32,
        ),
    ],
    session: DBSession,
    user: ActiveUser,
) -> SubzoneInfo:
    """Get specific subzone details."""
    esp_repo = ESPRepository(session)
    service = SubzoneService(esp_repo=esp_repo, session=session)

    subzone = await service.get_subzone(device_id=esp_id, subzone_id=subzone_id)

    if not subzone:
        raise SubzoneNotFoundException(subzone_id, esp_id)

    return subzone


# =============================================================================
# Subzone Metadata Endpoints
# =============================================================================


@router.patch(
    "/devices/{esp_id}/subzones/{subzone_id}/metadata",
    response_model=SubzoneInfo,
    responses={
        200: {"description": "Subzone metadata updated"},
        404: {"description": "Subzone not found", "model": ErrorResponse},
    },
    summary="Update Subzone Metadata",
    description="Update subzone-specific metadata (plant info, material, notes).",
)
async def update_subzone_metadata(
    esp_id: Annotated[
        str,
        Path(description="ESP device ID (real or mock)", pattern=ESP_ID_PATH_PATTERN),
    ],
    subzone_id: Annotated[
        str,
        Path(description="Subzone ID", min_length=1, max_length=32),
    ],
    body: SubzoneMetadataUpdate,
    session: DBSession,
    user: OperatorUser,
) -> SubzoneInfo:
    """Update subzone custom_data metadata."""
    from ...db.repositories.subzone_repo import SubzoneRepository

    logger.info(f"Subzone metadata update for {esp_id}/{subzone_id} by {user.username}")

    repo = SubzoneRepository(session)
    subzone = await repo.get_by_esp_and_subzone(esp_id, subzone_id)
    if not subzone:
        raise SubzoneNotFoundException(subzone_id, esp_id)

    existing = subzone.custom_data or {}
    existing.update(body.custom_data)
    subzone.custom_data = existing

    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(subzone, "custom_data")

    await session.commit()
    await session.refresh(subzone)

    return SubzoneInfo(
        subzone_id=subzone.subzone_id,
        subzone_name=subzone.subzone_name,
        parent_zone_id=subzone.parent_zone_id,
        assigned_gpios=subzone.assigned_gpios or [],
        safe_mode_active=subzone.safe_mode_active,
        sensor_count=subzone.sensor_count,
        actuator_count=subzone.actuator_count,
        custom_data=subzone.custom_data or {},
        created_at=subzone.created_at.isoformat() if subzone.created_at else None,
    )


# =============================================================================
# Safe-Mode Control Endpoints
# =============================================================================


@router.post(
    "/devices/{esp_id}/subzones/{subzone_id}/safe-mode",
    response_model=SafeModeResponse,
    responses={
        200: {"description": "Safe-mode enable command sent"},
        404: {"description": "ESP device not found", "model": ErrorResponse},
    },
    summary="Enable Subzone Safe-Mode",
    description="""
    Enable safe-mode for a specific subzone.

    **What happens:**
    - All GPIO pins in the subzone are set to INPUT_PULLUP
    - All actuators in the subzone are stopped
    - Sensor readings continue but actuator commands are blocked

    **Use cases:**
    - Emergency stop for specific subzone
    - Maintenance mode
    - Manual intervention required
    """,
)
async def enable_safe_mode(
    esp_id: Annotated[
        str,
        Path(
            description="ESP device ID (real or mock)",
            pattern=ESP_ID_PATH_PATTERN,
        ),
    ],
    subzone_id: Annotated[
        str,
        Path(
            description="Subzone ID",
            min_length=1,
            max_length=32,
        ),
    ],
    request: SafeModeRequest,
    session: DBSession,
    publisher: MQTTPublisher,
    user: OperatorUser,
) -> SafeModeResponse:
    """Enable safe-mode for subzone."""
    logger.info(
        f"Safe-mode ENABLE request for {esp_id}/{subzone_id} "
        f"by {user.username}, reason: {request.reason}"
    )

    esp_repo = ESPRepository(session)
    service = SubzoneService(esp_repo=esp_repo, session=session, publisher=publisher)

    try:
        result = await service.enable_safe_mode(
            device_id=esp_id,
            subzone_id=subzone_id,
            reason=request.reason,
        )
        await session.commit()
        return result
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg:
            raise SubzoneNotFoundException(subzone_id, esp_id)
        raise ValidationException("safe_mode", error_msg)


@router.delete(
    "/devices/{esp_id}/subzones/{subzone_id}/safe-mode",
    response_model=SafeModeResponse,
    responses={
        200: {"description": "Safe-mode disable command sent"},
        404: {"description": "ESP device not found", "model": ErrorResponse},
    },
    summary="Disable Subzone Safe-Mode",
    description="""
    Disable safe-mode for a specific subzone.

    **⚠️ WARNING:** This allows actuators to be controlled.
    Ensure the subzone is safe before disabling safe-mode.

    **What happens:**
    - GPIO pins are restored to their configured modes
    - Actuator commands are re-enabled
    - Normal operation resumes

    **Requirements:**
    - Operator permission required
    - Valid reason should be provided
    """,
)
async def disable_safe_mode(
    esp_id: Annotated[
        str,
        Path(
            description="ESP device ID (real or mock)",
            pattern=ESP_ID_PATH_PATTERN,
        ),
    ],
    subzone_id: Annotated[
        str,
        Path(
            description="Subzone ID",
            min_length=1,
            max_length=32,
        ),
    ],
    session: DBSession,
    publisher: MQTTPublisher,
    user: OperatorUser,
    request: SafeModeRequest = SafeModeRequest(reason="manual"),
) -> SafeModeResponse:
    """Disable safe-mode for subzone."""
    logger.warning(
        f"Safe-mode DISABLE request for {esp_id}/{subzone_id} "
        f"by {user.username}, reason: {request.reason}"
    )

    esp_repo = ESPRepository(session)
    service = SubzoneService(esp_repo=esp_repo, session=session, publisher=publisher)

    try:
        result = await service.disable_safe_mode(
            device_id=esp_id,
            subzone_id=subzone_id,
            reason=request.reason,
        )
        await session.commit()
        return result
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg:
            raise SubzoneNotFoundException(subzone_id, esp_id)
        raise ValidationException("safe_mode", error_msg)
