"""
Plant Pydantic Schemas (AUT-222 — Phyta Plants Schema).

Schemas mirror the SQLAlchemy ``Plant`` model and intentionally restrict
the fields that can be set / updated via the public REST API.

AUT-221 (Wave 2) extends this with:
- ``LifecycleEventCreate`` / ``LifecycleEventResponse`` for the
  ``POST /v1/plants/{id}/lifecycle-event`` endpoint.
- ``PlantMeasurementEntry`` / ``PlantMeasurementsResponse`` for
  ``GET /v1/plants/{id}/measurements``.
- ``PlantDeleteResponse`` for the soft-delete endpoint.
- ``ZonePlantSummaryResponse`` for ``GET /v1/zones/{id}/plant-summary``.
"""

import uuid
from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..db.models.plant import (
    LIFECYCLE_EVENT_TYPES,
    PLANT_PHASES,
    PLANT_VISIBILITY,
)


_PHASE_SET = set(PLANT_PHASES)
_VISIBILITY_SET = set(PLANT_VISIBILITY)
_EVENT_TYPE_SET = set(LIFECYCLE_EVENT_TYPES)


class PlantCreate(BaseModel):
    """Request schema for creating a new plant."""

    genotype_label: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Genotype label (e.g. 'Northern Lights x White Widow')",
    )
    planting_date: date = Field(
        ...,
        description="Calendar date the plant was planted / cloned",
    )
    phase: str = Field(
        ...,
        max_length=32,
        description=f"Lifecycle phase. One of: {sorted(_PHASE_SET)}",
    )
    kaiser_id: Optional[str] = Field(
        None,
        max_length=50,
        description="Optional tenant anchor (kaiser installation ID)",
    )
    cultivar_or_variety: Optional[str] = Field(
        None,
        max_length=128,
        description="Cultivar / variety designation",
    )
    batch_label: Optional[str] = Field(
        None,
        max_length=64,
        description="Optional batch grouping label",
    )
    subzone_id: Optional[uuid.UUID] = Field(
        None,
        description="Optional subzone_configs.id (current location)",
    )
    notes: Optional[str] = Field(
        None,
        description="Free-form notes",
    )

    @field_validator("phase")
    @classmethod
    def validate_phase(cls, v: str) -> str:
        if v not in _PHASE_SET:
            raise ValueError(
                f"Invalid phase '{v}'. Must be one of: {sorted(_PHASE_SET)}"
            )
        return v


class PlantUpdate(BaseModel):
    """Partial-update schema for an existing plant."""

    external_plant_id: Optional[str] = Field(
        None,
        max_length=128,
        description="Override the auto-assigned external_plant_id",
    )
    phase: Optional[str] = Field(
        None,
        max_length=32,
        description="New lifecycle phase",
    )
    notes: Optional[str] = Field(
        None,
        description="Updated notes",
    )
    current_position_label: Optional[str] = Field(
        None,
        max_length=128,
        description="Updated free-form position label",
    )
    visibility: Optional[str] = Field(
        None,
        max_length=24,
        description=f"Visibility. One of: {sorted(_VISIBILITY_SET)}",
    )
    genotype_label: Optional[str] = Field(
        None,
        min_length=1,
        max_length=128,
        description="Updated genotype label",
    )
    cultivar_or_variety: Optional[str] = Field(
        None,
        max_length=128,
        description="Updated cultivar / variety",
    )

    @field_validator("phase")
    @classmethod
    def validate_phase(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _PHASE_SET:
            raise ValueError(
                f"Invalid phase '{v}'. Must be one of: {sorted(_PHASE_SET)}"
            )
        return v

    @field_validator("visibility")
    @classmethod
    def validate_visibility(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _VISIBILITY_SET:
            raise ValueError(
                f"Invalid visibility '{v}'. Must be one of: {sorted(_VISIBILITY_SET)}"
            )
        return v


class PlantResponse(BaseModel):
    """Response schema for a single plant."""

    plant_id: uuid.UUID = Field(..., description="Plant UUID")
    kaiser_id: Optional[str] = Field(None, description="Tenant anchor (kaiser ID)")
    subzone_id: Optional[uuid.UUID] = Field(None, description="Current subzone FK")
    qr_code: str = Field(..., description="Print label QR code (PL-XXXXXXXX)")
    external_plant_id: Optional[str] = Field(
        None, description="External system ID (PhotosynQ etc.)"
    )
    external_track_trace_id: Optional[str] = Field(
        None, description="Track-and-Trace anchor (CanG)"
    )
    genotype_label: str = Field(..., description="Genotype label")
    cultivar_or_variety: Optional[str] = Field(
        None, description="Cultivar / variety"
    )
    lineage_parent_plant_id: Optional[uuid.UUID] = Field(
        None, description="Mother-clone lineage parent"
    )
    batch_label: Optional[str] = Field(None, description="Batch label")
    planting_date: date = Field(..., description="Planting date")
    phase: str = Field(..., description="Current lifecycle phase")
    current_position_label: Optional[str] = Field(
        None, description="Free-form position label"
    )
    visibility: str = Field(..., description="Visibility level")
    notes: Optional[str] = Field(None, description="Notes")
    rooting_success: Optional[bool] = Field(
        None, description="Whether rooting succeeded"
    )
    rooting_date: Optional[date] = Field(None, description="Rooting confirmation date")
    deleted_at: Optional[datetime] = Field(
        None, description="Soft-delete timestamp"
    )
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    model_config = ConfigDict(from_attributes=True)


class PlantListResponse(BaseModel):
    """Response schema for listing plants."""

    plants: list[PlantResponse] = Field(
        default_factory=list, description="List of plants"
    )
    total: int = Field(0, description="Number of plants returned", ge=0)


# =============================================================================
# AUT-221 Wave 2 — Lifecycle Events, Measurements, Delete, Zone-Summary
# =============================================================================


class LifecycleEventCreate(BaseModel):
    """
    Request schema for ``POST /v1/plants/{id}/lifecycle-event``.

    The optional ``new_phase`` field is only honoured when
    ``event_type == 'phase_changed'``; in that case the plant's current
    ``phase`` is updated atomically with the event row.

    The free-form ``metadata`` dict is JSON-serialised into the event's
    ``notes`` column (prefixed) when present, since the underlying model
    has no dedicated JSON metadata column. ``note`` always wins over
    ``metadata`` for the human-readable note text.
    """

    event_type: str = Field(
        ...,
        max_length=48,
        description=f"Lifecycle event type. One of: {sorted(_EVENT_TYPE_SET)}",
    )
    note: Optional[str] = Field(
        None,
        description="Free-form human-readable note for this event",
    )
    metadata: Optional[dict[str, Any]] = Field(
        None,
        description=(
            "Optional structured metadata. Persisted as JSON inside the "
            "event's ``notes`` column when no ``note`` is provided."
        ),
    )
    new_phase: Optional[str] = Field(
        None,
        max_length=32,
        description=(
            "Required when ``event_type == 'phase_changed'``. Updates "
            "``plants.phase`` atomically with the event insert."
        ),
    )

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, v: str) -> str:
        if v not in _EVENT_TYPE_SET:
            raise ValueError(
                f"Invalid event_type '{v}'. Must be one of: {sorted(_EVENT_TYPE_SET)}"
            )
        return v

    @field_validator("new_phase")
    @classmethod
    def validate_new_phase(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _PHASE_SET:
            raise ValueError(
                f"Invalid new_phase '{v}'. Must be one of: {sorted(_PHASE_SET)}"
            )
        return v


class LifecycleEventResponse(BaseModel):
    """Response schema for a single lifecycle event."""

    event_id: uuid.UUID = Field(..., description="Event UUID")
    plant_id: uuid.UUID = Field(..., description="Plant UUID")
    event_type: str = Field(..., description="Lifecycle event type")
    event_timestamp: datetime = Field(..., description="When the event occurred (UTC)")
    previous_phase: Optional[str] = Field(None, description="Phase before the event")
    new_phase: Optional[str] = Field(None, description="Phase after the event")
    notes: Optional[str] = Field(None, description="Free-form notes / metadata blob")
    created_by_user: int = Field(..., description="user_accounts.id of recorder")
    created_at: datetime = Field(..., description="Server insert timestamp (UTC)")

    model_config = ConfigDict(from_attributes=True)


class PlantDeleteResponse(BaseModel):
    """Response schema for soft-delete."""

    success: bool = Field(True, description="Always true on 200")
    message: str = Field(..., description="Human-readable result")
    plant_id: uuid.UUID = Field(..., description="Plant UUID that was soft-deleted")


class PlantMeasurementEntry(BaseModel):
    """
    Single sensor reading associated with a plant.

    Mirrors the subset of :class:`SensorData` that is meaningful for
    plant-centric measurement queries (no internal IDs, no metadata).
    """

    sensor_type: str = Field(..., description="Type of sensor")
    processed_value: Optional[float] = Field(
        None, description="Processed value (falls back to raw_value when None)"
    )
    raw_value: float = Field(..., description="Raw sensor reading")
    unit: Optional[str] = Field(None, description="Measurement unit")
    timestamp: datetime = Field(..., description="Reading timestamp (UTC)")
    gpio: int = Field(..., description="GPIO pin the sensor is wired to")


class PlantMeasurementsResponse(BaseModel):
    """Response schema for ``GET /v1/plants/{id}/measurements``."""

    plant_id: uuid.UUID = Field(..., description="Plant UUID")
    days: int = Field(..., description="Window size in days", ge=1, le=365)
    total: int = Field(..., description="Number of measurements returned", ge=0)
    measurements: list[PlantMeasurementEntry] = Field(
        default_factory=list,
        description="Measurements ordered by timestamp DESC",
    )


class ZonePlantSummaryResponse(BaseModel):
    """Response schema for ``GET /v1/zones/{id}/plant-summary``."""

    zone_id: str = Field(..., description="Zone identifier")
    plant_count: int = Field(..., description="Active (non-deleted) plant count", ge=0)
    phases: dict[str, int] = Field(
        default_factory=dict,
        description="Phase histogram: phase -> count",
    )
    avg_phi2: Optional[float] = Field(
        None,
        description=(
            "Average ``phi2`` measurement across active plants in this "
            "zone over the last 30 days. ``None`` when no readings exist."
        ),
    )
