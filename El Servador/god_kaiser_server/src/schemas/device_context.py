"""
Device Context Pydantic Schemas

T13-R2: Multi-Zone Device Scope and Data Routing
Schemas for active context management endpoints.
"""

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .common import BaseResponse

# Valid values for device_scope
VALID_DEVICE_SCOPES = ["zone_local", "multi_zone", "mobile"]
VALID_CONTEXT_SOURCES = ["manual", "sequence", "mqtt"]


class DeviceContextSet(BaseModel):
    """Request to set active zone context for a sensor or actuator."""

    active_zone_id: Optional[str] = Field(
        None,
        max_length=50,
        description="Zone ID to activate (None = all zones / static multi-zone)",
    )
    active_subzone_id: Optional[str] = Field(
        None,
        max_length=50,
        description="Subzone ID to activate (optional)",
    )
    context_source: str = Field(
        "manual",
        description="How context was set: 'manual', 'sequence', 'mqtt'",
    )

    @field_validator("context_source")
    @classmethod
    def validate_context_source(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in VALID_CONTEXT_SOURCES:
            raise ValueError(f"context_source must be one of {VALID_CONTEXT_SOURCES}")
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "active_zone_id": "zone_b",
                "active_subzone_id": None,
                "context_source": "manual",
            }
        }
    )


class DeviceContextResponse(BaseResponse):
    """Response for active context queries."""

    config_type: str = Field(..., description="Config type: 'sensor' or 'actuator'")
    config_id: uuid.UUID = Field(..., description="Config UUID")
    active_zone_id: Optional[str] = Field(None, description="Currently active zone")
    active_subzone_id: Optional[str] = Field(None, description="Currently active subzone")
    context_source: str = Field("manual", description="How context was set")
    context_since: Optional[datetime] = Field(None, description="When context became active")

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "success": True,
                "config_type": "sensor",
                "config_id": "550e8400-e29b-41d4-a716-446655440000",
                "active_zone_id": "zone_b",
                "active_subzone_id": None,
                "context_source": "manual",
                "context_since": "2026-03-09T14:30:00Z",
            }
        },
    )


class DeviceScopeUpdate(BaseModel):
    """Request to update device_scope and assigned_zones on a sensor or actuator config."""

    device_scope: str = Field(
        ...,
        description="Device scope: 'zone_local', 'multi_zone', 'mobile'",
    )
    assigned_zones: List[str] = Field(
        default_factory=list,
        description="List of zone_ids this device can serve",
    )
    assigned_subzones: List[str] = Field(
        default_factory=list,
        description="List of subzone_ids for static multi-zone assignment",
    )

    @field_validator("device_scope")
    @classmethod
    def validate_device_scope(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in VALID_DEVICE_SCOPES:
            raise ValueError(f"device_scope must be one of {VALID_DEVICE_SCOPES}")
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "device_scope": "multi_zone",
                "assigned_zones": ["zone_a", "zone_b"],
                "assigned_subzones": [],
            }
        }
    )
