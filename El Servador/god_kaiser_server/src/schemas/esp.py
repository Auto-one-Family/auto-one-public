"""
ESP Device Pydantic Schemas

Phase: 5 (Week 9-10) - API Layer
Priority: 🔴 CRITICAL
Status: IMPLEMENTED

Provides:
- ESP device registration and update models
- ESP health and status models
- Device discovery and assignment models

Consistency with El Trabajante:
- ESP ID format: ESP_XXXXXXXX (8 hex chars)
- Timestamps: Unix seconds
- Status values: online, offline, error, unknown

References:
- .claude/PI_SERVER_REFACTORING.md (Lines 125-133)
- El Trabajante/docs/Mqtt_Protocoll.md (Heartbeat topic)
- db/models/esp.py (ESPDevice model)
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .common import BaseResponse, PaginatedResponse, TimestampMixin

# =============================================================================
# ESP Device Base
# =============================================================================


class ESPDeviceBase(BaseModel):
    """Base ESP device fields."""

    device_id: str = Field(
        ...,
        pattern=r"^(ESP_[A-F0-9]{6,8}|MOCK_[A-Z0-9]+)$",
        description="ESP device ID (format: ESP_XXXXXX to ESP_XXXXXXXX for real devices or MOCK_XXX for mock devices)",
        examples=["ESP_D0B19C", "ESP_12AB34CD", "MOCK_TEST01"],
    )
    name: Optional[str] = Field(
        None,
        max_length=100,
        description="Human-readable device name",
        examples=["Greenhouse Sensor Node 1"],
    )
    zone_id: Optional[str] = Field(
        None,
        max_length=50,
        description="Zone identifier",
        examples=["greenhouse-zone-a"],
    )
    zone_name: Optional[str] = Field(
        None,
        max_length=100,
        description="Human-readable zone name",
        examples=["Greenhouse Zone A"],
    )
    is_zone_master: bool = Field(
        False,
        description="Whether device is zone master",
    )


class ESPDeviceCreate(ESPDeviceBase):
    """
    ESP device registration request.

    Used when manually registering an ESP or during auto-discovery.
    """

    ip_address: str = Field(
        ...,
        description="Device IP address",
        examples=["192.168.1.100"],
    )
    mac_address: str = Field(
        ...,
        pattern=r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$",
        description="Device MAC address",
        examples=["AA:BB:CC:DD:EE:FF"],
    )
    firmware_version: str = Field(
        "unknown",
        description="Firmware version",
        examples=["2.0.0"],
    )
    hardware_type: str = Field(
        "ESP32_WROOM",
        description="Hardware type (ESP32_WROOM, XIAO_ESP32_C3)",
        examples=["ESP32_WROOM", "XIAO_ESP32_C3"],
    )
    capabilities: Optional[Dict[str, Any]] = Field(
        None,
        description="Device capabilities (GPIO count, features)",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "device_id": "ESP_12AB34CD",
                "name": "Greenhouse Node 1",
                "zone_id": "greenhouse-a",
                "zone_name": "Greenhouse Zone A",
                "is_zone_master": False,
                "ip_address": "192.168.1.100",
                "mac_address": "AA:BB:CC:DD:EE:FF",
                "firmware_version": "2.0.0",
                "hardware_type": "ESP32_WROOM",
                "capabilities": {
                    "gpio_count": 39,
                    "adc_channels": 18,
                    "has_wifi": True,
                    "has_bluetooth": True,
                },
            }
        }
    )


class ESPDeviceUpdate(BaseModel):
    """
    ESP device update request.

    All fields optional - only provided fields are updated.
    """

    name: Optional[str] = Field(
        None,
        max_length=100,
        description="New device name",
    )
    zone_id: Optional[str] = Field(
        None,
        max_length=50,
        description="New zone ID",
    )
    zone_name: Optional[str] = Field(
        None,
        max_length=100,
        description="New zone name",
    )
    is_zone_master: Optional[bool] = Field(
        None,
        description="Set as zone master",
    )
    capabilities: Optional[Dict[str, Any]] = Field(
        None,
        description="Updated capabilities",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Custom metadata",
    )


class ZoneContextSummary(BaseModel):
    """Lightweight zone context summary for device inheritance."""

    zone_id: str
    zone_name: Optional[str] = None
    variety: Optional[str] = None
    substrate: Optional[str] = None
    growth_phase: Optional[str] = None
    plant_count: Optional[int] = None
    plant_age_days: Optional[int] = None
    days_to_harvest: Optional[int] = None
    responsible_person: Optional[str] = None


class SubzoneSummary(BaseModel):
    """Summary of a subzone assigned to an ESP device."""

    subzone_id: str = Field(..., description="Subzone identifier")
    subzone_name: str = Field(..., description="Human-readable subzone name")
    assigned_gpios: List[int] = Field(
        default_factory=list,
        description="GPIO pins assigned to this subzone",
    )
    sensor_count: int = Field(0, description="Number of sensors in this subzone", ge=0)
    actuator_count: int = Field(0, description="Number of actuators in this subzone", ge=0)
    is_active: bool = Field(True, description="Whether the subzone is active")

    model_config = ConfigDict(from_attributes=True)


class ESPDeviceResponse(ESPDeviceBase, TimestampMixin):
    """
    ESP device response model.

    Full device information including status and health.

    Note: ip_address, mac_address, firmware_version are Optional to support
    Mock ESP devices that may not have these hardware-specific values.
    """

    id: uuid.UUID = Field(
        ...,
        description="Unique identifier (UUID)",
    )

    ip_address: Optional[str] = Field(
        None,
        description="Device IP address (None for Mock ESPs without network)",
    )
    mac_address: Optional[str] = Field(
        None,
        description="Device MAC address (None for Mock ESPs without hardware)",
    )
    firmware_version: Optional[str] = Field(
        None,
        description="Firmware version (None for Mock ESPs)",
    )
    hardware_type: str = Field(
        ...,
        description="Hardware type (ESP32_WROOM, XIAO_ESP32_C3, MOCK_ESP32)",
    )
    capabilities: Optional[Dict[str, Any]] = Field(
        None,
        description="Device capabilities",
    )
    status: str = Field(
        "unknown",
        description="Device status (online, offline, error, unknown)",
    )
    last_seen: Optional[datetime] = Field(
        None,
        description="Last heartbeat timestamp",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Custom metadata",
    )
    # Counts from relationships
    sensor_count: int = Field(
        0,
        description="Number of configured sensors",
        ge=0,
    )
    actuator_count: int = Field(
        0,
        description="Number of configured actuators",
        ge=0,
    )

    # Mock-specific fields (only populated for Mock ESPs)
    auto_heartbeat: Optional[bool] = Field(
        None,
        description="Whether automatic heartbeat is enabled (Mock ESPs only)",
    )
    heartbeat_interval_seconds: Optional[int] = Field(
        None,
        description="Heartbeat interval in seconds (Mock ESPs only)",
        ge=1,
    )

    # Subzone summaries (T14-Fix-F: Hydration at page load)
    subzones: List["SubzoneSummary"] = Field(
        default_factory=list,
        description="Subzones assigned to this device with sensor/actuator counts.",
    )

    # Zone context inheritance (Phase 4)
    zone_context: Optional["ZoneContextSummary"] = Field(
        None,
        description="Inherited zone context (plant info, growth phase). Auto-populated when zone_id is set.",
    )

    # Soft-delete fields (T02-Fix1)
    deleted_at: Optional[datetime] = Field(
        None,
        description="Soft-delete timestamp. Present only for deleted devices (include_deleted=true).",
    )
    deleted_by: Optional[str] = Field(
        None,
        description="Username who soft-deleted this device.",
    )

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "device_id": "ESP_12AB34CD",
                "name": "Greenhouse Node 1",
                "zone_id": "greenhouse-a",
                "zone_name": "Greenhouse Zone A",
                "is_zone_master": False,
                "ip_address": "192.168.1.100",
                "mac_address": "AA:BB:CC:DD:EE:FF",
                "firmware_version": "2.0.0",
                "hardware_type": "ESP32_WROOM",
                "capabilities": {"gpio_count": 39},
                "status": "online",
                "last_seen": "2025-01-01T12:00:00Z",
                "metadata": None,
                "sensor_count": 3,
                "actuator_count": 2,
                "auto_heartbeat": None,
                "heartbeat_interval_seconds": None,
                "deleted_at": None,
                "deleted_by": None,
                "created_at": "2025-01-01T00:00:00Z",
                "updated_at": "2025-01-01T12:00:00Z",
            }
        },
    )


# =============================================================================
# GPIO Status (Phase 1 - GPIO-Status-Übertragung)
# =============================================================================


class GpioStatusItem(BaseModel):
    """
    Single GPIO pin status from ESP32 heartbeat.

    Represents the current reservation state of a GPIO pin as reported
    by the ESP32's GPIOManager. This is the SOURCE OF TRUTH for which
    GPIOs are actually in use on the physical device.

    Phase 2 Enhancement (2026-01-15):
    - Accepts Arduino pinMode raw values (1, 2, 5)
    - Normalizes to protocol enum (0, 1, 2) via field_validator
    - Maintains backwards-compatibility with deployed ESPs

    Reference: El Trabajante/docs/Mqtt_Protocoll.md (Heartbeat gpio_status)
    """

    gpio: int = Field(
        ...,
        ge=0,
        le=48,
        description="GPIO pin number (ESP32: 0-39, ESP32-C3: 0-21)",
    )
    owner: str = Field(
        ...,
        pattern=r"^(sensor|actuator|system|bus/.+)$",
        description="Owner category: sensor, actuator, system, or bus/<type>/<pin>",
    )
    component: str = Field(
        ...,
        max_length=32,
        description="Component name (e.g., DS18B20, pump_1, I2C_SDA)",
    )
    mode: int = Field(
        ...,
        ge=0,
        le=255,  # Tolerant: Accept any uint8 value (Arduino modes are 1, 2, 5)
        description="Pin mode (accepts Arduino raw values, normalized to 0-2)",
    )
    safe: bool = Field(
        ...,
        description="True if in safe mode (not actively used), False if actively used",
    )

    @field_validator("mode")
    @classmethod
    def normalize_gpio_mode(cls, v: int) -> int:
        """
        Normalize Arduino pinMode values to protocol enum.

        Arduino Core definitions (what ESP32 sends):
            INPUT           = 0x01 (1)
            OUTPUT          = 0x02 (2)
            INPUT_PULLUP    = 0x05 (5)

        Protocol enum (what Server/Frontend uses):
            0 = INPUT
            1 = OUTPUT
            2 = INPUT_PULLUP

        Mapping:
            Arduino INPUT (1)       → Protocol INPUT (0)
            Arduino OUTPUT (2)      → Protocol OUTPUT (1)
            Arduino INPUT_PULLUP (5) → Protocol INPUT_PULLUP (2)

        Args:
            v: Raw mode value from ESP (typically 1, 2, or 5)

        Returns:
            Normalized mode value (0, 1, or 2)

        Note:
            - ESP32 ALWAYS sends Arduino values (1, 2, 5)
            - Values 1, 2, 5 are ALWAYS normalized (assumed Arduino)
            - Value 0 is already Protocol INPUT (no Arduino equivalent)
            - Unknown values (3, 4, 6-255) are logged and passed through
        """
        # Mapping: Arduino → Protocol
        # ESP32 sends Arduino Core pinMode values, we normalize to protocol
        ARDUINO_TO_PROTOCOL = {
            1: 0,  # Arduino INPUT (0x01) → Protocol INPUT (0)
            2: 1,  # Arduino OUTPUT (0x02) → Protocol OUTPUT (1)
            5: 2,  # Arduino INPUT_PULLUP (0x05) → Protocol INPUT_PULLUP (2)
        }

        # Check if it's a known Arduino value and normalize
        if v in ARDUINO_TO_PROTOCOL:
            return ARDUINO_TO_PROTOCOL[v]

        # Value 0 is already Protocol INPUT (no Arduino equivalent sends 0)
        if v == 0:
            return 0

        # Unknown value (3, 4, 6-255) - log warning and pass through
        # This allows future Arduino modes to be tolerated
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(
            f"Unknown GPIO mode value: {v} (0x{v:02X}). "
            f"Passing through unchanged. "
            f"Known Arduino values: [1 (INPUT), 2 (OUTPUT), 5 (INPUT_PULLUP)]"
        )
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "gpio": 4,
                "owner": "sensor",
                "component": "DS18B20",
                "mode": 1,
                "safe": False,
            }
        }
    )


class GpioStatusList(BaseModel):
    """
    GPIO status list with validation.

    Used by heartbeat handler to validate incoming GPIO status data.
    """

    gpio_status: List[GpioStatusItem] = Field(
        default_factory=list,
        description="List of reserved GPIO pins",
    )
    gpio_reserved_count: int = Field(
        0,
        ge=0,
        description="Total count of reserved pins (should match len(gpio_status))",
    )

    @field_validator("gpio_reserved_count")
    @classmethod
    def validate_count_matches(cls, v: int, info) -> int:
        """Warn if count doesn't match array length."""
        gpio_status = info.data.get("gpio_status", [])
        if gpio_status and v != len(gpio_status):
            # Log warning but don't reject - ESP array is truth
            import logging

            logging.getLogger(__name__).warning(
                f"gpio_reserved_count ({v}) != len(gpio_status) ({len(gpio_status)})"
            )
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "gpio_status": [
                    {
                        "gpio": 4,
                        "owner": "sensor",
                        "component": "DS18B20",
                        "mode": 1,
                        "safe": False,
                    },
                    {
                        "gpio": 21,
                        "owner": "system",
                        "component": "I2C_SDA",
                        "mode": 1,
                        "safe": False,
                    },
                ],
                "gpio_reserved_count": 2,
            }
        }
    )


# =============================================================================
# GPIO Usage Status (Phase 2 - GPIO Validation)
# =============================================================================


class GpioUsageItem(BaseModel):
    """
    Einzelner GPIO-Belegungseintrag.

    Kombiniert DB-Daten mit ESP-gemeldetem Status für vollständige Übersicht.

    Phase: 2 (GPIO Validation)
    """

    gpio: int = Field(
        ...,
        description="GPIO pin number (0-39 for ESP32-WROOM)",
        ge=0,
        le=48,
    )
    owner: str = Field(
        ...,
        description="Owner type: sensor, actuator, system, or bus/<type>/<pin>",
        pattern=r"^(sensor|actuator|system|bus/.+)$",
    )
    component: str = Field(
        ...,
        description="Component type (e.g., DS18B20, pump, I2C_SDA)",
        max_length=32,
    )
    name: Optional[str] = Field(
        None,
        description="Human-readable name (if configured)",
        max_length=64,
    )
    id: Optional[str] = Field(
        None,
        description="Database ID of the sensor/actuator (UUID as string)",
    )
    source: str = Field(
        ...,
        description="Data source: database, esp_reported, or static",
        pattern=r"^(database|esp_reported|static)$",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "gpio": 4,
                "owner": "sensor",
                "component": "DS18B20",
                "name": "Temperature Sensor 1",
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "source": "database",
            }
        }
    )


class I2CBusInfo(BaseModel):
    """I2C Bus information with connected devices."""

    sda_pin: int = Field(..., description="SDA pin number (typically 21)")
    scl_pin: int = Field(..., description="SCL pin number (typically 22)")
    is_available: bool = Field(
        ..., description="Whether I2C bus is available (always true for shared bus)"
    )
    devices: List[dict] = Field(default_factory=list, description="List of I2C devices on bus")


class OneWireBusInfo(BaseModel):
    """OneWire Bus information with connected devices."""

    gpio: int = Field(..., description="OneWire bus GPIO pin")
    is_available: bool = Field(
        ..., description="Whether OneWire bus is available (always true for shared bus)"
    )
    devices: List[dict] = Field(default_factory=list, description="List of OneWire devices on bus")


class GpioStatusResponse(BaseModel):
    """
    Vollständiger GPIO-Belegungsstatus für einen ESP.

    Multi-Value Sensor Support (bus-aware):
    - I2C sensors share GPIO 21/22 (bus pins)
    - OneWire sensors share GPIO (bus pin)
    - Analog/Digital sensors have exclusive GPIO

    Phase: 2 (GPIO Validation) + Multi-Value Support
    """

    esp_id: str = Field(
        ...,
        description="ESP device ID",
    )
    available: List[int] = Field(
        default_factory=list,
        description="List of available GPIO pins (not in use)",
    )
    reserved: List[GpioUsageItem] = Field(
        default_factory=list,
        description="List of reserved/in-use GPIO pins (Analog/Digital only, backwards-compat)",
    )
    system: List[int] = Field(
        default_factory=list,
        description="List of system-reserved GPIO pins (Flash, UART, etc.)",
    )

    # =========================================================================
    # MULTI-VALUE SENSOR SUPPORT (Bus-aware)
    # =========================================================================
    reserved_gpios: List[int] = Field(
        default_factory=list,
        description="Exclusively reserved GPIOs (Analog/Digital sensors only)",
    )
    i2c_bus: Optional[I2CBusInfo] = Field(
        None,
        description="I2C bus status with connected devices (shared bus)",
    )
    onewire_buses: List[OneWireBusInfo] = Field(
        default_factory=list,
        description="OneWire bus status with connected devices (shared buses)",
    )
    # =========================================================================

    hardware_type: str = Field(
        "ESP32_WROOM",
        description="ESP32 hardware type (affects valid GPIO range)",
    )
    last_esp_report: Optional[str] = Field(
        None,
        description="Timestamp of last ESP GPIO status report (ISO format)",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "esp_id": "ESP_12AB34CD",
                "available": [4, 5, 12, 13, 14, 15, 16, 17, 18, 19, 23, 25, 26, 27, 32, 33, 34, 35],
                "reserved": [
                    {
                        "gpio": 21,
                        "owner": "system",
                        "component": "I2C_SDA",
                        "name": None,
                        "id": None,
                        "source": "static",
                    },
                    {
                        "gpio": 22,
                        "owner": "system",
                        "component": "I2C_SCL",
                        "name": None,
                        "id": None,
                        "source": "static",
                    },
                ],
                "system": [0, 1, 2, 3, 6, 7, 8, 9, 10, 11],
                "hardware_type": "ESP32_WROOM",
                "last_esp_report": "2026-01-08T12:00:00Z",
            }
        }
    )


# =============================================================================
# ESP Health
# =============================================================================


class ESPHealthMetrics(BaseModel):
    """
    ESP health metrics from heartbeat.

    Matches El Trabajante heartbeat payload format.
    """

    uptime: int = Field(
        ...,
        description="Seconds since boot",
        ge=0,
    )
    heap_free: int = Field(
        ...,
        description="Free heap memory (bytes)",
        ge=0,
    )
    wifi_rssi: int = Field(
        ...,
        description="WiFi signal strength (dBm, typically -100 to 0)",
        le=0,
    )
    sensor_count: int = Field(
        0,
        description="Number of active sensors",
        ge=0,
    )
    actuator_count: int = Field(
        0,
        description="Number of active actuators",
        ge=0,
    )
    handover_contract_reject: Optional[int] = Field(
        0,
        ge=0,
        description="Backward-compatible total reject counter (startup + runtime)",
    )
    handover_contract_reject_startup: Optional[int] = Field(
        0,
        ge=0,
        description="Reject counter in first second after MQTT connect",
    )
    handover_contract_reject_runtime: Optional[int] = Field(
        0,
        ge=0,
        description="Reject counter after startup window",
    )
    timestamp: int = Field(
        ...,
        description="Heartbeat timestamp (Unix seconds)",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "uptime": 3600,
                "heap_free": 245760,
                "wifi_rssi": -65,
                "sensor_count": 3,
                "actuator_count": 2,
                "handover_contract_reject": 0,
                "handover_contract_reject_startup": 0,
                "handover_contract_reject_runtime": 0,
                "timestamp": 1735818000,
            }
        }
    )


class SessionAnnouncePayload(BaseModel):
    """Session announce payload with canonical handover_epoch field."""

    handover_epoch: int = Field(..., ge=1, description="Canonical handover epoch")
    reason: str = Field(..., pattern=r"^(boot|reconnect)$", description="Session announce reason")
    ts_ms: int = Field(..., ge=0, description="Publish timestamp in milliseconds")
    connect_seq: Optional[int] = Field(None, ge=0, description="Optional connect sequence counter")

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "SessionAnnouncePayload":
        """Accept legacy session_epoch while normalizing to handover_epoch."""
        if not isinstance(payload, dict):
            raise ValueError("session announce payload must be object")
        normalized = dict(payload)
        epoch_raw = payload.get("handover_epoch", payload.get("session_epoch"))
        normalized["handover_epoch"] = epoch_raw

        # Legacy firmware may omit reason; infer from epoch as best effort.
        reason = normalized.get("reason")
        if not isinstance(reason, str) or not reason:
            epoch_int = 0
            try:
                epoch_int = int(epoch_raw)
            except (TypeError, ValueError):
                epoch_int = 0
            normalized["reason"] = "reconnect" if epoch_int > 1 else "boot"

        # Legacy firmware publishes boot_ts (seconds, sometimes string) instead of ts_ms.
        ts_ms_raw = normalized.get("ts_ms", payload.get("boot_ts", payload.get("ts")))
        if ts_ms_raw is not None:
            try:
                ts_ms = int(ts_ms_raw)
            except (TypeError, ValueError) as exc:
                raise ValueError("session announce ts_ms/boot_ts must be numeric") from exc
            if ts_ms > 0 and ts_ms < 10_000_000_000:
                ts_ms *= 1000
            normalized["ts_ms"] = ts_ms
        else:
            # Keep compatibility with minimal legacy payloads.
            normalized["ts_ms"] = 0

        return cls(**normalized)


class ESPHealthResponse(BaseResponse):
    """
    ESP health check response.
    """

    device_id: str = Field(
        ...,
        description="ESP device ID",
    )
    status: str = Field(
        ...,
        description="Device status",
    )
    metrics: Optional[ESPHealthMetrics] = Field(
        None,
        description="Latest health metrics (if available)",
    )
    last_seen: Optional[datetime] = Field(
        None,
        description="Last heartbeat timestamp",
    )
    uptime_formatted: Optional[str] = Field(
        None,
        description="Human-readable uptime (e.g., '1d 2h 30m')",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "device_id": "ESP_12AB34CD",
                "status": "online",
                "metrics": {
                    "uptime": 86400,
                    "heap_free": 200000,
                    "wifi_rssi": -55,
                    "sensor_count": 3,
                    "actuator_count": 2,
                    "timestamp": 1735818000,
                },
                "last_seen": "2025-01-01T12:00:00Z",
                "uptime_formatted": "1d 0h 0m",
            }
        }
    )


class ESPHealthSummary(BaseModel):
    """
    Summary health status for one ESP.
    """

    device_id: str = Field(..., description="ESP device ID")
    name: Optional[str] = Field(None, description="Device name")
    status: str = Field(..., description="online, offline, error, unknown")
    last_seen: Optional[datetime] = Field(None)
    heap_free: Optional[int] = Field(None, description="Free heap (bytes)")
    wifi_rssi: Optional[int] = Field(None, description="WiFi RSSI (dBm)")


class ESPHealthSummaryResponse(BaseResponse):
    """
    Summary health for all ESPs.
    """

    total_devices: int = Field(..., description="Total registered devices", ge=0)
    online_count: int = Field(..., description="Online devices", ge=0)
    offline_count: int = Field(..., description="Offline devices", ge=0)
    error_count: int = Field(..., description="Devices with errors", ge=0)
    devices: List[ESPHealthSummary] = Field(
        default_factory=list,
        description="Per-device health summary",
    )


class ComponentHealthScoreResponse(BaseModel):
    """Phase K4 L2.4 — Health score 0–100 per device for Inventar/K1."""

    device_id: str = Field(..., description="ESP device ID")
    score: float = Field(..., ge=0, le=100, description="Aggregated health score 0–100")
    factors: dict = Field(
        default_factory=dict,
        description="Per-factor scores (online, error_rate_24h, data_quality, maintenance, uptime)",
    )


# =============================================================================
# ESP Configuration
# =============================================================================


# =============================================================================
# ESP32 Config-Push Architektur
# =============================================================================
#
# Config-Payloads für ESP32-Geräte werden über folgenden Pfad generiert:
#
#   1. Sensor/Actuator CRUD-Operation (api/v1/sensors.py, api/v1/actuators.py)
#   2. ConfigPayloadBuilder.build_combined_config() (services/config_builder.py)
#   3. ConfigMappingEngine mit DEFAULT_SENSOR_MAPPINGS (core/config_mapping.py)
#   4. esp_service.send_config() → MQTT Publisher
#
# Feld-Mappings für den ESP32-Payload werden in core/config_mapping.py definiert.
#
# HINWEIS: Ein manueller Config-Push-Endpoint existiert NICHT.
# Configs werden automatisch nach Sensor/Actuator CRUD-Operationen gesendet.
# =============================================================================


class ESPConfigUpdate(BaseModel):
    """
    ESP system configuration update request (WiFi, MQTT, intervals).

    Note: This schema is for SYSTEM-LEVEL settings only (WiFi, MQTT broker, intervals).
    Sensor/Actuator configuration is handled automatically via the CRUD APIs
    (see api/v1/sensors.py and api/v1/actuators.py).
    """

    wifi_ssid: Optional[str] = Field(
        None,
        max_length=32,
        description="New WiFi SSID",
    )
    wifi_password: Optional[str] = Field(
        None,
        max_length=64,
        description="New WiFi password",
    )
    mqtt_broker: Optional[str] = Field(
        None,
        description="New MQTT broker address",
    )
    mqtt_port: Optional[int] = Field(
        None,
        ge=1,
        le=65535,
        description="New MQTT broker port",
    )
    report_interval_ms: Optional[int] = Field(
        None,
        ge=1000,
        le=300000,
        description="Sensor report interval (ms)",
    )
    heartbeat_interval_ms: Optional[int] = Field(
        None,
        ge=10000,
        le=300000,
        description="Heartbeat interval (ms)",
    )
    log_level: Optional[str] = Field(
        None,
        pattern=r"^(DEBUG|INFO|WARNING|ERROR)$",
        description="Log level",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "report_interval_ms": 30000,
                "heartbeat_interval_ms": 60000,
                "log_level": "INFO",
            }
        }
    )


class ESPConfigResponse(BaseResponse):
    """
    ESP config update response.
    """

    device_id: str = Field(..., description="ESP device ID")
    config_sent: bool = Field(..., description="Whether config was sent via MQTT")
    config_acknowledged: bool = Field(
        False,
        description="Whether ESP acknowledged config (requires ACK)",
    )


# =============================================================================
# ESP Commands
# =============================================================================


class ESPRestartRequest(BaseModel):
    """
    ESP restart command request.
    """

    delay_seconds: int = Field(
        0,
        ge=0,
        le=60,
        description="Delay before restart (seconds)",
    )
    reason: Optional[str] = Field(
        None,
        max_length=200,
        description="Restart reason (for logging)",
    )


class ESPResetRequest(BaseModel):
    """
    ESP factory reset command request.
    """

    confirm: bool = Field(
        ...,
        description="Must be True to confirm factory reset",
    )
    preserve_wifi: bool = Field(
        False,
        description="Preserve WiFi credentials during reset",
    )


class ESPCommandResponse(BaseResponse):
    """
    ESP command response.
    """

    device_id: str = Field(..., description="ESP device ID")
    command: str = Field(..., description="Command sent (restart, reset, etc.)")
    command_sent: bool = Field(..., description="Whether command was published to MQTT")


# =============================================================================
# ESP Assignment
# =============================================================================


class AssignKaiserRequest(BaseModel):
    """
    Assign ESP to Kaiser node request.
    """

    kaiser_id: str = Field(
        ...,
        description="Kaiser node ID to assign ESP to",
    )

    model_config = ConfigDict(json_schema_extra={"example": {"kaiser_id": "KAISER_001"}})


class AssignKaiserResponse(BaseResponse):
    """
    Kaiser assignment response.
    """

    device_id: str = Field(..., description="ESP device ID")
    kaiser_id: str = Field(..., description="Assigned Kaiser ID")
    previous_kaiser_id: Optional[str] = Field(
        None,
        description="Previous Kaiser ID (if reassigned)",
    )


# =============================================================================
# ESP Discovery
# =============================================================================


class DiscoveredESP(BaseModel):
    """
    Discovered ESP device from network scan.
    """

    device_id: str = Field(..., description="ESP device ID")
    ip_address: str = Field(..., description="IP address")
    mac_address: str = Field(..., description="MAC address")
    firmware_version: str = Field(..., description="Firmware version")
    hardware_type: str = Field(..., description="Hardware type")
    is_registered: bool = Field(..., description="Whether already registered in DB")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "device_id": "ESP_AABBCCDD",
                "ip_address": "192.168.1.150",
                "mac_address": "11:22:33:44:55:66",
                "firmware_version": "2.0.0",
                "hardware_type": "ESP32_WROOM",
                "is_registered": False,
            }
        }
    )


class ESPDiscoveryResponse(BaseResponse):
    """
    ESP discovery response.
    """

    discovered_count: int = Field(
        ...,
        description="Number of discovered devices",
        ge=0,
    )
    new_count: int = Field(
        ...,
        description="Number of unregistered devices",
        ge=0,
    )
    devices: List[DiscoveredESP] = Field(
        default_factory=list,
        description="List of discovered devices",
    )
    scan_duration_ms: int = Field(
        ...,
        description="Scan duration in milliseconds",
        ge=0,
    )


# =============================================================================
# Query Filters
# =============================================================================


class ESPListFilter(BaseModel):
    """
    Filter parameters for ESP list endpoint.
    """

    zone_id: Optional[str] = Field(None, description="Filter by zone ID")
    status: Optional[str] = Field(
        None,
        pattern=r"^(online|offline|error|unknown)$",
        description="Filter by status",
    )
    kaiser_id: Optional[str] = Field(None, description="Filter by Kaiser ID")
    hardware_type: Optional[str] = Field(None, description="Filter by hardware type")
    is_zone_master: Optional[bool] = Field(None, description="Filter zone masters only")


# =============================================================================
# Paginated Responses
# =============================================================================


class ESPDeviceListResponse(PaginatedResponse[ESPDeviceResponse]):
    """
    Paginated list of ESP devices.
    """

    pass


# =============================================================================
# Config Response (Phase 4 - Detailed Config Feedback)
# =============================================================================


class ConfigFailureItem(BaseModel):
    """
    Single configuration failure from ESP32.

    Used in config_response MQTT messages when one or more items
    fail to configure. Provides detailed error information for
    user feedback and debugging.

    Phase: 4 (Detailed Config Feedback)
    Reference: El Trabajante/src/models/config_types.h (ConfigFailureItem)
    """

    type: str = Field(
        ...,
        pattern=r"^(sensor|actuator)$",
        description="Component type that failed",
    )
    gpio: int = Field(
        ...,
        ge=0,
        le=48,
        description="GPIO pin number",
    )
    error_code: int = Field(
        ...,
        ge=0,
        description="Error code from error_codes.h (e.g., 1001 for GPIO_RESERVED)",
    )
    error: str = Field(
        ...,
        max_length=32,
        description="Short error name (e.g., GPIO_CONFLICT, MISSING_FIELD)",
    )
    detail: Optional[str] = Field(
        None,
        max_length=200,
        description="Human-readable error details",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "type": "sensor",
                "gpio": 5,
                "error_code": 1002,
                "error": "GPIO_CONFLICT",
                "detail": "GPIO 5 reserved by actuator (pump_1)",
            }
        }
    )


class ConfigResponsePayload(BaseModel):
    """
    Extended config_response payload with failures array.

    Supports three status values:
    - "success": All items configured successfully
    - "partial_success": Some items succeeded, some failed
    - "error" / "failed": All items failed

    Backward compatible with legacy config_response format
    (single failed_item instead of failures array).

    Phase: 4 (Detailed Config Feedback)
    Reference: El Trabajante/docs/Mqtt_Protocoll.md (config_response topic)
    """

    status: str = Field(
        ...,
        pattern=r"^(success|partial_success|error|failed)$",
        description="Overall configuration status",
    )
    type: str = Field(
        ...,
        pattern=r"^(sensor|actuator|zone|system|wifi|unknown)$",
        description="Configuration type",
    )
    count: int = Field(
        0,
        ge=0,
        description="Number of successfully configured items",
    )
    failed_count: int = Field(
        0,
        ge=0,
        description="Number of failed items (Phase 4)",
    )
    message: str = Field(
        "",
        max_length=500,
        description="Human-readable status message",
    )
    error_code: Optional[str] = Field(
        None,
        max_length=32,
        description="Legacy: Single error code (for backward compat)",
    )
    failed_item: Optional[Dict[str, Any]] = Field(
        None,
        description="Legacy: Single failed item (for backward compat)",
    )
    failures: List[ConfigFailureItem] = Field(
        default_factory=list,
        description="Phase 4: Array of failure details (max 10)",
    )
    failures_truncated: Optional[bool] = Field(
        None,
        description="True if failures were truncated (more than MAX_CONFIG_FAILURES)",
    )
    total_failures: Optional[int] = Field(
        None,
        description="Total failure count if truncated",
    )

    model_config = ConfigDict(
        extra="allow",  # Allow unknown fields for forward compatibility
        json_schema_extra={
            "example": {
                "status": "partial_success",
                "type": "sensor",
                "count": 2,
                "failed_count": 1,
                "message": "2 configured, 1 failed",
                "failures": [
                    {
                        "type": "sensor",
                        "gpio": 5,
                        "error_code": 1002,
                        "error": "GPIO_CONFLICT",
                        "detail": "GPIO 5 reserved by actuator (pump_1)",
                    }
                ],
            }
        },
    )


# =============================================================================
# Discovery/Approval Schemas
# =============================================================================


class PendingESPDevice(BaseModel):
    """
    Pending ESP device awaiting approval.

    Represents a device that has been discovered via heartbeat
    but has not yet been approved by an administrator.

    Time Fields:
    - discovered_at: When device was FIRST discovered (historical)
    - last_seen: When device was LAST active (for UI "vor X Zeit" display)
    """

    device_id: str = Field(
        ...,
        description="ESP device ID",
        examples=["ESP_D0B19C", "ESP_12AB34CD"],
    )
    discovered_at: datetime = Field(
        ...,
        description="When device was first discovered (historical)",
    )
    last_seen: Optional[datetime] = Field(
        None,
        description="When device was last active (last heartbeat). Use this for 'vor X Zeit' display.",
    )
    zone_id: Optional[str] = Field(
        None,
        description="Zone ID from heartbeat",
    )
    heap_free: Optional[int] = Field(
        None,
        description="Free heap memory from latest heartbeat (bytes)",
    )
    wifi_rssi: Optional[int] = Field(
        None,
        description="WiFi signal strength from latest heartbeat (dBm)",
    )
    sensor_count: int = Field(
        0,
        description="Number of sensors reported in latest heartbeat",
    )
    actuator_count: int = Field(
        0,
        description="Number of actuators reported in latest heartbeat",
    )
    heartbeat_count: int = Field(
        0,
        description="Number of heartbeats received while pending",
    )
    ip_address: Optional[str] = Field(
        None,
        description="IP address from heartbeat (wifi_ip field)",
    )
    hardware_type: Optional[str] = Field(
        None,
        description="Hardware type (e.g., ESP32_WROOM)",
    )

    model_config = ConfigDict(from_attributes=True)


class PendingDevicesListResponse(BaseResponse):
    """
    List of pending ESP devices awaiting approval.
    """

    devices: List[PendingESPDevice] = Field(
        default_factory=list,
        description="List of pending devices",
    )
    count: int = Field(
        0,
        description="Total pending devices",
    )


class ESPApprovalRequest(BaseModel):
    """
    Request to approve an ESP device.

    Optional fields allow admin to assign name and zone during approval.
    """

    name: Optional[str] = Field(
        None,
        max_length=100,
        description="Optional device name",
        examples=["Greenhouse Sensor Node 1"],
    )
    zone_id: Optional[str] = Field(
        None,
        max_length=50,
        description="Optional zone assignment",
        examples=["greenhouse-zone-a"],
    )
    zone_name: Optional[str] = Field(
        None,
        max_length=100,
        description="Optional zone name",
        examples=["Greenhouse Zone A"],
    )


class ESPRejectionRequest(BaseModel):
    """
    Request to reject an ESP device.

    Reason is required for audit trail.
    """

    reason: str = Field(
        ...,
        max_length=500,
        min_length=1,
        description="Reason for rejection (required)",
        examples=["Unknown device - not part of authorized hardware inventory"],
    )


class ESPApprovalResponse(BaseResponse):
    """
    Response after approving or rejecting an ESP device.
    """

    device_id: str = Field(
        ...,
        description="ESP device ID",
    )
    status: str = Field(
        ...,
        description="New device status (approved or rejected)",
    )
    approved_by: Optional[str] = Field(
        None,
        description="Username who approved (if approved)",
    )
    approved_at: Optional[datetime] = Field(
        None,
        description="Approval timestamp (if approved)",
    )
    rejection_reason: Optional[str] = Field(
        None,
        description="Rejection reason (if rejected)",
    )
