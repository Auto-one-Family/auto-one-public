"""
Debug API Schemas - Mock ESP32 Management

Pydantic schemas for the debug/testing API that allows
frontend control of mock ESP32 devices.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class GPIOPathParams(BaseModel):
    """Path params for GPIO-scoped routes."""

    esp_id: str = Field(..., description="ESP device ID (format: ESP_XXXXXXXX)")
    gpio: int = Field(..., ge=0, le=39, description="GPIO pin number")


class MockSystemState(str, Enum):
    """ESP32 System States - matches El Trabajante implementation."""

    BOOT = "BOOT"
    WIFI_SETUP = "WIFI_SETUP"
    WIFI_CONNECTED = "WIFI_CONNECTED"
    MQTT_CONNECTING = "MQTT_CONNECTING"
    MQTT_CONNECTED = "MQTT_CONNECTED"
    AWAITING_USER_CONFIG = "AWAITING_USER_CONFIG"
    ZONE_CONFIGURED = "ZONE_CONFIGURED"
    SENSORS_CONFIGURED = "SENSORS_CONFIGURED"
    OPERATIONAL = "OPERATIONAL"
    LIBRARY_DOWNLOADING = "LIBRARY_DOWNLOADING"
    SAFE_MODE = "SAFE_MODE"
    ERROR = "ERROR"


class QualityLevel(str, Enum):
    """Sensor quality levels."""

    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    BAD = "bad"
    STALE = "stale"


# =============================================================================
# Sensor Schemas
# =============================================================================
class VariationPattern(str, Enum):
    """Sensor value variation patterns."""

    CONSTANT = "constant"
    RANDOM = "random"
    DRIFT = "drift"


class MockSensorConfig(BaseModel):
    """Configuration for a mock sensor."""

    gpio: int = Field(..., ge=0, le=39, description="GPIO pin number")
    sensor_type: str = Field(..., description="Sensor type (DS18B20, SHT31, pH, etc.)")
    name: Optional[str] = Field(None, description="Human-readable sensor name")
    subzone_id: Optional[str] = Field(None, description="Subzone assignment for this sensor")
    raw_value: Optional[float] = Field(
        None,
        description="Base sensor value (used as base_value for simulation). None = use plausible physical default.",
    )
    unit: str = Field("", description="Unit of measurement")
    quality: QualityLevel = Field(QualityLevel.GOOD, description="Data quality")
    raw_mode: bool = Field(True, description="Send raw values (Pi-Enhanced processing)")

    # =========================================================================
    # MULTI-VALUE SENSOR SUPPORT (I2C/OneWire) - DS18B20 Integration
    # =========================================================================
    interface_type: Optional[str] = Field(
        None,
        pattern=r"^(I2C|ONEWIRE|ANALOG|DIGITAL|UART)$",
        description="Interface type: I2C, ONEWIRE, ANALOG, DIGITAL, UART (auto-inferred from sensor_type if not provided)",
    )
    onewire_address: Optional[str] = Field(
        None,
        max_length=32,
        description="OneWire ROM address for DS18B20 sensors (16 hex chars, e.g., '28FF641E8D3C0C79', or SIM_ prefix for mocks)",
    )
    i2c_address: Optional[int] = Field(
        None, ge=0, le=127, description="I2C address for I2C sensors (e.g., 0x44 = 68 for SHT31)"
    )
    # =========================================================================

    # Simulation Parameters (NEW - Paket B.1)
    interval_seconds: float = Field(
        30.0, ge=1.0, le=3600.0, description="Sensor publishing interval in seconds"
    )
    variation_pattern: VariationPattern = Field(
        VariationPattern.CONSTANT, description="Value variation pattern: constant, random, drift"
    )
    variation_range: float = Field(
        0.0, ge=0.0, description="Variation range (for random/drift patterns)"
    )
    min_value: Optional[float] = Field(
        None, description="Minimum allowed value (defaults to raw_value - 10)"
    )
    max_value: Optional[float] = Field(
        None, description="Maximum allowed value (defaults to raw_value + 10)"
    )

    model_config = ConfigDict(use_enum_values=True)


class SetSensorValueRequest(BaseModel):
    """Request to set a sensor's value."""

    raw_value: float = Field(..., description="New raw value")
    quality: Optional[QualityLevel] = Field(None, description="Optional quality override")
    publish: bool = Field(True, description="Publish MQTT message after setting")

    model_config = ConfigDict(use_enum_values=True)


class BatchSensorValueRequest(BaseModel):
    """Request to set multiple sensor values at once."""

    values: Dict[int, float] = Field(..., description="Map of GPIO -> raw_value")
    publish: bool = Field(True, description="Publish batch MQTT message")


# =============================================================================
# Actuator Schemas
# =============================================================================
class MockActuatorConfig(BaseModel):
    """Configuration for a mock actuator."""

    gpio: int = Field(..., ge=0, le=39, description="GPIO pin number")
    actuator_type: str = Field("relay", description="Actuator type (relay, pump, valve, pwm)")
    name: Optional[str] = Field(None, description="Human-readable actuator name")
    subzone_id: Optional[str] = Field(None, description="Subzone assignment for this actuator")
    state: bool = Field(False, description="Current on/off state")
    pwm_value: float = Field(0.0, ge=0.0, le=1.0, description="PWM duty cycle (0.0-1.0)")
    min_value: float = Field(0.0, description="Minimum allowed value")
    max_value: float = Field(1.0, description="Maximum allowed value")


class SetActuatorStateRequest(BaseModel):
    """Request to set actuator state."""

    state: bool = Field(..., description="On/Off state")
    pwm_value: Optional[float] = Field(None, ge=0.0, le=1.0, description="PWM value if applicable")
    publish: bool = Field(True, description="Publish MQTT status after setting")


class ActuatorCommandType(str, Enum):
    """Actuator command types - matches ESP32 actuator protocol."""

    ON = "ON"
    OFF = "OFF"
    PWM = "PWM"
    TOGGLE = "TOGGLE"


class ActuatorCommandRequest(BaseModel):
    """
    Request to simulate an actuator command via MQTT flow (Paket G).

    This simulates the full MQTT command flow as if sent by the Logic Engine:
    1. Server publishes command to MQTT
    2. Mock-ESP receives and processes command
    3. Mock-ESP publishes response and status
    """

    command: ActuatorCommandType = Field(..., description="Command type: ON, OFF, PWM, TOGGLE")
    value: float = Field(1.0, ge=0.0, le=1.0, description="Value for PWM command (0.0-1.0)")
    duration: int = Field(0, ge=0, description="Auto-off duration in seconds (0 = unlimited)")

    model_config = ConfigDict(
        use_enum_values=True,
        json_schema_extra={"example": {"command": "ON", "value": 1.0, "duration": 60}},
    )


class ActuatorCommandResponse(BaseModel):
    """Response from actuator command execution."""

    success: bool = Field(..., description="Whether command was executed successfully")
    esp_id: str = Field(..., description="ESP device ID")
    gpio: int = Field(..., description="GPIO pin number")
    command: str = Field(..., description="Executed command")
    state: bool = Field(..., description="Current actuator state after command")
    pwm_value: int = Field(..., description="Current PWM value (0-255)")
    message: str = Field("", description="Response message")


# =============================================================================
# Mock ESP CRUD Schemas
# =============================================================================
class MockESPCreate(BaseModel):
    """Request to create a new mock ESP32."""

    esp_id: str = Field(
        ...,
        pattern=r"^(ESP_[A-F0-9]{6,8}|MOCK_[A-Z0-9]+)$",
        description="ESP device ID (format: ESP_XXXXXX to ESP_XXXXXXXX or MOCK_XXXXXX)",
    )
    zone_id: Optional[str] = Field(
        None, description="Zone ID (technical, auto-generated from zone_name if not provided)"
    )
    zone_name: Optional[str] = Field(
        None, description="Human-readable zone name (e.g., 'Zelt 1', 'Gewächshaus')"
    )
    master_zone_id: Optional[str] = Field(None, description="Master zone ID")
    subzone_id: Optional[str] = Field(None, description="Subzone ID")
    sensors: List[MockSensorConfig] = Field(
        default_factory=list, description="Initial sensor configurations"
    )
    actuators: List[MockActuatorConfig] = Field(
        default_factory=list, description="Initial actuator configurations"
    )
    auto_heartbeat: bool = Field(False, description="Enable automatic heartbeat")
    heartbeat_interval_seconds: int = Field(
        60, ge=5, le=300, description="Heartbeat interval in seconds"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "esp_id": "ESP_12AB34CD",
                "zone_id": "greenhouse",
                "master_zone_id": "main",
                "sensors": [
                    {"gpio": 4, "sensor_type": "DS18B20", "name": "Water Temp"},
                    {"gpio": 34, "sensor_type": "pH", "name": "pH Sensor"},
                ],
                "actuators": [{"gpio": 18, "actuator_type": "pump", "name": "Main Pump"}],
                "auto_heartbeat": True,
            }
        }
    )


class MockESPUpdate(BaseModel):
    """Request to update mock ESP configuration."""

    zone_id: Optional[str] = None
    master_zone_id: Optional[str] = None
    subzone_id: Optional[str] = None
    auto_heartbeat: Optional[bool] = None
    heartbeat_interval_seconds: Optional[int] = Field(None, ge=5, le=300)


# =============================================================================
# State Transition
# =============================================================================
class StateTransitionRequest(BaseModel):
    """Request to transition ESP to a new state."""

    state: MockSystemState = Field(..., description="Target system state")
    reason: Optional[str] = Field(None, description="Reason for state transition")

    model_config = ConfigDict(use_enum_values=True)


# =============================================================================
# Response Schemas
# =============================================================================
class MockSensorResponse(BaseModel):
    """Sensor state in response."""

    gpio: int
    sensor_type: str
    name: Optional[str]
    subzone_id: Optional[str]
    raw_value: float
    unit: str
    quality: str
    raw_mode: bool
    last_read: Optional[datetime]
    i2c_address: Optional[int] = None
    interface_type: Optional[str] = None
    device_scope: Optional[str] = "zone_local"
    assigned_zones: Optional[List[str]] = None


class MockActuatorResponse(BaseModel):
    """Actuator state in response."""

    gpio: int
    actuator_type: str
    name: Optional[str]
    state: bool
    pwm_value: float
    emergency_stopped: bool
    last_command: Optional[str]
    device_scope: Optional[str] = "zone_local"
    assigned_zones: Optional[List[str]] = None


class MockESPResponse(BaseModel):
    """Full mock ESP state response."""

    esp_id: str
    name: Optional[str] = None  # Human-readable device name (from DB)
    zone_id: Optional[str]
    zone_name: Optional[str] = None
    master_zone_id: Optional[str]
    subzone_id: Optional[str]
    system_state: str
    sensors: List[MockSensorResponse]
    actuators: List[MockActuatorResponse]
    auto_heartbeat: bool
    heap_free: int
    wifi_rssi: int
    uptime: int
    last_heartbeat: Optional[datetime]
    created_at: datetime
    connected: bool
    hardware_type: str = Field(default="MOCK_ESP32", description="Hardware type identifier")
    status: str = Field(default="online", description="Connection status (online/offline)")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "esp_id": "ESP_12AB34CD",
                "zone_id": "greenhouse",
                "system_state": "OPERATIONAL",
                "sensors": [
                    {
                        "gpio": 4,
                        "sensor_type": "DS18B20",
                        "name": "Water Temp",
                        "raw_value": 23.5,
                        "unit": "°C",
                        "quality": "good",
                        "raw_mode": True,
                    }
                ],
                "actuators": [
                    {
                        "gpio": 18,
                        "actuator_type": "pump",
                        "name": "Main Pump",
                        "state": False,
                        "pwm_value": 0.0,
                        "emergency_stopped": False,
                    }
                ],
                "heap_free": 245760,
                "wifi_rssi": -65,
                "uptime": 3600,
                "connected": True,
            }
        }
    )


class MockESPListResponse(BaseModel):
    """List of mock ESPs response."""

    success: bool = True
    data: List[MockESPResponse]
    total: int


class HeartbeatResponse(BaseModel):
    """Response after triggering heartbeat."""

    success: bool
    esp_id: str
    timestamp: datetime
    message_published: bool
    payload: Optional[Dict[str, Any]] = None


class CommandResponse(BaseModel):
    """Generic command response."""

    success: bool
    esp_id: str
    command: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class MqttMessageRecord(BaseModel):
    """Record of a published MQTT message."""

    topic: str
    payload: Dict[str, Any]
    timestamp: datetime
    qos: int = 1


class MockESPMessagesResponse(BaseModel):
    """Response with published MQTT messages."""

    success: bool
    esp_id: str
    messages: List[MqttMessageRecord]
    total: int
