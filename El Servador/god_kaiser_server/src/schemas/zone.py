"""
Zone Assignment Pydantic Schemas

Phase: 7 - Zone Management
Priority: HIGH
Status: IMPLEMENTED

Provides:
- Zone assignment request/response models
- Zone ACK payload model (from ESP32)
- Zone info display model

Consistency with El Trabajante:
- Zone ID format: lowercase letters, numbers, underscores
- Master Zone ID: Parent zone for hierarchy
- kaiser_id: "god" for God-Kaiser Server
- Timestamps: Unix seconds

References:
- El Trabajante/docs/system-flows/08-zone-assignment-flow.md
- El Trabajante/src/models/system_types.h (KaiserZone struct)
- .claude/README.md (Developer Briefing Section 3)
"""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .common import BaseResponse

# =============================================================================
# Zone Assignment Request/Response
# =============================================================================


class ZoneAssignRequest(BaseModel):
    """
    Zone assignment request from Frontend/API.

    Used to assign an ESP to a zone via MQTT.
    ESP will receive this via: kaiser/{kaiser_id}/esp/{esp_id}/zone/assign

    T13-R1: Added subzone_strategy for subzone handling on zone change.
    """

    zone_id: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Primary zone identifier (e.g., 'greenhouse_zone_1')",
        examples=["greenhouse_zone_1", "farm_section_a"],
    )
    master_zone_id: Optional[str] = Field(
        None,
        max_length=50,
        description="Parent master zone ID for hierarchy (e.g., 'greenhouse_master')",
        examples=["greenhouse_master", "farm_master"],
    )
    zone_name: Optional[str] = Field(
        None,
        max_length=100,
        description="Human-readable zone name",
        examples=["Greenhouse Section 1", "Farm Section A"],
    )
    subzone_strategy: str = Field(
        "transfer",
        description=(
            "Subzone handling on zone change: "
            "'transfer' (move subzones), "
            "'copy' (clone subzones), "
            "'reset' (leave subzones in old zone)"
        ),
        examples=["transfer", "copy", "reset"],
    )

    @field_validator("zone_id")
    @classmethod
    def validate_zone_id_format(cls, v: str) -> str:
        """Validate zone_id contains only valid characters."""
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("zone_id must contain only letters, numbers, underscores, and hyphens")
        return v.lower()

    @field_validator("subzone_strategy")
    @classmethod
    def validate_subzone_strategy(cls, v: str) -> str:
        """Validate subzone_strategy is one of the allowed values."""
        valid = {"transfer", "copy", "reset"}
        if v not in valid:
            raise ValueError(f"subzone_strategy must be one of: {valid}")
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "zone_id": "greenhouse_zone_1",
                "master_zone_id": "greenhouse_master",
                "zone_name": "Greenhouse Section 1",
                "subzone_strategy": "transfer",
            }
        }
    )


class ZoneAssignResponse(BaseResponse):
    """
    Antwort auf Zonenzuweisung.

    **Finalität:** Nach erfolgreichem DB-Commit sendet der Server MQTT ``zone/assign`` und kann bei
    echten ESPs über ``MQTTCommandBridge`` bis zu ``zone/ack`` warten (Timeout, sonst Fehler/Warnung).
    ``mqtt_sent`` = Broker-Publish gelungen; ``ack_received`` = explizites ACK vom Gerät bzw. None bei Mock/Pfad ohne Warten.
    """

    device_id: str = Field(
        ...,
        description="ESP device ID that was assigned",
        examples=["ESP_12AB34CD"],
    )
    zone_id: str = Field(
        ...,
        description="Assigned zone ID",
        examples=["greenhouse_zone_1"],
    )
    master_zone_id: Optional[str] = Field(
        None,
        description="Assigned master zone ID",
        examples=["greenhouse_master"],
    )
    zone_name: Optional[str] = Field(
        None,
        description="Human-readable zone name",
        examples=["Greenhouse Section 1"],
    )
    mqtt_topic: str = Field(
        ...,
        description="MQTT topic used for assignment",
        examples=["kaiser/god/esp/ESP_12AB34CD/zone/assign"],
    )
    mqtt_sent: bool = Field(
        ...,
        description=(
            "True, wenn die Zuweisungsnachricht an den MQTT-Broker übergeben wurde; "
            "kein Nachweis der Verarbeitung auf dem ESP"
        ),
    )
    ack_received: Optional[bool] = Field(
        None,
        description=(
            "True: ``zone/ack`` innerhalb des Bridge-Timeouts mit passender Zuordnung erhalten "
            "(primär über ``correlation_id`` im ACK, sonst FIFO-Fallback pro ESP/``zone`` — "
            "bei parallelen Requests Vorsicht). False: Timeout oder fehlgeschlagene Zuordnung. "
            "None: Mock-Gerät oder Pfad ohne ACK-Warten."
        ),
    )
    warning: Optional[str] = Field(
        None,
        description="Optional warning message (e.g. ACK timeout)",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "message": "Zone assignment sent to ESP",
                "device_id": "ESP_12AB34CD",
                "zone_id": "greenhouse_zone_1",
                "master_zone_id": "greenhouse_master",
                "zone_name": "Greenhouse Section 1",
                "mqtt_topic": "kaiser/god/esp/ESP_12AB34CD/zone/assign",
                "mqtt_sent": True,
                "ack_received": True,
                "warning": None,
            }
        }
    )


class ZoneRemoveResponse(BaseResponse):
    """
    Antwort auf Zonenentfernung.

    Analog zu ``ZoneAssignResponse``: Bridge kann bei echten ESPs auf ``zone/ack`` warten.
    """

    device_id: str = Field(
        ...,
        description="ESP device ID that was unassigned",
        examples=["ESP_12AB34CD"],
    )
    mqtt_topic: str = Field(
        ...,
        description="MQTT topic used for removal",
        examples=["kaiser/god/esp/ESP_12AB34CD/zone/assign"],
    )
    mqtt_sent: bool = Field(
        ...,
        description=(
            "True, wenn die Entfernen-/Zuweisungsnachricht (Clear) an den Broker übergeben wurde"
        ),
    )
    ack_received: Optional[bool] = Field(
        None,
        description=(
            "Wie bei ``ZoneAssignResponse.ack_received``: Bestätigung über ``zone/ack`` nach Bridge-Logik; "
            "None wenn kein Warten (z. B. Mock)."
        ),
    )
    warning: Optional[str] = Field(
        None,
        description="Optional warning (e.g. ACK timeout) — mirrors ZoneAssignResponse semantics.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "message": "Zone removal sent to ESP",
                "device_id": "ESP_12AB34CD",
                "mqtt_topic": "kaiser/god/esp/ESP_12AB34CD/zone/assign",
                "mqtt_sent": True,
                "ack_received": True,
                "warning": None,
            }
        }
    )


# =============================================================================
# Zone ACK Payload (from ESP32)
# =============================================================================


class ZoneAckPayload(BaseModel):
    """
    Zone ACK payload from ESP32.

    Received via MQTT topic: kaiser/{kaiser_id}/esp/{esp_id}/zone/ack

    ESP32 sends this after processing zone assignment to confirm success/failure.
    """

    esp_id: str = Field(
        ...,
        description="ESP device ID",
        examples=["ESP_12AB34CD"],
    )
    status: str = Field(
        ...,
        description="Assignment status: 'zone_assigned' or 'error'",
        examples=["zone_assigned", "error"],
    )
    zone_id: str = Field(
        "",
        description="Assigned zone ID (empty on error or removal)",
        examples=["greenhouse_zone_1"],
    )
    master_zone_id: Optional[str] = Field(
        None,
        description="Assigned master zone ID",
        examples=["greenhouse_master"],
    )
    ts: int = Field(
        ...,
        description="Unix timestamp (seconds)",
        examples=[1734523800],
    )
    message: Optional[str] = Field(
        None,
        description="Error message (only on status='error')",
        examples=["Failed to save zone config to NVS"],
    )

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        """Validate status is one of the expected values."""
        valid_statuses = {"zone_assigned", "error"}
        if v not in valid_statuses:
            raise ValueError(f"status must be one of: {valid_statuses}")
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "esp_id": "ESP_12AB34CD",
                "status": "zone_assigned",
                "zone_id": "greenhouse_zone_1",
                "master_zone_id": "greenhouse_master",
                "ts": 1734523800,
            }
        }
    )


# =============================================================================
# Zone Info Display
# =============================================================================


class ZoneListEntry(BaseModel):
    """
    Zone list entry for GET /v1/zone/zones.

    T13-R1: Now sourced from zones table (Single Source of Truth),
    enriched with device/sensor/actuator counts via JOINs.
    """

    zone_id: str = Field(
        ...,
        description="Zone identifier",
        examples=["greenhouse_zone_1"],
    )
    zone_name: Optional[str] = Field(
        None,
        description="Human-readable zone name",
        examples=["Greenhouse Section 1"],
    )
    status: str = Field(
        "active",
        description="Zone lifecycle status: 'active', 'archived', 'deleted'",
        examples=["active", "archived"],
    )
    device_count: int = Field(
        0,
        description="Number of ESP devices in this zone",
    )
    sensor_count: int = Field(
        0,
        description="Number of sensors in this zone",
    )
    actuator_count: int = Field(
        0,
        description="Number of actuators in this zone",
    )

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "zone_id": "greenhouse_zone_1",
                "zone_name": "Greenhouse Section 1",
                "status": "active",
                "device_count": 3,
                "sensor_count": 8,
                "actuator_count": 2,
            }
        },
    )


class ZoneListResponse(BaseModel):
    """Response for GET /v1/zone/zones."""

    zones: list[ZoneListEntry] = Field(
        default_factory=list,
        description="All zones (including empty ones from ZoneContext)",
    )
    total: int = Field(
        0,
        description="Total number of zones",
    )


class ZoneInfo(BaseModel):
    """
    Zone information for display.

    Used when returning zone info as part of ESP device response.
    """

    zone_id: Optional[str] = Field(
        None,
        description="Primary zone identifier",
        examples=["greenhouse_zone_1"],
    )
    master_zone_id: Optional[str] = Field(
        None,
        description="Parent master zone ID",
        examples=["greenhouse_master"],
    )
    zone_name: Optional[str] = Field(
        None,
        description="Human-readable zone name",
        examples=["Greenhouse Section 1"],
    )
    is_zone_master: bool = Field(
        False,
        description="Whether this ESP is the zone master",
    )
    kaiser_id: Optional[str] = Field(
        None,
        description="Kaiser managing this ESP ('god' for God-Kaiser Server)",
        examples=["god"],
    )

    @property
    def is_assigned(self) -> bool:
        """Check if zone is assigned."""
        return bool(self.zone_id)

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "zone_id": "greenhouse_zone_1",
                "master_zone_id": "greenhouse_master",
                "zone_name": "Greenhouse Section 1",
                "is_zone_master": False,
                "kaiser_id": "god",
            }
        },
    )
