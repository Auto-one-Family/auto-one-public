"""
Actuator Pydantic Schemas

Phase: 5 (Week 9-10) - API Layer
Priority: 🔴 CRITICAL
Status: IMPLEMENTED

Provides:
- Actuator configuration models
- Command request/response models
- Status and state models
- Emergency stop models

Consistency with El Trabajante:
- Commands: ON, OFF, PWM, TOGGLE
- Value range: 0.0-1.0 (server/ESP32 converts to 0-255)
- Server types: digital, pwm, servo
- ESP32 types: pump, valve, relay, pwm (auto-mapped to server types)
- MQTT Topic: kaiser/god/esp/{esp_id}/actuator/{gpio}/command

Type Mapping (ESP32 → Server):
- pump → digital
- valve → digital
- relay → digital
- pwm → pwm
- servo → servo

References:
- .claude/PI_SERVER_REFACTORING.md (Lines 146-154)
- El Trabajante/docs/Mqtt_Protocoll.md (Actuator topics)
- El Trabajante/include/actuator_types.h (ActuatorTypeTokens)
- db/models/actuator.py
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .common import BaseResponse, PaginatedResponse, TimestampMixin

# =============================================================================
# Actuator Types and Constants
# =============================================================================


# Server-side actuator types (internal classification)
ACTUATOR_TYPES = ["digital", "pwm", "servo"]

# El Trabajante ESP32 actuator types (from actuator_types.h)
ESP32_ACTUATOR_TYPES = ["pump", "valve", "pwm", "relay"]

# Mapping from ESP32 types to server types
# ESP32 uses specific device types, server uses generic electrical types
ACTUATOR_TYPE_MAPPING = {
    "pump": "digital",  # Pump is a digital on/off device
    "valve": "digital",  # Valve is a digital on/off device
    "relay": "digital",  # Relay is a digital on/off device
    "pwm": "pwm",  # PWM maps directly
    "digital": "digital",  # Direct mapping
    "servo": "servo",  # Servo maps directly
}

# All valid types (server + ESP32)
ALL_ACTUATOR_TYPES = list(set(ACTUATOR_TYPES + ESP32_ACTUATOR_TYPES))

ACTUATOR_COMMANDS = ["ON", "OFF", "PWM", "TOGGLE"]


def normalize_actuator_type(esp_type: str) -> str:
    """
    Normalize ESP32 actuator type to server type.

    Args:
        esp_type: Actuator type from ESP32 (pump, valve, relay, pwm)

    Returns:
        Server-side type (digital, pwm, servo)
    """
    return ACTUATOR_TYPE_MAPPING.get(esp_type.lower(), "digital")


# =============================================================================
# Actuator Configuration
# =============================================================================


class ActuatorConfigBase(BaseModel):
    """Base actuator configuration fields."""

    gpio: int = Field(
        ...,
        ge=0,
        le=39,
        description="GPIO pin number (0-39 for ESP32)",
    )
    actuator_type: str = Field(
        "digital",
        description="Actuator type (digital, pwm, servo)",
    )
    hardware_type: Optional[str] = Field(
        None,
        description="Original ESP32 hardware type (relay, pump, valve, pwm) preserved before normalization",
    )
    name: Optional[str] = Field(
        None,
        max_length=100,
        description="Human-readable actuator name",
        examples=["Water Pump", "Grow Light", "Vent Fan"],
    )

    @model_validator(mode="before")
    @classmethod
    def capture_hardware_type(cls, values: Any) -> Any:
        """
        Capture the raw ESP32 type into hardware_type before normalization.

        Must run before field_validator so the original value is still available.
        Only sets hardware_type if the incoming actuator_type is an ESP32 type
        and hardware_type was not explicitly provided.
        """
        if not isinstance(values, dict):
            return values
        raw_type = values.get("actuator_type", "")
        if raw_type and isinstance(raw_type, str):
            raw_lower = raw_type.lower()
            if raw_lower in ESP32_ACTUATOR_TYPES and not values.get("hardware_type"):
                values["hardware_type"] = raw_lower
        return values

    @field_validator("actuator_type")
    @classmethod
    def validate_actuator_type(cls, v: str) -> str:
        """
        Validate and normalize actuator type.

        Accepts both server types (digital, pwm, servo) and
        ESP32 types (pump, valve, relay, pwm) for compatibility.
        ESP32 types are normalized to server types.
        """
        v = v.lower()
        if v not in ALL_ACTUATOR_TYPES:
            raise ValueError(f"actuator_type must be one of: {ALL_ACTUATOR_TYPES}")
        # Normalize ESP32 types to server types
        return normalize_actuator_type(v)


class ActuatorConfigCreate(ActuatorConfigBase):
    """
    Actuator configuration create request.
    """

    esp_id: str = Field(
        ...,
        pattern=r"^(ESP_[A-F0-9]{6,8}|MOCK_[A-Z0-9]+)$",
        description="ESP device ID",
        examples=["ESP_D0B19C", "ESP_12AB34CD", "MOCK_TEST01"],
    )
    enabled: bool = Field(
        True,
        description="Whether actuator is enabled",
    )
    # Safety constraints
    max_runtime_seconds: Optional[int] = Field(
        None,
        ge=0,
        le=86400,
        description="Maximum continuous runtime in seconds (0 = no limit)",
    )
    cooldown_seconds: Optional[int] = Field(
        None,
        ge=0,
        le=3600,
        description="Minimum time between activations (seconds)",
    )
    # PWM/Servo specific
    pwm_frequency: Optional[int] = Field(
        None,
        ge=1,
        le=40000,
        description="PWM frequency in Hz (for PWM/servo types)",
    )
    servo_min_pulse: Optional[int] = Field(
        None,
        ge=500,
        le=2500,
        description="Servo minimum pulse width (microseconds)",
    )
    servo_max_pulse: Optional[int] = Field(
        None,
        ge=500,
        le=2500,
        description="Servo maximum pulse width (microseconds)",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Custom metadata",
    )
    # AUT-482: Manual actuators without offline rule must turn OFF on disconnect.
    fail_safe_on_disconnect: Optional[bool] = Field(
        True,
        description=(
            "AUT-482: Force OFF on MQTT disconnect when true (product default). "
            "False = keep last state (explicit opt-out)."
        ),
    )
    subzone_id: Optional[str] = Field(
        None,
        max_length=50,
        description="Subzone ID to assign this actuator to. Null/empty = remove from all subzones.",
    )
    # Multi-Zone Device Scope (T13-R2)
    device_scope: Optional[str] = Field(
        None,
        pattern=r"^(zone_local|multi_zone|mobile)$",
        description="Device scope: 'zone_local' (default), 'multi_zone', 'mobile'",
    )
    assigned_zones: Optional[List[str]] = Field(
        None,
        description="List of zone_ids this actuator can serve (for multi_zone/mobile)",
    )
    assigned_subzones: Optional[List[str]] = Field(
        None,
        description="List of subzone_ids for static multi-zone assignment",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "esp_id": "ESP_12AB34CD",
                "gpio": 5,
                "actuator_type": "digital",
                "name": "Water Pump",
                "enabled": True,
                "max_runtime_seconds": 1800,
                "cooldown_seconds": 300,
            }
        }
    )


class ActuatorConfigUpdate(BaseModel):
    """
    Actuator configuration update request.

    All fields optional - only provided fields are updated.
    """

    name: Optional[str] = Field(None, max_length=100)
    enabled: Optional[bool] = Field(None)
    max_runtime_seconds: Optional[int] = Field(None, ge=1, le=86400)
    cooldown_seconds: Optional[int] = Field(None, ge=0, le=3600)
    pwm_frequency: Optional[int] = Field(None, ge=1, le=40000)
    servo_min_pulse: Optional[int] = Field(None, ge=500, le=2500)
    servo_max_pulse: Optional[int] = Field(None, ge=500, le=2500)
    metadata: Optional[Dict[str, Any]] = Field(None)
    # AUT-120: Override ESP32 fail-safe-on-disconnect default.
    # None = unchanged (no override sent), True/False = explicit override.
    fail_safe_on_disconnect: Optional[bool] = Field(
        None,
        description=(
            "AUT-120: Override ESP32 fail-safe-on-disconnect default. "
            "None leaves the persisted value unchanged."
        ),
    )
    # Multi-Zone Device Scope (T13-R2)
    device_scope: Optional[str] = Field(
        None,
        pattern=r"^(zone_local|multi_zone|mobile)$",
        description="Device scope: 'zone_local', 'multi_zone', 'mobile'",
    )
    assigned_zones: Optional[List[str]] = Field(
        None,
        description="List of zone_ids this actuator can serve",
    )
    # NOTE (AUT-227): assigned_subzones removed from ActuatorConfigUpdate (read-only).
    # The DB column is DEPRECATED and is not consumed by any business-logic layer.
    # Reads are still served via ActuatorConfigResponse for backwards compatibility.


class ActuatorConfigResponse(ActuatorConfigBase, TimestampMixin):
    """
    Actuator configuration response.
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
        description="Whether actuator is enabled",
    )
    max_runtime_seconds: Optional[int] = Field(None)
    cooldown_seconds: Optional[int] = Field(None)
    pwm_frequency: Optional[int] = Field(None)
    servo_min_pulse: Optional[int] = Field(None)
    servo_max_pulse: Optional[int] = Field(None)
    metadata: Optional[Dict[str, Any]] = Field(None)
    # AUT-120: Fail-safe-on-disconnect override (None = ESP32 default).
    fail_safe_on_disconnect: Optional[bool] = Field(
        None,
        description=(
            "AUT-120: Persisted fail-safe override. None means the ESP32 "
            "applies its own default (true for critical actuators)."
        ),
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
    config_error_detail: Optional[str] = Field(
        None,
        description="Error detail if config_status=failed",
    )
    # Multi-Zone Device Scope (T13-R2)
    device_scope: Optional[str] = Field(
        None,
        description="Device scope: 'zone_local', 'multi_zone', 'mobile'",
    )
    assigned_zones: Optional[List[str]] = Field(
        None,
        description="List of zone_ids this actuator can serve",
    )
    assigned_subzones: Optional[List[str]] = Field(
        None,
        description="List of subzone_ids for static multi-zone",
    )
    # hardware_type from ORM (may differ from base class field: here nullable=True is explicit)
    hardware_type: Optional[str] = Field(
        None,
        description="Original ESP32 hardware type (relay, pump, valve, pwm)",
    )
    # Current state
    current_value: Optional[float] = Field(
        None,
        description="Current actuator value (0.0-1.0)",
    )
    is_active: Optional[bool] = Field(
        None,
        description="Whether actuator is currently active",
    )
    last_command_at: Optional[datetime] = Field(
        None,
        description="Last command timestamp",
    )
    subzone_id: Optional[str] = Field(
        None,
        description="Subzone this actuator is assigned to (derived from subzone_configs)",
    )
    subzone_warning: Optional[str] = Field(
        None,
        description="Warning if subzone assignment failed (actuator was saved successfully)",
    )
    correlation_id: Optional[str] = Field(
        None,
        description="Intent handle der letzten ausgelösten Config-Publish-Operation (falls verfügbar)",
    )
    request_id: Optional[str] = Field(
        None,
        description="Alias/Fallback-Handle zur Korrelation von REST-Antwort und WS-Config-Lifecycle",
    )

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "esp_id": "440e8400-e29b-41d4-a716-446655440000",
                "esp_device_id": "ESP_12AB34CD",
                "gpio": 5,
                "actuator_type": "digital",
                "name": "Water Pump",
                "enabled": True,
                "max_runtime_seconds": 1800,
                "cooldown_seconds": 300,
                "current_value": 0.0,
                "is_active": False,
                "last_command_at": "2025-01-01T10:00:00Z",
                "created_at": "2025-01-01T00:00:00Z",
                "updated_at": "2025-01-01T10:00:00Z",
            }
        },
    )


# =============================================================================
# Actuator Commands
# =============================================================================


class ActuatorCommand(BaseModel):
    """
    Actuator command request.

    Sent via REST API, validated by SafetyService, published to MQTT.
    """

    command: str = Field(
        ...,
        description="Command type: ON, OFF, PWM, TOGGLE",
    )
    value: float = Field(
        1.0,
        ge=0.0,
        le=1.0,
        description="Command value (0.0-1.0, used for PWM/servo)",
    )
    duration: int = Field(
        0,
        ge=0,
        le=86400,
        description="Duration in seconds (0 = unlimited until OFF)",
    )

    @field_validator("command")
    @classmethod
    def validate_command(cls, v: str) -> str:
        """Validate and normalize command."""
        v = v.upper()
        if v not in ACTUATOR_COMMANDS:
            raise ValueError(f"command must be one of: {ACTUATOR_COMMANDS}")
        return v

    @model_validator(mode="after")
    def validate_command_value(self) -> "ActuatorCommand":
        """Validate value based on command type."""
        if self.command == "ON" and self.value != 1.0:
            # For ON command, value should be 1.0
            self.value = 1.0
        elif self.command == "OFF" and self.value != 0.0:
            # For OFF command, value should be 0.0
            self.value = 0.0
        return self

    model_config = ConfigDict(
        json_schema_extra={"example": {"command": "PWM", "value": 0.75, "duration": 300}}
    )


class ActuatorCommandResponse(BaseResponse):
    """
    Actuator command response.

    HTTP 2xx bedeutet: Validierung + ggf. MQTT-Publish (oder bewusster No-Op ohne Publish).
    Geräte-Finalität (ob der Aktor wirklich geschaltet hat) folgt asynchron über
    MQTT-Topic ``.../actuator/.../response`` und WebSocket-Event ``actuator_response``;
    optional Korrelation über ``correlation_id`` in MQTT-Payload, History und WS.
    """

    esp_id: str = Field(..., description="ESP device ID")
    gpio: int = Field(..., description="GPIO pin")
    command: str = Field(..., description="Command sent")
    value: float = Field(..., description="Value sent (0.0-1.0)")
    correlation_id: str = Field(
        ...,
        description=(
            "UUID dieses Befehlsversuchs; identisch zu WS ``actuator_command`` / "
            "``actuator_command_failed`` und zur ``correlation_id`` im MQTT-Command-Payload (sofern gesendet)"
        ),
    )
    command_sent: bool = Field(
        ...,
        description=(
            "True, wenn der Server einen MQTT-Actuator-Command veröffentlicht hat; False bei No-Op-Delta "
            "(Zielzustand = Istzustand, kein Publish) oder wenn der Publish vor dem ACK des Brokers scheitert. "
            "Kein Nachweis, dass das Gerät den Befehl ausgeführt hat."
        ),
    )
    acknowledged: bool = Field(
        False,
        description=(
            "In dieser REST-Antwort immer False: Es wird nicht auf eine ESP-Bestätigung gewartet. "
            "Bestätigung/Ausführung nur über asynchrone Kanäle (MQTT response, WS, History)."
        ),
    )
    safety_warnings: List[str] = Field(
        default_factory=list,
        description=(
            "Nicht-blockierende SafetyService-Hinweise bei erfolgreicher Validierung; "
            "Details ggf. auch in Command-History-Metadaten"
        ),
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "esp_id": "ESP_12AB34CD",
                "gpio": 5,
                "command": "ON",
                "value": 1.0,
                "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
                "command_sent": True,
                "acknowledged": False,
                "safety_warnings": [],
            }
        }
    )


# =============================================================================
# Actuator Status
# =============================================================================


class ActuatorState(BaseModel):
    """
    Current actuator state.
    """

    gpio: int = Field(..., description="GPIO pin")
    mode: str = Field(..., description="Actuator mode (digital, pwm, servo)")
    value: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Current value (0.0-1.0)",
    )
    is_active: bool = Field(..., description="Whether actuator is active")
    last_command: Optional[str] = Field(None, description="Last command received")
    last_command_at: Optional[datetime] = Field(None, description="Last command timestamp")
    runtime_seconds: Optional[int] = Field(
        None,
        description="Current runtime if active (seconds)",
        ge=0,
    )


class ActuatorStatusResponse(BaseResponse):
    """
    Actuator status response.
    """

    esp_id: str = Field(..., description="ESP device ID")
    gpio: int = Field(..., description="GPIO pin")
    state: ActuatorState = Field(..., description="Current actuator state")
    config: Optional[ActuatorConfigResponse] = Field(
        None,
        description="Actuator configuration (if requested)",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "esp_id": "ESP_12AB34CD",
                "gpio": 5,
                "state": {
                    "gpio": 5,
                    "mode": "digital",
                    "value": 1.0,
                    "is_active": True,
                    "last_command": "ON",
                    "last_command_at": "2025-01-01T10:00:00Z",
                    "runtime_seconds": 300,
                },
            }
        }
    )


# =============================================================================
# Emergency Stop
# =============================================================================


class EmergencyStopRequest(BaseModel):
    """
    Emergency stop request.

    CRITICAL: Stops all actuators immediately, bypasses normal safety checks.
    """

    esp_id: Optional[str] = Field(
        None,
        pattern=r"^(ESP_[A-F0-9]{6,8}|MOCK_[A-Z0-9]+)$",
        description="Specific ESP to stop (None = all ESPs)",
    )
    gpio: Optional[int] = Field(
        None,
        ge=0,
        le=39,
        description="Specific GPIO to stop (None = all actuators on ESP)",
    )
    reason: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Emergency stop reason (for audit log)",
        examples=["Manual safety override", "Sensor malfunction detected"],
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "esp_id": None,
                "gpio": None,
                "reason": "Manual safety override - immediate stop all actuators",
            }
        }
    )


class EmergencyStopActuatorResult(BaseModel):
    """Result of an emergency stop command for a single actuator."""

    esp_id: str = Field(..., description="ESP device ID (external)")
    gpio: int = Field(..., description="GPIO pin")
    success: bool = Field(..., description="Whether OFF command was published")
    message: Optional[str] = Field(
        None, description="Error or status information for this actuator"
    )


class EmergencyStopDeviceResult(BaseModel):
    """Aggregated emergency stop results per device."""

    esp_id: str = Field(..., description="ESP device ID (external)")
    actuators: List[EmergencyStopActuatorResult] = Field(
        default_factory=list,
        description="Actuator-level results for this device",
    )


class EmergencyStopResponse(BaseResponse):
    """
    Not-Aus-Antwort.

    HTTP 2xx: Safety-Blockade gesetzt und pro GPIO MQTT-OFF versucht (siehe ``details``);
    zusätzlich Broadcast ``kaiser/broadcast/emergency`` und WS ``actuator_alert``.
    Es gibt keinen separaten „Emergency-ACK“-Pfad; GPIO-Antworten laufen wie üblich über
    ``actuator/.../response`` (Echo von ``correlation_id`` firmware-abhängig).
    """

    incident_correlation_id: str = Field(
        ...,
        description=(
            "Eine UUID pro Not-Aus-Request; verbindet Audit-Log, WS-Payload, Broadcast und "
            "pro-GPIO-MQTT-``correlation_id`` (Format incident:esp:gpio über Hilfsfunktion)"
        ),
    )
    devices_stopped: int = Field(
        ...,
        description="Anzahl ESPs, bei denen mindestens ein OFF erfolgreich publiziert wurde",
        ge=0,
    )
    actuators_stopped: int = Field(
        ...,
        description="Anzahl Aktoren, für die OFF erfolgreich publiziert wurde",
        ge=0,
    )
    reason: str = Field(..., description="Not-Aus-Grund (Audit)")
    timestamp: datetime = Field(..., description="Zeitstempel Server-seitig (UTC)")
    details: List[EmergencyStopDeviceResult] = Field(
        default_factory=list,
        description="Pro Gerät: je Aktor ob MQTT-Publish für OFF erfolgreich war",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "message": "Emergency stop executed",
                "incident_correlation_id": "550e8400-e29b-41d4-a716-446655440000",
                "devices_stopped": 5,
                "actuators_stopped": 12,
                "reason": "Manual safety override",
                "timestamp": "2025-01-01T10:00:00Z",
                "details": [
                    {
                        "esp_id": "ESP_12345678",
                        "actuators": [
                            {"esp_id": "ESP_12345678", "gpio": 5, "success": True},
                            {
                                "esp_id": "ESP_12345678",
                                "gpio": 6,
                                "success": False,
                                "message": "MQTT publish failed",
                            },
                        ],
                    }
                ],
            }
        }
    )


class ClearEmergencyRequest(BaseModel):
    """
    Clear emergency stop request.

    Releases emergency stop state so actuators can be controlled again.
    Sends clear_emergency command via MQTT to each ESP.
    """

    esp_id: Optional[str] = Field(
        None,
        pattern=r"^(ESP_[A-F0-9]{6,8}|MOCK_[A-Z0-9]+)$",
        description="Specific ESP to clear (None = all ESPs)",
    )
    reason: str = Field(
        "manual",
        min_length=1,
        max_length=200,
        description="Reason for clearing emergency (for audit)",
    )


class ClearEmergencyResponse(BaseResponse):
    """
    Aufheben der Not-Aus-Blockade.

    HTTP 2xx mit ``success=true``: MQTT ``clear_emergency`` an die betroffenen ESPs publiziert
    und Safety-Blockade serverseitig gelöst. Es wird nicht auf eine Gerätebestätigung gewartet;
    Folgezustände über MQTT/WS/Monitor.
    """

    devices_cleared: int = Field(
        ...,
        description="Anzahl ESPs, an die der Clear-Befehl publiziert wurde (unabhängig von Geräte-ACK)",
        ge=0,
    )
    reason: str = Field(..., description="Grund für Aufhebung (Audit)")
    timestamp: datetime = Field(..., description="Zeitstempel Server-seitig (UTC)")


# =============================================================================
# Actuator History
# =============================================================================


class ActuatorHistoryEntry(BaseModel):
    """
    Actuator command history entry.
    """

    id: Any = Field(..., description="History entry ID")
    gpio: int = Field(..., description="GPIO pin")
    actuator_type: str = Field(..., description="Actuator type")
    command_type: str = Field(..., description="Command sent")
    value: Optional[float] = Field(None, description="Value sent (None for stop commands)")
    success: bool = Field(..., description="Whether command succeeded")
    issued_by: Optional[str] = Field(None, description="Who issued command")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    metadata: Optional[Dict[str, Any]] = Field(None)
    timestamp: datetime = Field(..., description="Command timestamp")

    model_config = ConfigDict(from_attributes=True)


class ActuatorAggregation(BaseModel):
    """
    Aggregated runtime statistics computed from actuator history entries.
    """

    total_runtime_seconds: float = Field(..., description="Total ON time in seconds")
    total_cycles: int = Field(..., description="Number of ON commands (set with value > 0)")
    duty_cycle_percent: float = Field(..., description="Percentage of time the actuator was ON")
    avg_cycle_seconds: float = Field(..., description="Average duration per ON cycle in seconds")


class ActuatorHistoryResponse(BaseResponse):
    """
    Actuator history response with optional aggregation.
    """

    esp_id: str = Field(..., description="ESP device ID")
    gpio: Optional[int] = Field(None, description="GPIO filter (if applied)")
    entries: List[ActuatorHistoryEntry] = Field(
        default_factory=list,
        description="History entries",
    )
    total_count: int = Field(..., description="Number of entries returned (may be limited)", ge=0)
    aggregation: Optional[ActuatorAggregation] = Field(
        None, description="Runtime aggregation (when include_aggregation=true)"
    )
    from_time: Optional[datetime] = Field(None, description="Start of queried time range")
    to_time: Optional[datetime] = Field(None, description="End of queried time range")


# =============================================================================
# Query Filters
# =============================================================================


class ActuatorListFilter(BaseModel):
    """
    Filter parameters for actuator list endpoint.
    """

    esp_id: Optional[str] = Field(
        None,
        pattern=r"^(ESP_[A-F0-9]{6,8}|MOCK_[A-Z0-9]+)$",
        description="Filter by ESP device ID",
    )
    actuator_type: Optional[str] = Field(
        None,
        description="Filter by actuator type",
    )
    enabled: Optional[bool] = Field(
        None,
        description="Filter by enabled status",
    )
    is_active: Optional[bool] = Field(
        None,
        description="Filter by active status",
    )


# =============================================================================
# Paginated Responses
# =============================================================================


class ActuatorConfigListResponse(PaginatedResponse[ActuatorConfigResponse]):
    """
    Paginated list of actuator configurations.
    """

    pass
