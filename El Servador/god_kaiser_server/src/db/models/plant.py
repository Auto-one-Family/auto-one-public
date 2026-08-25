"""
Plant Models: Plant, PlantCannabisExtension, PlantLifecycleEvent

Plant entity for MultispeQ/Phyta integration. Supports generic plants
(all tenants) plus a 1:1 Cannabis extension for CSC/CanG compliance.

AUT-222 — Phyta Plants Schema
OQ-2: tenant anchor uses kaiser_id (VARCHAR, nullable) — consistent with
esp_devices.kaiser_id (string-only, no FK constraint). No new tenant
concept introduced; can be migrated to a formal tenant FK later.
"""

import secrets
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin, _utc_now


PLANT_PHASES: tuple[str, ...] = (
    "invitro_donor",
    "invitro_initiation",
    "invitro_multiplication",
    "invitro_rooting",
    "invitro_acclimatization",
    "clone",
    "veg-frueh",
    "veg-spaet",
    # Photoperiod flip / pre-stretch (12/12 induction before visible stretch).
    "uebergang-vorbluete",
    "bluete-stretch",
    "bluete-bulk",
    "bluete-ende",
    "mutter",
    "steckling_wurzelung",
    "steckling_vor_versand",
    "harvested",
    "archived",
)

# AUT-1183 introduced this axis as an alias of PLANT_PHASES ("so gardeners
# can freely combine them"). AUT-1209 added uebergang-vorbluete on the nutrient
# axis first; the light/growth axis now shares the same transition step
# (pre-stretch after 12/12 flip). Constraints stay separately named so the
# axes can diverge again if needed.
NUTRIENT_PHASES: tuple[str, ...] = (
    "invitro_donor",
    "invitro_initiation",
    "invitro_multiplication",
    "invitro_rooting",
    "invitro_acclimatization",
    "clone",
    "veg-frueh",
    "veg-spaet",
    "uebergang-vorbluete",  # AUT-1209: fertigation transition (8-6-12)
    "bluete-stretch",
    "bluete-bulk",
    "bluete-ende",
    "mutter",
    "steckling_wurzelung",
    "steckling_vor_versand",
    "harvested",
    "archived",
)

PLANT_VISIBILITY: tuple[str, ...] = ("tenant_private", "open_aggregate", "open_full")

LIFECYCLE_EVENT_TYPES: tuple[str, ...] = (
    "clone_taken",
    "roots_established",
    "transplanted",
    "phase_changed",
    # AUT-1183: second independent phase axis — nutrient/fertilizer schedule.
    # ``previous_phase`` / ``new_phase`` on the event row capture the
    # transition on the nutrient axis (same columns, different event_type).
    "nutrient_phase_changed",
    "defoliation",
    "topping",
    "training",
    "pest_detected",
    "treatment_applied",
    "emergency_triage",
    "harvest_started",
    "harvest_completed",
    "drying_started",
    "drying_completed",
    "sample_taken",
    "archived",
    "note_added",
    "subzone_moved",
)

# AUT-1207: truth status of a lifecycle event.
#   occurred    — default; matches the prior implicit behaviour (event really happened)
#   planned     — foreseen, not yet occurred; must never set current plant state
#   reverted    — was recorded in error, kept for history, excluded from state/aggregates
#   test_data   — debug/test artefact, not real operational data
EVENT_STATUSES: tuple[str, ...] = (
    "occurred",
    "planned",
    "reverted",
    "test_data",
)

_PHASE_CHECK = f"phase IN ({', '.join(repr(p) for p in PLANT_PHASES)})"
# AUT-1183: separate constraint name, managed independently from ck_plants_phase
# so nutrient and light axes can diverge when needed.
_NUTRIENT_PHASE_CHECK = (
    f"nutrient_phase IS NULL OR nutrient_phase IN ({', '.join(repr(p) for p in NUTRIENT_PHASES)})"
)
_VISIBILITY_CHECK = f"visibility IN ({', '.join(repr(v) for v in PLANT_VISIBILITY)})"
_EVENT_TYPE_CHECK = f"event_type IN ({', '.join(repr(e) for e in LIFECYCLE_EVENT_TYPES)})"
_EVENT_STATUS_CHECK = f"event_status IN ({', '.join(repr(s) for s in EVENT_STATUSES)})"


def _generate_qr_code() -> str:
    """Generate a unique plant QR code in format ``PL-XXXXXXXX``."""
    return f"PL-{secrets.token_hex(4).upper()}"


class Plant(Base, TimestampMixin):
    """
    Generic plant entity for all Phyta tenants.

    Soft-Delete Pattern (analogous to ESPDevice/Zone):
    ``deleted_at`` is NULL for active plants. The unique indexes for
    ``qr_code`` and ``external_plant_id`` are partial (WHERE deleted_at IS NULL),
    so soft-deleted records do not block re-use of identifiers.

    Cannabis Extension:
    A 1:1 relationship to :class:`PlantCannabisExtension` carries
    CSC/CanG-specific fields. Generic plants (e.g. tomato) do not
    require an extension row.
    """

    __tablename__ = "plants"

    __table_args__ = (
        CheckConstraint(_PHASE_CHECK, name="ck_plants_phase"),
        # AUT-1183: nutrient/fertilizer phase axis — nullable, same valid values
        # as the light/growth phase axis.
        CheckConstraint(_NUTRIENT_PHASE_CHECK, name="ck_plants_nutrient_phase"),
        CheckConstraint(_VISIBILITY_CHECK, name="ck_plants_visibility"),
        # NOTE: The (partial) UNIQUE indexes for (kaiser_id, qr_code) and
        # (kaiser_id, external_plant_id) are created in Alembic with
        # ``postgresql_where=deleted_at IS NULL`` because SQLAlchemy declarative
        # ``UniqueConstraint`` does not support partial conditions.
        Index("idx_plants_kaiser_id", "kaiser_id"),
        Index("idx_plants_phase", "phase"),
        Index("idx_plants_nutrient_phase", "nutrient_phase"),
        Index("idx_plants_deleted_at", "deleted_at"),
        Index("idx_plants_zone_id", "zone_id"),
        Index("idx_plants_subzone_id", "subzone_id"),
    )

    plant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Primary key (UUID)",
    )

    # OQ-2 resolved: use kaiser_id (String) as tenant anchor — consistent with
    # esp_devices.kaiser_id (string-only, no FK constraint).
    kaiser_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        doc=(
            "Kaiser installation ID (tenant anchor). OQ-2: nullable pending "
            "formal tenant schema. Consistent with esp_devices.kaiser_id."
        ),
    )

    # AUT-1073: direct zone assignment (fallback when no Ortseinheit / when
    # Ortseinheit has no parent zone). Effective zone at read time is
    # COALESCE(subzone.parent_zone_id, plants.zone_id) — see PlantRepository.
    # Pattern reused from esp_devices.zone_id. Not a denormalised Ortseinheit copy.
    zone_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        ForeignKey("zones.zone_id", ondelete="SET NULL"),
        nullable=True,
        doc=(
            "Direct zone assignment (AUT-1073). Fallback when the plant has no "
            "subzone, or the subzone has no parent_zone_id. Ortseinheit parent "
            "wins at read time when present."
        ),
    )

    subzone_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subzone_configs.id", ondelete="SET NULL"),
        nullable=True,
        doc="Optional FK to subzone_configs.id (current Ortseinheit).",
    )
    subzone: Mapped[Optional["SubzoneConfig"]] = relationship(
        "SubzoneConfig",
        foreign_keys=[subzone_id],
    )

    qr_code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=_generate_qr_code,
        doc="Print label QR code, format PL-XXXXXXXX",
    )

    external_plant_id: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
        doc=(
            "PhotosynQ / external system ID. Auto-set to qr_code on create, "
            "overrideable via PATCH."
        ),
    )

    external_track_trace_id: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
        doc="Track-and-Trace system anchor (CanG compliance)",
    )

    genotype_label: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
        doc="Genotype label (e.g. 'Northern Lights x White Widow'); optional (AUT-1073)",
    )

    cultivar_or_variety: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
        doc="Cultivar / variety designation",
    )

    lineage_parent_plant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plants.plant_id", ondelete="SET NULL"),
        nullable=True,
        doc="Mother-clone lineage self-FK",
    )

    batch_label: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        doc="Optional batch grouping label",
    )

    planting_date: Mapped[Optional[datetime]] = mapped_column(
        Date,
        nullable=True,
        doc="Calendar date the plant was planted / cloned; optional (AUT-1073)",
    )

    phase: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="clone",
        server_default="clone",
        doc="Current light/growth lifecycle phase (see PLANT_PHASES); default clone (AUT-1073)",
    )

    # AUT-1183: second, independent nutrient/fertilizer phase axis.
    # NULL until explicitly set (existing plants default to light-axis only).
    # Valid values: same set as ``phase`` (see NUTRIENT_PHASES / PLANT_PHASES).
    # Changed via lifecycle event ``nutrient_phase_changed``; queried via
    # ``PlantRepository.get_plant_nutrient_phase_at``.
    nutrient_phase: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
        doc=(
            "Current nutrient/fertilizer phase (AUT-1183). "
            "Independent of ``phase`` (light/growth axis). "
            "NULL when not explicitly set."
        ),
    )

    current_position_label: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
        doc="Free-form position label (rack/row/slot)",
    )

    visibility: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="tenant_private",
        server_default="tenant_private",
        doc="Visibility level (see PLANT_VISIBILITY)",
    )

    notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Free-form notes",
    )

    rooting_success: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        nullable=True,
        doc="Whether rooting succeeded (NULL = unknown / not applicable)",
    )

    rooting_date: Mapped[Optional[datetime]] = mapped_column(
        Date,
        nullable=True,
        doc="Date rooting was confirmed",
    )

    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Soft-delete timestamp (NULL = active)",
    )

    deleted_by: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("user_accounts.id", ondelete="SET NULL"),
        nullable=True,
        doc="user_accounts.id of the user who soft-deleted this plant",
    )

    cannabis_extension: Mapped[Optional["PlantCannabisExtension"]] = relationship(
        "PlantCannabisExtension",
        back_populates="plant",
        uselist=False,
        cascade="all, delete-orphan",
    )

    lifecycle_events: Mapped[list["PlantLifecycleEvent"]] = relationship(
        "PlantLifecycleEvent",
        back_populates="plant",
        order_by="PlantLifecycleEvent.event_timestamp",
    )

    @property
    def is_active(self) -> bool:
        """Return True when the plant is not soft-deleted."""
        return self.deleted_at is None

    def __repr__(self) -> str:
        return (
            f"<Plant(qr_code='{self.qr_code}', "
            f"genotype='{self.genotype_label}', phase='{self.phase}', "
            f"nutrient_phase='{self.nutrient_phase}')>"
        )


class PlantCannabisExtension(Base, TimestampMixin):
    """Cannabis-specific 1:1 extension (CSC/CanG compliance)."""

    __tablename__ = "plants_cannabis_extension"

    __table_args__ = (UniqueConstraint("plant_id", name="uq_cannabis_extension_plant_id"),)

    extension_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Primary key (UUID)",
    )

    plant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plants.plant_id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        doc="FK to plants.plant_id (1:1)",
    )

    # OQ-2 consistent denormalised tenant anchor.
    kaiser_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        doc="Denormalised kaiser_id mirror of plant.kaiser_id (OQ-2).",
    )

    harvest_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    drying_end_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    dry_weight_g: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    harvested_weight_g: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    thc_content_pct: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    cbd_content_pct: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    lab_analysis_ref: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    lab_analysis_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    disposal_reason: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    disposal_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    pflanzenpass_nr: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    plant: Mapped["Plant"] = relationship(
        "Plant",
        back_populates="cannabis_extension",
    )

    def __repr__(self) -> str:
        return f"<PlantCannabisExtension(plant_id='{self.plant_id}')>"


class PlantLifecycleEvent(Base):
    """
    Append-only lifecycle event log per plant.

    No TimestampMixin: ``created_at`` is set explicitly. "Append-only" here
    means nothing is silently overwritten or deleted — it does not mean
    content can never be corrected. ``event_status``/``status_reason``/
    ``status_changed_at`` (AUT-1207) are mutable via the dedicated
    ``PATCH .../lifecycle-event/{event_id}/status`` endpoint. That endpoint
    is the intended extension point for future field-level corrections
    (see AUT-1208) rather than a second endpoint — any such correction must
    keep leaving a traceable trail (who, when, field, old, new, reason) and
    must never hard-delete or reassign an event to a different plant.
    """

    __tablename__ = "plant_lifecycle_events"

    __table_args__ = (
        CheckConstraint(_EVENT_TYPE_CHECK, name="ck_lifecycle_event_type"),
        CheckConstraint(_EVENT_STATUS_CHECK, name="ck_lifecycle_event_status"),
        Index("idx_lifecycle_plant_id", "plant_id"),
        Index("idx_lifecycle_event_timestamp", "event_timestamp"),
        Index("idx_lifecycle_zone_id", "zone_id"),
        Index("idx_lifecycle_subzone_id", "subzone_id"),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Primary key (UUID)",
    )

    plant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plants.plant_id", ondelete="RESTRICT"),
        nullable=False,
        doc="FK to plants.plant_id",
    )

    kaiser_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        doc="Denormalised kaiser_id mirror of plant.kaiser_id (OQ-2).",
    )

    event_type: Mapped[str] = mapped_column(
        String(48),
        nullable=False,
        doc="Lifecycle event type (see LIFECYCLE_EVENT_TYPES)",
    )

    event_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        doc="Wall-clock time the event occurred (UTC)",
    )

    previous_phase: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    new_phase: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    linked_sensor_window_start: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Optional sensor-data window start linked to this event",
    )
    linked_sensor_window_end: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Optional sensor-data window end linked to this event",
    )

    # Spatial snapshot at write time (WHERE). Phase sections are WHEN.
    # Snapshot so a later plant move does not silently re-home the action.
    zone_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        ForeignKey("zones.zone_id", ondelete="SET NULL"),
        nullable=True,
        doc="Zone snapshot when the event was recorded (effective plant zone).",
    )
    subzone_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subzone_configs.id", ondelete="SET NULL"),
        nullable=True,
        doc="Subzone snapshot when the event was recorded (plants.subzone_id).",
    )

    track_trace_export_status: Mapped[Optional[str]] = mapped_column(
        String(24),
        nullable=True,
        doc="Track-and-Trace export status (e.g. 'pending', 'exported', 'failed')",
    )

    created_by_user: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("user_accounts.id", ondelete="RESTRICT"),
        nullable=False,
        doc="user_accounts.id of the user who recorded the event",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        doc="Server insert timestamp (UTC)",
    )

    event_status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="occurred",
        doc="Truth status of this event (see EVENT_STATUSES). AUT-1207.",
    )
    status_reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Short justification for a non-default event_status.",
    )
    status_changed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc=(
            "When this event was last changed via the status/correction "
            "endpoint (AUT-1207: status change; AUT-1208: any field "
            "correction) — the general 'last corrected' marker, not only "
            "for status changes despite the column name."
        ),
    )

    plant: Mapped["Plant"] = relationship(
        "Plant",
        back_populates="lifecycle_events",
    )

    def __repr__(self) -> str:
        return (
            f"<PlantLifecycleEvent(plant_id='{self.plant_id}', " f"event_type='{self.event_type}')>"
        )
