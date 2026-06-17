"""
Zone Entity Pydantic Schemas

Phase: 0.3 - Zone as DB Entity
Status: IMPLEMENTED

Provides CRUD schemas for the Zone entity (independent of zone assignment).
The existing zone.py schemas handle zone assignment (ESP <-> Zone via MQTT).
These schemas handle zone CRUD operations (create, read, update, delete).
"""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ZoneCreate(BaseModel):
    """Request schema for creating a new zone."""

    zone_id: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Unique human-readable zone identifier (e.g., 'greenhouse_zone_1')",
        examples=["greenhouse_zone_1", "office_main"],
    )
    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Display name for the zone",
        examples=["Greenhouse Section 1", "Main Office"],
    )
    description: Optional[str] = Field(
        None,
        max_length=500,
        description="Optional zone description",
        examples=["Primary growing area with 12 LED panels"],
    )

    @field_validator("zone_id")
    @classmethod
    def validate_zone_id_format(cls, v: str) -> str:
        """Validate zone_id contains only valid characters."""
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("zone_id must contain only letters, numbers, underscores, and hyphens")
        return v.lower()


class ZoneUpdate(BaseModel):
    """Request schema for updating a zone. Only provided fields are updated."""

    name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=100,
        description="New display name",
    )
    description: Optional[str] = Field(
        None,
        max_length=500,
        description="New description",
    )


class ZoneResponse(BaseModel):
    """Response schema for a single zone (T13-R1: includes status)."""

    id: uuid.UUID = Field(..., description="Zone UUID")
    zone_id: str = Field(..., description="Human-readable zone identifier")
    name: str = Field(..., description="Display name")
    description: Optional[str] = Field(None, description="Zone description")
    status: str = Field("active", description="Zone lifecycle: 'active', 'archived', 'deleted'")
    deleted_at: Optional[datetime] = Field(None, description="Soft-delete timestamp")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    model_config = ConfigDict(from_attributes=True)


class ZoneListResponse(BaseModel):
    """Response schema for listing zones."""

    zones: list[ZoneResponse] = Field(default_factory=list, description="List of zones")
    total: int = Field(0, description="Total number of zones", ge=0)


class ZoneDeleteResponse(BaseModel):
    """Response schema for zone deletion."""

    success: bool = Field(True, description="Whether deletion succeeded")
    message: str = Field(..., description="Status message")
    zone_id: str = Field(..., description="Deleted zone_id")
    had_devices: bool = Field(
        False,
        description="Whether the zone still had devices assigned (warning)",
    )
    device_count: int = Field(
        0,
        description="Number of devices that were assigned to this zone",
        ge=0,
    )
