"""
ESP Device Management API Endpoints

Phase: 5 (Week 9-10) - API Layer
Priority: 🔴 CRITICAL
Status: IMPLEMENTED

Provides:
- GET /devices - List all ESPs
- GET /devices/{esp_id} - ESP details
- POST /devices - Register new ESP
- PATCH /devices/{esp_id} - Update ESP
- DELETE /devices/{esp_id} - Delete ESP (for orphaned mocks/decommissioned HW)
- POST /devices/{esp_id}/restart - Restart command
- POST /devices/{esp_id}/reset - Factory reset
- GET /devices/{esp_id}/health - Health metrics
- GET /devices/{esp_id}/gpio-status - GPIO pin availability (Phase 2)
- POST /devices/{esp_id}/assign_kaiser - Assign to Kaiser
- GET /discovery - Network discovery results

Note: Config-Push to ESP32 happens AUTOMATICALLY via Sensor/Actuator CRUD APIs.
See api/v1/sensors.py and api/v1/actuators.py for details.

References:
- .claude/PI_SERVER_REFACTORING.md (Lines 125-133)
- El Trabajante/docs/Mqtt_Protocoll.md (System commands)
"""

from datetime import datetime, timezone
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, Query, status

from ...schemas.alert_config import DeviceAlertConfigUpdate

from ...core.logging_config import get_logger
from ...db.models.audit_log import AuditEventType, AuditSeverity
from ...db.repositories import ActuatorRepository, ESPRepository, SensorRepository
from ...db.repositories.subzone_repo import SubzoneRepository
from ...db.repositories.audit_log_repo import AuditLogRepository
from ...mqtt.publisher import Publisher
from ...schemas import (
    AssignKaiserRequest,
    AssignKaiserResponse,
    ESPApprovalRequest,
    ESPApprovalResponse,
    ESPCommandResponse,
    ESPDeviceCreate,
    ESPDeviceListResponse,
    ESPDeviceResponse,
    ESPDeviceUpdate,
    ESPDiscoveryResponse,
    ESPHealthResponse,
    ESPRejectionRequest,
    ESPResetRequest,
    ESPRestartRequest,
    DiscoveredESP,
    PendingDevicesListResponse,
    PendingESPDevice,
)
from ...schemas.esp import (
    ComponentHealthScoreResponse,
    GpioStatusResponse,
    GpioUsageItem,
    SubzoneSummary,
)
from ...services.gpio_validation_service import GpioValidationService, SYSTEM_RESERVED_PINS
from ...schemas.common import PaginationMeta
from ...core.exceptions import DuplicateESPError, ESPNotFoundError, ValidationException
from ..deps import ActiveUser, DBSession, OperatorUser, get_mqtt_publisher

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/esp", tags=["esp"])


# =============================================================================
# Helper Functions
# =============================================================================


def _extract_mock_fields(device) -> tuple[Optional[bool], Optional[int]]:
    """
    Extract Mock ESP specific fields from device_metadata.

    Returns:
        Tuple of (auto_heartbeat, heartbeat_interval_seconds)
        Both are None for non-Mock ESPs.
    """
    if device.hardware_type != "MOCK_ESP32":
        return None, None

    if not device.device_metadata:
        return None, None

    sim_config = device.device_metadata.get("simulation_config", {})
    auto_heartbeat = sim_config.get("auto_heartbeat")
    heartbeat_interval = sim_config.get("heartbeat_interval")

    # Convert to int if present (DB stores as float)
    heartbeat_interval_seconds = int(heartbeat_interval) if heartbeat_interval is not None else None

    return auto_heartbeat, heartbeat_interval_seconds


async def _enrich_zone_context(device, session, context_cache: dict) -> Optional[dict]:
    """Fetch zone context summary for a device, with caching per zone_id."""
    if not device.zone_id:
        return None
    # Check opt-out flag
    meta = device.device_metadata or {}
    if meta.get("inherit_zone_context") is False:
        return None
    if device.zone_id in context_cache:
        return context_cache[device.zone_id]
    from ...services.zone_context_service import ZoneContextService

    svc = ZoneContextService(session)
    summary = await svc.get_context_summary(device.zone_id)
    context_cache[device.zone_id] = summary
    return summary


async def _get_subzone_summaries(
    device_id: str, subzone_repo: SubzoneRepository
) -> list[SubzoneSummary]:
    """Fetch subzone summaries for a device.

    Args:
        device_id: ESP device_id string (e.g., ESP_472204)
        subzone_repo: SubzoneRepository instance

    Returns:
        List of SubzoneSummary for the device (empty if no subzones).
    """
    subzone_configs = await subzone_repo.get_by_esp(device_id)
    return [
        SubzoneSummary(
            subzone_id=sc.subzone_id,
            subzone_name=sc.subzone_name or sc.subzone_id,
            assigned_gpios=sc.assigned_gpios or [],
            sensor_count=sc.sensor_count or 0,
            actuator_count=sc.actuator_count or 0,
            is_active=sc.is_active if sc.is_active is not None else True,
        )
        for sc in subzone_configs
    ]


# =============================================================================
# List Devices
# =============================================================================


@router.get(
    "/devices",
    response_model=ESPDeviceListResponse,
    summary="List ESP devices",
    description="Get all registered ESP devices with optional filters.",
)
async def list_devices(
    db: DBSession,
    current_user: ActiveUser,
    zone_id: Annotated[Optional[str], Query(description="Filter by zone ID")] = None,
    status_filter: Annotated[
        Optional[str], Query(alias="status", description="Filter by status")
    ] = None,
    hardware_type: Annotated[Optional[str], Query(description="Filter by hardware type")] = None,
    include_deleted: Annotated[
        bool, Query(description="Include soft-deleted devices (admin/audit)")
    ] = False,
    runtime_only: Annotated[
        bool,
        Query(description="Runtime view only (default). Set false for historical/audit listings."),
    ] = True,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ESPDeviceListResponse:
    """
    List all ESP devices.

    Args:
        db: Database session
        current_user: Authenticated user
        zone_id: Optional zone filter
        status_filter: Optional status filter
        hardware_type: Optional hardware type filter
        include_deleted: Include soft-deleted devices (historical/audit view only)
        runtime_only: If true, enforce runtime-safe active device view
        page: Page number
        page_size: Items per page

    Returns:
        Paginated list of ESP devices
    """
    esp_repo = ESPRepository(db)
    sensor_repo = SensorRepository(db)
    actuator_repo = ActuatorRepository(db)
    subzone_repo = SubzoneRepository(db)

    # Runtime vs historical filter semantics:
    # - runtime_only=True: always active runtime view (deleted rows hidden)
    # - runtime_only=False: historical mode; include_deleted can opt in deleted rows
    effective_include_deleted = include_deleted and not runtime_only
    devices = await esp_repo.get_all(include_deleted=effective_include_deleted)

    # Optional in-memory filters to keep runtime/historical semantics consistent
    # across all query variants.
    if zone_id:
        devices = [d for d in devices if d.zone_id == zone_id]
    if status_filter:
        devices = [d for d in devices if d.status == status_filter]
    if hardware_type:
        devices = [d for d in devices if d.hardware_type == hardware_type]

    if runtime_only:
        devices = [d for d in devices if d.deleted_at is None and d.status != "deleted"]

    # Filter out pending_approval devices unless explicitly requested
    if status_filter != "pending_approval":
        devices = [d for d in devices if d.status != "pending_approval"]

    # Apply pagination
    total_items = len(devices)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paginated_devices = devices[start_idx:end_idx]

    # Build response with sensor/actuator counts + zone context + subzones
    device_responses = []
    zone_context_cache: dict = {}
    include_context = True

    for device in paginated_devices:
        sensor_count = await sensor_repo.count_by_esp(device.id)
        actuator_count = await actuator_repo.count_by_esp(device.id)

        # Extract Mock-specific fields
        auto_heartbeat, heartbeat_interval_seconds = _extract_mock_fields(device)

        # Zone context inheritance (Phase 4)
        zone_ctx = None
        if include_context:
            zone_ctx_data = await _enrich_zone_context(device, db, zone_context_cache)
            if zone_ctx_data:
                from ...schemas.esp import ZoneContextSummary

                zone_ctx = ZoneContextSummary(**zone_ctx_data)

        # Subzone summaries (T14-Fix-F)
        subzone_summaries = await _get_subzone_summaries(device.device_id, subzone_repo)

        device_responses.append(
            ESPDeviceResponse(
                id=device.id,
                device_id=device.device_id,
                name=device.name,
                zone_id=device.zone_id,
                zone_name=device.zone_name,
                is_zone_master=device.is_zone_master,
                ip_address=device.ip_address,
                mac_address=device.mac_address,
                firmware_version=device.firmware_version,
                hardware_type=device.hardware_type,
                capabilities=device.capabilities,
                status=device.status,
                last_seen=device.last_seen,
                metadata=device.device_metadata,
                sensor_count=sensor_count,
                actuator_count=actuator_count,
                auto_heartbeat=auto_heartbeat,
                heartbeat_interval_seconds=heartbeat_interval_seconds,
                created_at=device.created_at,
                updated_at=device.updated_at,
                zone_context=zone_ctx,
                subzones=subzone_summaries,
                deleted_at=device.deleted_at,
                deleted_by=device.deleted_by,
            )
        )

    return ESPDeviceListResponse(
        success=True,
        data=device_responses,
        pagination=PaginationMeta.from_pagination(page, page_size, total_items),
    )


# =============================================================================
# Discovery/Approval Endpoints (BEFORE wildcard routes!)
# =============================================================================
# CRITICAL: These specific routes MUST come BEFORE /devices/{esp_id}
# Otherwise FastAPI will match "pending" as esp_id parameter → 404


@router.get(
    "/devices/pending",
    response_model=PendingDevicesListResponse,
    summary="List pending ESP devices",
    description="Get all ESP devices awaiting approval.",
)
async def list_pending_devices(
    db: DBSession,
    current_user: OperatorUser,
) -> PendingDevicesListResponse:
    """
    List all pending ESP devices.

    Returns devices that have been discovered via heartbeat
    but have not yet been approved by an administrator.

    Requires operator or admin role.

    Args:
        db: Database session
        current_user: Operator or admin user

    Returns:
        List of pending devices
    """
    esp_repo = ESPRepository(db)
    devices = await esp_repo.get_by_status("pending_approval")

    pending_devices = []
    for device in devices:
        metadata = device.device_metadata or {}
        initial_heartbeat = metadata.get("initial_heartbeat", {})

        # Use last_seen for current activity, discovered_at for historical reference
        # Prefer metadata last_* values (updated on every heartbeat) over initial_heartbeat
        last_heap = metadata.get("last_heap_free")
        last_rssi = metadata.get("last_wifi_rssi")
        last_sensors = metadata.get("last_sensor_count")
        last_actuators = metadata.get("last_actuator_count")
        pending_devices.append(
            PendingESPDevice(
                device_id=device.device_id,
                discovered_at=device.discovered_at or device.created_at,
                last_seen=device.last_seen,  # Current activity timestamp (for UI "vor X Zeit")
                ip_address=device.ip_address,  # IP from heartbeat wifi_ip field
                zone_id=metadata.get("zone_id"),
                heap_free=(
                    last_heap
                    if last_heap is not None
                    else initial_heartbeat.get("heap_free", initial_heartbeat.get("free_heap"))
                ),
                wifi_rssi=(
                    last_rssi if last_rssi is not None else initial_heartbeat.get("wifi_rssi")
                ),
                sensor_count=(
                    last_sensors
                    if last_sensors is not None
                    else initial_heartbeat.get("sensor_count", 0)
                ),
                actuator_count=(
                    last_actuators
                    if last_actuators is not None
                    else initial_heartbeat.get("actuator_count", 0)
                ),
                heartbeat_count=metadata.get("heartbeat_count", 0),
                hardware_type=device.hardware_type,  # From auto-registration
            )
        )

    return PendingDevicesListResponse(
        success=True,
        devices=pending_devices,
        count=len(pending_devices),
    )


# =============================================================================
# Get Device (AFTER specific routes)
# =============================================================================


@router.get(
    "/devices/{esp_id}",
    response_model=ESPDeviceResponse,
    responses={
        200: {"description": "Device found"},
        404: {"description": "Device not found"},
    },
    summary="Get ESP device details",
    description="Get detailed information about a specific ESP device.",
)
async def get_device(
    esp_id: str,
    db: DBSession,
    current_user: ActiveUser,
) -> ESPDeviceResponse:
    """
    Get ESP device by device_id.

    Args:
        esp_id: ESP device ID (e.g., ESP_12AB34CD)
        db: Database session
        current_user: Authenticated user

    Returns:
        ESP device details

    Raises:
        HTTPException: 404 if not found
    """
    esp_repo = ESPRepository(db)
    sensor_repo = SensorRepository(db)
    actuator_repo = ActuatorRepository(db)
    subzone_repo = SubzoneRepository(db)

    device = await esp_repo.get_by_device_id(esp_id)
    if not device:
        raise ESPNotFoundError(esp_id)

    sensor_count = await sensor_repo.count_by_esp(device.id)
    actuator_count = await actuator_repo.count_by_esp(device.id)

    # Extract Mock-specific fields
    auto_heartbeat, heartbeat_interval_seconds = _extract_mock_fields(device)

    # Zone context inheritance (Phase 4)
    zone_ctx = None
    zone_ctx_data = await _enrich_zone_context(device, db, {})
    if zone_ctx_data:
        from ...schemas.esp import ZoneContextSummary

        zone_ctx = ZoneContextSummary(**zone_ctx_data)

    # Subzone summaries (T14-Fix-F)
    subzone_summaries = await _get_subzone_summaries(device.device_id, subzone_repo)

    return ESPDeviceResponse(
        id=device.id,
        device_id=device.device_id,
        name=device.name,
        zone_id=device.zone_id,
        zone_name=device.zone_name,
        is_zone_master=device.is_zone_master,
        ip_address=device.ip_address,
        mac_address=device.mac_address,
        firmware_version=device.firmware_version,
        hardware_type=device.hardware_type,
        capabilities=device.capabilities,
        status=device.status,
        last_seen=device.last_seen,
        metadata=device.device_metadata,
        sensor_count=sensor_count,
        actuator_count=actuator_count,
        auto_heartbeat=auto_heartbeat,
        heartbeat_interval_seconds=heartbeat_interval_seconds,
        created_at=device.created_at,
        updated_at=device.updated_at,
        zone_context=zone_ctx,
        subzones=subzone_summaries,
        deleted_at=device.deleted_at,
        deleted_by=device.deleted_by,
    )


# =============================================================================
# Register Device
# =============================================================================


@router.post(
    "/devices",
    response_model=ESPDeviceResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Device registered"},
        400: {"description": "Device already exists"},
    },
    summary="Register new ESP device",
    description="Manually register a new ESP device.",
)
async def register_device(
    request: ESPDeviceCreate,
    db: DBSession,
    current_user: OperatorUser,
) -> ESPDeviceResponse:
    """
    Register a new ESP device.

    Args:
        request: Device registration data
        db: Database session
        current_user: Operator or admin user

    Returns:
        Registered device details

    Raises:
        HTTPException: 400 if device already exists
    """
    esp_repo = ESPRepository(db)

    # Check if device already exists
    existing = await esp_repo.get_by_device_id(request.device_id)
    if existing:
        raise DuplicateESPError(request.device_id)

    # Create device
    from ...db.models.esp import ESPDevice

    device = ESPDevice(
        device_id=request.device_id,
        name=request.name,
        zone_id=request.zone_id,
        zone_name=request.zone_name,
        is_zone_master=request.is_zone_master,
        ip_address=request.ip_address,
        mac_address=request.mac_address,
        firmware_version=request.firmware_version,
        hardware_type=request.hardware_type,
        capabilities=request.capabilities or {},
        status="pending_approval",
        device_metadata={},
    )

    db.add(device)
    await db.flush()
    await db.refresh(device)
    await db.commit()

    logger.info(f"ESP device registered: {device.device_id} by {current_user.username}")

    # Extract Mock-specific fields (will be None for newly registered real ESPs)
    auto_heartbeat, heartbeat_interval_seconds = _extract_mock_fields(device)

    return ESPDeviceResponse(
        id=device.id,
        device_id=device.device_id,
        name=device.name,
        zone_id=device.zone_id,
        zone_name=device.zone_name,
        is_zone_master=device.is_zone_master,
        ip_address=device.ip_address,
        mac_address=device.mac_address,
        firmware_version=device.firmware_version,
        hardware_type=device.hardware_type,
        capabilities=device.capabilities,
        status=device.status,
        last_seen=device.last_seen,
        metadata=device.device_metadata,
        sensor_count=0,
        actuator_count=0,
        auto_heartbeat=auto_heartbeat,
        heartbeat_interval_seconds=heartbeat_interval_seconds,
        created_at=device.created_at,
        updated_at=device.updated_at,
    )


# =============================================================================
# Update Device
# =============================================================================


@router.patch(
    "/devices/{esp_id}",
    response_model=ESPDeviceResponse,
    responses={
        200: {"description": "Device updated"},
        404: {"description": "Device not found"},
    },
    summary="Update ESP device",
    description="Update ESP device information.",
)
async def update_device(
    esp_id: str,
    request: ESPDeviceUpdate,
    db: DBSession,
    current_user: OperatorUser,
) -> ESPDeviceResponse:
    """
    Update ESP device.

    Args:
        esp_id: ESP device ID
        request: Update data
        db: Database session
        current_user: Operator or admin user

    Returns:
        Updated device details
    """
    esp_repo = ESPRepository(db)
    sensor_repo = SensorRepository(db)
    actuator_repo = ActuatorRepository(db)

    device = await esp_repo.get_by_device_id(esp_id)
    if not device:
        raise ESPNotFoundError(esp_id)

    # Update fields
    update_data = request.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(device, field, value)

    await db.flush()
    await db.commit()

    # Sensor/Actuator counts (needed for MOCK-FIX and response)
    sensor_count = await sensor_repo.count_by_esp(device.id)
    actuator_count = await actuator_repo.count_by_esp(device.id)

    # Für Mock ESPs: Heartbeat triggern für korrekte Health-Metriken
    # Der SimulationScheduler hat die aktuellen Runtime-Werte und sendet ein
    # vollständiges esp_health Event via MQTT → WebSocket
    if device.hardware_type == "MOCK_ESP32":
        try:
            from ..deps import get_simulation_scheduler

            scheduler = get_simulation_scheduler()
            if scheduler.is_mock_active(esp_id):
                await scheduler.trigger_heartbeat(esp_id)
                logger.debug(f"[MOCK-FIX] Triggered heartbeat for {esp_id} after update")
            else:
                logger.debug(f"[MOCK-FIX] Mock {esp_id} not active, skipping heartbeat")
        except Exception as e:
            # Non-critical: Log but don't fail the update
            logger.warning(f"[MOCK-FIX] ERROR triggering heartbeat for {esp_id}: {e}")

    logger.info(f"ESP device updated: {esp_id} by {current_user.username}")

    # Extract Mock-specific fields
    auto_heartbeat, heartbeat_interval_seconds = _extract_mock_fields(device)

    return ESPDeviceResponse(
        id=device.id,
        device_id=device.device_id,
        name=device.name,
        zone_id=device.zone_id,
        zone_name=device.zone_name,
        is_zone_master=device.is_zone_master,
        ip_address=device.ip_address,
        mac_address=device.mac_address,
        firmware_version=device.firmware_version,
        hardware_type=device.hardware_type,
        capabilities=device.capabilities,
        status=device.status,
        last_seen=device.last_seen,
        metadata=device.device_metadata,
        sensor_count=sensor_count,
        actuator_count=actuator_count,
        auto_heartbeat=auto_heartbeat,
        heartbeat_interval_seconds=heartbeat_interval_seconds,
        created_at=device.created_at,
        updated_at=device.updated_at,
    )


# =============================================================================
# Delete Device
# =============================================================================


@router.delete(
    "/devices/{esp_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        204: {"description": "Device soft-deleted"},
        404: {"description": "Device not found"},
    },
    summary="Soft-delete ESP device",
    description="Soft-delete an ESP device. Sensor data and historical records are preserved. Configs (sensors/actuators) are cascade-deleted.",
)
async def delete_device(
    esp_id: str,
    db: DBSession,
    current_user: OperatorUser,
) -> None:
    """
    Soft-delete ESP device (T02-Fix1).

    Sets deleted_at timestamp instead of physical deletion.
    Sensor data, heartbeat logs, actuator history are preserved.
    Sensor/actuator configs are cascade-deleted (they belong to the device).

    Args:
        esp_id: ESP device ID (e.g., ESP_MOCK_E92BAA)
        db: Database session
        current_user: Operator or admin user

    Raises:
        HTTPException: 404 if not found
    """
    esp_repo = ESPRepository(db)

    device = await esp_repo.get_by_device_id(esp_id)
    if not device:
        raise ESPNotFoundError(esp_id)

    # Stop simulation if this is a running mock device
    if device.hardware_type == "MOCK_ESP32":
        try:
            from ..deps import get_simulation_scheduler

            sim_scheduler = get_simulation_scheduler()
            if sim_scheduler.is_mock_active(esp_id):
                await sim_scheduler.stop_mock(esp_id)
                logger.info(f"Stopped simulation for {esp_id} before soft-delete")
        except RuntimeError:
            pass  # Scheduler not initialized

    # Resolve open alerts for this device before deletion (Fix E — NB4)
    from ...db.repositories.notification_repo import NotificationRepository

    notif_repo = NotificationRepository(db)
    resolved_count = await notif_repo.resolve_alerts_for_device(esp_id)
    if resolved_count > 0:
        logger.info(f"Auto-resolved {resolved_count} alerts for deleted device {esp_id}")

    # Remove dashboard widgets referencing this device before deletion
    from ...db.repositories.dashboard_repo import DashboardRepository

    dashboard_repo = DashboardRepository(db)
    removed_widgets = await dashboard_repo.remove_widgets_by_esp_id(esp_id)
    if removed_widgets > 0:
        logger.info(
            f"Removed {removed_widgets} dashboard widget(s) referencing deleted device {esp_id}"
        )

    # Soft-delete the device (sets deleted_at, status='deleted')
    await esp_repo.soft_delete(esp_id, deleted_by=current_user.username)
    await db.commit()

    logger.warning(f"ESP device soft-deleted: {esp_id} by {current_user.username}")


# =============================================================================
# Config-Push Architektur
# =============================================================================
#
# ESP32 Config-Push erfolgt AUTOMATISCH nach Sensor/Actuator CRUD-Operationen.
# Der Pfad ist:
#
#   api/v1/sensors.py oder api/v1/actuators.py
#       → ConfigPayloadBuilder.build_combined_config()
#       → esp_service.send_config()
#       → MQTT Topic: kaiser/{kaiser_id}/esp/{esp_id}/config
#
# Ein manueller Config-Push-Endpoint existiert nicht.
# Für Feld-Mappings siehe: core/config_mapping.py (DEFAULT_SENSOR_MAPPINGS)
# =============================================================================


# =============================================================================
# Restart Command
# =============================================================================


@router.post(
    "/devices/{esp_id}/restart",
    response_model=ESPCommandResponse,
    responses={
        200: {"description": "Restart command sent"},
        404: {"description": "Device not found"},
    },
    summary="Restart ESP device",
    description="Send restart command to ESP via MQTT.",
)
async def restart_device(
    esp_id: str,
    request: ESPRestartRequest,
    db: DBSession,
    current_user: OperatorUser,
    publisher: Annotated[Publisher, Depends(get_mqtt_publisher)],
) -> ESPCommandResponse:
    """
    Send restart command to ESP.

    Args:
        esp_id: ESP device ID
        request: Restart parameters
        db: Database session
        current_user: Operator or admin user
        publisher: MQTT publisher

    Returns:
        Command response
    """
    esp_repo = ESPRepository(db)

    device = await esp_repo.get_by_device_id(esp_id)
    if not device:
        raise ESPNotFoundError(esp_id)

    # Publish restart command
    success = publisher.publish_system_command(
        esp_id=esp_id,
        command="REBOOT",
        params={
            "delay_seconds": request.delay_seconds,
            "reason": request.reason or f"Manual restart by {current_user.username}",
        },
    )

    logger.info(f"Restart command sent to {esp_id} by {current_user.username}")

    return ESPCommandResponse(
        success=success,
        message="Restart command sent" if success else "Failed to send restart command",
        device_id=esp_id,
        command="restart",
        command_sent=success,
    )


# =============================================================================
# Factory Reset
# =============================================================================


@router.post(
    "/devices/{esp_id}/reset",
    response_model=ESPCommandResponse,
    responses={
        200: {"description": "Reset command sent"},
        400: {"description": "Confirmation required"},
        404: {"description": "Device not found"},
    },
    summary="Factory reset ESP device",
    description="Send factory reset command to ESP. Requires confirmation.",
)
async def reset_device(
    esp_id: str,
    request: ESPResetRequest,
    db: DBSession,
    current_user: OperatorUser,
    publisher: Annotated[Publisher, Depends(get_mqtt_publisher)],
) -> ESPCommandResponse:
    """
    Send factory reset command to ESP.

    Args:
        esp_id: ESP device ID
        request: Reset parameters (must confirm=True)
        db: Database session
        current_user: Operator or admin user
        publisher: MQTT publisher

    Returns:
        Command response
    """
    if not request.confirm:
        raise ValidationException("confirm", "Factory reset requires confirm=true")

    esp_repo = ESPRepository(db)

    device = await esp_repo.get_by_device_id(esp_id)
    if not device:
        raise ESPNotFoundError(esp_id)

    # Publish factory reset command
    success = publisher.publish_system_command(
        esp_id=esp_id,
        command="FACTORY_RESET",
        params={
            "preserve_wifi": request.preserve_wifi,
            "initiated_by": current_user.username,
        },
    )

    logger.warning(f"Factory reset sent to {esp_id} by {current_user.username}")

    return ESPCommandResponse(
        success=success,
        message="Factory reset command sent" if success else "Failed to send reset command",
        device_id=esp_id,
        command="factory_reset",
        command_sent=success,
    )


# =============================================================================
# Health Check
# =============================================================================


@router.get(
    "/devices/{esp_id}/health",
    response_model=ESPHealthResponse,
    responses={
        200: {"description": "Health data retrieved"},
        404: {"description": "Device not found"},
    },
    summary="Get ESP health metrics",
    description="Get latest health metrics for an ESP device.",
)
async def get_device_health(
    esp_id: str,
    db: DBSession,
    current_user: ActiveUser,
) -> ESPHealthResponse:
    """
    Get ESP device health metrics.

    Args:
        esp_id: ESP device ID
        db: Database session
        current_user: Authenticated user

    Returns:
        Health metrics
    """
    esp_repo = ESPRepository(db)

    device = await esp_repo.get_by_device_id(esp_id)
    if not device:
        raise ESPNotFoundError(esp_id)

    # Get latest health from device_metadata (populated by heartbeat handler)
    health_data = device.device_metadata.get("health", {}) if device.device_metadata else {}

    # Format uptime
    uptime_formatted = None
    if "uptime" in health_data:
        uptime = health_data["uptime"]
        days = uptime // 86400
        hours = (uptime % 86400) // 3600
        minutes = (uptime % 3600) // 60
        uptime_formatted = f"{days}d {hours}h {minutes}m"

    from ...schemas import ESPHealthMetrics

    metrics = None
    if health_data:
        metrics = ESPHealthMetrics(
            uptime=health_data.get("uptime", 0),
            heap_free=health_data.get("heap_free", 0),
            wifi_rssi=health_data.get("wifi_rssi", -100),
            sensor_count=health_data.get("sensor_count", 0),
            actuator_count=health_data.get("actuator_count", 0),
            timestamp=health_data.get("timestamp", 0),
        )

    return ESPHealthResponse(
        success=True,
        device_id=esp_id,
        status=device.status,
        metrics=metrics,
        last_seen=device.last_seen,
        uptime_formatted=uptime_formatted,
    )


@router.get(
    "/devices/{esp_id}/health/score",
    response_model=ComponentHealthScoreResponse,
    responses={
        200: {"description": "Health score 0–100 and factors"},
        404: {"description": "Device not found"},
    },
    summary="Get component health score (Phase K4 L2.4)",
    description="Aggregated health score for Inventar/K1 badge (online, error rate, data quality, maintenance, uptime).",
)
async def get_device_health_score(
    esp_id: str,
    db: DBSession,
    current_user: ActiveUser,
) -> ComponentHealthScoreResponse:
    from ...services.health_score_service import HealthScoreService

    svc = HealthScoreService(db)
    result = await svc.get_score(esp_id)
    if not result:
        raise ESPNotFoundError(esp_id)
    return ComponentHealthScoreResponse(**result)


# =============================================================================
# GPIO Status (Phase 2 - GPIO Validation)
# =============================================================================


@router.get(
    "/devices/{esp_id}/gpio-status",
    response_model=GpioStatusResponse,
    responses={
        200: {"description": "GPIO status retrieved"},
        404: {"description": "Device not found"},
    },
    summary="Get GPIO pin status",
    description="Get GPIO pin availability and usage for an ESP device. Combines database configuration with ESP-reported status.",
)
async def get_gpio_status(
    esp_id: str,
    db: DBSession,
    current_user: ActiveUser,
) -> GpioStatusResponse:
    """
    Get GPIO pin status for an ESP device (bus-aware).

    Multi-Value Sensor Support:
    - I2C sensors share GPIO 21/22 (bus pins)
    - OneWire sensors share GPIO (bus pin)
    - Analog/Digital sensors have exclusive GPIO

    Args:
        esp_id: ESP device ID
        db: Database session
        current_user: Authenticated user

    Returns:
        GpioStatusResponse with bus-aware GPIO status

    Phase: 2 (GPIO Validation) + Multi-Value Support
    """
    esp_repo = ESPRepository(db)
    sensor_repo = SensorRepository(db)
    actuator_repo = ActuatorRepository(db)

    device = await esp_repo.get_by_device_id(esp_id)
    if not device:
        raise ESPNotFoundError(esp_id)

    # Get all sensors for this ESP
    all_sensors = await sensor_repo.get_by_esp(device.id)

    # Separate by interface type
    analog_digital = [s for s in all_sensors if s.interface_type in ["ANALOG", "DIGITAL"]]
    i2c_sensors = [s for s in all_sensors if s.interface_type == "I2C"]
    onewire_sensors = [s for s in all_sensors if s.interface_type == "ONEWIRE"]

    # Reserved GPIOs (only Analog/Digital)
    reserved_gpios = [s.gpio for s in analog_digital if s.gpio is not None]

    # I2C Bus Info
    i2c_bus_info = None
    if i2c_sensors:
        i2c_bus_info = {
            "sda_pin": 21,
            "scl_pin": 22,
            "is_available": True,  # I2C bus is always shareable
            "devices": [
                {
                    "i2c_address": f"0x{s.i2c_address:02X}" if s.i2c_address else None,
                    "sensor_type": s.sensor_type,
                    "sensor_name": s.sensor_name,
                }
                for s in i2c_sensors
            ],
        }

    # OneWire Bus Info (group by GPIO)
    onewire_by_gpio = {}
    for sensor in onewire_sensors:
        gpio = sensor.gpio or 4  # Default to GPIO 4 if NULL
        if gpio not in onewire_by_gpio:
            onewire_by_gpio[gpio] = []
        onewire_by_gpio[gpio].append(
            {
                "onewire_address": sensor.onewire_address,
                "sensor_type": sensor.sensor_type,
                "sensor_name": sensor.sensor_name,
            }
        )

    onewire_buses = [
        {"gpio": gpio, "is_available": True, "devices": devices}  # OneWire bus is always shareable
        for gpio, devices in onewire_by_gpio.items()
    ]

    # Calculate available GPIOs
    # All GPIOs except reserved ones are available
    # ESP32 WROOM: GPIO 0-39 (exclude input-only 34-39 for output)
    all_gpios = set(range(0, 40))
    available_gpios = [
        g for g in all_gpios if g not in reserved_gpios and g not in [34, 35, 36, 37, 38, 39]
    ]

    # Use GpioValidationService for backwards-compat "reserved" field
    gpio_validator = GpioValidationService(
        session=db, sensor_repo=sensor_repo, actuator_repo=actuator_repo, esp_repo=esp_repo
    )

    used_gpios = await gpio_validator.get_all_used_gpios(device.id)
    reserved_items = [
        GpioUsageItem(
            gpio=g["gpio"],
            owner=g["owner"],
            component=g["component"],
            name=g.get("name"),
            id=g.get("id"),
            source=g["source"],
        )
        for g in used_gpios
    ]

    # Get hardware type and last ESP report timestamp
    hardware_type = device.hardware_type or "ESP32_WROOM"
    last_esp_report = None
    if device.device_metadata:
        last_esp_report = device.device_metadata.get("gpio_status_updated_at")

    return GpioStatusResponse(
        esp_id=esp_id,
        available=sorted(available_gpios),
        reserved=reserved_items,  # Backwards-compat
        system=sorted(SYSTEM_RESERVED_PINS),
        reserved_gpios=sorted(reserved_gpios),  # New: Analog/Digital only
        i2c_bus=i2c_bus_info,  # New: I2C bus status
        onewire_buses=onewire_buses,  # New: OneWire buses
        hardware_type=hardware_type,
        last_esp_report=last_esp_report,
    )


# =============================================================================
# Assign Kaiser
# =============================================================================


@router.post(
    "/devices/{esp_id}/assign_kaiser",
    response_model=AssignKaiserResponse,
    responses={
        200: {"description": "Kaiser assigned"},
        404: {"description": "Device not found"},
    },
    summary="Assign ESP to Kaiser node",
    description="Assign an ESP device to a Kaiser relay node.",
)
async def assign_kaiser(
    esp_id: str,
    request: AssignKaiserRequest,
    db: DBSession,
    current_user: OperatorUser,
) -> AssignKaiserResponse:
    """
    Assign ESP to Kaiser node.

    Args:
        esp_id: ESP device ID
        request: Kaiser assignment
        db: Database session
        current_user: Operator or admin user

    Returns:
        Assignment response
    """
    esp_repo = ESPRepository(db)

    device = await esp_repo.get_by_device_id(esp_id)
    if not device:
        raise ESPNotFoundError(esp_id)

    previous_kaiser = device.device_metadata.get("kaiser_id") if device.device_metadata else None

    # Update device_metadata with Kaiser assignment
    metadata = device.device_metadata or {}
    metadata["kaiser_id"] = request.kaiser_id
    device.device_metadata = metadata

    await db.flush()
    await db.commit()

    logger.info(f"ESP {esp_id} assigned to Kaiser {request.kaiser_id} by {current_user.username}")

    return AssignKaiserResponse(
        success=True,
        message=f"ESP assigned to Kaiser '{request.kaiser_id}'",
        device_id=esp_id,
        kaiser_id=request.kaiser_id,
        previous_kaiser_id=previous_kaiser,
    )


# =============================================================================
# Discovery
# =============================================================================


@router.get(
    "/discovery",
    response_model=ESPDiscoveryResponse,
    summary="Get discovered ESP devices",
    description="Get list of ESP devices discovered via mDNS/network scan.",
)
async def get_discovery(
    db: DBSession,
    current_user: ActiveUser,
) -> ESPDiscoveryResponse:
    """
    Get discovered ESP devices.

    Returns devices found via mDNS or the discovery MQTT topic.

    Args:
        db: Database session
        current_user: Authenticated user

    Returns:
        Discovery results
    """
    esp_repo = ESPRepository(db)

    # Get all registered devices
    _registered_devices = await esp_repo.get_all()
    # In a full implementation, this would query:
    # 1. mDNS discovered devices
    # 2. Discovery MQTT topic (kaiser/god/discovery/esp32_nodes)
    # For now, return empty list (discovery handled by MQTT handler)

    discovered: List[DiscoveredESP] = []

    return ESPDiscoveryResponse(
        success=True,
        message="Discovery results",
        discovered_count=len(discovered),
        new_count=sum(1 for d in discovered if not d.is_registered),
        devices=discovered,
        scan_duration_ms=0,
    )


# =============================================================================
# Approve/Reject Device Endpoints
# =============================================================================


@router.post(
    "/devices/{esp_id}/approve",
    response_model=ESPApprovalResponse,
    responses={
        200: {"description": "Device approved"},
        404: {"description": "Device not found"},
        400: {"description": "Device not in pending state"},
    },
    summary="Approve ESP device",
    description="Approve a pending ESP device for normal operation.",
)
async def approve_device(
    esp_id: str,
    request: ESPApprovalRequest,
    db: DBSession,
    current_user: OperatorUser,
) -> ESPApprovalResponse:
    """
    Approve a pending ESP device.

    After approval, device will become 'online' on next heartbeat.

    Args:
        esp_id: ESP device ID
        request: Approval request with optional name/zone
        db: Database session
        current_user: Operator or admin user

    Returns:
        Approval response

    Raises:
        HTTPException: 404 if not found, 400 if not pending
    """
    esp_repo = ESPRepository(db)
    device = await esp_repo.get_by_device_id(esp_id)

    if not device:
        raise ESPNotFoundError(esp_id)

    if device.status not in ("pending_approval", "rejected"):
        raise ValidationException(
            "status", f"Device '{esp_id}' is not pending approval (status: {device.status})"
        )

    # Capture old status before update
    old_status = device.status

    # Update device
    device.status = "approved"
    device.approved_at = datetime.now(timezone.utc)
    device.approved_by = current_user.username
    device.rejection_reason = None

    if request.name:
        device.name = request.name
    if request.zone_id:
        device.zone_id = request.zone_id
    if request.zone_name:
        device.zone_name = request.zone_name

    # Audit Logging: device_approved
    try:
        audit_repo = AuditLogRepository(db)
        await audit_repo.log_device_event(
            esp_id=esp_id,
            event_type=AuditEventType.DEVICE_APPROVED,
            status="success",
            message=f"Device approved by {current_user.username}",
            details={
                "approved_by": current_user.username,
                "approved_by_id": str(current_user.id),
                "previous_status": old_status,
                "zone_id": device.zone_id,
                "zone_name": device.zone_name,
            },
            severity=AuditSeverity.INFO,
        )
    except Exception as audit_error:
        logger.warning(f"Failed to audit log device_approved: {audit_error}")

    await db.commit()

    # Broadcast approval event
    try:
        from ...websocket.manager import WebSocketManager

        ws_manager = await WebSocketManager.get_instance()
        await ws_manager.broadcast(
            "device_approved",
            {
                "device_id": esp_id,  # Frontend expects device_id, not esp_id
                "approved_by": current_user.username,
                "approved_at": device.approved_at.isoformat(),
                "status": "approved",
            },
        )
    except Exception as e:
        logger.warning(f"Failed to broadcast device_approved: {e}")

    logger.info(f"✅ Device approved: {esp_id} by {current_user.username}")

    return ESPApprovalResponse(
        success=True,
        message=f"Device '{esp_id}' approved successfully",
        device_id=esp_id,
        status="approved",
        approved_by=current_user.username,
        approved_at=device.approved_at,
    )


@router.post(
    "/devices/{esp_id}/reject",
    response_model=ESPApprovalResponse,
    responses={
        200: {"description": "Device rejected"},
        404: {"description": "Device not found"},
        400: {"description": "Device not in pending state"},
    },
    summary="Reject ESP device",
    description="Reject a pending ESP device. Device can be rediscovered after 5 minute cooldown.",
)
async def reject_device(
    esp_id: str,
    request: ESPRejectionRequest,
    db: DBSession,
    current_user: OperatorUser,
) -> ESPApprovalResponse:
    """
    Reject a pending ESP device.

    Rejected devices are ignored for 5 minutes, then can rediscover.

    Args:
        esp_id: ESP device ID
        request: Rejection request with reason
        db: Database session
        current_user: Operator or admin user

    Returns:
        Rejection response

    Raises:
        HTTPException: 404 if not found, 400 if not in valid state
    """
    esp_repo = ESPRepository(db)
    device = await esp_repo.get_by_device_id(esp_id)

    if not device:
        raise ESPNotFoundError(esp_id)

    if device.status not in ("pending_approval", "approved", "online"):
        raise ValidationException(
            "status", f"Device '{esp_id}' cannot be rejected (status: {device.status})"
        )

    # Capture old status before update
    old_status = device.status

    # Update device
    device.status = "rejected"
    device.rejection_reason = request.reason
    device.last_rejection_at = datetime.now(timezone.utc)

    # Audit Logging: device_rejected
    try:
        audit_repo = AuditLogRepository(db)
        await audit_repo.log_device_event(
            esp_id=esp_id,
            event_type=AuditEventType.DEVICE_REJECTED,
            status="success",
            message=f"Device rejected by {current_user.username}: {request.reason}",
            details={
                "rejected_by": current_user.username,
                "rejected_by_id": str(current_user.id),
                "rejection_reason": request.reason,
                "previous_status": old_status,
            },
            severity=AuditSeverity.WARNING,
        )
    except Exception as audit_error:
        logger.warning(f"Failed to audit log device_rejected: {audit_error}")

    await db.commit()

    # Broadcast rejection event
    try:
        from ...websocket.manager import WebSocketManager

        ws_manager = await WebSocketManager.get_instance()
        await ws_manager.broadcast(
            "device_rejected",
            {
                "device_id": esp_id,  # Frontend expects device_id, not esp_id
                "rejection_reason": request.reason,  # Frontend expects rejection_reason, not reason
                "rejected_at": device.last_rejection_at.isoformat(),
                "cooldown_until": None,  # No cooldown implemented yet
            },
        )
    except Exception as e:
        logger.warning(f"Failed to broadcast device_rejected: {e}")

    logger.warning(
        f"❌ Device rejected: {esp_id} by {current_user.username}, reason: {request.reason}"
    )

    return ESPApprovalResponse(
        success=True,
        message=f"Device '{esp_id}' rejected",
        device_id=esp_id,
        status="rejected",
        rejection_reason=request.reason,
    )


@router.post(
    "/devices/{esp_id}/set-pending",
    response_model=ESPApprovalResponse,
    responses={
        200: {"description": "Device moved to pending approval"},
        404: {"description": "Device not found"},
        400: {"description": "Device cannot be moved to pending approval"},
    },
    summary="Move ESP to pending approval",
    description="Forces a device back to pending_approval for deterministic registration handshake tests.",
)
async def set_device_pending(
    esp_id: str,
    db: DBSession,
    current_user: OperatorUser,
) -> ESPApprovalResponse:
    esp_repo = ESPRepository(db)
    device = await esp_repo.get_by_device_id(esp_id)

    if not device:
        raise ESPNotFoundError(esp_id)

    if device.status in ("deleted",):
        raise ValidationException(
            "status",
            f"Device '{esp_id}' cannot be moved to pending approval (status: {device.status})",
        )

    old_status = device.status
    device.status = "pending_approval"
    device.approved_at = None
    device.approved_by = None
    device.rejection_reason = None

    try:
        audit_repo = AuditLogRepository(db)
        await audit_repo.log_device_event(
            esp_id=esp_id,
            event_type=AuditEventType.DEVICE_REDISCOVERED,
            status="success",
            message=f"Device moved to pending_approval by {current_user.username}",
            details={
                "changed_by": current_user.username,
                "changed_by_id": str(current_user.id),
                "previous_status": old_status,
                "new_status": "pending_approval",
            },
            severity=AuditSeverity.INFO,
        )
    except Exception as audit_error:
        logger.warning(f"Failed to audit log device_pending_transition: {audit_error}")

    await db.commit()

    logger.info(f"Device moved to pending_approval: {esp_id} by {current_user.username}")
    return ESPApprovalResponse(
        success=True,
        message=f"Device '{esp_id}' moved to pending approval",
        device_id=esp_id,
        status="pending_approval",
    )


# =========================================================================
# ALERT CONFIGURATION (Phase 4A.7 — Device-Level Alert Suppression)
# =========================================================================


@router.patch(
    "/devices/{esp_id}/alert-config",
    summary="Update device-level alert configuration",
)
async def update_device_alert_config(
    esp_id: str,
    payload: DeviceAlertConfigUpdate,
    db: DBSession,
    current_user: OperatorUser,
) -> dict:
    """
    Update device-level alert configuration (ISA-18.2 Shelved Alarms).

    Merges provided fields into the existing alert_config JSONB.
    When propagate_to_children=True, all child sensors/actuators
    inherit the device suppression.
    """
    esp_repo = ESPRepository(db)
    device = await esp_repo.get_by_device_id(esp_id)
    if not device:
        raise ESPNotFoundError(esp_id)

    # Merge into existing alert_config
    existing = device.alert_config or {}
    update_data = payload.model_dump(exclude_unset=True)
    existing.update(update_data)
    device.alert_config = existing

    await db.commit()
    await db.refresh(device)

    logger.info(
        f"Device alert config updated for {esp_id} by user {current_user.id}, "
        f"propagate_to_children={existing.get('propagate_to_children', True)}"
    )

    return {
        "success": True,
        "esp_id": esp_id,
        "alert_config": device.alert_config,
    }


@router.get(
    "/devices/{esp_id}/alert-config",
    summary="Get device-level alert configuration",
)
async def get_device_alert_config(
    esp_id: str,
    db: DBSession,
    current_user: ActiveUser,
) -> dict:
    """Get device-level alert configuration."""
    esp_repo = ESPRepository(db)
    device = await esp_repo.get_by_device_id(esp_id)
    if not device:
        raise ESPNotFoundError(esp_id)

    return {
        "success": True,
        "esp_id": esp_id,
        "alert_config": device.alert_config or {},
    }
