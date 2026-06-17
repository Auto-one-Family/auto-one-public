"""
Zone Context Pydantic Schemas

Phase: K3 - Zone-Context Data Model
Status: IMPLEMENTED

Provides:
- ZoneContextUpdate: Partial update (PATCH) / full upsert (PUT)
- ZoneContextResponse: Full response with computed fields
- ZoneContextListResponse: Paginated list
- CycleArchiveResponse: After archiving a cycle
"""

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from .common import BaseResponse

# =============================================================================
# Request Schemas
# =============================================================================


class ZoneContextUpdate(BaseModel):
    """
    Zone context create/update request.

    All fields optional for PATCH. PUT uses same schema (upsert).
    """

    zone_name: Optional[str] = Field(
        None,
        max_length=100,
        description="Human-readable zone name",
        examples=["Blüte-Raum A"],
    )
    plant_count: Optional[int] = Field(
        None,
        ge=0,
        description="Number of plants in zone",
        examples=[24],
    )
    variety: Optional[str] = Field(
        None,
        max_length=200,
        description="Plant variety or strain",
        examples=["Wedding Cake"],
    )
    substrate: Optional[str] = Field(
        None,
        max_length=200,
        description="Growing medium",
        examples=["Coco/Perlite 70/30"],
    )
    growth_phase: Optional[str] = Field(
        None,
        max_length=50,
        description="Current growth phase",
        examples=["flower_week_5"],
    )
    planted_date: Optional[date] = Field(
        None,
        description="Date current cycle was planted",
        examples=["2026-01-15"],
    )
    expected_harvest: Optional[date] = Field(
        None,
        description="Expected harvest date",
        examples=["2026-04-15"],
    )
    responsible_person: Optional[str] = Field(
        None,
        max_length=100,
        description="Responsible person",
        examples=["Robin"],
    )
    work_hours_weekly: Optional[float] = Field(
        None,
        ge=0,
        description="Estimated weekly work hours",
        examples=[8.0],
    )
    notes: Optional[str] = Field(
        None,
        description="Free-text notes",
    )
    custom_data: Optional[dict] = Field(
        None,
        description="User-defined custom fields",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "zone_name": "Blüte-Raum A",
                "plant_count": 24,
                "variety": "Wedding Cake",
                "substrate": "Coco/Perlite 70/30",
                "growth_phase": "flower_week_5",
                "planted_date": "2026-01-15",
                "expected_harvest": "2026-04-15",
                "responsible_person": "Robin",
                "work_hours_weekly": 8.0,
            }
        }
    )


# =============================================================================
# Response Schemas
# =============================================================================


class ZoneContextResponse(BaseModel):
    """
    Full zone context response with computed fields.
    """

    id: int = Field(..., description="Record ID")
    zone_id: str = Field(..., description="Zone identifier")
    zone_name: Optional[str] = Field(None, description="Zone name")
    plant_count: Optional[int] = Field(None, description="Number of plants")
    variety: Optional[str] = Field(None, description="Plant variety")
    substrate: Optional[str] = Field(None, description="Growing medium")
    growth_phase: Optional[str] = Field(None, description="Current growth phase")
    planted_date: Optional[date] = Field(None, description="Planted date")
    expected_harvest: Optional[date] = Field(None, description="Expected harvest date")
    responsible_person: Optional[str] = Field(None, description="Responsible person")
    work_hours_weekly: Optional[float] = Field(None, description="Weekly work hours")
    notes: Optional[str] = Field(None, description="Notes")
    custom_data: dict = Field(default_factory=dict, description="Custom fields")
    cycle_history: list = Field(default_factory=list, description="Archived cycles")
    created_at: Optional[datetime] = Field(None, description="Created timestamp")
    updated_at: Optional[datetime] = Field(None, description="Updated timestamp")

    # Computed fields
    plant_age_days: Optional[int] = Field(None, description="Plant age in days (computed)")
    days_to_harvest: Optional[int] = Field(None, description="Days until harvest (computed)")

    model_config = ConfigDict(from_attributes=True)


class ZoneContextListResponse(BaseResponse):
    """Paginated list of zone contexts."""

    data: List[ZoneContextResponse] = Field(default_factory=list)
    total_count: int = Field(0, description="Total number of zone contexts")


class CycleArchiveResponse(BaseResponse):
    """Response after archiving a growing cycle."""

    zone_id: str = Field(..., description="Zone ID")
    archived_cycle: dict = Field(..., description="The archived cycle data")
    cycle_number: int = Field(..., description="Total number of archived cycles")


class CycleHistoryResponse(BaseResponse):
    """Response for cycle history query."""

    zone_id: str = Field(..., description="Zone ID")
    cycles: List[dict] = Field(default_factory=list, description="List of archived cycles")
    total_count: int = Field(0, description="Total number of cycles")
