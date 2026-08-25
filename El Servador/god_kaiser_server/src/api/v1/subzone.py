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

from typing import Annotated, Optional

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
    ActuatorSubzoneAssignRequest,
    ActuatorSubzoneAssignmentInfo,
    ActuatorSubzoneAssignmentsResponse,
    SafeModeRequest,
    SafeModeResponse,
    SensorSubzoneAssignRequest,
    SensorSubzoneAssignmentInfo,
    SensorSubzoneAssignmentsResponse,
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
    """Partial update for subzone custom_data and optional position_label (AUT-1241)."""

    custom_data: dict = PydanticField(..., description="Subzone-specific metadata to merge")
    position_label: Optional[str] = PydanticField(
        None,
        max_length=128,
        description=(
            "Optional free-text spatial position. "
            "Omit to leave unchanged; empty string clears to null."
        ),
    )


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
    - ESP zone is optional (AUT-1156): if the ESP has no zone yet, the subzone
      is created as a DB-only pre-config (`mqtt_sent=False`) and appears
      zoneless until a zone is later assigned
    - parent_zone_id must match ESP's zone_id (if both are set)

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
            position_label=request.position_label,
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
    """Update subzone custom_data metadata and optional position_label."""
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

    # AUT-1241: only touch position_label when the client sent the field
    if "position_label" in body.model_fields_set:
        label = body.position_label
        subzone.position_label = label.strip() if label and label.strip() else None

    await session.commit()
    await session.refresh(subzone)

    return SubzoneInfo(
        subzone_id=subzone.subzone_id,
        subzone_name=subzone.subzone_name,
        position_label=subzone.position_label,
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


# =============================================================================
# Sensor-Subzone n:m Assignment Endpoints (AUT-1155)
# =============================================================================


@router.post(
    "/devices/{esp_id}/subzones/{subzone_id}/sensors",
    response_model=SensorSubzoneAssignmentInfo,
    responses={
        200: {"description": "Sensor assigned to subzone"},
        400: {"description": "Validation error or already assigned", "model": ErrorResponse},
        404: {"description": "Subzone or sensor config not found", "model": ErrorResponse},
    },
    summary="Assign Sensor to Subzone",
    description="""
    Explicitly assign a sensor config to a subzone via the server-side n:m
    junction table (`sensor_subzone_assignments`).

    **Additive:** The existing `assigned_gpios` / `get_subzone_by_gpio()` path
    for ESP32 config-push remains unchanged.  This endpoint is the server-side
    logical assignment layer (AUT-1155 [B1]).

    **Idempotency:** A second POST with the same sensor+subzone pair returns 400
    (already assigned) rather than silently succeeding.
    """,
)
async def assign_sensor_to_subzone(
    esp_id: Annotated[
        str,
        Path(
            description="ESP device ID (real or mock)",
            pattern=ESP_ID_PATH_PATTERN,
        ),
    ],
    subzone_id: Annotated[
        str,
        Path(description="Subzone ID", min_length=1, max_length=32),
    ],
    request: SensorSubzoneAssignRequest,
    session: DBSession,
    user: OperatorUser,
) -> SensorSubzoneAssignmentInfo:
    """Assign a sensor config to a subzone (n:m, AUT-1155)."""
    logger.info(
        "Sensor-subzone assign: %s/%s <- sensor %s by %s",
        esp_id,
        subzone_id,
        request.sensor_config_id,
        user.username,
    )

    esp_repo = ESPRepository(session)
    service = SubzoneService(esp_repo=esp_repo, session=session)

    try:
        result = await service.assign_sensor_to_subzone(
            esp_id=esp_id,
            subzone_id=subzone_id,
            sensor_config_id=request.sensor_config_id,
            assigned_by=user.id,
        )
        await session.commit()
        return result
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            raise SubzoneNotFoundException(subzone_id, esp_id)
        raise ValidationException("sensor_subzone_assignment", error_msg)


@router.delete(
    "/devices/{esp_id}/subzones/{subzone_id}/sensors/{sensor_config_id}",
    response_model=SubzoneRemoveResponse,
    responses={
        200: {"description": "Sensor assignment removed"},
        404: {
            "description": "Assignment, subzone or sensor config not found",
            "model": ErrorResponse,
        },
    },
    summary="Remove Sensor from Subzone",
    description="""
    Remove a sensor config from a subzone in the n:m junction table.

    Returns 404 if the assignment does not exist.
    The sensor config itself is not deleted.
    """,
)
async def remove_sensor_from_subzone(
    esp_id: Annotated[
        str,
        Path(
            description="ESP device ID (real or mock)",
            pattern=ESP_ID_PATH_PATTERN,
        ),
    ],
    subzone_id: Annotated[
        str,
        Path(description="Subzone ID", min_length=1, max_length=32),
    ],
    sensor_config_id: Annotated[
        str,
        Path(description="UUID of the sensor_config to remove from this subzone"),
    ],
    session: DBSession,
    user: OperatorUser,
) -> SubzoneRemoveResponse:
    """Remove sensor→subzone assignment (n:m, AUT-1155)."""
    logger.info(
        "Sensor-subzone remove: %s/%s <- sensor %s by %s",
        esp_id,
        subzone_id,
        sensor_config_id,
        user.username,
    )

    esp_repo = ESPRepository(session)
    service = SubzoneService(esp_repo=esp_repo, session=session)

    try:
        deleted = await service.remove_sensor_from_subzone(
            esp_id=esp_id,
            subzone_id=subzone_id,
            sensor_config_id=sensor_config_id,
        )
        if not deleted:
            raise SubzoneNotFoundException(subzone_id, esp_id)
        await session.commit()
        return SubzoneRemoveResponse(
            success=True,
            message="Sensor assignment removed",
            device_id=esp_id,
            subzone_id=subzone_id,
            mqtt_topic="",
            mqtt_sent=False,
        )
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            raise SubzoneNotFoundException(subzone_id, esp_id)
        raise ValidationException("sensor_subzone_assignment", error_msg)


@router.get(
    "/devices/{esp_id}/subzones/{subzone_id}/sensors",
    response_model=SensorSubzoneAssignmentsResponse,
    responses={
        200: {"description": "List of sensor assignments for this subzone"},
        404: {"description": "Subzone not found", "model": ErrorResponse},
    },
    summary="List Sensor Assignments for Subzone",
    description="""
    Return all sensor configs explicitly assigned to a subzone via the n:m
    junction table (`sensor_subzone_assignments`).

    Note: This returns only assignments created through the n:m API
    (AUT-1155 [B1]).  Sensors whose GPIO is listed in `assigned_gpios` but
    which have no explicit n:m record are not included here.
    """,
)
async def get_subzone_sensor_assignments(
    esp_id: Annotated[
        str,
        Path(
            description="ESP device ID (real or mock)",
            pattern=ESP_ID_PATH_PATTERN,
        ),
    ],
    subzone_id: Annotated[
        str,
        Path(description="Subzone ID", min_length=1, max_length=32),
    ],
    session: DBSession,
    user: ActiveUser,
) -> SensorSubzoneAssignmentsResponse:
    """List sensor assignments for a subzone (n:m, AUT-1155)."""
    esp_repo = ESPRepository(session)
    service = SubzoneService(esp_repo=esp_repo, session=session)

    try:
        return await service.get_subzone_sensor_assignments(
            esp_id=esp_id,
            subzone_id=subzone_id,
        )
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            raise SubzoneNotFoundException(subzone_id, esp_id)
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Actuator-Subzone n:m Assignment Endpoints (Verortung)
# =============================================================================


@router.post(
    "/devices/{esp_id}/subzones/{subzone_id}/actuators",
    response_model=ActuatorSubzoneAssignmentInfo,
    responses={
        200: {"description": "Actuator assigned to subzone"},
        400: {"description": "Validation error or already assigned", "model": ErrorResponse},
        404: {"description": "Subzone or actuator config not found", "model": ErrorResponse},
    },
    summary="Assign Actuator to Subzone",
    description="""
    Explicitly assign an actuator config to a subzone via the server-side n:m
    junction table (`actuator_subzone_assignments`).

    **Verortung only:** The existing `assigned_gpios` / `get_subzone_by_gpio()`
    path for ESP32 config-push and Logic Engine control matching remains
    unchanged. `assigned_subzones` JSON stays dead (AUT-227).
    """,
)
async def assign_actuator_to_subzone(
    esp_id: Annotated[
        str,
        Path(
            description="ESP device ID (real or mock)",
            pattern=ESP_ID_PATH_PATTERN,
        ),
    ],
    subzone_id: Annotated[
        str,
        Path(description="Subzone ID", min_length=1, max_length=32),
    ],
    request: ActuatorSubzoneAssignRequest,
    session: DBSession,
    user: OperatorUser,
) -> ActuatorSubzoneAssignmentInfo:
    """Assign an actuator config to a subzone (n:m Verortung)."""
    logger.info(
        "Actuator-subzone assign: %s/%s <- actuator %s by %s",
        esp_id,
        subzone_id,
        request.actuator_config_id,
        user.username,
    )

    esp_repo = ESPRepository(session)
    service = SubzoneService(esp_repo=esp_repo, session=session)

    try:
        result = await service.assign_actuator_to_subzone(
            esp_id=esp_id,
            subzone_id=subzone_id,
            actuator_config_id=request.actuator_config_id,
            assigned_by=user.id,
        )
        await session.commit()
        return result
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            raise SubzoneNotFoundException(subzone_id, esp_id)
        raise ValidationException("actuator_subzone_assignment", error_msg)


@router.delete(
    "/devices/{esp_id}/subzones/{subzone_id}/actuators/{actuator_config_id}",
    response_model=SubzoneRemoveResponse,
    responses={
        200: {"description": "Actuator assignment removed"},
        404: {
            "description": "Assignment, subzone or actuator config not found",
            "model": ErrorResponse,
        },
    },
    summary="Remove Actuator from Subzone",
    description="""
    Remove an actuator config from a subzone in the n:m junction table.

    Returns 404 if the assignment does not exist.
    The actuator config itself is not deleted.
    """,
)
async def remove_actuator_from_subzone(
    esp_id: Annotated[
        str,
        Path(
            description="ESP device ID (real or mock)",
            pattern=ESP_ID_PATH_PATTERN,
        ),
    ],
    subzone_id: Annotated[
        str,
        Path(description="Subzone ID", min_length=1, max_length=32),
    ],
    actuator_config_id: Annotated[
        str,
        Path(description="UUID of the actuator_config to remove from this subzone"),
    ],
    session: DBSession,
    user: OperatorUser,
) -> SubzoneRemoveResponse:
    """Remove actuator→subzone assignment (n:m Verortung)."""
    logger.info(
        "Actuator-subzone remove: %s/%s <- actuator %s by %s",
        esp_id,
        subzone_id,
        actuator_config_id,
        user.username,
    )

    esp_repo = ESPRepository(session)
    service = SubzoneService(esp_repo=esp_repo, session=session)

    try:
        deleted = await service.remove_actuator_from_subzone(
            esp_id=esp_id,
            subzone_id=subzone_id,
            actuator_config_id=actuator_config_id,
        )
        if not deleted:
            raise SubzoneNotFoundException(subzone_id, esp_id)
        await session.commit()
        return SubzoneRemoveResponse(
            success=True,
            message="Actuator assignment removed",
            device_id=esp_id,
            subzone_id=subzone_id,
            mqtt_topic="",
            mqtt_sent=False,
        )
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            raise SubzoneNotFoundException(subzone_id, esp_id)
        raise ValidationException("actuator_subzone_assignment", error_msg)


@router.get(
    "/devices/{esp_id}/subzones/{subzone_id}/actuators",
    response_model=ActuatorSubzoneAssignmentsResponse,
    responses={
        200: {"description": "List of actuator assignments for this subzone"},
        404: {"description": "Subzone not found", "model": ErrorResponse},
    },
    summary="List Actuator Assignments for Subzone",
    description="""
    Return all actuator configs explicitly assigned to a subzone via the n:m
    junction table (`actuator_subzone_assignments`).

    Note: This returns only Verortung assignments. Actuators whose GPIO is
    listed in `assigned_gpios` but which have no explicit n:m record are not
    included here.
    """,
)
async def get_subzone_actuator_assignments(
    esp_id: Annotated[
        str,
        Path(
            description="ESP device ID (real or mock)",
            pattern=ESP_ID_PATH_PATTERN,
        ),
    ],
    subzone_id: Annotated[
        str,
        Path(description="Subzone ID", min_length=1, max_length=32),
    ],
    session: DBSession,
    user: ActiveUser,
) -> ActuatorSubzoneAssignmentsResponse:
    """List actuator assignments for a subzone (n:m Verortung)."""
    esp_repo = ESPRepository(session)
    service = SubzoneService(esp_repo=esp_repo, session=session)

    try:
        return await service.get_subzone_actuator_assignments(
            esp_id=esp_id,
            subzone_id=subzone_id,
        )
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            raise SubzoneNotFoundException(subzone_id, esp_id)
        raise HTTPException(status_code=500, detail=str(e))
