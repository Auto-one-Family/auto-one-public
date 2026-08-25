"""
Sensor Pydantic Schemas

Phase: 5 (Week 9-10) - API Layer
Priority: 🔴 CRITICAL
Status: IMPLEMENTED

Provides:
- Sensor configuration CRUD models
- Sensor data query and response models
- Calibration models

Consistency with El Trabajante:
- Sensor types: ph, temperature, humidity, ec, moisture, pressure, co2, light, flow
- Quality levels: excellent, good, fair, poor, bad, stale, degraded, …
- MQTT Topic: kaiser/god/esp/{esp_id}/sensor/{gpio}/data

References:
- .claude/PI_SERVER_REFACTORING.md (Lines 135-145)
- El Trabajante/docs/Mqtt_Protocoll.md (Sensor topics)
- api/schemas.py (existing processing schemas - to be consolidated)
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .alert_config import CustomThresholds
from .common import (
    BaseResponse,
    PaginatedResponse,
    PaginationMeta,
    TimestampMixin,
)

# =============================================================================
# Sensor Types and Constants
# =============================================================================


SENSOR_TYPES = [
    "ph",
    "temperature",
    "humidity",
    "ec",
    "moisture",
    "pressure",
    "co2",
    "light",
    "flow",
    "analog",
    "digital",
]

QUALITY_LEVELS = [
    "excellent",
    "good",
    "fair",
    "poor",
    "bad",
    "stale",
    "suspect",
    "critical",
    "error",
    "degraded",  # PKG-HW-01: server-side ingest without matching sensor_configs row
    "aggregated",
    "unknown",
    "warming_up",
]

# AUT-299: Sensor types that are valid ATC temperature sources.
# Used both for schema documentation and for API-layer validation in sensors.py.
_TEMPERATURE_SENSOR_TYPES: frozenset[str] = frozenset(
    {
        "ds18b20",
        "temperature",
        "sht31_temp",
        "bmp280_temp",
    }
)


# =============================================================================
# Sensor Configuration
# =============================================================================


class SensorConfigBase(BaseModel):
    """Base sensor configuration fields."""

    gpio: int = Field(
        ...,
        ge=0,
        le=39,
        description="GPIO pin number (0-39 for ESP32)",
    )
    sensor_type: str = Field(
        ...,
        description="Sensor type (ph, temperature, humidity, etc.)",
    )
    name: Optional[str] = Field(
        None,
        max_length=100,
        description="Human-readable sensor name",
        examples=["Tank pH Sensor", "Ambient Temperature"],
    )
    description: Optional[str] = Field(
        None,
        max_length=500,
        description="Human-readable sensor description",
    )
    unit: Optional[str] = Field(
        None,
        max_length=20,
        description="Physical unit, e.g. °C, %, pH",
    )
    measurement_role: Optional[str] = Field(
        None,
        pattern=r"^(inflow|runoff)$",
        description="Domain role: 'inflow', 'runoff', or None for unassigned",
    )

    @field_validator("sensor_type")
    @classmethod
    def validate_sensor_type(cls, v: str) -> str:
        """Validate and normalize sensor type."""
        v = v.lower().strip()
        if v not in SENSOR_TYPES:
            # Allow custom types but warn
            pass
        return v


class SensorConfigCreate(SensorConfigBase):
    """
    Sensor configuration create request.

    Multi-Value Sensor Support:
    - I2C sensors: Multiple sensor_types can share same GPIO (bus pins 21/22)
    - OneWire sensors: Multiple devices can share same GPIO (bus pin)
    - Analog/Digital: GPIO must be exclusive
    """

    esp_id: str = Field(
        ...,
        pattern=r"^(ESP_[A-F0-9]{6,8}|MOCK_[A-Z0-9]+)$",
        description="ESP device ID",
        examples=["ESP_12AB34CD"],
    )
    enabled: bool = Field(
        True,
        description="Whether sensor is enabled",
    )
    interval_ms: int = Field(
        30000,
        ge=1000,
        le=300000,
        description="Reading interval in milliseconds",
    )
    # Processing mode
    processing_mode: str = Field(
        "pi_enhanced",
        description="Processing mode: pi_enhanced (server), local (ESP), raw (no processing)",
        pattern=r"^(pi_enhanced|local|raw)$",
    )

    # =========================================================================
    # MULTI-VALUE SENSOR SUPPORT (I2C/OneWire)
    # =========================================================================
    interface_type: Optional[str] = Field(
        None,
        pattern=r"^(I2C|ONEWIRE|ANALOG|DIGITAL|UART|VIRTUAL)$",
        description="Interface type: I2C, ONEWIRE, ANALOG, DIGITAL, UART, VIRTUAL (auto-inferred if not provided)",
    )

    i2c_address: Optional[int] = Field(
        None,
        ge=0,
        le=127,
        description="I2C address (required for I2C sensors, e.g., 68 for 0x44)",
    )

    onewire_address: Optional[str] = Field(
        None,
        max_length=32,
        description="OneWire device address (required for OneWire sensors, e.g. 28FF82F110C78897 or SIM_ prefix)",
    )

    provides_values: Optional[List[str]] = Field(
        None,
        description="List of value types this sensor provides (for multi-value sensors, e.g., ['sht31_temp', 'sht31_humidity'])",
    )

    # =========================================================================
    # EXTERNAL ADC SOURCE (ADS1115) — per-sensor acquisition source for pH/EC
    # =========================================================================
    adc_source: Optional[str] = Field(
        None,
        pattern=r"^(internal|ads1115)$",
        description="ADC acquisition source: 'internal' (ESP32 12-bit, default) or "
        "'ads1115' (external 16-bit I2C ADC). Only the acquisition source changes; "
        "RAW still flows through the identical conversion/calibration path.",
    )
    adc_channel: Optional[int] = Field(
        None,
        ge=0,
        le=3,
        description="ADS1115 single-ended channel 0-3 (only for adc_source='ads1115')",
    )
    pga_gain: Optional[str] = Field(
        None,
        pattern=r"^(6\.144|4\.096|2\.048|1\.024|0\.512|0\.256)$",
        description="ADS1115 PGA full-scale range in volts (only for adc_source='ads1115'; default '4.096')",
    )
    # =========================================================================
    polarity: Optional[str] = Field(
        None,
        pattern=r"^(active_high|active_low)$",
        description="Signal polarity for digital sensors: 'active_low' (NPN, default) or 'active_high' (PNP). "
        "Only relevant for interface_type=DIGITAL (e.g. liquid_level). Omit to use default 'active_low'.",
    )

    # Calibration
    calibration: Optional[Dict[str, Any]] = Field(
        None,
        description="Calibration data (sensor-specific)",
    )
    # Thresholds
    threshold_min: Optional[float] = Field(
        None,
        description="Minimum valid value threshold",
    )
    threshold_max: Optional[float] = Field(
        None,
        description="Maximum valid value threshold",
    )
    warning_min: Optional[float] = Field(
        None,
        description="Warning threshold (low)",
    )
    warning_max: Optional[float] = Field(
        None,
        description="Warning threshold (high)",
    )
    # Metadata (description/unit from SensorConfigBase are persisted in sensor_metadata)
    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Custom metadata",
    )
    # =========================================================================
    # OPERATING MODE CONFIGURATION (Phase 2F)
    # =========================================================================
    operating_mode: Optional[str] = Field(
        None,
        description="Operating mode override: continuous, on_demand, scheduled, paused. "
        "NULL = use SensorTypeDefaults",
        pattern=r"^(continuous|on_demand|scheduled|paused)$",
    )
    timeout_seconds: Optional[int] = Field(
        None,
        ge=0,
        le=86400,  # Max 24 hours
        description="Timeout override in seconds. NULL = use SensorTypeDefaults, 0 = no timeout",
    )
    timeout_warning_enabled: Optional[bool] = Field(
        None,
        description="Enable timeout warnings. NULL = use SensorTypeDefaults",
    )
    schedule_config: Optional[Dict[str, Any]] = Field(
        None,
        description="Schedule configuration for scheduled mode",
    )
    measurement_freshness_hours: Optional[int] = Field(
        None,
        ge=1,
        le=8760,
        description="Hours after which measurement is stale. NULL = use SensorTypeDefaults",
    )
    calibration_interval_days: Optional[int] = Field(
        None,
        ge=1,
        le=365,
        description="Days between recalibrations. NULL = use SensorTypeDefaults",
    )

    subzone_id: Optional[str] = Field(
        None,
        max_length=50,
        description="Subzone ID to assign this sensor to. Null/empty = remove from all subzones.",
    )

    # =========================================================================
    # MULTI-ZONE DEVICE SCOPE (T13-R2)
    # =========================================================================
    device_scope: Optional[str] = Field(
        None,
        pattern=r"^(zone_local|multi_zone|mobile)$",
        description="Device scope: 'zone_local' (default), 'multi_zone', 'mobile'",
    )
    assigned_zones: Optional[List[str]] = Field(
        None,
        description="List of zone_ids this sensor can serve (for multi_zone/mobile)",
    )
    assigned_subzones: Optional[List[str]] = Field(
        None,
        description="List of subzone_ids for static multi-zone assignment",
    )

    # AUT-299: Optional linked temperature sensor for ATC
    temp_sensor_config_id: Optional[uuid.UUID] = Field(
        None,
        description=(
            "UUID of a temperature SensorConfig to use for ATC. "
            "Must reference a sensor_type in: ds18b20, temperature, sht31_temp, bmp280_temp. "
            "NULL = auto-discover same-ESP temperature sensor."
        ),
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "esp_id": "ESP_12AB34CD",
                "gpio": 34,
                "sensor_type": "ph",
                "name": "Nutrient Tank pH",
                "enabled": True,
                "interval_ms": 30000,
                "processing_mode": "pi_enhanced",
                "calibration": {"slope": -3.5, "offset": 21.34},
                "threshold_min": 0.0,
                "threshold_max": 14.0,
                "warning_min": 5.5,
                "warning_max": 7.5,
                "operating_mode": "continuous",
                "timeout_seconds": 180,
                "measurement_freshness_hours": 24,
                "calibration_interval_days": 30,
            }
        }
    )


class SensorConfigUpdate(BaseModel):
    """
    Sensor configuration update request.

    All fields optional - only provided fields are updated.
    """

    name: Optional[str] = Field(None, max_length=100)
    enabled: Optional[bool] = Field(None)
    interval_ms: Optional[int] = Field(None, ge=1000, le=300000)
    processing_mode: Optional[str] = Field(
        None,
        pattern=r"^(pi_enhanced|local|raw)$",
    )
    calibration: Optional[Dict[str, Any]] = Field(None)
    threshold_min: Optional[float] = Field(None)
    threshold_max: Optional[float] = Field(None)
    warning_min: Optional[float] = Field(None)
    warning_max: Optional[float] = Field(None)
    metadata: Optional[Dict[str, Any]] = Field(None)
    # =========================================================================
    # OPERATING MODE CONFIGURATION (Phase 2F)
    # =========================================================================
    operating_mode: Optional[str] = Field(
        None,
        description="Operating mode override: continuous, on_demand, scheduled, paused. "
        "NULL = use SensorTypeDefaults",
        pattern=r"^(continuous|on_demand|scheduled|paused)$",
    )
    timeout_seconds: Optional[int] = Field(
        None,
        ge=0,
        le=86400,
        description="Timeout override in seconds. NULL = use SensorTypeDefaults, 0 = no timeout",
    )
    timeout_warning_enabled: Optional[bool] = Field(
        None,
        description="Enable timeout warnings. NULL = use SensorTypeDefaults",
    )
    schedule_config: Optional[Dict[str, Any]] = Field(
        None,
        description="Schedule configuration for scheduled mode",
    )
    measurement_freshness_hours: Optional[int] = Field(
        None,
        ge=1,
        le=8760,
        description="Hours after which measurement is stale. NULL = use SensorTypeDefaults",
    )
    calibration_interval_days: Optional[int] = Field(
        None,
        ge=1,
        le=365,
        description="Days between recalibrations. NULL = use SensorTypeDefaults",
    )
    # =========================================================================
    # MULTI-ZONE DEVICE SCOPE (T13-R2)
    # =========================================================================
    device_scope: Optional[str] = Field(
        None,
        pattern=r"^(zone_local|multi_zone|mobile)$",
        description="Device scope: 'zone_local', 'multi_zone', 'mobile'",
    )
    assigned_zones: Optional[List[str]] = Field(
        None,
        description="List of zone_ids this sensor can serve",
    )
    # NOTE (AUT-227): assigned_subzones removed from SensorConfigUpdate (read-only).
    # The DB column is DEPRECATED and is not consumed by any business-logic layer.
    # Reads are still served via SensorConfigResponse for backwards compatibility.
    # AUT-299: Optional linked temperature sensor for ATC
    temp_sensor_config_id: Optional[uuid.UUID] = Field(
        None,
        description=(
            "UUID of a temperature SensorConfig to use for ATC. "
            "Must reference a sensor_type in: ds18b20, temperature, sht31_temp, bmp280_temp. "
            "NULL = auto-discover same-ESP temperature sensor."
        ),
    )


class SensorConfigResponse(SensorConfigBase, TimestampMixin):
    """
    Sensor configuration response.
    """

    id: uuid.UUID = Field(
        ...,
        description="Unique identifier (UUID)",
    )
    esp_id: uuid.UUID = Field(
        ...,
        description="ESP device database ID (UUID)",
    )
    esp_device_id: Optional[str] = Field(
        None,
        description="ESP device ID string (ESP_XXXXXXXX)",
    )
    enabled: bool = Field(
        ...,
        description="Whether sensor is enabled",
    )
    interval_ms: int = Field(
        ...,
        description="Reading interval (ms)",
    )
    processing_mode: str = Field(
        ...,
        description="Processing mode",
    )

    # =========================================================================
    # MULTI-VALUE SENSOR SUPPORT
    # =========================================================================
    interface_type: str = Field(
        ...,
        description="Interface type: I2C, ONEWIRE, ANALOG, DIGITAL, UART, VIRTUAL",
    )

    i2c_address: Optional[int] = Field(
        None,
        description="I2C address (for I2C sensors)",
    )

    onewire_address: Optional[str] = Field(
        None,
        description="OneWire device address (for OneWire sensors)",
    )

    provides_values: Optional[List[str]] = Field(
        None,
        description="List of value types this sensor provides",
    )

    # External ADC source (ADS1115) — per-sensor acquisition source for pH/EC
    adc_source: Optional[str] = Field(
        None,
        description="ADC acquisition source: 'internal' (default) or 'ads1115'",
    )
    adc_channel: Optional[int] = Field(
        None,
        description="ADS1115 single-ended channel 0-3 (only for adc_source='ads1115')",
    )
    pga_gain: Optional[str] = Field(
        None,
        description="ADS1115 PGA full-scale range in volts (only for adc_source='ads1115')",
    )
    polarity: Optional[str] = Field(
        None, description="Signal polarity: 'active_low' or 'active_high'"
    )
    # =========================================================================

    calibration: Optional[Dict[str, Any]] = Field(None)
    threshold_min: Optional[float] = Field(None)
    threshold_max: Optional[float] = Field(None)
    warning_min: Optional[float] = Field(None)
    warning_max: Optional[float] = Field(None)
    # AUT-1104: sensor.alert_config.custom_thresholds passthrough — the same
    # value alert_suppression_service.get_effective_thresholds() prioritizes
    # over threshold_min/max above. Read-only here; written via the dedicated
    # alert-config endpoint (see sensors.py ALLOWED_VIEWER_FIELDS).
    custom_thresholds: Optional[CustomThresholds] = Field(
        None,
        description="Operator-configured alert thresholds (alert_config.custom_thresholds), "
        "if set. Takes priority over threshold_min/max for scale/zone derivation.",
    )
    metadata: Optional[Dict[str, Any]] = Field(None)
    # AUT-299: Linked temperature sensor config UUID for ATC
    temp_sensor_config_id: Optional[uuid.UUID] = Field(
        None,
        description="Linked temperature sensor config UUID for ATC",
    )
    description: Optional[str] = Field(
        None,
        description="Human-readable sensor description (from sensor_metadata)",
    )
    unit: Optional[str] = Field(
        None,
        description="Physical unit, e.g. °C, %, pH (from sensor_metadata)",
    )
    # Config status from ESP32 verification
    config_status: Optional[str] = Field(
        None,
        description="Config status: pending, applied, failed",
    )
    config_error: Optional[str] = Field(
        None,
        description="Error code if config_status=failed",
    )
    subzone_id: Optional[str] = Field(
        None,
        description="Subzone ID this sensor belongs to (if any)",
    )
    operating_mode: Optional[str] = Field(
        None,
        description="Operating mode: continuous, on_demand, scheduled, paused",
    )
    timeout_seconds: Optional[int] = Field(
        None,
        ge=0,
        le=86400,
        description="Timeout for stale detection in seconds (0 = disabled)",
    )
    config_error_detail: Optional[str] = Field(
        None,
        description="Error detail if config_status=failed",
    )
    measurement_freshness_hours: Optional[int] = Field(
        None,
        description="Hours after which measurement is stale",
    )
    calibration_interval_days: Optional[int] = Field(
        None,
        description="Days between recalibrations",
    )
    # Multi-Zone Device Scope (T13-R2)
    device_scope: Optional[str] = Field(
        None,
        description="Device scope: 'zone_local', 'multi_zone', 'mobile'",
    )
    assigned_zones: Optional[List[str]] = Field(
        None,
        description="List of zone_ids this sensor can serve",
    )
    assigned_subzones: Optional[List[str]] = Field(
        None,
        description="List of subzone_ids for static multi-zone",
    )
    # Latest reading (optional)
    latest_value: Optional[float] = Field(
        None,
        description="Latest sensor value",
    )
    latest_quality: Optional[str] = Field(
        None,
        description="Latest reading quality",
    )
    latest_timestamp: Optional[datetime] = Field(
        None,
        description="Latest reading timestamp",
    )
    subzone_warning: Optional[str] = Field(
        None,
        description="Warning if subzone assignment failed (sensor was saved successfully)",
    )
    correlation_id: Optional[str] = Field(
        None,
        description=(
            "MQTT config push correlation_id from the last send_config in this request; "
            "matches ESP config_response and WS config_published/config_failed for UI contract tracking."
        ),
    )

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "esp_id": "440e8400-e29b-41d4-a716-446655440000",
                "esp_device_id": "ESP_12AB34CD",
                "gpio": 34,
                "sensor_type": "ph",
                "name": "Nutrient Tank pH",
                "enabled": True,
                "interval_ms": 30000,
                "processing_mode": "pi_enhanced",
                "calibration": {"slope": -3.5, "offset": 21.34},
                "threshold_min": 0.0,
                "threshold_max": 14.0,
                "latest_value": 6.8,
                "latest_quality": "good",
                "latest_timestamp": "2025-01-01T12:00:00Z",
                "created_at": "2025-01-01T00:00:00Z",
                "updated_at": "2025-01-01T12:00:00Z",
            }
        },
    )


# =============================================================================
# Sensor Data
# =============================================================================


class SensorReading(BaseModel):
    """
    Single sensor reading (raw or aggregated bucket).
    """

    timestamp: datetime = Field(
        ..., description="Reading timestamp (or bucket start for aggregated)"
    )
    raw_value: Optional[float] = Field(
        None,
        description="Raw sensor value (or avg for aggregated). Null when the "
        "bucket has no raw samples — never coerced to 0.0 (AUT-723 E3).",
    )
    processed_value: Optional[float] = Field(
        None,
        description="Processed value (after calibration/conversion, or avg for aggregated)",
    )
    unit: Optional[str] = Field(
        None,
        description="Measurement unit",
    )
    quality: str = Field(
        "good",
        description="Data quality (excellent, good, fair, poor, bad, stale)",
    )
    sensor_type: Optional[str] = Field(
        None,
        description="Sensor type (e.g. 'sht31_temp', 'sht31_humidity', 'ds18b20'). "
        "Allows frontend to distinguish readings from multi-value sensors.",
    )
    zone_id: Optional[str] = Field(
        None,
        description="Zone ID at measurement time (Phase 0.1)",
    )
    subzone_id: Optional[str] = Field(
        None,
        description="Subzone ID at measurement time (Phase 0.1)",
    )
    # Aggregation fields (only set when resolution != raw)
    min_value: Optional[float] = Field(
        None,
        description="Minimum processed_value in bucket (aggregated only)",
    )
    max_value: Optional[float] = Field(
        None,
        description="Maximum processed_value in bucket (aggregated only)",
    )
    sample_count: Optional[int] = Field(
        None,
        description="Number of samples in bucket (aggregated only)",
    )

    @field_validator("quality")
    @classmethod
    def validate_quality(cls, v: str) -> str:
        """Validate quality level."""
        v = v.lower()
        if v not in QUALITY_LEVELS:
            v = "good"  # Default to good if unknown
        return v

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "timestamp": "2025-01-01T12:00:00Z",
                "raw_value": 2150,
                "processed_value": 6.8,
                "unit": "pH",
                "quality": "good",
                "sensor_type": "ph",
            }
        },
    )


class SensorDataQuery(BaseModel):
    """
    Sensor data query parameters.

    Note: This schema is kept for documentation/OpenAPI purposes.
    The actual endpoint uses individual Query() parameters.
    """

    esp_id: Optional[str] = Field(
        None,
        pattern=r"^(ESP_[A-F0-9]{6,8}|MOCK_[A-Z0-9]+)$",
        description="Filter by ESP device ID",
    )
    gpio: Optional[int] = Field(
        None,
        ge=0,
        le=39,
        description="Filter by GPIO pin",
    )
    sensor_type: Optional[str] = Field(
        None,
        description="Filter by sensor type",
    )
    start_time: Optional[datetime] = Field(
        None,
        description="Start of time range",
    )
    end_time: Optional[datetime] = Field(
        None,
        description="End of time range",
    )
    quality: Optional[str] = Field(
        None,
        description="Filter by quality level",
    )
    resolution: Optional[str] = Field(
        None,
        pattern=r"^(raw|1m|5m|1h|1d)$",
        description="Time resolution for aggregation (raw, 1m, 5m, 1h, 1d)",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "esp_id": "ESP_12AB34CD",
                "gpio": 34,
                "start_time": "2025-01-01T00:00:00Z",
                "end_time": "2025-01-01T23:59:59Z",
                "resolution": "1h",
            }
        }
    )


class SensorDataResponse(BaseResponse):
    """
    Sensor data query response.
    """

    esp_id: Optional[str] = Field(None, description="ESP device ID filter")
    gpio: Optional[int] = Field(None, description="GPIO filter")
    sensor_type: Optional[str] = Field(None, description="Sensor type")
    readings: List[SensorReading] = Field(
        default_factory=list,
        description="Sensor readings",
    )
    count: int = Field(..., description="Number of readings returned", ge=0)
    resolution: Optional[str] = Field(None, description="Resolution applied (raw, 1m, 5m, 1h, 1d)")
    time_range: Optional[Dict[str, Any]] = Field(
        None,
        description="Time range and pagination metadata (start, end, has_more, next_cursor)",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "esp_id": "ESP_12AB34CD",
                "gpio": 34,
                "sensor_type": "ph",
                "readings": [
                    {
                        "timestamp": "2025-01-01T12:00:00Z",
                        "raw_value": 2150,
                        "processed_value": 6.8,
                        "unit": "pH",
                        "quality": "good",
                    }
                ],
                "count": 1,
                "resolution": "raw",
                "time_range": {
                    "start": "2025-01-01T00:00:00Z",
                    "end": "2025-01-01T23:59:59Z",
                    "has_more": False,
                },
            }
        }
    )


class SensorDataPaginatedResponse(BaseResponse):
    """
    Paginated sensor data response.
    """

    esp_id: Optional[str] = Field(None)
    gpio: Optional[int] = Field(None)
    readings: List[SensorReading] = Field(default_factory=list)
    pagination: PaginationMeta = Field(...)


# =============================================================================
# Sensor Statistics
# =============================================================================


class SensorStats(BaseModel):
    """
    Statistical summary for sensor data.
    """

    min_value: Optional[float] = Field(None, description="Minimum value")
    max_value: Optional[float] = Field(None, description="Maximum value")
    avg_value: Optional[float] = Field(None, description="Average value")
    std_dev: Optional[float] = Field(None, description="Standard deviation")
    reading_count: int = Field(..., description="Number of readings", ge=0)
    quality_distribution: Dict[str, int] = Field(
        default_factory=dict,
        description="Count per quality level",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "min_value": 6.2,
                "max_value": 7.4,
                "avg_value": 6.8,
                "std_dev": 0.3,
                "reading_count": 100,
                "quality_distribution": {"excellent": 50, "good": 40, "fair": 10},
            }
        }
    )


class SensorStatsResponse(BaseResponse):
    """
    Sensor statistics response.
    """

    esp_id: str = Field(..., description="ESP device ID")
    gpio: int = Field(..., description="GPIO pin")
    sensor_type: str = Field(..., description="Sensor type")
    stats: SensorStats = Field(..., description="Statistical summary")
    time_range: Dict[str, datetime] = Field(..., description="Data time range")


# =============================================================================
# Query Filters
# =============================================================================


class SensorListFilter(BaseModel):
    """
    Filter parameters for sensor list endpoint.
    """

    esp_id: Optional[str] = Field(
        None,
        pattern=r"^(ESP_[A-F0-9]{6,8}|MOCK_[A-Z0-9]+)$",
        description="Filter by ESP device ID",
    )
    sensor_type: Optional[str] = Field(
        None,
        description="Filter by sensor type",
    )
    enabled: Optional[bool] = Field(
        None,
        description="Filter by enabled status",
    )
    processing_mode: Optional[str] = Field(
        None,
        pattern=r"^(pi_enhanced|local|raw)$",
        description="Filter by processing mode",
    )


# =============================================================================
# Paginated Responses
# =============================================================================


class SensorConfigListResponse(PaginatedResponse[SensorConfigResponse]):
    """
    Paginated list of sensor configurations.
    """

    pass


# =============================================================================
# Processing Schemas (moved from api/schemas.py for consistency)
# =============================================================================


class SensorProcessRequest(BaseModel):
    """
    Request model for sensor processing endpoint.

    ESP32 sends raw sensor data for server-side processing.
    """

    esp_id: str = Field(
        ...,
        description="ESP device ID (format: ESP_XXXXXXXX)",
        pattern=r"^(ESP_[A-F0-9]{6,8}|MOCK_[A-Z0-9]+)$",
        examples=["ESP_12AB34CD"],
    )
    gpio: int = Field(
        ...,
        ge=0,
        le=39,
        description="GPIO pin number (0-39 for ESP32)",
    )
    sensor_type: str = Field(
        ...,
        min_length=2,
        max_length=50,
        description="Sensor type identifier",
        examples=["ph", "temperature", "humidity", "ec"],
    )
    raw_value: float = Field(
        ...,
        description="Raw sensor value (ADC reading 0-4095 for ESP32)",
        ge=0,
        le=4095,
    )
    calibration: Optional[Dict[str, Any]] = Field(
        None,
        description="Calibration data (sensor-specific format)",
    )
    params: Optional[Dict[str, Any]] = Field(
        None,
        description="Processing parameters (sensor-specific)",
    )
    timestamp: Optional[int] = Field(
        None,
        description="Unix timestamp (seconds)",
    )

    @field_validator("sensor_type")
    @classmethod
    def validate_sensor_type(cls, v: str) -> str:
        """Validate sensor type format."""
        return v.lower().strip()

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "esp_id": "ESP_12AB34CD",
                "gpio": 34,
                "sensor_type": "ph",
                "raw_value": 2150,
                "calibration": {"slope": -3.5, "offset": 21.34},
                "timestamp": 1735818000,
            }
        }
    )


class SensorProcessResponse(BaseResponse):
    """
    Response model for sensor processing endpoint.
    """

    processed_value: Optional[float] = Field(
        None,
        description="Processed sensor value",
    )
    unit: Optional[str] = Field(
        None,
        description="Measurement unit",
    )
    quality: Optional[str] = Field(
        None,
        description="Data quality indicator",
    )
    processing_time_ms: Optional[float] = Field(
        None,
        description="Server processing time (ms)",
    )
    error: Optional[str] = Field(
        None,
        description="Error message if processing failed",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Additional processing metadata",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "processed_value": 6.8,
                "unit": "pH",
                "quality": "good",
                "processing_time_ms": 5.2,
                "metadata": {"voltage": 1.75, "calibrated": True},
            }
        }
    )


# =============================================================================
# Calibration Schemas
# =============================================================================


class CalibrationPoint(BaseModel):
    """Single calibration point."""

    raw: float = Field(
        ...,
        description="Raw sensor value",
        examples=[1500, 3000, 2048],
    )
    reference: float = Field(
        ...,
        description="Known reference value",
        examples=[7.0, 1413, 100.0],
    )


class SensorCalibrateRequest(BaseModel):
    """
    Sensor calibration request.
    """

    esp_id: str = Field(
        ...,
        pattern=r"^(ESP_[A-F0-9]{6,8}|MOCK_[A-Z0-9]+)$",
        description="ESP device ID",
    )
    gpio: int = Field(
        ...,
        ge=0,
        le=39,
        description="GPIO pin number",
    )
    sensor_type: str = Field(
        ...,
        description="Sensor type",
    )
    calibration_points: List[CalibrationPoint] = Field(
        ...,
        min_length=1,
        max_length=10,
        description="Calibration points",
    )
    method: Optional[str] = Field(
        None,
        pattern=r"^(linear|offset|polynomial)$",
        description="Calibration method",
    )
    save_to_config: bool = Field(
        True,
        description="Save calibration to database",
    )

    @field_validator("sensor_type")
    @classmethod
    def validate_sensor_type(cls, v: str) -> str:
        return v.lower().strip()


class SensorCalibrateResponse(BaseResponse):
    """
    Sensor calibration response.
    """

    calibration: Dict[str, Any] = Field(
        ...,
        description="Calculated calibration data",
    )
    sensor_type: str = Field(..., description="Sensor type")
    method: str = Field(..., description="Calibration method used")
    saved: bool = Field(..., description="Whether saved to database")
    message: Optional[str] = Field(None, description="Additional info")


# =============================================================================
# OneWire Scan (DS18B20 Support)
# =============================================================================


class OneWireDevice(BaseModel):
    """
    OneWire device found during bus scan.

    Used for DS18B20 and other 1-Wire sensors.
    Each device has a unique 64-bit ROM address.

    OneWire Multi-Device Support:
    - Multiple DS18B20 sensors can share the same GPIO pin (bus topology)
    - Each device is uniquely identified by its 64-bit ROM code
    - Scan results are enriched with already_configured flag to distinguish
      new devices from those already in the database
    """

    rom_code: str = Field(
        ...,
        min_length=16,
        max_length=16,
        description="OneWire ROM code (16 hex chars, e.g., '28FF641E8D3C0C79')",
        examples=["28FF641E8D3C0C79"],
    )
    device_type: str = Field(
        ...,
        description="Device type: ds18b20, ds18s20, ds1822, unknown",
        examples=["ds18b20"],
    )
    pin: int = Field(
        ...,
        ge=0,
        le=48,
        description="GPIO pin the device was found on",
    )
    # =========================================================================
    # OneWire Multi-Device Support (GPIO-Sharing)
    # =========================================================================
    already_configured: bool = Field(
        False,
        description="True if this device is already configured in database",
    )
    sensor_name: Optional[str] = Field(
        None,
        description="Sensor name if already configured (for display in UI)",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "rom_code": "28FF641E8D3C0C79",
                "device_type": "ds18b20",
                "pin": 4,
                "already_configured": False,
                "sensor_name": None,
            }
        }
    )


class OneWireScanRequest(BaseModel):
    """
    OneWire scan request parameters.
    """

    pin: int = Field(
        4,
        ge=0,
        le=48,
        description="GPIO pin for OneWire bus (default: 4)",
    )

    model_config = ConfigDict(json_schema_extra={"example": {"pin": 4}})


class OneWireScanResponse(BaseResponse):
    """
    Response from OneWire bus scan.

    Contains list of discovered devices with their ROM codes and types.

    OneWire Multi-Device Support:
    - Devices are enriched with already_configured flag
    - new_count indicates how many devices are NOT yet in database
    - Frontend can use this to show which devices are new vs already configured
    """

    devices: List[OneWireDevice] = Field(
        default_factory=list,
        description="List of discovered OneWire devices",
    )
    found_count: int = Field(
        ...,
        ge=0,
        description="Total number of devices found on bus",
    )
    # =========================================================================
    # OneWire Multi-Device Support (GPIO-Sharing)
    # =========================================================================
    new_count: int = Field(
        0,
        ge=0,
        description="Number of NEW devices (not yet configured in database)",
    )
    pin: int = Field(
        ...,
        description="GPIO pin that was scanned",
    )
    esp_id: str = Field(
        ...,
        description="ESP device that performed the scan",
    )
    scan_duration_ms: Optional[int] = Field(
        None,
        description="Scan duration in milliseconds",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "message": "Found 3 OneWire device(s) (2 new)",
                "devices": [
                    {
                        "rom_code": "28FF641E8D3C0C79",
                        "device_type": "ds18b20",
                        "pin": 4,
                        "already_configured": True,
                        "sensor_name": "Gewächshaus Temp",
                    },
                    {
                        "rom_code": "28FF123456789ABC",
                        "device_type": "ds18b20",
                        "pin": 4,
                        "already_configured": False,
                        "sensor_name": None,
                    },
                    {
                        "rom_code": "28FF987654321DEF",
                        "device_type": "ds18b20",
                        "pin": 4,
                        "already_configured": False,
                        "sensor_name": None,
                    },
                ],
                "found_count": 3,
                "new_count": 2,
                "pin": 4,
                "esp_id": "ESP_12AB34CD",
                "scan_duration_ms": 250,
            }
        }
    )


# =============================================================================
# On-Demand Measurement (Phase 2D)
# =============================================================================


class TriggerMeasurementResponse(BaseModel):
    """Response for trigger measurement endpoint."""

    success: bool = Field(..., description="Whether command was sent successfully")
    request_id: str = Field(..., description="Unique request ID for tracking")
    esp_id: str = Field(..., description="Target ESP device ID")
    gpio: int = Field(..., description="Target sensor GPIO")
    sensor_type: str = Field(..., description="Sensor type")
    message: str = Field(..., description="Status message")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "request_id": "550e8400-e29b-41d4-a716-446655440000",
                "esp_id": "ESP_12AB34CD",
                "gpio": 34,
                "sensor_type": "ph",
                "message": "Measurement command sent",
            }
        }
    )


class TriggerMeasurementRequest(BaseModel):
    """Optional parameters for on-demand sensor measurement."""

    sensor_type: Optional[str] = Field(
        None, description="Sensor type for multi-value GPIO disambiguation"
    )
    sample_count: Optional[int] = Field(
        None, ge=1, le=32, description="Number of ADC samples on ESP (EC/pH default: 30)"
    )
    sample_delay_ms: Optional[int] = Field(
        None, ge=0, le=1000, description="Delay between ADC samples in ms (EC/pH default: 100)"
    )
    timeout_ms: Optional[int] = Field(
        None, ge=1000, le=60000, description="Measurement timeout in ms (EC/pH default: 15000)"
    )
