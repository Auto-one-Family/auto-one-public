"""
Nutrient Solution Batch Model

AUT-1211 follow-up — event log of tank mix/refill/withdrawal entries, so
manual (non-automated) chemistry bookkeeping works exactly like an
automated one. EC alone cannot tell individual nutrient concentrations
apart (it is a sum quantity across differently-conducting ions); this
table is the ledger of accumulated component additions and withdrawals
per tank, with EC/pH readings kept only as control-anchor comparison
values, not as the source of truth.

Design notes (verify-plan, Stufe 2):
- Append-only event log, same shape as PlantLifecycleEvent (plant.py):
  ``occurred_at`` is a freely settable, backdatable wall-clock timestamp
  (default is "now" but callers may set a past date, e.g. correcting a
  batch entered a day late); ``created_at`` is the immutable server
  insert timestamp. Deliberately NOT TimestampMixin — there is no
  meaningful "updated_at" for an append-only ledger row.
- entry_type/acquisition_method/qualifier follow the
  LIFECYCLE_EVENT_TYPES/_EVENT_TYPE_CHECK convention (plant.py): a plain
  tuple of allowed values plus a generated CHECK constraint, rather than
  a DB-level ENUM type (consistent with the rest of the codebase).
- No required field assumes a dosing pump or automation rule exists —
  this must work for a fully manual operation too.
- ``components`` (JSONBCompat) holds a list of dicts, both forms may
  appear side by side in the same batch:
    Fertilizer-product form: {"kind": "product", "name": str,
        "dose_ml_per_l" | "dose_g_per_l": float,
        "ec_contribution_ms_cm": float?}  # optional
    Salt-recipe form: {"kind": "salt", "name": str, "conc_g_per_l": float,
        "elements": {<element>: float, ...},  # "elements" optional/empty
        "ec_contribution_ms_cm": float?}  # optional
  ``ec_contribution_ms_cm`` (optional, both forms): operator-/calibration-
  supplied EC contribution (mS/cm) of this component at the dose used in
  THIS entry. Entered value only — never auto-derived from ml/L or g/L
  (no ion-balance model). Used by the EC control-anchor check
  (ec_control_anchor.py); omit when unknown (component then skipped for
  expected-EC estimation).
  No fixed Pydantic sub-schema is enforced at the DB layer (JSON column);
  API-layer schemas validate the shape on write.
- ec_was_measured/ph_was_measured exist to distinguish "never measured"
  from "measured as 0" — ec_measured_after/ph_measured_after alone would
  conflate NULL-as-not-measured with a real (if implausible) zero
  reading.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, _utc_now
from ..types import JSONBCompat

NUTRIENT_BATCH_ENTRY_TYPES: tuple[str, ...] = (
    "full_reset",  # Neuansatz / voller Wechsel
    "top_up_dose",  # Nachdosierung / Zugang ohne vollen Wechsel
    "fresh_water_refill",  # Nachfuellung / Frischwasser-Zugang
    "withdrawal",  # Entnahme / Abgang zur Bewaesserung
    "remeasurement_only",  # reine Nachmessung ohne Volumen-Aenderung
    "system_incident",  # Anlagen-Vorfall
)

NUTRIENT_BATCH_ACQUISITION_METHODS: tuple[str, ...] = (
    "measured_flow",
    "measured_level",
    "computed_runtime_x_rate",
    "manual_entry",
)

NUTRIENT_BATCH_QUALIFIERS: tuple[str, ...] = (
    "precise",
    "approximate",
    "estimated",
)

_ENTRY_TYPE_CHECK = (
    f"entry_type IN ({', '.join(repr(e) for e in NUTRIENT_BATCH_ENTRY_TYPES)})"
)
_ACQUISITION_METHOD_CHECK = (
    f"acquisition_method IN ({', '.join(repr(m) for m in NUTRIENT_BATCH_ACQUISITION_METHODS)})"
)
_QUALIFIER_CHECK = f"qualifier IN ({', '.join(repr(q) for q in NUTRIENT_BATCH_QUALIFIERS)})"


class NutrientSolutionBatch(Base):
    """
    Nutrient Solution Batch Model.

    Append-only ledger entry for a tank mix/refill/withdrawal/remeasurement
    event. See module docstring for the full design rationale.

    Attributes:
        id: Primary key (UUID)
        tank_id: Tank this entry belongs to (FK to tanks.id, mandatory)
        entry_type: Kind of entry (see NUTRIENT_BATCH_ENTRY_TYPES)
        occurred_at: Backdatable wall-clock time the entry occurred (UTC)
        created_at: Server insert timestamp (UTC), never backdated
        recipe_label: Optional free-text recipe/profile name
        volume_l: Volume in liters this entry represents
        components: JSONB list of fertilizer-product and/or salt-recipe
            component dicts (see module docstring; optional
            ec_contribution_ms_cm per component)
        ec_measured_after: Measured EC (mS/cm) after this entry, if any
        ec_was_measured: Whether EC was actually measured (distinguishes
            "never measured" from a real 0 reading)
        ph_measured_after: Measured pH after this entry, if any
        ph_was_measured: Whether pH was actually measured (same principle
            as ec_was_measured)
        acquisition_method: How volume_l was determined (see
            NUTRIENT_BATCH_ACQUISITION_METHODS)
        qualifier: Confidence qualifier for this entry (see
            NUTRIENT_BATCH_QUALIFIERS)
        prior_volume_l: Optional tank volume (L) immediately before this
            entry (AUT-1346). NULL for legacy rows / unknown — never
            backfilled.
        prior_ec_ms_cm: Optional last-known EC before this entry
            (AUT-1346). Same numeric convention as ec_measured_after.
            NULL when unknown.
    """

    __tablename__ = "nutrient_solution_batches"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Primary key (UUID)",
    )

    # Foreign Key
    tank_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tanks.id", ondelete="RESTRICT"),
        nullable=False,
        doc="Foreign key to tanks.id",
    )

    entry_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        doc="Entry type (see NUTRIENT_BATCH_ENTRY_TYPES)",
    )

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        doc="Backdatable wall-clock time the entry occurred (UTC)",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        doc="Server insert timestamp (UTC), never backdated",
    )

    recipe_label: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True,
        doc="Optional free-text recipe/profile name",
    )

    volume_l: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        doc="Volume in liters this entry represents",
    )

    components: Mapped[List[Dict[str, Any]]] = mapped_column(
        JSONBCompat,
        nullable=False,
        default=list,
        doc=(
            "List of component dicts, product- and salt-form may be mixed "
            "in the same list (see module docstring for the two shapes)"
        ),
    )

    ec_measured_after: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        doc="Measured EC (mS/cm) after this entry, if any",
    )

    ec_was_measured: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        doc="Whether EC was actually measured (NULL-vs-0 disambiguation)",
    )

    ph_measured_after: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        doc="Measured pH after this entry, if any",
    )

    ph_was_measured: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        doc="Whether pH was actually measured (NULL-vs-0 disambiguation)",
    )

    acquisition_method: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        doc="How volume_l was determined (see NUTRIENT_BATCH_ACQUISITION_METHODS)",
    )

    qualifier: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        doc="Confidence qualifier for this entry (see NUTRIENT_BATCH_QUALIFIERS)",
    )

    # AUT-1346 / PKG-04 — additive, nullable; legacy rows stay NULL.
    prior_volume_l: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        doc="Tank volume (L) before this entry; NULL = unknown (AUT-1346)",
    )

    prior_ec_ms_cm: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        doc="Last known EC before this entry; NULL = unknown (AUT-1346)",
    )

    __table_args__ = (
        CheckConstraint(_ENTRY_TYPE_CHECK, name="ck_nutrient_solution_batches_entry_type"),
        CheckConstraint(
            _ACQUISITION_METHOD_CHECK, name="ck_nutrient_solution_batches_acquisition_method"
        ),
        CheckConstraint(_QUALIFIER_CHECK, name="ck_nutrient_solution_batches_qualifier"),
        Index("idx_nutrient_solution_batches_tank_id", "tank_id"),
        Index("idx_nutrient_solution_batches_occurred_at", "occurred_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<NutrientSolutionBatch(tank_id='{self.tank_id}', "
            f"entry_type='{self.entry_type}', occurred_at='{self.occurred_at}')>"
        )
