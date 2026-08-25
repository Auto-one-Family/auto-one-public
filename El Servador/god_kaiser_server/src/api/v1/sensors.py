"""
Sensor Management API Endpoints

Phase: 5 (Week 9-10) - API Layer
Priority: 🔴 CRITICAL
Status: IMPLEMENTED

Provides:
- GET / - List sensor configs
- GET /{esp_id}/{gpio} - Get sensor config
- POST /{esp_id}/{gpio} - Create/update config
- DELETE /{esp_id}/{config_id} - Remove config by sensor_config_id
- GET /data - Query sensor data
- POST /esp/{esp_id}/onewire/scan - Scan OneWire bus for devices (DS18B20)
- GET /esp/{esp_id}/onewire - List configured OneWire sensors

Note: /process and /calibrate are in sensor_processing.py

References:
- .claude/PI_SERVER_REFACTORING.md (Lines 135-145)
- El Trabajante/docs/Mqtt_Protocoll.md (Sensor topics)
- ds18b20_onewire_integration Plan (Phase 5)
"""

import csv
import io
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import SQLAlchemyError

from ...core.exceptions import (
    ConfigurationException,
    DeviceNotApprovedError,
    DuplicateError,
    ESPNotFoundError,
    GatewayTimeoutError,
    GpioConflictError,
    MeasurementBusyError,
    SensorConfigInvalidUuidError,
    SensorNotFoundException,
    SensorProcessingException,
    ServiceUnavailableError,
    ValidationException,
)
from ...core.logging_config import get_logger
from ...db.models.sensor import SensorConfig
from ...db.models.enums import DataSource
from ...db.repositories import (
    ActuatorRepository,
    ESPRepository,
    SensorRepository,
    SubzoneRepository,
)
from ...schemas import (
    OneWireScanResponse,
    SensorConfigCreate,
    SensorConfigListResponse,
    SensorConfigResponse,
    SensorDataResponse,
    SensorReading,
    SensorStats,
    SensorStatsResponse,
    TriggerMeasurementRequest,
    TriggerMeasurementResponse,
)
from ...schemas.alert_config import (
    CustomThresholds,
    SensorAlertConfigUpdate,
    SensorAlertConfigViewResponse,
    SensorRuntimeUpdateResponse,
    SensorRuntimeViewResponse,
)
from ...schemas.common import PaginationMeta
from ...schemas.sensor import _TEMPERATURE_SENSOR_TYPES
from ...sensors.sensor_type_registry import (
    get_all_value_types_for_device,
    get_device_type_from_sensor_type,
    is_multi_value_sensor,
    normalize_sensor_type,
)
from ...services.esp_service import ESPService
from ..deps import (
    ActiveUser,
    DBSession,
    MQTTPublisher,
    OperatorUser,
    ViewerUser,
    get_esp_service,
    get_mqtt_publisher,
    get_sensor_service,
    get_sensor_scheduler_service,
)
from ...services.sensor_scheduler_service import SensorSchedulerService
from ...services.sensor_service import SensorService
from ...services.gpio_validation_service import GpioValidationService
from ...services.subzone_service import SubzoneService
from ...services.calibration_payloads import canonicalize_calibration_data
from ...services.config_builder import ConfigConflictError
from ...mqtt.topics import TopicBuilder
from ...utils.subzone_helpers import normalize_subzone_id

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/sensors", tags=["sensors"])


# =============================================================================
# Helper Functions: Model <-> Schema Conversion
# =============================================================================


def _build_sensor_delete_tombstones(
    *,
    gpio: int,
    sensor_type: str,
    sensor_name: str,
    onewire_address: str,
    i2c_address: int,
) -> list[dict]:
    """Build tombstone entries for sensor deletion config push.

    CO2 (UART) sensors occupy two GPIO pins (RX=gpio, TX=gpio-1).
    Both need tombstone entries so the ESP removes both from NVS.
    All other sensor types produce a single tombstone.
    """
    base: dict = {
        "sensor_type": sensor_type,
        "sensor_name": sensor_name,
        "active": False,
        "onewire_address": onewire_address,
        "i2c_address": i2c_address,
    }
    if sensor_type == "co2":
        tx_pin = gpio - 1
        rx_entry = {**base, "gpio": gpio, "uart_rx_pin": gpio, "uart_tx_pin": tx_pin}
        tx_entry = {**base, "gpio": tx_pin, "uart_rx_pin": gpio, "uart_tx_pin": tx_pin}
        return [rx_entry, tx_entry]
    return [{**base, "gpio": gpio}]


def _model_to_response(
    sensor: SensorConfig,
    esp_device_id: Optional[str] = None,
    subzone_id: Optional[str] = None,
    subzone_warning: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> SensorConfigResponse:
    """
    Convert SensorConfig model to SensorConfigResponse schema.

    Handles field name mapping between model and schema:
    - sensor_name (model) -> name (schema)
    - sample_interval_ms (model) -> interval_ms (schema)
    - pi_enhanced (model) -> processing_mode (schema)
    - calibration_data (model) -> calibration (schema)
    - thresholds dict (model) -> threshold_min/max/warning_min/max (schema)
    - alert_config.custom_thresholds dict (model) -> custom_thresholds (schema)
    - sensor_metadata (model) -> metadata (schema)
    - interface_type, i2c_address, onewire_address, provides_values (multi-value support)
    """
    # Extract thresholds from dict
    thresholds = sensor.thresholds or {}
    threshold_min = thresholds.get("min")
    threshold_max = thresholds.get("max")
    warning_min = thresholds.get("warning_min")
    warning_max = thresholds.get("warning_max")

    # AUT-1104: alert_config.custom_thresholds passthrough (same source
    # alert_suppression_service.get_effective_thresholds() prioritizes over
    # `thresholds` above). None if unset — CustomThresholds() would produce an
    # all-None object instead, which the frontend can't distinguish from "unset".
    custom_thresholds_raw = (sensor.alert_config or {}).get("custom_thresholds")
    custom_thresholds = (
        CustomThresholds(**custom_thresholds_raw) if custom_thresholds_raw else None
    )

    # Convert pi_enhanced boolean to processing_mode string
    processing_mode = "pi_enhanced" if sensor.pi_enhanced else "raw"

    # Get interface_type from model or infer from sensor_type (fallback for legacy data)
    interface_type = (
        sensor.interface_type
        if sensor.interface_type
        else _infer_interface_type(sensor.sensor_type)
    )

    return SensorConfigResponse(
        id=sensor.id,
        esp_id=sensor.esp_id,
        esp_device_id=esp_device_id,
        gpio=sensor.gpio if sensor.gpio is not None else 0,
        sensor_type=sensor.sensor_type,
        name=sensor.sensor_name,  # Model: sensor_name -> Schema: name
        enabled=sensor.enabled,
        interval_ms=sensor.sample_interval_ms,  # Model: sample_interval_ms -> Schema: interval_ms
        processing_mode=processing_mode,  # Model: pi_enhanced -> Schema: processing_mode
        # =========================================================================
        # MULTI-VALUE SENSOR SUPPORT
        # =========================================================================
        interface_type=interface_type,
        i2c_address=sensor.i2c_address,
        onewire_address=sensor.onewire_address,
        provides_values=sensor.provides_values,
        # External ADC source (ADS1115) — per-sensor acquisition source for pH/EC
        adc_source=getattr(sensor, "adc_source", None),
        adc_channel=getattr(sensor, "adc_channel", None),
        pga_gain=getattr(sensor, "pga_gain", None),
        polarity=getattr(sensor, "polarity", None),
        # =========================================================================
        calibration=sensor.calibration_data,  # Model: calibration_data -> Schema: calibration
        threshold_min=threshold_min,
        threshold_max=threshold_max,
        warning_min=warning_min,
        warning_max=warning_max,
        custom_thresholds=custom_thresholds,
        metadata=sensor.sensor_metadata,  # Model: sensor_metadata -> Schema: metadata
        description=(sensor.sensor_metadata or {}).get("description"),
        unit=(sensor.sensor_metadata or {}).get("unit"),
        measurement_role=(sensor.sensor_metadata or {}).get("measurement_role"),
        # Config status from ESP32 verification (Phase 2: write-after-verification)
        config_status=sensor.config_status,
        config_error=sensor.config_error,
        config_error_detail=sensor.config_error_detail,
        subzone_id=subzone_id,
        operating_mode=sensor.operating_mode,
        timeout_seconds=sensor.timeout_seconds,
        schedule_config=sensor.schedule_config,
        measurement_freshness_hours=sensor.measurement_freshness_hours,
        calibration_interval_days=sensor.calibration_interval_days,
        # Multi-Zone Device Scope (T13-R2)
        device_scope=sensor.device_scope,
        assigned_zones=sensor.assigned_zones,
        # assigned_subzones: Legacy field, passed through the API layer but not evaluated
        # in business logic (logic_engine, config_builder, notification_router, safety).
        # Primary subzone assignment is via subzone_configs.assigned_gpios. Candidate for
        # future DB cleanup.
        assigned_subzones=sensor.assigned_subzones,
        # AUT-299: Linked temperature sensor config UUID for ATC
        temp_sensor_config_id=sensor.temp_sensor_config_id,
        latest_value=None,  # Will be set by caller if available
        latest_quality=None,
        latest_timestamp=None,
        created_at=sensor.created_at,
        updated_at=sensor.updated_at,
        subzone_warning=subzone_warning,
        correlation_id=correlation_id,
    )


def _schema_to_model_fields(request: SensorConfigCreate) -> dict:
    """
    Convert SensorConfigCreate schema fields to SensorConfig model fields.

    Returns dict with model field names for direct model creation.
    """
    # Convert processing_mode string to pi_enhanced boolean
    pi_enhanced = request.processing_mode == "pi_enhanced"

    # Build thresholds dict from individual fields
    thresholds = {}
    if request.threshold_min is not None:
        thresholds["min"] = request.threshold_min
    if request.threshold_max is not None:
        thresholds["max"] = request.threshold_max
    if request.warning_min is not None:
        thresholds["warning_min"] = request.warning_min
    if request.warning_max is not None:
        thresholds["warning_max"] = request.warning_max

    # Infer interface_type if not provided
    interface_type = request.interface_type or _infer_interface_type(request.sensor_type)

    # Merge description/unit/measurement_role into sensor_metadata (Config-Panel-Optimierung: persist user input)
    sensor_metadata = dict(request.metadata or {})
    if request.description is not None:
        sensor_metadata["description"] = request.description
    if request.unit is not None:
        sensor_metadata["unit"] = request.unit
    if request.measurement_role is not None:
        sensor_metadata["measurement_role"] = request.measurement_role

    return {
        "sensor_type": normalize_sensor_type(request.sensor_type),
        "sensor_name": request.name or "",  # Schema: name -> Model: sensor_name
        "enabled": request.enabled,
        "sample_interval_ms": request.interval_ms,  # Schema: interval_ms -> Model: sample_interval_ms
        "pi_enhanced": pi_enhanced,  # Schema: processing_mode -> Model: pi_enhanced
        "calibration_data": canonicalize_calibration_data(
            request.calibration,
            source="api_v1_sensors",
        ),  # Schema: calibration -> Model: calibration_data
        "thresholds": thresholds if thresholds else None,
        "sensor_metadata": sensor_metadata,  # Schema: metadata + description/unit -> Model: sensor_metadata
        # =========================================================================
        # MULTI-VALUE SENSOR SUPPORT (I2C/OneWire)
        # =========================================================================
        "interface_type": interface_type,
        "i2c_address": request.i2c_address,
        "onewire_address": request.onewire_address,
        "provides_values": request.provides_values,
        # =========================================================================
        # EXTERNAL ADC SOURCE (ADS1115) — per-sensor acquisition source for pH/EC
        # =========================================================================
        "adc_source": request.adc_source or "internal",
        "adc_channel": request.adc_channel,
        "pga_gain": request.pga_gain,
        "polarity": request.polarity or "active_low",
        # =========================================================================
        # OPERATING MODE FIELDS (Phase 2F)
        # =========================================================================
        "operating_mode": request.operating_mode,
        "timeout_seconds": request.timeout_seconds,
        "timeout_warning_enabled": request.timeout_warning_enabled,
        "schedule_config": request.schedule_config,
        "measurement_freshness_hours": request.measurement_freshness_hours,
        "calibration_interval_days": request.calibration_interval_days,
        # =========================================================================
        # MULTI-ZONE DEVICE SCOPE (T13-R2)
        # =========================================================================
        "device_scope": request.device_scope if request.device_scope is not None else "zone_local",
        "assigned_zones": request.assigned_zones if request.assigned_zones is not None else [],
        # AUT-227: assigned_subzones is DEPRECATED (read-only API).
        # Writes from clients are ignored; column persists as empty list for new rows.
        # Reads continue via the response schema for backwards compatibility.
        "assigned_subzones": [],
        # AUT-299: Optional linked temperature sensor for ATC
        "temp_sensor_config_id": request.temp_sensor_config_id,
    }


# =============================================================================
# List Sensors
# =============================================================================


@router.get(
    "/",
    response_model=SensorConfigListResponse,
    summary="List sensor configurations",
    description="Get all sensor configurations with optional filters.",
)
async def list_sensors(
    db: DBSession,
    current_user: ActiveUser,
    esp_id: Annotated[Optional[str], Query(description="Filter by ESP device ID")] = None,
    sensor_type: Annotated[Optional[str], Query(description="Filter by sensor type")] = None,
    enabled: Annotated[Optional[bool], Query(description="Filter by enabled status")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> SensorConfigListResponse:
    """
    List sensor configurations.

    Args:
        db: Database session
        current_user: Authenticated user
        esp_id: Optional ESP filter
        sensor_type: Optional type filter
        enabled: Optional enabled filter
        page: Page number
        page_size: Items per page

    Returns:
        Paginated list of sensor configs
    """
    sensor_repo = SensorRepository(db)
    subzone_repo = SubzoneRepository(db)
    # Normalize sensor type filter (e.g. "soil_moisture" → "moisture")
    if sensor_type:
        sensor_type = normalize_sensor_type(sensor_type)
    offset = (page - 1) * page_size
    rows, total_items = await sensor_repo.query_paginated(
        esp_device_id=esp_id,
        sensor_type=sensor_type,
        enabled=enabled,
        offset=offset,
        limit=page_size,
    )

    responses = []
    for sensor, esp_device_id in rows:
        # Pass sensor_type for correct multi-value sensor latest reading
        latest = await sensor_repo.get_latest_reading(
            sensor.esp_id, sensor.gpio, sensor_type=sensor.sensor_type
        )
        subzone = await subzone_repo.get_subzone_by_gpio(esp_device_id, sensor.gpio)
        subzone_id_val = subzone.subzone_id if subzone else None
        response = _model_to_response(sensor, esp_device_id, subzone_id=subzone_id_val)
        response.latest_value = (
            (latest.processed_value if latest.processed_value is not None else latest.raw_value)
            if latest
            else None
        )
        response.latest_quality = latest.quality if latest else None
        response.latest_timestamp = latest.timestamp if latest else None

        responses.append(response)

    return SensorConfigListResponse(
        success=True,
        data=responses,
        pagination=PaginationMeta.from_pagination(page, page_size, total_items),
    )


# =============================================================================
# Sensor by ID Endpoints (must be before /{esp_id}/{gpio} to avoid route clash)
# =============================================================================


@router.get(
    "/{sensor_id}/alert-config",
    response_model=SensorAlertConfigViewResponse,
    summary="Get sensor alert configuration",
)
async def get_sensor_alert_config(
    sensor_id: uuid.UUID,
    session: DBSession,
    user: ActiveUser,
) -> SensorAlertConfigViewResponse:
    """Get the current alert configuration for a sensor."""
    sensor_repo = SensorRepository(session)
    sensor = await sensor_repo.get_by_id(sensor_id)
    if not sensor:
        raise SensorNotFoundException(str(sensor_id))

    return SensorAlertConfigViewResponse(
        status="ok",
        alert_config=sensor.alert_config or {},
        thresholds=sensor.thresholds or {},
    )


@router.get(
    "/{sensor_id}/runtime",
    response_model=SensorRuntimeViewResponse,
    summary="Get sensor runtime stats",
)
async def get_sensor_runtime(
    sensor_id: uuid.UUID,
    session: DBSession,
    user: ActiveUser,
) -> SensorRuntimeViewResponse:
    """Get runtime statistics for a sensor."""
    sensor_repo = SensorRepository(session)
    sensor = await sensor_repo.get_by_id(sensor_id)
    if not sensor:
        raise SensorNotFoundException(str(sensor_id))

    runtime = sensor.runtime_stats or {}
    metadata = sensor.sensor_metadata or {}

    # Compute uptime from installation_date
    uptime_hours = None
    installation_date = metadata.get("installation_date")
    if installation_date:
        try:
            inst_dt = datetime.fromisoformat(installation_date)
            if inst_dt.tzinfo is None:
                inst_dt = inst_dt.replace(tzinfo=timezone.utc)
            delta = datetime.now(timezone.utc) - inst_dt
            uptime_hours = round(delta.total_seconds() / 3600, 1)
        except (ValueError, TypeError):
            pass

    # Compute next_maintenance
    next_maintenance = None
    maintenance_overdue = False
    last_maintenance = metadata.get("last_maintenance")
    interval_days = metadata.get("maintenance_interval_days")
    if last_maintenance and interval_days:
        try:
            last_dt = datetime.fromisoformat(last_maintenance)
            # Ensure timezone-aware for comparison with utcnow
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            next_dt = last_dt + timedelta(days=interval_days)
            next_maintenance = next_dt.isoformat()
            maintenance_overdue = next_dt < datetime.now(timezone.utc)
        except (ValueError, TypeError):
            pass

    return SensorRuntimeViewResponse(
        status="ok",
        runtime_stats=runtime,
        computed_uptime_hours=uptime_hours,
        last_restart=runtime.get("last_restart"),
        expected_lifetime_hours=runtime.get("expected_lifetime_hours"),
        maintenance_log=runtime.get("maintenance_log", []) or [],
        next_maintenance=next_maintenance,
        maintenance_overdue=maintenance_overdue,
    )


# =============================================================================
# Get Sensor by config_id (UUID) — always unambiguous
# =============================================================================


@router.get(
    "/config/{config_id}",
    response_model=SensorConfigResponse,
    responses={
        200: {"description": "Sensor config found"},
        404: {"description": "Sensor config not found"},
    },
    summary="Get sensor config by config_id",
    description="Get sensor configuration by its unique UUID. "
    "Always unambiguous, even for multi-value sensors (e.g. 2x SHT31).",
)
async def get_sensor_by_config_id(
    config_id: uuid.UUID,
    db: DBSession,
    current_user: ActiveUser,
) -> SensorConfigResponse:
    """Get sensor configuration by its unique database UUID."""
    sensor_repo = SensorRepository(db)
    subzone_repo = SubzoneRepository(db)
    esp_repo = ESPRepository(db)

    sensor = await sensor_repo.get_by_id(config_id)
    if not sensor:
        raise SensorNotFoundException(str(config_id))

    # Resolve esp_device_id for response
    esp_device = await esp_repo.get_by_id(sensor.esp_id)
    esp_device_id = esp_device.device_id if esp_device else None

    # Resolve subzone
    subzone_id_val = None
    if esp_device_id and sensor.gpio is not None:
        subzone = await subzone_repo.get_subzone_by_gpio(esp_device_id, sensor.gpio)
        subzone_id_val = subzone.subzone_id if subzone else None

    # Latest reading
    latest = await sensor_repo.get_latest_reading(
        sensor.esp_id, sensor.gpio, sensor_type=sensor.sensor_type
    )

    response = _model_to_response(sensor, esp_device_id, subzone_id=subzone_id_val)
    response.latest_value = (
        (latest.processed_value if latest.processed_value is not None else latest.raw_value)
        if latest
        else None
    )
    response.latest_quality = latest.quality if latest else None
    response.latest_timestamp = latest.timestamp if latest else None

    return response


# =============================================================================
# Get Sensor by ESP + GPIO
# =============================================================================


@router.get(
    "/{esp_id}/{gpio}",
    response_model=SensorConfigResponse,
    responses={
        200: {"description": "Sensor found"},
        404: {"description": "Sensor not found"},
    },
    summary="Get sensor configuration",
    description="Get configuration for a specific sensor.",
)
async def get_sensor(
    esp_id: str,
    gpio: int,
    db: DBSession,
    current_user: ActiveUser,
    sensor_type: Annotated[
        Optional[str],
        Query(description="Sensor type filter (required for multi-value sensors like SHT31)"),
    ] = None,
) -> SensorConfigResponse:
    """
    Get sensor configuration.

    Args:
        esp_id: ESP device ID
        gpio: GPIO pin number
        db: Database session
        current_user: Authenticated user
        sensor_type: Optional sensor type (e.g. 'sht31_temp'). Required for
                     multi-value sensors that share a GPIO pin.

    Returns:
        Sensor configuration
    """
    esp_repo = ESPRepository(db)
    sensor_repo = SensorRepository(db)
    subzone_repo = SubzoneRepository(db)

    esp_device = await esp_repo.get_by_device_id(esp_id)
    if not esp_device:
        raise ESPNotFoundError(esp_id)

    # Multi-value sensor support: use sensor_type for precise lookup
    if sensor_type:
        sensor_type = normalize_sensor_type(sensor_type)
        sensor = await sensor_repo.get_by_esp_gpio_and_type(esp_device.id, gpio, sensor_type)
    else:
        # Fallback: get all sensors on this GPIO, return first
        sensors = await sensor_repo.get_all_by_esp_and_gpio(esp_device.id, gpio)
        if len(sensors) > 1:
            logger.warning(
                f"Multiple sensors on GPIO {gpio} for ESP '{esp_id}' "
                f"(types: {[s.sensor_type for s in sensors]}). "
                f"Use ?sensor_type= to select specific sensor."
            )
        sensor = sensors[0] if sensors else None

    if not sensor:
        raise SensorNotFoundException(esp_id, gpio)

    # Get latest reading filtered by sensor_type for correct multi-value data
    latest = await sensor_repo.get_latest_reading(
        esp_device.id, gpio, sensor_type=sensor.sensor_type
    )

    # Resolve subzone_id (GPIO can belong to at most one subzone)
    subzone = await subzone_repo.get_subzone_by_gpio(esp_id, gpio)
    subzone_id_val = subzone.subzone_id if subzone else None

    # Convert model to response schema
    response = _model_to_response(sensor, esp_id, subzone_id=subzone_id_val)
    response.latest_value = (
        (latest.processed_value if latest.processed_value is not None else latest.raw_value)
        if latest
        else None
    )
    response.latest_quality = latest.quality if latest else None
    response.latest_timestamp = latest.timestamp if latest else None

    return response


# =============================================================================
# Create/Update Sensor
# =============================================================================


@router.post(
    "/{esp_id}/{gpio}",
    response_model=SensorConfigResponse,
    responses={
        200: {"description": "Sensor created/updated"},
        404: {"description": "ESP device not found"},
    },
    summary="Create or update sensor",
    description="Create new sensor config or update existing.",
)
async def create_or_update_sensor(
    esp_id: str,
    gpio: int,
    request: SensorConfigCreate,
    db: DBSession,
    current_user: OperatorUser,
    publisher: MQTTPublisher,
) -> SensorConfigResponse:
    """
    Create or update sensor configuration.

    Args:
        esp_id: ESP device ID
        gpio: GPIO pin number
        request: Sensor configuration
        db: Database session
        current_user: Operator or admin user

    Returns:
        Created/updated sensor config
    """
    # Path params are authoritative — override body values for robustness
    request.esp_id = esp_id
    request.gpio = gpio

    esp_repo = ESPRepository(db)
    sensor_repo = SensorRepository(db)
    actuator_repo = ActuatorRepository(db)

    esp_device = await esp_repo.get_by_device_id(esp_id)
    if not esp_device:
        raise ESPNotFoundError(esp_id)

    # =========================================================================
    # DEVICE STATUS GUARD - Only approved/online/offline devices can be configured
    # "offline" = previously approved device that is temporarily disconnected
    # "pending" = newly discovered device awaiting approval → blocked
    # =========================================================================
    if esp_device.status not in ("approved", "online", "offline"):
        raise DeviceNotApprovedError(esp_id, esp_device.status)

    # =========================================================================
    # MULTI-ZONE VALIDATION (T13-R2 H3)
    # Validate assigned_zones exist in zones table when scope is multi_zone/mobile
    # =========================================================================
    scope = request.device_scope or "zone_local"
    if scope in ("multi_zone", "mobile") and request.assigned_zones:
        from ...services.device_scope_service import DeviceScopeService

        scope_service = DeviceScopeService(db)
        invalid_zones = await scope_service.validate_assigned_zones(request.assigned_zones)
        if invalid_zones:
            raise ValidationException(
                "assigned_zones",
                f"Invalid or inactive zone_ids: {invalid_zones}",
            )

    # =========================================================================
    # MULTI-VALUE SENSOR SPLITTING
    # =========================================================================
    # Base device types (e.g., "sht31") are split into individual value types
    # (e.g., "sht31_temp" + "sht31_humidity"). Each gets its own sensor_config.
    # The first created config is returned; frontend reloads all via fetchDevice().
    if is_multi_value_sensor(request.sensor_type):
        value_types = get_all_value_types_for_device(request.sensor_type)

        # Guard: empty value_types means registry misconfiguration
        if not value_types:
            raise ConfigurationException(
                "sensor_type_registry",
                f"Sensor type '{request.sensor_type}' is registered as multi-value "
                "but has no defined sub-types. Contact system administrator.",
            )

        logger.info(
            f"Multi-value sensor '{request.sensor_type}' for ESP {esp_id}: "
            f"splitting into {value_types}"
        )
        created_sensors = []

        # Atomic transaction: all sub-types succeed or all rollback
        try:
            for value_type in value_types:
                # Check if this sub-type already exists (I2C-aware for multiple same-type devices)
                if request.i2c_address is not None:
                    existing_vt = await sensor_repo.get_by_esp_gpio_type_and_i2c(
                        esp_device.id, gpio, value_type, request.i2c_address
                    )
                else:
                    existing_vt = await sensor_repo.get_by_esp_gpio_and_type(
                        esp_device.id, gpio, value_type
                    )

                # Build model fields, override sensor_type + interface_type per sub-type
                model_fields = _schema_to_model_fields(request)
                model_fields["sensor_type"] = value_type
                model_fields["interface_type"] = request.interface_type or _infer_interface_type(
                    value_type
                )

                if existing_vt:
                    # Update existing sub-type (same field set as single-value path)
                    existing_vt.sensor_type = model_fields["sensor_type"]
                    if request.name is not None:
                        existing_vt.sensor_name = model_fields["sensor_name"]
                    existing_vt.enabled = model_fields["enabled"]
                    existing_vt.sample_interval_ms = model_fields["sample_interval_ms"]
                    existing_vt.pi_enhanced = model_fields["pi_enhanced"]
                    if request.calibration is not None:
                        existing_vt.calibration_data = model_fields["calibration_data"]
                    if model_fields["thresholds"]:
                        existing_vt.thresholds = model_fields["thresholds"]
                    if (
                        request.description is not None
                        or request.unit is not None
                        or request.measurement_role is not None
                        or request.metadata is not None
                    ):
                        meta = dict(existing_vt.sensor_metadata or {})
                        meta.update(model_fields["sensor_metadata"])
                        existing_vt.sensor_metadata = meta
                    existing_vt.interface_type = model_fields["interface_type"]
                    existing_vt.operating_mode = model_fields["operating_mode"]
                    existing_vt.timeout_seconds = model_fields["timeout_seconds"]
                    existing_vt.timeout_warning_enabled = model_fields["timeout_warning_enabled"]
                    existing_vt.schedule_config = model_fields["schedule_config"]
                    existing_vt.measurement_freshness_hours = model_fields[
                        "measurement_freshness_hours"
                    ]
                    existing_vt.calibration_interval_days = model_fields[
                        "calibration_interval_days"
                    ]
                    # Multi-Zone Device Scope (T13-R2)
                    if request.device_scope is not None:
                        existing_vt.device_scope = model_fields["device_scope"]
                    if request.assigned_zones is not None:
                        existing_vt.assigned_zones = model_fields["assigned_zones"]
                    # AUT-227: assigned_subzones is read-only — writes from clients are ignored.
                    existing_vt.config_status = "pending"
                    existing_vt.config_error = None
                    existing_vt.config_error_detail = None
                    sensor = existing_vt
                    logger.info(
                        f"Multi-value '{value_type}': updated existing config (config_status=pending)"
                    )
                else:
                    # Create new sub-type config
                    sensor = SensorConfig(
                        esp_id=esp_device.id,
                        gpio=gpio,
                        **model_fields,
                    )
                    await sensor_repo.create(sensor)
                    logger.info(
                        f"Multi-value '{value_type}': created new config (config_status=pending)"
                    )

                created_sensors.append(sensor)

            # Single atomic commit for all sub-types
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error(
                f"Failed to create multi-value sensor '{request.sensor_type}' for ESP {esp_id}: "
                f"rolling back all sub-types. Error: {e}",
                exc_info=True,
            )
            raise SensorProcessingException(
                esp_id,
                gpio,
                f"Multi-value sensor creation failed for '{request.sensor_type}': {str(e)}",
            )

        # Refresh all sensors
        for sensor in created_sensors:
            await db.refresh(sensor)

        # Subzone assignment (same GPIO for all sub-types)
        # subzone_error: set when assignment fails — passed to response as warning.
        # Config-Push MUST always run after the primary DB commit regardless.
        subzone_error: Optional[str] = None
        try:
            subzone_service = SubzoneService(esp_repo=esp_repo, session=db, publisher=publisher)
            subzone_id_val = normalize_subzone_id(request.subzone_id)
            if subzone_id_val:
                await subzone_service.assign_subzone(
                    device_id=esp_id,
                    subzone_id=subzone_id_val,
                    assigned_gpios=[gpio],
                    subzone_name=None,
                    parent_zone_id=esp_device.zone_id,
                    safe_mode_active=True,
                )
                await db.commit()
            else:
                await subzone_service.remove_gpio_from_all_subzones(esp_id, gpio)
                await db.commit()
        except ValueError as e:
            logger.warning(f"Subzone assignment skipped for {esp_id}/GPIO {gpio}: {e}")
            await db.rollback()
            subzone_error = str(e)
        except SQLAlchemyError as e:
            # AUT-228 (E2): Erwartete DB-Fehler -> WARNING, non-fatal
            logger.warning(
                f"Subzone assignment DB error for {esp_id}/GPIO {gpio}: {e}"
            )
            await db.rollback()
            subzone_error = "subzone_db_error"
        except Exception as e:
            # AUT-228 (E2): Unerwartete Exceptions -> ERROR + Stacktrace,
            # damit Drift in der Subzone-Logik nicht stillschweigend untergeht.
            logger.error(
                f"Unexpected subzone assignment failure for {esp_id}/GPIO {gpio}: {e}",
                exc_info=True,
            )
            await db.rollback()
            subzone_error = "subzone_unexpected_error"

        subzone_repo = SubzoneRepository(db)
        subzone = await subzone_repo.get_subzone_by_gpio(esp_id, gpio)
        subzone_id_val = subzone.subzone_id if subzone else None

        # Publish combined config to ESP32 via MQTT (once for all sub-types)
        mqtt_correlation_id: Optional[str] = None
        try:
            esp_service: ESPService = get_esp_service(db)
            schedule_result = await esp_service.trigger_config_push_debounced(
                esp_id,
                reason_code="sensor_config_change",
            )
            mqtt_correlation_id = schedule_result.get("correlation_id")
            logger.info("Config push coalesced for ESP %s after multi-value sensor create", esp_id)
        except Exception as e:
            # Log error but don't fail the request (DB save was successful)
            logger.error(f"Failed to publish config to ESP {esp_id}: {e}", exc_info=True)

        return _model_to_response(
            created_sensors[0],
            esp_id,
            subzone_id=subzone_id_val,
            subzone_warning=subzone_error,
            correlation_id=mqtt_correlation_id,
        )

    # =========================================================================
    # SINGLE-VALUE SENSOR (existing logic unchanged)
    # =========================================================================
    # Infer interface_type BEFORE lookup (needed for address-aware matching)
    interface_type = request.interface_type or _infer_interface_type(request.sensor_type)

    # Address-aware lookup: use specific repo method when address is provided
    # to correctly distinguish multiple sensors on the same GPIO (R20-P1 fix)
    if interface_type == "ONEWIRE" and request.onewire_address is not None:
        existing = await sensor_repo.get_by_esp_gpio_type_and_onewire(
            esp_device.id, gpio, request.sensor_type, request.onewire_address
        )
    elif interface_type == "I2C" and request.i2c_address is not None:
        existing = await sensor_repo.get_by_esp_gpio_type_and_i2c(
            esp_device.id, gpio, request.sensor_type, request.i2c_address
        )
    else:
        # ANALOG/DIGITAL or no address provided — GPIO alone is unique
        existing = await sensor_repo.get_by_esp_gpio_and_type(
            esp_device.id, gpio, request.sensor_type
        )

    # Track validated addresses (may be auto-generated for OneWire)
    validated_onewire_address: Optional[str] = None

    # Interface-based validation
    if interface_type == "I2C":
        # I2C: Check i2c_address conflict, NOT GPIO conflict
        await _validate_i2c_config(
            sensor_repo,
            esp_device.id,
            request.i2c_address,
            sensor_type=request.sensor_type,
            exclude_sensor_id=existing.id if existing else None,
        )
        # I2C sensors can share GPIO (bus pins 21/22)
        # No GPIO validation needed
    elif interface_type == "ONEWIRE":
        # OneWire: Validate address (or generate placeholder if not provided)
        validated_onewire_address = await _validate_onewire_config(
            sensor_repo,
            esp_device.id,
            request.onewire_address,
            exclude_sensor_id=existing.id if existing else None,
        )
        # OneWire sensors can share GPIO (bus pin)
        # No GPIO validation needed
    else:  # ANALOG or DIGITAL
        # ADS1115 sensors use gpio=0 as convention meaning "no direct GPIO" —
        # the actual ADC chip is connected via I2C (SDA/SCL), not a GPIO pin.
        # Skip system-pin check; the ADS1115 i2c_address conflict check is
        # handled implicitly (same sensor_type + gpio=0 lookup above).
        _is_ads1115 = gpio == 0 and request.adc_source == "ads1115"
        if not _is_ads1115:
            # Analog/Digital: Check GPIO conflict (exclusive)
            gpio_validator = GpioValidationService(
                session=db, sensor_repo=sensor_repo, actuator_repo=actuator_repo, esp_repo=esp_repo
            )

            validation_result = await gpio_validator.validate_gpio_available(
                esp_db_id=esp_device.id,
                gpio=gpio,
                exclude_sensor_id=existing.id if existing else None,
                purpose="sensor",
                interface_type=interface_type,
            )

        if not _is_ads1115:
            if not validation_result.available:
                logger.warning(
                    f"GPIO conflict for ESP {esp_id}, GPIO {gpio}: "
                    f"{validation_result.conflict_type} - {validation_result.message}"
                )
                raise GpioConflictError(
                    gpio=gpio,
                    conflict_type=validation_result.conflict_type.value,
                    conflict_component=validation_result.conflict_component,
                    conflict_id=(
                        str(validation_result.conflict_id) if validation_result.conflict_id else None
                    ),
                    message=validation_result.message,
                )
            if validation_result.warning:
                logger.info(f"GPIO warning for ESP {esp_id}, GPIO {gpio}: {validation_result.warning}")
    # =========================================================================

    # Convert schema fields to model fields
    model_fields = _schema_to_model_fields(request)

    # Override onewire_address if it was auto-generated during validation
    if interface_type == "ONEWIRE" and validated_onewire_address:
        model_fields["onewire_address"] = validated_onewire_address

    # =========================================================================
    # AUT-299: Validate temp_sensor_config_id references a temperature sensor
    # =========================================================================
    if request.temp_sensor_config_id is not None:
        temp_cfg = await sensor_repo.get_by_id(request.temp_sensor_config_id)
        if temp_cfg is None:
            raise ValidationException(
                "temp_sensor_config_id",
                "refers to a non-existent SensorConfig",
            )
        if temp_cfg.sensor_type not in _TEMPERATURE_SENSOR_TYPES:
            raise ValidationException(
                "temp_sensor_config_id",
                f"must reference a temperature sensor (got '{temp_cfg.sensor_type}')",
            )

    # Capture old values for H2 audit trail before modification
    old_scope = existing.device_scope if existing else None
    old_zones = list(existing.assigned_zones or []) if existing else None

    if existing:
        # Update existing sensor
        existing.sensor_type = model_fields["sensor_type"]
        if request.name is not None:
            existing.sensor_name = model_fields["sensor_name"]
        existing.enabled = model_fields["enabled"]
        existing.sample_interval_ms = model_fields["sample_interval_ms"]
        existing.pi_enhanced = model_fields["pi_enhanced"]
        if request.calibration is not None:
            existing.calibration_data = model_fields["calibration_data"]
        if model_fields["thresholds"]:
            existing.thresholds = model_fields["thresholds"]
        if (
            request.description is not None
            or request.unit is not None
            or request.measurement_role is not None
            or request.metadata is not None
        ):
            meta = dict(existing.sensor_metadata or {})
            meta.update(model_fields["sensor_metadata"])
            existing.sensor_metadata = meta
        # =========================================================================
        # OPERATING MODE FIELDS (Phase 2F)
        # Note: Always update - None is valid (means "use type default")
        # =========================================================================
        existing.operating_mode = model_fields["operating_mode"]
        existing.timeout_seconds = model_fields["timeout_seconds"]
        existing.timeout_warning_enabled = model_fields["timeout_warning_enabled"]
        existing.schedule_config = model_fields["schedule_config"]
        existing.measurement_freshness_hours = model_fields["measurement_freshness_hours"]
        existing.calibration_interval_days = model_fields["calibration_interval_days"]
        # =========================================================================
        # MULTI-ZONE DEVICE SCOPE (T13-R2)
        # Only update if explicitly provided (don't reset to defaults on partial update)
        # =========================================================================
        if request.device_scope is not None:
            existing.device_scope = model_fields["device_scope"]
        if request.assigned_zones is not None:
            existing.assigned_zones = model_fields["assigned_zones"]
        # AUT-227: assigned_subzones is read-only — writes from clients are ignored.
        # AUT-299: temp_sensor_config_id — explicit NULL clears the link (intentional write)
        if "temp_sensor_config_id" in model_fields:
            existing.temp_sensor_config_id = model_fields["temp_sensor_config_id"]
        # =========================================================================
        # ADDRESS FIELDS (R20-P1): Update if provided so re-addressing works
        # =========================================================================
        if request.onewire_address is not None:
            existing.onewire_address = request.onewire_address
        if request.i2c_address is not None:
            existing.i2c_address = request.i2c_address
        # External ADC source (ADS1115) — update when provided so switching the
        # acquisition source per sensor works (and reverting to internal too).
        if request.adc_source is not None:
            existing.adc_source = request.adc_source
        if request.adc_channel is not None:
            existing.adc_channel = request.adc_channel
        if request.pga_gain is not None:
            existing.pga_gain = request.pga_gain
        if request.polarity is not None:
            existing.polarity = request.polarity
        # =========================================================================
        # WRITE-AFTER-VERIFICATION: Reset config_status to pending
        # Status will be updated to "applied" or "failed" by config_handler
        # when ESP32 responds via MQTT config_response
        # =========================================================================
        existing.config_status = "pending"
        existing.config_error = None
        existing.config_error_detail = None
        sensor = existing
        logger.info(
            f"Sensor updated: {esp_id} GPIO {gpio} by {current_user.username} (config_status=pending)"
        )
    else:
        # Create new sensor (config_status defaults to "pending" in model)
        sensor = SensorConfig(
            esp_id=esp_device.id,
            gpio=gpio,
            **model_fields,
        )
        await sensor_repo.create(sensor)
        logger.info(
            f"Sensor created: {esp_id} GPIO {gpio} by {current_user.username} (config_status=pending)"
        )

    # =========================================================================
    # AUDIT TRAIL for scope/zones changes (T13-R2 H2)
    # =========================================================================
    scope_changed = False
    zones_changed = False
    if existing and old_scope is not None:
        if request.device_scope is not None and request.device_scope != old_scope:
            from ...db.models.device_zone_change import DeviceZoneChange

            db.add(
                DeviceZoneChange(
                    esp_id=f"sensor:{sensor.id}",
                    old_zone_id=old_scope,
                    new_zone_id=request.device_scope,
                    subzone_strategy="scope",
                    change_type="scope_change",
                    changed_by=current_user.username,
                )
            )
            scope_changed = True
        if request.assigned_zones is not None and sorted(request.assigned_zones) != sorted(
            old_zones or []
        ):
            from ...db.models.device_zone_change import DeviceZoneChange

            db.add(
                DeviceZoneChange(
                    esp_id=f"sensor:{sensor.id}",
                    old_zone_id=",".join(old_zones or []),
                    new_zone_id=",".join(request.assigned_zones),
                    subzone_strategy="zones",
                    change_type="zones_update",
                    changed_by=current_user.username,
                )
            )
            zones_changed = True

    await db.commit()
    await db.refresh(sensor)

    # =========================================================================
    # WS BROADCAST device_scope_changed (T13-R2 H1)
    # =========================================================================
    if scope_changed or zones_changed:
        try:
            from ...websocket.manager import WebSocketManager

            ws_manager = await WebSocketManager.get_instance()
            await ws_manager.broadcast(
                "device_scope_changed",
                {
                    "config_type": "sensor",
                    "config_id": str(sensor.id),
                    "device_scope": sensor.device_scope,
                    "assigned_zones": sensor.assigned_zones or [],
                },
            )
        except Exception as e:
            logger.warning(f"Failed to broadcast device_scope_changed: {e}")

    # =========================================================================
    # SCHEDULE JOB UPDATE (Phase 2H)
    # Update APScheduler job based on operating_mode and schedule_config
    # =========================================================================
    try:
        scheduler_service: SensorSchedulerService = get_sensor_scheduler_service(db)

        if sensor.operating_mode == "scheduled" and sensor.schedule_config:
            # Create or update scheduled job
            job_success = await scheduler_service.create_or_update_job(
                esp_id=esp_id,
                gpio=gpio,
                schedule_config=sensor.schedule_config,
            )
            if job_success:
                logger.info(f"Scheduled job created/updated for {esp_id}/GPIO {gpio}")
            else:
                logger.warning(f"Failed to create scheduled job for {esp_id}/GPIO {gpio}")
        else:
            # Remove job if mode is not scheduled (or schedule_config is None)
            await scheduler_service.remove_job(esp_id, gpio)
    except Exception as e:
        # Non-fatal: DB save was successful, job can be recovered on server restart
        logger.warning(f"Schedule job update failed for {esp_id}/GPIO {gpio}: {e}")

    # =========================================================================
    # SUBZONE ASSIGNMENT (Phase 1.2)
    # Assign sensor GPIO to subzone or remove from all subzones
    # Block D2: Normalize "__none__" and "" to None (defensive)
    # subzone_error: set when assignment fails — passed to response as warning.
    # Config-Push MUST always run after the primary DB commit regardless.
    # =========================================================================
    subzone_error: Optional[str] = None
    try:
        subzone_service = SubzoneService(esp_repo=esp_repo, session=db, publisher=publisher)
        subzone_id_val = normalize_subzone_id(request.subzone_id)
        if subzone_id_val:
            await subzone_service.assign_subzone(
                device_id=esp_id,
                subzone_id=subzone_id_val,
                assigned_gpios=[gpio],
                subzone_name=None,
                parent_zone_id=esp_device.zone_id,
                safe_mode_active=True,
            )
            await db.commit()
        else:
            await subzone_service.remove_gpio_from_all_subzones(esp_id, gpio)
            await db.commit()
    except ValueError as e:
        # Subzone validation failed (e.g. subzone not found, zone mismatch)
        logger.warning(f"Subzone assignment skipped for {esp_id}/GPIO {gpio}: {e}")
        await db.rollback()
        subzone_error = str(e)
    except SQLAlchemyError as e:
        # AUT-228 (E2): Erwartete DB-Fehler -> WARNING, non-fatal
        logger.warning(f"Subzone assignment DB error for {esp_id}/GPIO {gpio}: {e}")
        await db.rollback()
        subzone_error = "subzone_db_error"
    except Exception as e:
        # AUT-228 (E2): Unerwartete Exceptions -> ERROR + Stacktrace,
        # damit Drift in der Subzone-Logik nicht stillschweigend untergeht.
        logger.error(
            f"Unexpected subzone assignment failure for {esp_id}/GPIO {gpio}: {e}",
            exc_info=True,
        )
        await db.rollback()
        subzone_error = "subzone_unexpected_error"
        # Non-fatal: sensor was saved, subzone can be fixed manually

    # Publish config to ESP32 via MQTT (using dependency-injected services)
    mqtt_correlation_id: Optional[str] = None
    try:
        esp_service: ESPService = get_esp_service(db)
        schedule_result = await esp_service.trigger_config_push_debounced(
            esp_id,
            reason_code="sensor_config_change",
        )
        mqtt_correlation_id = schedule_result.get("correlation_id")
        logger.info("Config push coalesced for ESP %s after sensor create/update", esp_id)
    except ConfigConflictError as e:
        logger.error(f"Failed to publish config to ESP {esp_id}: {e}", exc_info=True)
        raise HTTPException(status_code=409, detail=f"GPIO-Konflikt: {e}")
    except Exception as e:
        # Log error but don't fail the request (DB save was successful)
        logger.error(f"Failed to publish config to ESP {esp_id}: {e}", exc_info=True)

    # Resolve subzone_id for response
    subzone_repo = SubzoneRepository(db)
    subzone = await subzone_repo.get_subzone_by_gpio(esp_id, gpio)
    subzone_id_val = subzone.subzone_id if subzone else None

    # Convert model to response schema
    return _model_to_response(
        sensor,
        esp_id,
        subzone_id=subzone_id_val,
        subzone_warning=subzone_error,
        correlation_id=mqtt_correlation_id,
    )


# =============================================================================
# Delete Sensor
# =============================================================================


@router.delete(
    "/{esp_id}/{config_id}",
    response_model=SensorConfigResponse,
    responses={
        200: {"description": "Sensor deleted"},
        404: {"description": "Sensor not found"},
    },
    summary="Delete sensor configuration by config ID",
    description="Remove sensor configuration by sensor_config_id. Sensor data (historical readings) is preserved.",
)
async def delete_sensor(
    esp_id: str,
    config_id: uuid.UUID,
    db: DBSession,
    current_user: OperatorUser,
) -> SensorConfigResponse:
    """
    Delete sensor configuration by sensor_config_id (T08-Fix-D).

    Uses DB primary key instead of GPIO to avoid MultipleResultsFound
    when multiple sensors share the same GPIO (SHT31, multiple DS18B20s).

    Pipeline: DB delete → rebuild_simulation_config → scheduler stop → WS event.
    sensor_data rows are intentionally preserved (historical data).

    Args:
        esp_id: ESP device ID (e.g., ESP_MOCK_E92BAA)
        config_id: SensorConfig UUID primary key
        db: Database session
        current_user: Operator or admin user

    Returns:
        Deleted sensor config
    """
    esp_repo = ESPRepository(db)
    sensor_repo = SensorRepository(db)

    esp_device = await esp_repo.get_by_device_id(esp_id)
    if not esp_device:
        raise ESPNotFoundError(esp_id)

    # Lookup by primary key — always unique, no MultipleResultsFound
    sensor = await sensor_repo.get_by_id(config_id)
    if not sensor or sensor.esp_id != esp_device.id:
        raise SensorNotFoundException(esp_id, config_id)

    gpio = sensor.gpio if sensor.gpio is not None else 0

    # Save a detached response snapshot and tombstone fields before delete.
    # This avoids relying on deleted ORM state after commit.
    deleted_sensor_response = _model_to_response(sensor, esp_id)
    deleted_sensor_type = sensor.sensor_type
    deleted_sensor_name = sensor.sensor_name
    deleted_onewire_address = sensor.onewire_address or ""
    deleted_i2c_address = sensor.i2c_address or 0

    # 1. Delete sensor config (sensor_data rows are NOT cascade-deleted)
    await sensor_repo.delete(sensor.id)

    # 2. Check if other sensors remain on the same GPIO (multi-value support)
    #    SHT31 temp+humidity share GPIO, multiple DS18B20 share OneWire bus pin.
    #    Only clean up GPIO-level resources if NO sensors remain on this GPIO.
    remaining_on_gpio = await sensor_repo.get_all_by_esp_and_gpio(esp_device.id, gpio)

    # 3. Subzone cleanup: remove GPIO from subzones ONLY if no sensors remain
    if not remaining_on_gpio:
        try:
            subzone_service = SubzoneService(
                esp_repo=esp_repo, session=db, publisher=get_mqtt_publisher()
            )
            await subzone_service.remove_gpio_from_all_subzones(esp_id, gpio)
        except Exception as e:
            logger.debug(f"Subzone cleanup for deleted sensor: {e}")

    # 4. Rebuild simulation_config (removes deleted sensor from mock cache)
    try:
        remaining_cfgs = await sensor_repo.get_by_esp(esp_device.id)
        await esp_repo.rebuild_simulation_config(esp_device, remaining_cfgs)
    except Exception as e:
        logger.debug(f"Simulation config rebuild after sensor delete: {e}")

    await db.commit()

    # R20-P5 + T13-R1: Sync assigned_sensor_config_ids and counts after sensor delete
    try:
        _subzone_svc = SubzoneService(esp_repo=esp_repo, session=db, publisher=get_mqtt_publisher())
        await _subzone_svc.sync_assigned_config_ids(esp_id)
        _subzone_repo = SubzoneRepository(db)
        await _subzone_repo.sync_subzone_counts(esp_id, esp_device.id)
        await db.commit()
    except Exception:
        logger.debug("Subzone sync skipped for %s", esp_id)

    logger.info(
        f"Sensor deleted: {esp_id} config_id={config_id} GPIO {gpio} "
        f"type={deleted_sensor_type} by {current_user.username}"
    )

    # 5. Remove APScheduler job ONLY if no sensors remain on this GPIO
    #    Job ID is per-GPIO (esp_id + gpio), so removing it would stop
    #    scheduled measurements for ALL sensors on the same GPIO.
    if not remaining_on_gpio:
        try:
            scheduler_service: SensorSchedulerService = get_sensor_scheduler_service(db)
            await scheduler_service.remove_job(esp_id, gpio)
        except Exception as e:
            logger.debug(f"Schedule job removal for deleted sensor: {e}")

    # 6. Stop simulation sensor job for mock devices (targeted by sensor_type)
    if esp_device.hardware_type == "MOCK_ESP32":
        try:
            from ..deps import get_simulation_scheduler

            sim_scheduler = get_simulation_scheduler()
            sim_scheduler.remove_sensor_job(esp_id, gpio, deleted_sensor_type)
        except Exception as e:
            logger.debug(f"Simulation job removal for deleted sensor: {e}")

    # 7. Publish updated config to ESP32 via MQTT.
    #    A tombstone entry (active=False) is appended so the ESP removes the
    #    deleted sensor from NVS via its active=False removal path.
    mqtt_correlation_id: Optional[str] = None
    try:
        tombstone: dict = {
            "gpio": gpio,
            "sensor_type": deleted_sensor_type,
            "sensor_name": deleted_sensor_name,
            "active": False,
            "onewire_address": deleted_onewire_address,
            "i2c_address": deleted_i2c_address,
        }
        esp_service: ESPService = get_esp_service(db)
        schedule_result = await esp_service.trigger_config_push_debounced(
            esp_id,
            reason_code="sensor_config_change",
            extra_sensor_entries=[tombstone],
        )
        mqtt_correlation_id = schedule_result.get("correlation_id")
        logger.info("Config push coalesced for ESP %s after sensor delete", esp_id)
    except Exception as e:
        logger.error(f"Failed to publish config to ESP {esp_id}: {e}", exc_info=True)

    # 8. WebSocket event: Frontend removes ghost sensor from store
    try:
        from ...websocket.manager import WebSocketManager

        ws_manager = await WebSocketManager.get_instance()
        await ws_manager.broadcast(
            "sensor_config_deleted",
            {
                "config_id": str(config_id),
                "esp_id": esp_id,
                "gpio": gpio,
                "sensor_type": deleted_sensor_type,
            },
        )
    except Exception as e:
        logger.debug(f"WebSocket broadcast for sensor_config_deleted: {e}")

    # Convert model to response schema (correlation_id = last MQTT config push, like create/update)
    deleted_sensor_response.correlation_id = mqtt_correlation_id
    return deleted_sensor_response


# =============================================================================
# Query Sensor Data
# =============================================================================


def _aggregated_row_to_reading(row: Any) -> Optional[SensorReading]:
    """Map an aggregated query row to SensorReading.

    AUT-723 E3: do not coerce missing avg_raw to 0.0. Skip the bucket when
    both avg_raw and avg_processed are None (no numeric chart Y).
    """
    raw_value = float(row.avg_raw) if row.avg_raw is not None else None
    processed_value = float(row.avg_processed) if row.avg_processed is not None else None
    if raw_value is None and processed_value is None:
        return None
    return SensorReading(
        timestamp=row.bucket,
        raw_value=raw_value,
        processed_value=processed_value,
        unit=row.unit,
        quality="aggregated",
        sensor_type=row.sensor_type,
        min_value=float(row.min_val) if row.min_val is not None else None,
        max_value=float(row.max_val) if row.max_val is not None else None,
        sample_count=int(row.sample_count),
    )


def _raw_row_to_reading(row: Any) -> Optional[SensorReading]:
    """Map a raw SensorData row to SensorReading.

    AUT-723 E3: warming_up is quality-only — never a numeric chart Y.
    """
    if row.quality == "warming_up":
        return None
    return SensorReading(
        timestamp=row.timestamp,
        raw_value=row.raw_value,
        processed_value=row.processed_value,
        unit=row.unit,
        quality=row.quality,
        sensor_type=row.sensor_type,
        zone_id=row.zone_id,
        subzone_id=row.subzone_id,
    )


@router.get(
    "/data",
    response_model=SensorDataResponse,
    summary="Query sensor data",
    description="Query historical sensor data with filters.",
)
async def query_sensor_data(
    db: DBSession,
    current_user: ActiveUser,
    esp_id: Annotated[Optional[str], Query(description="Filter by ESP device ID")] = None,
    gpio: Annotated[Optional[int], Query(ge=0, le=39, description="Filter by GPIO")] = None,
    sensor_type: Annotated[Optional[str], Query(description="Filter by sensor type")] = None,
    start_time: Annotated[Optional[datetime], Query(description="Start of time range")] = None,
    end_time: Annotated[Optional[datetime], Query(description="End of time range")] = None,
    quality: Annotated[Optional[str], Query(description="Filter by quality")] = None,
    zone_id: Annotated[Optional[str], Query(description="Filter by zone ID (Phase 0.1)")] = None,
    subzone_id: Annotated[
        Optional[str], Query(description="Filter by subzone ID (Phase 0.1)")
    ] = None,
    sensor_config_id: Annotated[
        Optional[str], Query(description="Filter by sensor_config UUID (T13-R2)")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=1000, description="Max results")] = 100,
    resolution: Annotated[
        Optional[str],
        Query(
            pattern=r"^(raw|1m|5m|1h|1d)$",
            description="Time resolution: raw (default), 1m, 5m, 1h, 1d",
        ),
    ] = None,
    before_timestamp: Annotated[
        Optional[datetime],
        Query(description="Cursor: only return data before this timestamp"),
    ] = None,
) -> SensorDataResponse:
    """
    Query sensor data with optional time aggregation and cursor pagination.

    Args:
        db: Database session
        current_user: Authenticated user
        esp_id: Optional ESP filter
        gpio: Optional GPIO filter
        sensor_type: Optional type filter
        start_time: Start of time range
        end_time: End of time range
        quality: Filter by quality
        limit: Max results (applies to raw; aggregated has generous cap)
        resolution: Time aggregation (raw, 1m, 5m, 1h, 1d)
        before_timestamp: Cursor for pagination — only data before this timestamp

    Returns:
        Sensor data readings (raw or aggregated)
    """
    esp_repo = ESPRepository(db)
    sensor_repo = SensorRepository(db)

    # Default time range to last 24 hours (timezone-aware UTC for TIMESTAMPTZ)
    if not start_time:
        start_time = datetime.now(timezone.utc) - timedelta(hours=24)
    elif start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
    if not end_time:
        end_time = datetime.now(timezone.utc)
    elif end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=timezone.utc)

    # Ensure before_timestamp is timezone-aware
    if before_timestamp and before_timestamp.tzinfo is None:
        before_timestamp = before_timestamp.replace(tzinfo=timezone.utc)

    # Get ESP device ID if specified.
    # include_deleted: historical rows remain after soft-delete; deep-links must not 404.
    esp_db_id = None
    if esp_id:
        esp_device = await esp_repo.get_by_device_id(esp_id, include_deleted=True)
        if not esp_device:
            raise ESPNotFoundError(esp_id)
        esp_db_id = esp_device.id

    # Resolve sensor_config_id to get esp_id/gpio/sensor_type if needed (T13-R2)
    resolved_config_id = None
    if sensor_config_id:
        import uuid as _uuid

        try:
            resolved_config_id = _uuid.UUID(sensor_config_id)
        except ValueError as exc:
            # AUT-228 (E3): Strukturierte Exception statt HTTPException -> numeric_code 5209
            raise SensorConfigInvalidUuidError(sensor_config_id) from exc

    # Effective resolution (default = raw)
    effective_resolution = resolution or "raw"
    is_aggregated = effective_resolution != "raw"

    # Query data
    readings = await sensor_repo.query_data(
        esp_id=esp_db_id,
        gpio=gpio,
        sensor_type=sensor_type,
        start_time=start_time,
        end_time=end_time,
        quality=quality,
        zone_id=zone_id,
        subzone_id=subzone_id,
        sensor_config_id=resolved_config_id,
        limit=limit,
        resolution=effective_resolution,
        before_timestamp=before_timestamp,
    )

    # Convert to response format (skip rows without a chartable Y — AUT-723 E3)
    if is_aggregated:
        # Aggregated rows: (bucket, avg_raw, avg_processed, min_val, max_val, sample_count, sensor_type, unit)
        reading_responses = [
            reading
            for reading in (_aggregated_row_to_reading(r) for r in readings)
            if reading is not None
        ]
    else:
        reading_responses = [
            reading
            for reading in (_raw_row_to_reading(r) for r in readings)
            if reading is not None
        ]

    # Cursor pagination metadata
    has_more = len(reading_responses) == limit
    next_cursor = None
    if has_more and reading_responses:
        next_cursor = reading_responses[-1].timestamp.isoformat()

    response = SensorDataResponse(
        success=True,
        esp_id=esp_id,
        gpio=gpio,
        sensor_type=sensor_type,
        readings=reading_responses,
        count=len(reading_responses),
        resolution=effective_resolution,
        time_range={"start": start_time, "end": end_time},
    )

    # Add pagination metadata to response dict
    # (Using model_extra or direct attribute would need schema change;
    #  for now we include it via the time_range dict as a pragmatic approach)
    if next_cursor:
        response.time_range["next_cursor"] = next_cursor
        response.time_range["has_more"] = True
    else:
        response.time_range["has_more"] = False

    return response


# =============================================================================
# Query Sensor Data by Source
# =============================================================================


@router.get(
    "/data/by-source/{source}",
    response_model=SensorDataResponse,
    summary="Query sensor data by source",
    description="Query sensor data filtered by data source (production, mock, test, simulation).",
)
async def get_sensor_data_by_source(
    source: str,
    db: DBSession,
    current_user: ActiveUser,
    esp_id: Annotated[Optional[str], Query(description="Filter by ESP device ID")] = None,
    limit: Annotated[int, Query(ge=1, le=1000, description="Max results")] = 100,
) -> SensorDataResponse:
    """
    Query sensor data filtered by data source.

    Args:
        source: Data source (production, mock, test, simulation)
        db: Database session
        current_user: Authenticated user
        esp_id: Optional ESP filter
        limit: Max results

    Returns:
        Sensor data readings from specified source
    """
    # Validate source
    try:
        data_source = DataSource(source.lower())
    except ValueError:
        valid_sources = [e.value for e in DataSource]
        raise ValidationException(
            "source",
            f"Invalid source '{source}'. Valid sources: {valid_sources}",
        )

    esp_repo = ESPRepository(db)
    sensor_repo = SensorRepository(db)

    # Get ESP device ID if specified (history may reference soft-deleted ESPs)
    esp_db_id = None
    if esp_id:
        esp_device = await esp_repo.get_by_device_id(esp_id, include_deleted=True)
        if not esp_device:
            raise ESPNotFoundError(esp_id)
        esp_db_id = esp_device.id

    # Query data by source
    readings = await sensor_repo.get_by_source(
        source=data_source,
        limit=limit,
        esp_id=esp_db_id,
    )

    # Convert to response format (skip warming_up — AUT-723 E3)
    reading_responses = [
        reading
        for reading in (_raw_row_to_reading(r) for r in readings)
        if reading is not None
    ]

    return SensorDataResponse(
        success=True,
        esp_id=esp_id,
        gpio=None,
        sensor_type=None,
        readings=reading_responses,
        count=len(reading_responses),
        aggregation=None,
        time_range=None,
    )


@router.get(
    "/data/stats/by-source",
    summary="Get sensor data count by source",
    description="Get count of sensor data entries grouped by data source.",
)
async def get_sensor_data_stats_by_source(
    db: DBSession,
    current_user: ActiveUser,
) -> dict:
    """
    Get sensor data count by data source.

    Returns count of sensor data entries for each source type.
    """
    sensor_repo = SensorRepository(db)
    counts = await sensor_repo.count_by_source()

    return {
        "success": True,
        "counts": counts,
        "total": sum(counts.values()),
    }


# =============================================================================
# Sensor Statistics
# =============================================================================


@router.get(
    "/{esp_id}/{gpio}/stats",
    response_model=SensorStatsResponse,
    summary="Get sensor statistics",
    description="Get statistical summary for sensor data.",
)
async def get_sensor_stats(
    esp_id: str,
    gpio: int,
    db: DBSession,
    current_user: ActiveUser,
    start_time: Annotated[Optional[datetime], Query(description="Start of time range")] = None,
    end_time: Annotated[Optional[datetime], Query(description="End of time range")] = None,
    sensor_type: Annotated[
        Optional[str], Query(description="Sensor type filter for multi-value sensors")
    ] = None,
) -> SensorStatsResponse:
    """
    Get sensor statistics.

    Args:
        esp_id: ESP device ID
        gpio: GPIO pin number
        db: Database session
        current_user: Authenticated user
        start_time: Start of time range
        end_time: End of time range
        sensor_type: Optional sensor type filter (e.g. sht31_temp, sht31_humidity)

    Returns:
        Statistical summary
    """
    esp_repo = ESPRepository(db)
    sensor_repo = SensorRepository(db)

    esp_device = await esp_repo.get_by_device_id(esp_id)
    if not esp_device:
        raise ESPNotFoundError(esp_id)

    # Use type-specific lookup when sensor_type is provided
    if sensor_type:
        sensor = await sensor_repo.get_by_esp_gpio_and_type(esp_device.id, gpio, sensor_type)
    else:
        configs = await sensor_repo.get_all_by_esp_and_gpio(esp_device.id, gpio)
        if len(configs) > 1:
            logger.warning(
                "get_sensor_stats without sensor_type for multi-value GPIO: "
                "esp=%s gpio=%s (%d configs). Using first. "
                "Pass ?sensor_type= for accurate stats.",
                esp_id,
                gpio,
                len(configs),
            )
        sensor = configs[0] if configs else None
    if not sensor:
        raise SensorNotFoundException(esp_id, gpio)

    # Default time range (timezone-aware UTC for TIMESTAMPTZ)
    if not start_time:
        start_time = datetime.now(timezone.utc) - timedelta(hours=24)
    elif start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
    if not end_time:
        end_time = datetime.now(timezone.utc)
    elif end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=timezone.utc)

    # Get statistics filtered by sensor_type for multi-value sensors
    stats = await sensor_repo.get_stats(
        esp_id=esp_device.id,
        gpio=gpio,
        start_time=start_time,
        end_time=end_time,
        sensor_type=sensor.sensor_type,
    )

    return SensorStatsResponse(
        success=True,
        esp_id=esp_id,
        gpio=gpio,
        sensor_type=sensor.sensor_type,
        stats=SensorStats(
            min_value=stats.get("min_value"),
            max_value=stats.get("max_value"),
            avg_value=stats.get("avg_value"),
            std_dev=stats.get("std_dev"),
            reading_count=stats.get("reading_count", 0),
            quality_distribution=stats.get("quality_distribution", {}),
        ),
        time_range={"start": start_time, "end": end_time},
    )


# =============================================================================
# On-Demand Measurement (Phase 2D)
# =============================================================================


@router.post(
    "/{esp_id}/{gpio}/measure",
    response_model=TriggerMeasurementResponse,
    summary="Trigger manual measurement",
    description="Triggers a manual measurement for an on-demand sensor.",
    responses={
        200: {"description": "Measurement command sent successfully"},
        404: {"description": "ESP or sensor not found"},
        429: {"description": "Measurement already in progress for this sensor"},
        503: {"description": "ESP offline or MQTT failure"},
    },
)
async def trigger_measurement(
    esp_id: str,
    gpio: int,
    db: DBSession,
    current_user: OperatorUser,
    sensor_service: Annotated[SensorService, Depends(get_sensor_service)],
    body: TriggerMeasurementRequest | None = None,
) -> TriggerMeasurementResponse:
    """
    Trigger a manual measurement for a sensor.

    Used primarily for sensors with operating_mode='on_demand'.
    Can also be used to force a measurement on any sensor.

    Returns HTTP 429 if a measurement is already in progress for this
    sensor (busy-guard against rapid-fire MQTT bursts, AUT-302).

    Requires Operator role or higher.

    Args:
        esp_id: ESP device ID
        gpio: Sensor GPIO pin

    Returns:
        TriggerMeasurementResponse with request tracking info
    """
    try:
        measure_opts = body or TriggerMeasurementRequest()
        result = await sensor_service.trigger_measurement(
            esp_id=esp_id,
            gpio=gpio,
            sensor_type=measure_opts.sensor_type,
            sample_count=measure_opts.sample_count,
            sample_delay_ms=measure_opts.sample_delay_ms,
            timeout_ms=measure_opts.timeout_ms,
        )
        return TriggerMeasurementResponse(**result)

    except MeasurementBusyError:
        # Measurement already in progress — re-raise directly (handled by global handler)
        raise

    except ValueError as e:
        # ESP or sensor not found, or sensor disabled
        raise SensorNotFoundException(esp_id, gpio) from e

    except RuntimeError as e:
        # ESP offline or MQTT failure
        raise ServiceUnavailableError("ESP32", str(e)) from e


# =============================================================================
# OneWire Scan (DS18B20 Support)
# =============================================================================


@router.post(
    "/esp/{esp_id}/onewire/scan",
    response_model=OneWireScanResponse,
    summary="Scan OneWire bus for devices",
    description="""
    Triggers OneWire bus scan on ESP32 device.
    
    **Flow:**
    1. Server sends MQTT command to ESP
    2. ESP scans OneWire bus (finds all connected DS18B20, etc.)
    3. ESP publishes scan results
    4. Server returns found devices
    
    **Timeout:** 10 seconds
    
    **Use-Case:** Discovery of DS18B20 temperature sensors before configuration.
    """,
    responses={
        200: {"description": "Scan completed successfully"},
        404: {"description": "ESP device not found"},
        503: {"description": "ESP device offline"},
        504: {"description": "ESP did not respond to scan command (timeout)"},
    },
)
async def scan_onewire_bus(
    esp_id: str,
    db: DBSession,
    current_user: OperatorUser,
    publisher: MQTTPublisher,
    pin: Annotated[int, Query(ge=0, le=48, description="GPIO pin for OneWire bus")] = 4,
) -> OneWireScanResponse:
    """
    Scan OneWire bus for connected devices.

    Sends MQTT command to ESP32 and waits for scan result.
    Returns list of discovered devices with ROM codes and types.

    **Pattern:** MQTT Command-Response with async timeout
    **Referenz:** ESP32 main.cpp:692-790 (onewire/scan command)

    Args:
        esp_id: ESP device ID (e.g., "ESP_12AB34CD")
        pin: GPIO pin for OneWire bus (default: 4)

    Returns:
        OneWireScanResponse with list of found devices
    """
    import asyncio
    import time

    from ...mqtt.client import MQTTClient
    from ...schemas.sensor import OneWireDevice, OneWireScanResponse

    start_time = time.time()

    logger.info(f"OneWire scan requested: esp_id={esp_id}, pin={pin}")

    # Step 1: Lookup ESP device
    esp_repo = ESPRepository(db)
    esp_device = await esp_repo.get_by_device_id(esp_id)

    if not esp_device:
        raise ESPNotFoundError(esp_id)

    # =========================================================================
    # MOCK-ESP DETECTION: Return fake devices without MQTT
    # =========================================================================
    # Mock-ESPs (device_id starts with "MOCK_") have no real hardware,
    # so we return fake DS18B20 devices for testing the Frontend workflow.
    # =========================================================================
    if esp_id.startswith("MOCK_"):
        scan_duration_ms = int((time.time() - start_time) * 1000)

        # =====================================================================
        # OneWire Multi-Device Support: Query existing sensors for enrichment
        # =====================================================================
        sensor_repo = SensorRepository(db)
        existing_sensors = await sensor_repo.get_all_by_esp_and_gpio(esp_device.id, pin)

        # Filter to only OneWire sensors (ds18b20) and build ROM -> name mapping
        existing_rom_map: dict[str, str] = {}
        for sensor in existing_sensors:
            if sensor.interface_type == "ONEWIRE" and sensor.onewire_address:
                existing_rom_map[sensor.onewire_address] = sensor.sensor_name or "Unbenannt"

        # Generate fake OneWire devices for testing
        fake_rom_codes = [
            "28FF641E8D3C0C79",
            "28FF123456789ABC",
            "28FF987654321DEF",  # Third device for testing multi-add
        ]

        fake_devices = []
        new_count = 0
        for rom_code in fake_rom_codes:
            already_configured = rom_code in existing_rom_map
            if not already_configured:
                new_count += 1

            fake_devices.append(
                OneWireDevice(
                    rom_code=rom_code,
                    device_type="ds18b20",
                    pin=pin,
                    already_configured=already_configured,
                    sensor_name=existing_rom_map.get(rom_code),
                )
            )

        logger.info(
            f"Mock OneWire scan: {esp_id}, GPIO {pin} - "
            f"returning {len(fake_devices)} fake devices ({new_count} new)"
        )

        return OneWireScanResponse(
            success=True,
            message=f"Mock scan: Found {len(fake_devices)} DS18B20 devices ({new_count} new)",
            devices=fake_devices,
            found_count=len(fake_devices),
            new_count=new_count,
            pin=pin,
            esp_id=esp_id,
            scan_duration_ms=scan_duration_ms,
        )
    # =========================================================================

    if esp_device.status != "online":
        raise ServiceUnavailableError(
            "ESP32",
            f"ESP device {esp_id} is {esp_device.status}, must be online for OneWire scan",
        )

    # Step 2: Prepare MQTT command (publisher injected via Depends)

    # Command topic: kaiser/god/esp/{esp_id}/system/command
    # Payload: {"command": "onewire/scan", "pin": 4}
    # Response topic: kaiser/god/esp/{esp_id}/onewire/scan_result
    response_topic = TopicBuilder.build_onewire_scan_result_topic(esp_id)

    # Step 3: Setup response listener with asyncio.Future
    # IMPORTANT: Capture event loop in async context BEFORE callback registration
    # asyncio.get_event_loop() is deprecated; use get_running_loop() in async context
    loop = asyncio.get_running_loop()
    response_future: asyncio.Future = loop.create_future()

    def on_scan_result(client, userdata, message):
        """Callback for scan result message (runs in paho-mqtt thread)."""
        import json

        try:
            payload = json.loads(message.payload.decode("utf-8"))
            if not response_future.done():
                # Thread-safe: Use captured loop reference
                loop.call_soon_threadsafe(response_future.set_result, payload)
        except Exception as e:
            logger.error(f"Failed to parse OneWire scan result: {e}")
            if not response_future.done():
                loop.call_soon_threadsafe(response_future.set_exception, e)

    # Get MQTT client and register callback
    mqtt_client = MQTTClient.get_instance()

    # Check if MQTT client is connected
    if not mqtt_client.is_connected() or mqtt_client.client is None:
        logger.error(f"OneWire scan failed: MQTT client not connected")
        raise ServiceUnavailableError(
            "MQTT",
            "MQTT broker not connected. Cannot send scan command to ESP.",
        )

    # Subscribe to response topic
    mqtt_client.client.subscribe(response_topic, qos=1)
    mqtt_client.client.message_callback_add(response_topic, on_scan_result)

    try:
        # Step 4: Publish command
        success = publisher.publish_system_command(
            esp_id=esp_id, command="onewire/scan", params={"pin": pin}, retry=True
        )

        if not success:
            raise ServiceUnavailableError(
                "MQTT",
                "Failed to send OneWire scan command to ESP. Check MQTT connection.",
            )

        logger.debug(f"OneWire scan command sent to {esp_id}, waiting for response...")

        # Step 5: Wait for response with timeout (10 seconds)
        try:
            result = await asyncio.wait_for(response_future, timeout=10.0)
        except asyncio.TimeoutError:
            logger.error(f"OneWire scan timeout: ESP {esp_id} did not respond within 10 seconds")
            raise GatewayTimeoutError(
                message=f"ESP {esp_id} did not respond to OneWire scan command within 10 seconds. "
                f"Ensure ESP is online and OneWire bus is configured on GPIO {pin}.",
                details={"esp_id": esp_id, "pin": pin, "timeout_seconds": 10},
            )

        # Step 6: Parse response and build device list with enrichment
        # =====================================================================
        # OneWire Multi-Device Support: Query existing sensors for enrichment
        # =====================================================================
        sensor_repo = SensorRepository(db)
        existing_sensors = await sensor_repo.get_all_by_esp_and_gpio(esp_device.id, pin)

        # Filter to only OneWire sensors and build ROM -> name mapping
        existing_rom_map: dict[str, str] = {}
        for sensor in existing_sensors:
            if sensor.interface_type == "ONEWIRE" and sensor.onewire_address:
                existing_rom_map[sensor.onewire_address] = sensor.sensor_name or "Unbenannt"

        logger.debug(
            f"OneWire enrichment: Found {len(existing_rom_map)} already configured "
            f"sensors on ESP {esp_id}, GPIO {pin}"
        )

        # Parse and enrich scan results
        devices = []
        new_count = 0
        for device_data in result.get("devices", []):
            try:
                rom_code = device_data.get("rom_code", "")
                already_configured = rom_code in existing_rom_map

                if not already_configured:
                    new_count += 1

                device = OneWireDevice(
                    rom_code=rom_code,
                    device_type=device_data.get("device_type", "unknown"),
                    pin=device_data.get("pin", pin),
                    already_configured=already_configured,
                    sensor_name=existing_rom_map.get(rom_code),
                )
                devices.append(device)
            except Exception as e:
                logger.warning(f"Failed to parse OneWire device: {e}")

        found_count = len(devices)
        scan_duration_ms = int((time.time() - start_time) * 1000)

        logger.info(
            f"OneWire scan complete: {found_count} device(s) found on ESP {esp_id}, "
            f"GPIO {pin} ({new_count} new) in {scan_duration_ms}ms"
        )

        return OneWireScanResponse(
            success=True,
            message=f"Found {found_count} OneWire device(s) on GPIO {pin} ({new_count} new)",
            devices=devices,
            found_count=found_count,
            new_count=new_count,
            pin=pin,
            esp_id=esp_id,
            scan_duration_ms=scan_duration_ms,
        )

    finally:
        # Step 7: Cleanup - unregister callback and unsubscribe
        try:
            if mqtt_client.client:
                mqtt_client.client.message_callback_remove(response_topic)
                mqtt_client.client.unsubscribe(response_topic)
        except Exception as e:
            logger.warning(f"Failed to cleanup MQTT subscription: {e}")


@router.get(
    "/esp/{esp_id}/onewire",
    response_model=SensorConfigListResponse,
    summary="List OneWire sensors on ESP",
    description="Get all configured OneWire sensors for an ESP device.",
)
async def list_onewire_sensors(
    esp_id: str,
    db: DBSession,
    current_user: ActiveUser,
    pin: Annotated[Optional[int], Query(ge=0, le=48, description="Filter by GPIO pin")] = None,
) -> SensorConfigListResponse:
    """
    List all OneWire sensors configured on an ESP device.

    Optionally filter by GPIO pin to see all sensors on a specific OneWire bus.

    Args:
        esp_id: ESP device ID
        pin: Optional GPIO pin filter

    Returns:
        List of configured OneWire sensors
    """
    esp_repo = ESPRepository(db)
    sensor_repo = SensorRepository(db)

    esp_device = await esp_repo.get_by_device_id(esp_id)
    if not esp_device:
        raise ESPNotFoundError(esp_id)

    # Get all OneWire sensors for this ESP
    onewire_sensors = await sensor_repo.get_all_by_interface(esp_device.id, "ONEWIRE")

    # Filter by pin if specified
    if pin is not None:
        onewire_sensors = [s for s in onewire_sensors if s.gpio == pin]

    subzone_repo = SubzoneRepository(db)
    # Convert to response format
    responses = []
    for sensor in onewire_sensors:
        # Pass sensor_type for correct multi-value sensor latest reading
        latest = await sensor_repo.get_latest_reading(
            sensor.esp_id, sensor.gpio, sensor_type=sensor.sensor_type
        )
        subzone = await subzone_repo.get_subzone_by_gpio(esp_id, sensor.gpio)
        subzone_id_val = subzone.subzone_id if subzone else None
        response = _model_to_response(sensor, esp_id, subzone_id=subzone_id_val)
        response.latest_value = (
            (latest.processed_value if latest.processed_value is not None else latest.raw_value)
            if latest
            else None
        )
        response.latest_quality = latest.quality if latest else None
        response.latest_timestamp = latest.timestamp if latest else None
        responses.append(response)

    return SensorConfigListResponse(
        success=True,
        data=responses,
        pagination=PaginationMeta.from_pagination(1, len(responses), len(responses)),
    )


# =============================================================================
# Helper Functions for Multi-Value Sensor Support
# =============================================================================


def _infer_interface_type(sensor_type: str) -> str:
    """
    Infer interface_type from sensor_type naming convention.

    Rules:
    - sht31*, bmp280*, bme280*, bh1750*, veml7700* → I2C
    - ds18b20* → ONEWIRE
    - co2, mhz19*, sen0220* → UART
    - flow, yfs201, liquid_level → DIGITAL (pulse / reed-switch sensors)
    - Everything else → ANALOG (default)

    Args:
        sensor_type: Sensor type string (e.g., 'sht31_temp')

    Returns:
        Interface type: 'I2C', 'ONEWIRE', 'UART', 'DIGITAL', or 'ANALOG'
    """
    sensor_lower = sensor_type.lower()

    if any(s in sensor_lower for s in ["sht31", "bmp280", "bme280", "bh1750", "veml7700"]):
        return "I2C"
    elif "ds18b20" in sensor_lower:
        return "ONEWIRE"
    elif any(s in sensor_lower for s in ["co2", "mhz19", "sen0220"]):
        return "UART"
    elif any(s in sensor_lower for s in ["flow", "yfs201", "liquid_level"]):
        return "DIGITAL"
    else:
        return "ANALOG"


async def _validate_i2c_config(
    sensor_repo: SensorRepository,
    esp_id: uuid.UUID,
    i2c_address: Optional[int],
    sensor_type: Optional[str] = None,
    exclude_sensor_id: Optional[uuid.UUID] = None,
):
    """
    Validate I2C configuration.

    Rules:
    - i2c_address is required for I2C sensors
    - i2c_address must be in valid 7-bit range (0x00-0x7F)
    - Reserved addresses are rejected (0x00-0x07, 0x78-0x7F)
    - Valid range: 0x08-0x77 (112 usable addresses)
    - i2c_address must be unique per ESP (can't have 2 devices on same address)
    - Sibling sub-types of multi-value sensors are excluded from conflict check
    - GPIO 21/22 are shared (bus pins), no conflict

    Args:
        sensor_repo: Sensor repository instance
        esp_id: ESP device UUID
        i2c_address: I2C address (0-127)
        sensor_type: Sensor type for sibling sub-type exclusion (e.g. "sht31_temp")
        exclude_sensor_id: Sensor ID to exclude from conflict check (for updates)

    Raises:
        HTTPException: If validation fails
    """
    logger = get_logger(__name__)

    # Check 1: Address is required
    if not i2c_address:
        raise ValidationException("i2c_address", "i2c_address is required for I2C sensors")

    # Check 1.5: Negative addresses (Ergänzung 1)
    if i2c_address < 0:
        rejection_reason = f"i2c_address must be positive, got {i2c_address}"
        logger.info(
            f"Rejected I2C config: ESP {esp_id}, address 0x{i2c_address:02X} "
            f"(reason: {rejection_reason})"
        )
        raise ValidationException("i2c_address", rejection_reason)

    # Check 2: Validate 7-bit range (0x00-0x7F)
    if i2c_address > 0x7F:
        rejection_reason = (
            f"I2C address 0x{i2c_address:02X} ({i2c_address}) exceeds 7-bit range. "
            f"Valid range: 0x08-0x77 (8-119 decimal)"
        )
        logger.info(
            f"Rejected I2C config: ESP {esp_id}, address 0x{i2c_address:02X} "
            f"(reason: {rejection_reason})"
        )
        raise ValidationException("i2c_address", rejection_reason)

    # Check 3: Reserved address ranges
    # 0x00-0x07: General call, START byte, reserved
    if 0x00 <= i2c_address <= 0x07:
        rejection_reason = (
            f"I2C address 0x{i2c_address:02X} is reserved (general call/START byte range). "
            f"Valid range: 0x08-0x77 (8-119 decimal)"
        )
        logger.info(
            f"Rejected I2C config: ESP {esp_id}, address 0x{i2c_address:02X} "
            f"(reason: {rejection_reason})"
        )
        raise ValidationException("i2c_address", rejection_reason)

    # 0x78-0x7F: 10-bit addressing reserved
    if 0x78 <= i2c_address <= 0x7F:
        rejection_reason = (
            f"I2C address 0x{i2c_address:02X} is reserved (10-bit addressing range). "
            f"Valid range: 0x08-0x77 (8-119 decimal)"
        )
        logger.info(
            f"Rejected I2C config: ESP {esp_id}, address 0x{i2c_address:02X} "
            f"(reason: {rejection_reason})"
        )
        raise ValidationException("i2c_address", rejection_reason)

    # Check 4: Address already used (conflict check)
    # Use get_all to properly filter sibling sub-types of multi-value sensors
    all_with_address = await sensor_repo.get_all_by_i2c_address(esp_id, i2c_address)

    # Determine sibling sub-types to exclude from conflict detection
    # e.g. sht31_temp saving should not conflict with sht31_humidity
    sibling_types: list[str] = []
    if sensor_type:
        base_device = get_device_type_from_sensor_type(sensor_type)
        if base_device:
            sibling_types = get_all_value_types_for_device(base_device)

    conflicting = [
        s
        for s in all_with_address
        if s.id != exclude_sensor_id and s.sensor_type not in sibling_types
    ]

    if conflicting:
        rejection_reason = f"Address 0x{i2c_address:02X} already in use"
        logger.info(
            f"Rejected I2C config: ESP {esp_id}, address 0x{i2c_address:02X} "
            f"(reason: {rejection_reason}, conflict with {conflicting[0].sensor_type})"
        )
        raise DuplicateError("I2CSensor", "i2c_address", f"0x{i2c_address:02X}")


async def _validate_onewire_config(
    sensor_repo: SensorRepository,
    esp_id: uuid.UUID,
    onewire_address: Optional[str],
    exclude_sensor_id: Optional[uuid.UUID] = None,
) -> Optional[str]:
    """
    Validate OneWire configuration.

    Rules:
    - onewire_address is OPTIONAL for OneWire sensors (Auto-Discovery use case)
    - If not provided, a placeholder address is generated
    - If provided, it must be unique per ESP
    - GPIO (bus pin) is shared, no conflict

    Rationale:
    - User typically doesn't know OneWire ROM addresses when adding sensors
    - ESP32 can auto-discover devices on the bus
    - For single-device buses, the address doesn't matter
    - The actual address can be updated later via ESP heartbeat/discovery

    Args:
        sensor_repo: Sensor repository instance
        esp_id: ESP device UUID
        onewire_address: OneWire device address (optional)
        exclude_sensor_id: Sensor ID to exclude from conflict check (for updates)

    Returns:
        The validated or generated onewire_address

    Raises:
        HTTPException: If address conflict detected
    """
    # If no address provided, generate a placeholder
    # Format: SIM_<random_hex> to distinguish from real ROM addresses
    # Kept within varchar(32) limit (SIM_ + 12 hex = 16 chars)
    if not onewire_address:
        import secrets

        onewire_address = f"SIM_{secrets.token_hex(6).upper()}"
        logger.info(f"Generated placeholder OneWire address: {onewire_address}")
        return onewire_address

    # Check if address already used (only if a real address was provided)
    existing_with_address = await sensor_repo.get_by_onewire_address(esp_id, onewire_address)

    if existing_with_address and existing_with_address.id != exclude_sensor_id:
        raise DuplicateError("OneWireSensor", "onewire_address", onewire_address)

    return onewire_address


# =============================================================================
# Alert Config Endpoints (Phase 4A.7)
# =============================================================================


@router.patch(
    "/{sensor_id}/alert-config",
    response_model=SensorAlertConfigViewResponse,
    summary="Update sensor alert configuration",
)
async def update_sensor_alert_config(
    sensor_id: uuid.UUID,
    body: SensorAlertConfigUpdate,
    session: DBSession,
    user: ViewerUser,
) -> SensorAlertConfigViewResponse:
    """
    Update per-sensor alert configuration (suppression, thresholds, severity).

    The alert_config is a JSONB field — partial updates merge with existing config.

    Role-based field access (AUT-1097):
    - viewer: may only write ``custom_thresholds``.
    - operator / admin: all fields allowed.

    Field-presence is determined via ``exclude_unset=True`` so that an explicit
    ``null`` value in the payload is treated as "field was set" (= delete the key).
    """
    # Field-level role check: viewer may only touch custom_thresholds (AUT-1097).
    # Whitelist approach: any field NOT in ALLOWED_VIEWER_FIELDS triggers 403.
    # This prevents future new fields from becoming viewer-writable by default.
    ALLOWED_VIEWER_FIELDS: set[str] = {"custom_thresholds"}
    is_operator_or_above = user.role in ("admin", "operator")

    if not is_operator_or_above:
        sent_fields = set(body.model_dump(exclude_unset=True).keys())
        forbidden = sent_fields - ALLOWED_VIEWER_FIELDS
        if forbidden:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Insufficient permissions. Fields {sorted(forbidden)} require "
                    "operator role. Viewers may only write custom_thresholds."
                ),
            )

    sensor_repo = SensorRepository(session)
    sensor = await sensor_repo.get_by_id(sensor_id)
    if not sensor:
        raise SensorNotFoundException(str(sensor_id))

    # Merge with existing config (partial update — only sent fields change).
    # exclude_unset=True: only fields explicitly present in the request are merged.
    existing = dict(sensor.alert_config or {})
    for key, value in body.model_dump(exclude_unset=True).items():
        if value is None:
            # Explicit null → remove the key from alert_config
            existing.pop(key, None)
        else:
            # Nested Pydantic models (e.g. CustomThresholds) are already dicts
            # after model_dump(); no extra serialization needed.
            existing[key] = value

    sensor.alert_config = existing
    await session.commit()

    logger.info(f"Alert config updated: sensor {sensor_id}, user={user.username}, config={existing}")
    return SensorAlertConfigViewResponse(status="ok", alert_config=existing)


@router.patch(
    "/{sensor_id}/runtime",
    response_model=SensorRuntimeUpdateResponse,
    summary="Update sensor runtime stats",
)
async def update_sensor_runtime(
    sensor_id: uuid.UUID,
    body: dict,
    session: DBSession,
    user: OperatorUser,
) -> SensorRuntimeUpdateResponse:
    """Update runtime statistics for a sensor (expected_lifetime, maintenance_log)."""
    sensor_repo = SensorRepository(session)
    sensor = await sensor_repo.get_by_id(sensor_id)
    if not sensor:
        raise SensorNotFoundException(str(sensor_id))

    existing = dict(sensor.runtime_stats or {})
    for key, value in body.items():
        if value is None:
            existing.pop(key, None)
        else:
            existing[key] = value

    sensor.runtime_stats = existing
    await session.commit()

    return SensorRuntimeUpdateResponse(status="ok", runtime_stats=existing)


# =============================================================================
# Export Sensor Data as CSV
# =============================================================================

_EXPORT_BATCH_SIZE = 500
_EXPORT_ALLOWED_COLUMNS: frozenset[str] = frozenset(
    {
        "timestamp",
        "raw_value",
        "processed_value",
        "unit",
        "quality",
        "sensor_type",
        "esp_id",
        "gpio",
        "zone_id",
        "subzone_id",
    }
)
_EXPORT_DEFAULT_COLUMNS: list[str] = [
    "timestamp",
    "processed_value",
    "unit",
    "quality",
    "sensor_type",
]


def _export_column_value(row: object, col: str, is_aggregated: bool) -> str:
    """Extract a column value from a SensorData row (raw or aggregated) as a string."""
    if is_aggregated:
        mapping = {
            "timestamp": "bucket",
            "raw_value": "avg_raw",
            "processed_value": "avg_processed",
        }
        attr = mapping.get(col, col)
        if col == "quality":
            return "aggregated"
        if col in ("zone_id", "subzone_id"):
            return "aggregated"
        val = getattr(row, attr, None)
    else:
        val = getattr(row, col, None)

    if val is None:
        return ""
    if isinstance(val, datetime):
        return val.isoformat()
    if isinstance(val, uuid.UUID):
        return str(val)
    return str(val)


async def _generate_csv(
    sensor_repo: SensorRepository,
    esp_db_id: Optional[uuid.UUID],
    gpio: Optional[int],
    sensor_type: Optional[str],
    start_time: datetime,
    end_time: datetime,
    resolution: Optional[str],
    zone_id: Optional[str],
    subzone_id: Optional[str],
    col_list: list[str],
    is_aggregated: bool,
) -> AsyncGenerator[str, None]:
    """Yield BOM + CSV header, then data rows via cursor-based batching (500 rows/batch)."""
    buf = io.StringIO()
    writer = csv.writer(buf)

    yield "﻿"  # BOM for Excel compatibility

    buf.seek(0)
    buf.truncate()
    writer.writerow(col_list)
    buf.seek(0)
    yield buf.read()

    cursor: Optional[datetime] = None
    while True:
        batch = await sensor_repo.query_data(
            esp_id=esp_db_id,
            gpio=gpio,
            sensor_type=sensor_type,
            start_time=start_time,
            end_time=end_time,
            resolution=resolution or "raw",
            zone_id=zone_id,
            subzone_id=subzone_id,
            limit=_EXPORT_BATCH_SIZE,
            before_timestamp=cursor,
        )
        if not batch:
            break

        for row in batch:
            buf.seek(0)
            buf.truncate()
            writer.writerow([_export_column_value(row, col, is_aggregated) for col in col_list])
            buf.seek(0)
            yield buf.read()

        if len(batch) < _EXPORT_BATCH_SIZE:
            break

        # Cursor: oldest timestamp in DESC-ordered batch (last element)
        last_row = batch[-1]
        ts_attr = "bucket" if is_aggregated else "timestamp"
        cursor = getattr(last_row, ts_attr, None)
        if cursor is None:
            break


@router.get(
    "/export",
    response_class=StreamingResponse,
    summary="Export sensor data as CSV",
    responses={200: {"content": {"text/csv": {}}, "description": "Sensor data CSV file"}},
)
async def export_sensor_data(
    db: DBSession,
    current_user: ActiveUser,
    esp_id: Annotated[Optional[str], Query(description="Filter by ESP device ID")] = None,
    gpio: Annotated[Optional[int], Query(ge=0, le=39, description="Filter by GPIO")] = None,
    sensor_type: Annotated[Optional[str], Query(description="Filter by sensor type")] = None,
    start_time: Annotated[Optional[datetime], Query(description="Start of time range (ISO-8601)")] = None,
    end_time: Annotated[Optional[datetime], Query(description="End of time range (ISO-8601)")] = None,
    columns: Annotated[
        Optional[str],
        Query(description="Comma-separated column names (default: timestamp,processed_value,unit,quality,sensor_type)"),
    ] = None,
    resolution: Annotated[
        Optional[str],
        Query(
            pattern=r"^(raw|1m|5m|1h|1d)$",
            description="Time resolution: raw (default), 1m, 5m, 1h, 1d",
        ),
    ] = None,
    zone_id: Annotated[Optional[str], Query(description="Filter by zone ID")] = None,
    subzone_id: Annotated[Optional[str], Query(description="Filter by subzone ID")] = None,
    format: Annotated[
        Literal["csv"],
        Query(description="Export format (currently only csv)"),
    ] = "csv",
) -> StreamingResponse:
    """
    Stream all sensor data matching the given filters as a CSV file.

    Pagination is handled internally via cursor batching (500 rows/batch).
    No hard cap on total rows — suitable for multi-day exports.

    Requires at least one of: esp_id, zone_id, subzone_id.
    """
    # Validate: at least one scoping filter required
    if not esp_id and not zone_id and not subzone_id:
        raise HTTPException(
            status_code=422,
            detail="Mindestens esp_id, zone_id oder subzone_id erforderlich.",
        )

    # Validate and parse column selection
    if columns is not None:
        col_list = [c.strip() for c in columns.split(",") if c.strip()]
        if not col_list:
            # AUT-400 / AUT-839 B4: leerer columns-Parameter faellt auf
            # Default-Spalten zurueck statt HTTP 422 zu werfen.
            col_list = list(_EXPORT_DEFAULT_COLUMNS)
        unknown = sorted(set(col_list) - _EXPORT_ALLOWED_COLUMNS)
        if unknown:
            raise HTTPException(
                status_code=422,
                detail=f"Unbekannte Spalten: {unknown}. Erlaubt: {sorted(_EXPORT_ALLOWED_COLUMNS)}",
            )
    else:
        col_list = list(_EXPORT_DEFAULT_COLUMNS)

    # Normalize time range (timezone-aware UTC)
    if not start_time:
        start_time = datetime.now(timezone.utc) - timedelta(hours=24)
    elif start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
    if not end_time:
        end_time = datetime.now(timezone.utc)
    elif end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=timezone.utc)

    if start_time >= end_time:
        raise HTTPException(
            status_code=422,
            detail="start_time muss vor end_time liegen.",
        )

    # Resolve esp_id string → internal UUID (export allows soft-deleted history)
    esp_repo = ESPRepository(db)
    sensor_repo = SensorRepository(db)
    esp_db_id: Optional[uuid.UUID] = None
    if esp_id:
        esp_device = await esp_repo.get_by_device_id(esp_id, include_deleted=True)
        if not esp_device:
            raise ESPNotFoundError(esp_id)
        esp_db_id = esp_device.id

    is_aggregated = bool(resolution and resolution != "raw")

    # Build filename: sensor-export_{esp_id}_{start}_{end}.csv
    start_str = start_time.strftime("%Y%m%dT%H%M%S")
    end_str = end_time.strftime("%Y%m%dT%H%M%S")
    filename = f"sensor-export_{esp_id or zone_id or subzone_id or 'all'}_{start_str}_{end_str}.csv"

    generator = _generate_csv(
        sensor_repo=sensor_repo,
        esp_db_id=esp_db_id,
        gpio=gpio,
        sensor_type=sensor_type,
        start_time=start_time,
        end_time=end_time,
        resolution=resolution,
        zone_id=zone_id,
        subzone_id=subzone_id,
        col_list=col_list,
        is_aggregated=is_aggregated,
    )

    return StreamingResponse(
        generator,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
