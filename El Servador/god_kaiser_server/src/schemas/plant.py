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
from datetime import date, datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..db.models.plant import (
    EVENT_STATUSES,
    LIFECYCLE_EVENT_TYPES,
    NUTRIENT_PHASES,
    PLANT_PHASES,
    PLANT_VISIBILITY,
)


_PHASE_SET = set(PLANT_PHASES)
_NUTRIENT_PHASE_SET = set(NUTRIENT_PHASES)
# AUT-1209: the two axes' value lists diverged. A lifecycle event's
# new_phase field is shared by both event types (phase_changed /
# nutrient_phase_changed), so a single field-level validator cannot know
# which axis applies — it only rejects values unknown to EITHER axis (typo
# protection). The axis-correct check happens in the API handler, which has
# the event_type in context.
_ANY_PHASE_SET = _PHASE_SET | _NUTRIENT_PHASE_SET
_VISIBILITY_SET = set(PLANT_VISIBILITY)
_EVENT_TYPE_SET = set(LIFECYCLE_EVENT_TYPES)
_EVENT_STATUS_SET = set(EVENT_STATUSES)


class PlantCreate(BaseModel):
    """Request schema for creating a new plant."""

    genotype_label: Optional[str] = Field(
        None,
        max_length=128,
        description=(
            "Genotype label (e.g. 'Northern Lights x White Widow'). "
            "Optional (AUT-1073) — fresh clones / generic plants may omit it."
        ),
    )
    planting_date: Optional[date] = Field(
        None,
        description=("Calendar date the plant was planted / cloned. " "Optional (AUT-1073)."),
    )
    phase: Optional[str] = Field(
        None,
        max_length=32,
        description=(
            f"Light/growth lifecycle phase. One of: {sorted(_PHASE_SET)}. "
            "Optional on create — DB/server default is ``clone`` (AUT-1073)."
        ),
    )
    # AUT-1183: optional nutrient/fertilizer phase axis.
    nutrient_phase: Optional[str] = Field(
        None,
        max_length=32,
        description=(
            "Nutrient/fertilizer phase (AUT-1183). Independent of ``phase`` "
            f"(light/growth axis). One of: {sorted(_NUTRIENT_PHASE_SET)}"
        ),
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
    zone_id: Optional[str] = Field(
        None,
        max_length=50,
        description=(
            "Direct zone assignment (AUT-1073). Used when the plant has no "
            "Ortseinheit, or the Ortseinheit has no parent zone. Not a "
            "denormalised copy of the Ortseinheit parent."
        ),
    )
    subzone_id: Optional[uuid.UUID] = Field(
        None,
        description="Optional subzone_configs.id (current Ortseinheit)",
    )
    notes: Optional[str] = Field(
        None,
        description="Free-form notes",
    )

    @field_validator("phase")
    @classmethod
    def validate_phase(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _PHASE_SET:
            raise ValueError(f"Invalid phase '{v}'. Must be one of: {sorted(_PHASE_SET)}")
        return v

    @field_validator("nutrient_phase")
    @classmethod
    def validate_nutrient_phase(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _NUTRIENT_PHASE_SET:
            raise ValueError(
                f"Invalid nutrient_phase '{v}'. Must be one of: {sorted(_NUTRIENT_PHASE_SET)}"
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
        description="New light/growth lifecycle phase",
    )
    # AUT-1183: allow direct PATCH of the nutrient phase axis.
    nutrient_phase: Optional[str] = Field(
        None,
        max_length=32,
        description=(
            "New nutrient/fertilizer phase (AUT-1183). "
            "Set to empty string to clear (not supported — use lifecycle event "
            "instead; direct PATCH only sets, never clears)."
        ),
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
        max_length=128,
        description="Updated genotype label",
    )
    cultivar_or_variety: Optional[str] = Field(
        None,
        max_length=128,
        description="Updated cultivar / variety",
    )
    zone_id: Optional[str] = Field(
        None,
        max_length=50,
        description=(
            "Direct zone assignment (AUT-1073). Stored value for edit forms — "
            "display/grouping uses ``parent_zone_id`` (effective)."
        ),
    )
    # AUT-1266 / AUT-1073: Ortseinheit writable on PATCH (drag-and-drop fix).
    subzone_id: Optional[uuid.UUID] = Field(
        None,
        description="Ortseinheit FK (subzone_configs.id).",
    )

    @field_validator("phase")
    @classmethod
    def validate_phase(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _PHASE_SET:
            raise ValueError(f"Invalid phase '{v}'. Must be one of: {sorted(_PHASE_SET)}")
        return v

    @field_validator("nutrient_phase")
    @classmethod
    def validate_nutrient_phase(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _NUTRIENT_PHASE_SET:
            raise ValueError(
                f"Invalid nutrient_phase '{v}'. Must be one of: {sorted(_NUTRIENT_PHASE_SET)}"
            )
        return v

    @field_validator("visibility")
    @classmethod
    def validate_visibility(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _VISIBILITY_SET:
            raise ValueError(f"Invalid visibility '{v}'. Must be one of: {sorted(_VISIBILITY_SET)}")
        return v


class PlantResponse(BaseModel):
    """Response schema for a single plant."""

    plant_id: uuid.UUID = Field(..., description="Plant UUID")
    kaiser_id: Optional[str] = Field(None, description="Tenant anchor (kaiser ID)")
    zone_id: Optional[str] = Field(
        None,
        description=(
            "Direct stored zone assignment (AUT-1073). For edit forms only. "
            "Display and grouping use ``parent_zone_id`` (effective)."
        ),
    )
    subzone_id: Optional[uuid.UUID] = Field(None, description="Current subzone FK")
    subzone_name: Optional[str] = Field(None, description="Human-readable current subzone name")
    parent_zone_id: Optional[str] = Field(
        None,
        description=(
            "Effective zone for display/grouping (AUT-1073): "
            "COALESCE(Ortseinheit.parent_zone_id, plants.zone_id). "
            "Clients must not re-resolve."
        ),
    )
    zone_name: Optional[str] = Field(
        None, description="Human-readable name of the effective parent zone"
    )
    qr_code: str = Field(..., description="Print label QR code (PL-XXXXXXXX)")
    external_plant_id: Optional[str] = Field(
        None, description="External system ID (PhotosynQ etc.)"
    )
    external_track_trace_id: Optional[str] = Field(
        None, description="Track-and-Trace anchor (CanG)"
    )
    genotype_label: Optional[str] = Field(None, description="Genotype label")
    cultivar_or_variety: Optional[str] = Field(None, description="Cultivar / variety")
    lineage_parent_plant_id: Optional[uuid.UUID] = Field(
        None, description="Mother-clone lineage parent"
    )
    batch_label: Optional[str] = Field(None, description="Batch label")
    planting_date: Optional[date] = Field(None, description="Planting date")
    phase: str = Field(..., description="Current light/growth lifecycle phase")
    # AUT-1183: second independent phase axis.
    nutrient_phase: Optional[str] = Field(
        None, description="Current nutrient/fertilizer phase (AUT-1183)"
    )
    current_position_label: Optional[str] = Field(None, description="Free-form position label")
    visibility: str = Field(..., description="Visibility level")
    notes: Optional[str] = Field(None, description="Notes")
    rooting_success: Optional[bool] = Field(None, description="Whether rooting succeeded")
    rooting_date: Optional[date] = Field(None, description="Rooting confirmation date")
    deleted_at: Optional[datetime] = Field(None, description="Soft-delete timestamp")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    model_config = ConfigDict(from_attributes=True)


class PlantListResponse(BaseModel):
    """Response schema for listing plants."""

    plants: list[PlantResponse] = Field(default_factory=list, description="List of plants")
    total: int = Field(0, description="Number of plants returned", ge=0)


# =============================================================================
# AUT-221 Wave 2 — Lifecycle Events, Measurements, Delete, Zone-Summary
# =============================================================================


def _normalize_and_reject_future_timestamp(v: Optional[datetime]) -> Optional[datetime]:
    """Shared event_timestamp validation for creation (AUT-1181) and
    correction (AUT-1208): normalise to UTC-aware, reject timestamps in the
    future (allowing a 60-second clock-skew buffer via the ``>`` comparison
    against the current moment)."""
    if v is None:
        return v
    if v.tzinfo is None:
        v = v.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    if v > now:
        raise ValueError("event_timestamp must not lie in the future")
    return v


class LifecycleEventCreate(BaseModel):
    """
    Request schema for ``POST /v1/plants/{id}/lifecycle-event``.

    The optional ``new_phase`` field is honoured for two event types:

    - ``event_type == 'phase_changed'`` — updates ``plants.phase``
      (light/growth axis) atomically with the event insert.
    - ``event_type == 'nutrient_phase_changed'`` (AUT-1183) — updates
      ``plants.nutrient_phase`` (nutrient/fertilizer axis) atomically.

    Both event types require ``new_phase`` and record ``previous_phase``
    on the event row. The ``event_type`` value distinguishes which axis the
    transition belongs to; two events on the same day (one per axis) land
    in their respective column without overwriting each other.

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
            "Required when ``event_type`` is ``'phase_changed'`` or "
            "``'nutrient_phase_changed'``. "
            "For ``phase_changed``: updates ``plants.phase`` (light/growth axis). "
            "For ``nutrient_phase_changed``: updates ``plants.nutrient_phase`` "
            "(nutrient/fertilizer axis). "
            "Valid on light axis (PLANT_PHASES) or nutrient axis (NUTRIENT_PHASES)."
        ),
    )
    event_timestamp: Optional[datetime] = Field(
        None,
        description=(
            "Optional back-dated event timestamp (UTC). "
            "Must not lie in the future. "
            "When omitted the server uses the current UTC moment."
        ),
    )
    event_status: str = Field(
        "occurred",
        description=(
            f"Truth status of this event (AUT-1207). One of: {sorted(_EVENT_STATUS_SET)}. "
            "Defaults to 'occurred' (matches prior implicit behaviour). "
            "Use 'planned' to record a foreseen-but-not-yet-occurred event; "
            "'test_data' for debug/test artefacts. 'reverted' is set via the "
            "dedicated status-update endpoint, not at creation."
        ),
    )
    linked_sensor_window_start: Optional[datetime] = Field(
        None,
        description=(
            "Start of the marked action range (UTC). Required together with "
            "linked_sensor_window_end when recording an executed plant measure."
        ),
    )
    linked_sensor_window_end: Optional[datetime] = Field(
        None,
        description="End of the marked action range (UTC, exclusive-or-after start).",
    )

    @field_validator("event_status")
    @classmethod
    def validate_event_status(cls, v: str) -> str:
        if v not in _EVENT_STATUS_SET:
            raise ValueError(
                f"Invalid event_status '{v}'. Must be one of: {sorted(_EVENT_STATUS_SET)}"
            )
        return v

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, v: str) -> str:
        if v not in _EVENT_TYPE_SET:
            raise ValueError(f"Invalid event_type '{v}'. Must be one of: {sorted(_EVENT_TYPE_SET)}")
        return v

    @field_validator("new_phase")
    @classmethod
    def validate_new_phase(cls, v: Optional[str]) -> Optional[str]:
        # AUT-1209: loose check only (either axis) — the axis-correct check
        # happens in the API handler, which knows event_type.
        if v is not None and v not in _ANY_PHASE_SET:
            raise ValueError(f"Invalid new_phase '{v}'. Must be one of: {sorted(_ANY_PHASE_SET)}")
        return v

    @field_validator("event_timestamp")
    @classmethod
    def validate_event_timestamp(cls, v: Optional[datetime]) -> Optional[datetime]:
        return _normalize_and_reject_future_timestamp(v)


class LifecycleEventResponse(BaseModel):
    """Response schema for a single lifecycle event."""

    event_id: uuid.UUID = Field(..., description="Event UUID")
    plant_id: uuid.UUID = Field(..., description="Plant UUID")
    event_type: str = Field(..., description="Lifecycle event type")
    event_timestamp: datetime = Field(..., description="When the event occurred (UTC)")
    previous_phase: Optional[str] = Field(
        None,
        description=(
            "Phase before the event. For ``phase_changed``: light/growth axis. "
            "For ``nutrient_phase_changed``: nutrient/fertilizer axis (AUT-1183)."
        ),
    )
    new_phase: Optional[str] = Field(
        None,
        description=(
            "Phase after the event. For ``phase_changed``: light/growth axis. "
            "For ``nutrient_phase_changed``: nutrient/fertilizer axis (AUT-1183)."
        ),
    )
    notes: Optional[str] = Field(None, description="Free-form notes / metadata blob")
    created_by_user: int = Field(..., description="user_accounts.id of recorder")
    created_at: datetime = Field(..., description="Server insert timestamp (UTC)")
    event_status: str = Field(
        "occurred",
        description=f"Truth status of this event (AUT-1207). One of: {sorted(_EVENT_STATUS_SET)}",
    )
    status_reason: Optional[str] = Field(
        None, description="Short justification for a non-default event_status."
    )
    status_changed_at: Optional[datetime] = Field(
        None, description="When event_status was last changed, if ever."
    )
    linked_sensor_window_start: Optional[datetime] = Field(
        None, description="Marked action range start (UTC), if any."
    )
    linked_sensor_window_end: Optional[datetime] = Field(
        None, description="Marked action range end (UTC), if any."
    )
    zone_id: Optional[str] = Field(None, description="Zone snapshot at write time (WHERE).")
    subzone_id: Optional[uuid.UUID] = Field(
        None, description="Subzone snapshot at write time (WHERE)."
    )

    model_config = ConfigDict(from_attributes=True)


class PhaseSectionActionResponse(BaseModel):
    """Executed or planned measure belonging to one phase section."""

    event_id: uuid.UUID
    event_type: str
    event_timestamp: datetime
    event_status: str
    notes: Optional[str] = None
    linked_sensor_window_start: Optional[datetime] = None
    linked_sensor_window_end: Optional[datetime] = None
    zone_id: Optional[str] = None
    subzone_id: Optional[uuid.UUID] = None

    model_config = ConfigDict(from_attributes=True)


class PhaseSectionResponse(BaseModel):
    """Explicit WHEN interval for one plant on one phase axis."""

    plant_id: uuid.UUID
    phase: str
    axis: str
    start: datetime
    end: Optional[datetime] = None
    source_event_id: Optional[uuid.UUID] = None
    zone_id: Optional[str] = None
    subzone_id: Optional[uuid.UUID] = None
    actions: list[PhaseSectionActionResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class PhaseSectionListResponse(BaseModel):
    """Phase sections plus the plant's current spatial assignment."""

    plant_id: uuid.UUID
    zone_id: Optional[str] = None
    subzone_id: Optional[uuid.UUID] = None
    current_phase: Optional[str] = None
    axis: str
    sections: list[PhaseSectionResponse] = Field(default_factory=list)


class LifecycleEventStatusUpdate(BaseModel):
    """
    Request schema for ``PATCH /v1/plants/{id}/lifecycle-event/{event_id}/status``
    (AUT-1207 + AUT-1208).

    ``event_status``/``reason`` (AUT-1207) change the event's truth status.
    ``event_timestamp``/``notes``/``event_type``/``new_phase`` (AUT-1208) are
    additive field-level corrections — all optional, only the fields present
    in a given request are changed. Not correctable through this schema:
    plant_id, event_id, created_at, created_by_user (see AUT-1208 scope).
    """

    event_status: Optional[str] = Field(
        None,
        description=f"New truth status. One of: {sorted(_EVENT_STATUS_SET)}",
    )
    reason: Optional[str] = Field(
        None,
        description=(
            "Short justification. Required when event_status == 'reverted', "
            "and required whenever any correction field below is set "
            "(AUT-1208: no correction without a reason)."
        ),
    )
    event_timestamp: Optional[datetime] = Field(
        None,
        description=(
            "AUT-1208: corrected event timestamp (UTC). Same future-timestamp "
            "validation as event creation."
        ),
    )
    notes: Optional[str] = Field(None, description="AUT-1208: corrected free-form note text.")
    event_type: Optional[str] = Field(
        None,
        max_length=48,
        description=(
            f"AUT-1208: corrected event type, e.g. to fix an event recorded on "
            f"the wrong axis. One of: {sorted(_EVENT_TYPE_SET)}"
        ),
    )
    new_phase: Optional[str] = Field(
        None,
        max_length=32,
        description=(
            f"AUT-1208: corrected phase value (relevant when event_type is/"
            f"becomes 'phase_changed' or 'nutrient_phase_changed'). "
            f"One of: {sorted(_PHASE_SET)}"
        ),
    )

    @field_validator("event_status")
    @classmethod
    def validate_event_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _EVENT_STATUS_SET:
            raise ValueError(
                f"Invalid event_status '{v}'. Must be one of: {sorted(_EVENT_STATUS_SET)}"
            )
        return v

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _EVENT_TYPE_SET:
            raise ValueError(f"Invalid event_type '{v}'. Must be one of: {sorted(_EVENT_TYPE_SET)}")
        return v

    @field_validator("new_phase")
    @classmethod
    def validate_new_phase(cls, v: Optional[str]) -> Optional[str]:
        # AUT-1209: loose check only (either axis) — the axis-correct check
        # happens in the API handler, which knows event_type.
        if v is not None and v not in _ANY_PHASE_SET:
            raise ValueError(f"Invalid new_phase '{v}'. Must be one of: {sorted(_ANY_PHASE_SET)}")
        return v

    @field_validator("event_timestamp")
    @classmethod
    def validate_event_timestamp(cls, v: Optional[datetime]) -> Optional[datetime]:
        return _normalize_and_reject_future_timestamp(v)

    @model_validator(mode="after")
    def validate_reason_required(self) -> "LifecycleEventStatusUpdate":
        # mode="after" (not @field_validator) so this always runs regardless
        # of which fields were present in the input — see AUT-1207 commit
        # 34877c25 for why a field-level validator on 'reason' would miss an
        # omitted field entirely.
        has_correction = any(
            f is not None
            for f in (self.event_timestamp, self.notes, self.event_type, self.new_phase)
        )
        reason_given = bool(self.reason and self.reason.strip())
        if self.event_status == "reverted" and not reason_given:
            raise ValueError("reason is required when event_status is 'reverted'")
        if has_correction and not reason_given:
            raise ValueError("reason is required when correcting event fields (AUT-1208)")
        if self.event_status is None and not has_correction:
            raise ValueError("at least one of event_status or a correction field is required")
        return self


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


class TankIncidentEventResponse(BaseModel):
    """
    Tank-level system-incident entry relevant to a plant (AUT-1211 follow-up).

    Sourced from the nutrient-balance ledger (``nutrient_solution_batches``,
    ``entry_type == 'system_incident'``) via the plant's subzone -> tank
    assignment. Deliberately a distinct response type from
    ``LifecycleEventResponse`` — a tank-wide incident is not a per-plant
    lifecycle event and is never stored a second time in
    ``plant_lifecycle_events``.
    """

    id: uuid.UUID = Field(..., description="nutrient_solution_batches.id")
    tank_id: uuid.UUID = Field(..., description="Tank this incident occurred on")
    occurred_at: datetime = Field(..., description="When the incident occurred (UTC)")
    recipe_label: Optional[str] = Field(None, description="Optional free-text recipe/profile name")
    volume_l: float = Field(..., description="Reservoir volume in liters for this entry")
    ph_measured_after: Optional[float] = Field(
        None, description="Measured pH after the incident, if any"
    )
    ec_measured_after: Optional[float] = Field(
        None, description="Measured EC after the incident, if any"
    )
    qualifier: str = Field(..., description="Confidence qualifier (precise/approximate/estimated)")

    model_config = ConfigDict(from_attributes=True)


class LifecycleEventListResponse(BaseModel):
    """Response schema for ``GET /v1/plants/{id}/lifecycle-events``."""

    plant_id: uuid.UUID = Field(..., description="Plant UUID")
    total: int = Field(0, ge=0, description="Number of events returned")
    events: list[LifecycleEventResponse] = Field(
        default_factory=list,
        description="Lifecycle events ordered by event_timestamp ASC",
    )
    tank_incidents: list[TankIncidentEventResponse] = Field(
        default_factory=list,
        description=(
            "System-wide tank incidents (nutrient_solution_batches, "
            "entry_type='system_incident') affecting this plant via its "
            "tank/subzone — NOT duplicated into plant_lifecycle_events."
        ),
    )


class ZonePlantSummaryResponse(BaseModel):
    """Response schema for ``GET /v1/zones/{id}/plant-summary``.

    AUT-1194: Both phase axes are included so callers can distinguish them.
    ``phases`` is the **light/growth** axis (backward-compatible field name).
    ``nutrient_phase_histogram`` is the additive **nutrient/fertilizer** axis
    (AUT-1183); it is empty when no plant in the zone has ``nutrient_phase``
    set.  The field names unambiguously identify which axis each histogram
    refers to — ``phases`` alone would be ambiguous after AUT-1183.
    """

    zone_id: str = Field(..., description="Zone identifier")
    plant_count: int = Field(..., description="Active (non-deleted) plant count", ge=0)
    phases: dict[str, int] = Field(
        default_factory=dict,
        description=(
            "Light/growth phase histogram: phase (str) → count (int). "
            "Counts ``plants.phase`` (light/growth axis) for all active "
            "plants in the zone.  See also ``nutrient_phase_histogram`` for "
            "the independent nutrient/fertilizer axis (AUT-1194)."
        ),
    )
    # AUT-1194: additive second axis — nutrient/fertilizer phase histogram.
    # Empty dict when no plant in the zone has a nutrient_phase set.
    # Field presence in the response proves that the caller always sees both
    # axes; the axis identity is unambiguous from the field name.
    nutrient_phase_histogram: dict[str, int] = Field(
        default_factory=dict,
        description=(
            "Nutrient/fertilizer phase histogram: nutrient_phase (str) → "
            "count (int).  Counts ``plants.nutrient_phase`` (AUT-1183) for "
            "active plants that have an explicit nutrient phase set.  Plants "
            "with ``nutrient_phase=NULL`` are excluded.  Empty dict when no "
            "plant in the zone has a nutrient phase."
        ),
    )
    avg_phi2: Optional[float] = Field(
        None,
        description=(
            "Average ``phi2`` measurement across active plants in this "
            "zone over the last 30 days. ``None`` when no readings exist."
        ),
    )
