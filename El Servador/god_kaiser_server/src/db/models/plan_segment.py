"""
Plan Segment Model (AUT-1232 / Welle 5 T2, AUT-1239 / Welle 6 K2)

Additive interval-setpoint store per Zone (mandatory) × optional Subzone(s) ×
domain × measure. Does NOT replace CrossESPLogic setpoints — rules opt in via
follows_plan + plan_* fields on CrossESPLogic (see logic.py).

Domains in catalog: nutrient_solution (target_ec / target_ph) and climate
(target_temperature / target_humidity; VPD is derived, never stored).
recipe_ref points at stock_mix_recipes.id (UUID string, AUT-1361 / P9);
legacy free-text seeds remain readable. phase_ref holds a NUTRIENT_PHASES key.
No chemistry / dose / batch-timing logic here.
No agronomic default values — value slots stay operator-supplied.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin, _utc_now


# Generic domain catalog — nutrient_solution (EC/pH) + climate (T/RH).
PLAN_DOMAINS: tuple[str, ...] = (
    "nutrient_solution",
    "climate",
)

# Measure catalog — model stays generic. VPD is NOT a measure (derived).
PLAN_MEASURES: tuple[str, ...] = (
    "target_ec",
    "target_ph",
    "target_temperature",
    "target_humidity",
    "target_co2",
    "light_regime",
    "recipe_ref",
)

# Transition to the next segment: hard step vs linear ramp.
PLAN_INTERPS: tuple[str, ...] = (
    "step",
    "linear",
)

# Own segment status list (idea shared with PlantLifecycleEvent EVENT_STATUSES,
# but NOT a foreign reference — see AUT-1207 / plant.py).
PLAN_SEGMENT_STATUSES: tuple[str, ...] = (
    "planned",
    "active",
    "occurred",
    "withdrawn",
)

_DOMAIN_CHECK = f"domain IN ({', '.join(repr(d) for d in PLAN_DOMAINS)})"
_MEASURE_CHECK = f"measure IN ({', '.join(repr(m) for m in PLAN_MEASURES)})"
_INTERP_CHECK = f"interp IN ({', '.join(repr(i) for i in PLAN_INTERPS)})"
_STATUS_CHECK = f"status IN ({', '.join(repr(s) for s in PLAN_SEGMENT_STATUSES)})"


class PlanSegment(Base, TimestampMixin):
    """
    Interval setpoint segment for a zone (and optionally subzones).

    Attributes:
        id: Primary key (UUID)
        zone_id: Mandatory zone FK (Tank.zone_id pattern)
        domain: Functional domain (see PLAN_DOMAINS)
        measure: Setpoint kind (see PLAN_MEASURES)
        value: Planned numeric value (nullable when only recipe_ref is used later)
        recipe_ref: Reserved for future recipe-profile identity (unwired in v1)
        from_ts / to_ts: Interval bounds; to_ts NULL = open-ended
        interp: step | linear
        phase_ref: Optional growth-/nutrient-phase key (PLANT_PHASES / NUTRIENT_PHASES)
        status: Segment truth status (see PLAN_SEGMENT_STATUSES)
        tolerance: Optional ± band; stored but not evaluated in v1
    """

    __tablename__ = "plan_segments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Primary key (UUID)",
    )

    zone_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("zones.zone_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        doc="Zone identifier (FK to zones.zone_id) — mandatory, Tank pattern",
    )

    domain: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        doc="Functional domain (see PLAN_DOMAINS)",
    )

    measure: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        doc="Setpoint measure (see PLAN_MEASURES)",
    )

    value: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        doc="Planned numeric setpoint (EC/pH in v1); NULL reserved for recipe-only rows",
    )

    recipe_ref: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        doc=(
            "Stock mix recipe identity (AUT-1361): stock_mix_recipes.id as UUID string. "
            "Legacy free-text labels remain readable until migrated."
        ),
    )

    from_ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        doc="Interval start (inclusive, UTC)",
    )

    to_ts: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Interval end (exclusive, UTC); NULL = open-ended",
    )

    interp: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="step",
        doc="Transition type: step (hard) or linear (ramp)",
    )

    phase_ref: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        doc=(
            "Canonical plant/nutrient phase key (PLANT_PHASES / NUTRIENT_PHASES). "
            "Same vocabulary as plants.phase — not a second enum. "
            "Drives stock_mix_recipes lookup together with actuator dose_role."
        ),
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="planned",
        doc="Segment truth status (see PLAN_SEGMENT_STATUSES)",
    )

    tolerance: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        doc="Optional ± tolerance; stored only — not evaluated in v1",
    )

    __table_args__ = (
        CheckConstraint(_DOMAIN_CHECK, name="ck_plan_segments_domain"),
        CheckConstraint(_MEASURE_CHECK, name="ck_plan_segments_measure"),
        CheckConstraint(_INTERP_CHECK, name="ck_plan_segments_interp"),
        CheckConstraint(_STATUS_CHECK, name="ck_plan_segments_status"),
        Index(
            "idx_plan_segments_zone_domain_measure_from",
            "zone_id",
            "domain",
            "measure",
            "from_ts",
        ),
    )

    def covers(self, at: datetime) -> bool:
        """Half-open interval [from_ts, to_ts) — open end when to_ts is NULL."""
        if at < self.from_ts:
            return False
        if self.to_ts is not None and at >= self.to_ts:
            return False
        return True

    def __repr__(self) -> str:
        return (
            f"<PlanSegment(zone_id={self.zone_id!r}, domain={self.domain!r}, "
            f"measure={self.measure!r}, value={self.value})>"
        )


class PlanSegmentSubzoneAssignment(Base):
    """
    Optional n:m assignment of a plan_segment to subzone_configs.

    Pattern copied from TankSubzoneAssignment (AUT-1211) — segments without
    rows here apply zone-wide.
    """

    __tablename__ = "plan_segment_subzone_assignments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Primary key (UUID)",
    )

    plan_segment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plan_segments.id", ondelete="CASCADE"),
        nullable=False,
        doc="Foreign key to plan_segments.id",
    )

    subzone_config_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subzone_configs.id", ondelete="CASCADE"),
        nullable=False,
        doc="Foreign key to subzone_configs.id",
    )

    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        nullable=False,
        doc="Timestamp when the assignment was created (UTC)",
    )

    __table_args__ = (
        UniqueConstraint(
            "plan_segment_id",
            "subzone_config_id",
            name="uq_plan_segment_subzone_assignment",
        ),
        Index("idx_plan_segment_subzone_segment_id", "plan_segment_id"),
        Index("idx_plan_segment_subzone_config_id", "subzone_config_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<PlanSegmentSubzoneAssignment("
            f"plan_segment_id={self.plan_segment_id!r}, "
            f"subzone_config_id={self.subzone_config_id!r})>"
        )
