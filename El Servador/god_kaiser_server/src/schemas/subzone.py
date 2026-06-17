"""
Subzone Management Pydantic Schemas

Phase: 9 - Subzone Management
Status: IMPLEMENTED

Provides:
- Subzone assignment request/response models
- Subzone ACK payload model (from ESP32)
- Safe-mode control models
- Subzone info display model

Consistency with El Trabajante:
- subzone_id format: lowercase letters, numbers, underscores (max 32 chars)
- parent_zone_id: Must match ESP's assigned zone_id
- assigned_gpios: Array of GPIO pin numbers
- safe_mode_active: Boolean, default True
- Timestamps: Unix seconds

References:
- El Trabajante/docs/system-flows/09-subzone-management-flow.md
- El Trabajante/src/models/system_types.h (SubzoneConfig struct)
"""

import re
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .common import BaseResponse

# =============================================================================
# Subzone Assignment Request/Response
# =============================================================================


class SubzoneAssignRequest(BaseModel):
    """
    Subzone assignment request from Frontend/API.

    Used to assign GPIO pins to a subzone via MQTT.
    ESP will receive this via: kaiser/{kaiser_id}/esp/{esp_id}/subzone/assign
    """

    subzone_id: str = Field(
        ...,
        min_length=1,
        max_length=32,
        description="Unique subzone identifier (max 32 chars for NVS compatibility)",
        examples=["irrigation_section_A", "climate_control"],
    )
    subzone_name: Optional[str] = Field(
        None,
        max_length=100,
        description="Human-readable subzone name",
        examples=["Irrigation Section A", "Climate Control Zone"],
    )
    parent_zone_id: Optional[str] = Field(
        None,
        max_length=50,
        description="Parent zone ID (if empty, uses ESP's zone_id)",
        examples=["greenhouse_zone_1"],
    )
    assigned_gpios: List[int] = Field(
        ...,
        min_length=0,
        max_length=20,
        description="GPIO pin numbers to assign to this subzone (empty = create subzone only)",
        examples=[[4, 5, 6], [18, 21]],
    )
    safe_mode_active: bool = Field(
        True,
        description="Whether subzone starts in safe-mode (default: true for safety)",
    )
    custom_data: Optional[dict] = Field(
        None,
        description="Subzone-specific metadata (plant info, material, notes)",
        examples=[{"variety": "Wedding Cake", "substrate": "Coco", "notes": "Drip line A"}],
    )

    @field_validator("subzone_id")
    @classmethod
    def validate_subzone_id_format(cls, v: str) -> str:
        """Validate subzone_id contains only ASCII letters, numbers, and underscores."""
        if not re.match(r"^[A-Za-z0-9_]+$", v):
            raise ValueError("subzone_id must contain only ASCII letters, numbers, and underscores")
        return v.lower()

    @field_validator("assigned_gpios")
    @classmethod
    def validate_gpios(cls, v: List[int]) -> List[int]:
        """Validate GPIO pin numbers."""
        for gpio in v:
            if gpio < 0 or gpio > 39:
                raise ValueError(f"Invalid GPIO pin: {gpio}. Must be 0-39.")
        # Remove duplicates while preserving order
        seen = set()
        unique = []
        for gpio in v:
            if gpio not in seen:
                seen.add(gpio)
                unique.append(gpio)
        return unique

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "subzone_id": "irrigation_section_A",
                "subzone_name": "Irrigation Section A",
                "parent_zone_id": "greenhouse_zone_1",
                "assigned_gpios": [4, 5, 6],
                "safe_mode_active": False,
            }
        }
    )


class SubzoneAssignResponse(BaseResponse):
    """
    Subzonenzuweisung — REST-Antwort.

    **Finalität:** HTTP 2xx = DB-Update und MQTT-Publish abgeschlossen; **kein**
    ``MQTTCommandBridge``-Warten auf ``subzone/ack``. Bestätigung und NVS-Seite des ESP nur
    asynchron über MQTT ``subzone/ack`` und WS ``subzone_assignment``.
    """

    device_id: str = Field(
        ...,
        description="ESP device ID that was assigned",
        examples=["ESP_AB12CD"],
    )
    subzone_id: str = Field(
        ...,
        description="Assigned subzone ID",
        examples=["irrigation_section_A"],
    )
    assigned_gpios: List[int] = Field(
        ...,
        description="GPIO pins assigned to this subzone",
        examples=[[4, 5, 6]],
    )
    mqtt_topic: str = Field(
        ...,
        description="MQTT topic used for assignment",
        examples=["kaiser/god/esp/ESP_AB12CD/subzone/assign"],
    )
    mqtt_sent: bool = Field(
        ...,
        description=(
            "True, wenn die Zuweisung an den Broker publiziert wurde; "
            "kein ACK-Flag in dieser Antwort — Geräte-Finalität nur über MQTT/WS"
        ),
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "message": "Subzone assignment sent to ESP",
                "device_id": "ESP_AB12CD",
                "subzone_id": "irrigation_section_A",
                "assigned_gpios": [4, 5, 6],
                "mqtt_topic": "kaiser/god/esp/ESP_AB12CD/subzone/assign",
                "mqtt_sent": True,
            }
        }
    )


class SubzoneRemoveResponse(BaseResponse):
    """
    Subzone entfernt — wie ``SubzoneAssignResponse`` ohne Bridge-Wait auf ACK.
    """

    device_id: str = Field(
        ...,
        description="ESP device ID",
        examples=["ESP_AB12CD"],
    )
    subzone_id: str = Field(
        ...,
        description="Removed subzone ID",
        examples=["irrigation_section_A"],
    )
    mqtt_topic: str = Field(
        ...,
        description="MQTT topic used for removal",
        examples=["kaiser/god/esp/ESP_AB12CD/subzone/remove"],
    )
    mqtt_sent: bool = Field(
        ...,
        description=(
            "True, wenn die Remove-Nachricht an den Broker publiziert wurde; "
            "Bestätigung asynchron über ``subzone/ack`` / WS"
        ),
    )


# =============================================================================
# Safe-Mode Control
# =============================================================================


class SafeModeRequest(BaseModel):
    """
    Safe-mode control request.
    """

    reason: str = Field(
        "manual",
        max_length=100,
        description="Reason for safe-mode change",
        examples=["manual", "emergency_stop", "maintenance"],
    )


class SafeModeResponse(BaseResponse):
    """
    Safe-Mode-Umschaltung: Fire-and-forget MQTT; kein synchrones ACK in HTTP.
    """

    device_id: str = Field(..., description="ESP device ID")
    subzone_id: str = Field(..., description="Betroffene Subzone")
    safe_mode_active: bool = Field(..., description="Zielzustand Safe-Mode nach Serverlogik")
    mqtt_sent: bool = Field(
        ...,
        description="Ob die Steuerungsnachricht an den Broker übergeben wurde",
    )


# =============================================================================
# Subzone ACK Payload (from ESP32)
# =============================================================================


class SubzoneAckPayload(BaseModel):
    """
    Subzone ACK payload from ESP32.

    Received via MQTT topic: kaiser/{kaiser_id}/esp/{esp_id}/subzone/ack

    ESP32 sends this after processing subzone assignment to confirm success/failure.
    """

    esp_id: str = Field(
        ...,
        description="ESP device ID",
        examples=["ESP_AB12CD"],
    )
    status: str = Field(
        ...,
        description="Assignment status: 'subzone_assigned', 'subzone_removed', or 'error'",
        examples=["subzone_assigned", "error"],
    )
    subzone_id: str = Field(
        ...,
        description="Subzone ID that was processed",
        examples=["irrigation_section_A"],
    )
    timestamp: int = Field(
        ...,
        alias="ts",
        description="Unix timestamp (seconds)",
        examples=[1734523800],
    )
    error_code: Optional[int] = Field(
        None,
        description="Error code (only on status='error'). Range: 2500-2506",
        examples=[2501],
    )
    message: Optional[str] = Field(
        None,
        description="Error message (only on status='error')",
        examples=["GPIO 5 already assigned to subzone irrigation_section_B"],
    )
    reason_code: Optional[str] = Field(
        None,
        max_length=64,
        description="Stable string from firmware (e.g. CONFIG_LANE_BUSY, JSON_PARSE_ERROR)",
    )

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        """Validate status is one of the expected values."""
        valid_statuses = {"subzone_assigned", "subzone_removed", "error"}
        if v not in valid_statuses:
            raise ValueError(f"status must be one of: {valid_statuses}")
        return v

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "esp_id": "ESP_AB12CD",
                "status": "subzone_assigned",
                "subzone_id": "irrigation_section_A",
                "ts": 1734523800,
            }
        },
    )


# =============================================================================
# Subzone Info Display
# =============================================================================


class SubzoneInfo(BaseModel):
    """
    Subzone information for display.

    Used when returning subzone info as part of ESP device response.
    """

    subzone_id: str = Field(
        ...,
        description="Unique subzone identifier",
        examples=["irrigation_section_A"],
    )
    subzone_name: Optional[str] = Field(
        None,
        description="Human-readable subzone name",
        examples=["Irrigation Section A"],
    )
    parent_zone_id: str = Field(
        ...,
        description="Parent zone ID",
        examples=["greenhouse_zone_1"],
    )
    assigned_gpios: List[int] = Field(
        ...,
        description="GPIO pins in this subzone",
        examples=[[4, 5, 6]],
    )
    safe_mode_active: bool = Field(
        ...,
        description="Whether subzone is in safe-mode",
    )
    sensor_count: int = Field(
        0,
        description="Number of sensors in subzone",
    )
    actuator_count: int = Field(
        0,
        description="Number of actuators in subzone",
    )
    custom_data: dict = Field(
        default_factory=dict,
        description="Subzone-specific metadata (plant info, material, notes)",
    )
    created_at: Optional[str] = Field(
        None,
        description="Creation timestamp (ISO format)",
    )

    @property
    def gpio_count(self) -> int:
        """Get number of assigned GPIOs."""
        return len(self.assigned_gpios)

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "subzone_id": "irrigation_section_A",
                "subzone_name": "Irrigation Section A",
                "parent_zone_id": "greenhouse_zone_1",
                "assigned_gpios": [4, 5, 6],
                "safe_mode_active": False,
                "sensor_count": 1,
                "actuator_count": 2,
                "created_at": "2025-12-18T10:30:00Z",
            }
        },
    )


class SubzoneListResponse(BaseResponse):
    """
    Response for listing all subzones of an ESP.
    """

    device_id: str = Field(...)
    zone_id: Optional[str] = Field(None)
    subzones: List[SubzoneInfo] = Field(default_factory=list)
    total_count: int = Field(0)
