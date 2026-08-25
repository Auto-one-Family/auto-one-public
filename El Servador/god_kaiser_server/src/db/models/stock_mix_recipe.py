"""
Stock Mix Recipe Identity (AUT-1361 / P9)

Canonical Stammlösungs-Rezeptur: dose_role × (optional) nutrient_phase →
components with target_g_per_l. Not ledger history; not pump concentration.
plan_segments.recipe_ref may point at stock_mix_recipes.id (UUID string).

AUT-1369: optional metadata key ``dose_ml_per_l`` is display-only recipe
volume intent (e.g. 4+4 ml/L). Runtime dosing uses ``volume_share`` × pump
``concentration`` (AUT-1366/1367), not this metadata field.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin
from ..types import JSONBCompat
from .plant import NUTRIENT_PHASES

# Same catalogue as actuator_configs.dose_role / schemas.actuator.DOSE_ROLES
DOSE_ROLES: tuple[str, ...] = ("part_a", "part_b", "ph_down", "generic")
STOCK_MIX_COVERAGES: tuple[str, ...] = ("universal", "phase_specific")

_DOSE_ROLE_CHECK = f"dose_role IN ({', '.join(repr(r) for r in DOSE_ROLES)})"
_COVERAGE_CHECK = f"coverage IN ({', '.join(repr(c) for c in STOCK_MIX_COVERAGES)})"
_NUTRIENT_PHASE_CHECK = (
    "nutrient_phase IS NULL OR nutrient_phase IN ("
    + ", ".join(repr(p) for p in NUTRIENT_PHASES)
    + ")"
)
_COVERAGE_PHASE_CHECK = (
    "(coverage = 'universal' AND nutrient_phase IS NULL) OR "
    "(coverage = 'phase_specific' AND nutrient_phase IS NOT NULL)"
)


class StockMixRecipe(Base, TimestampMixin):
    """Stammlösungs-Rezeptur (P9 identity)."""

    __tablename__ = "stock_mix_recipes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Canonical identity — target for plan_segments.recipe_ref",
    )

    label: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        doc="Display label (e.g. Stock A — Veg 16-7-20)",
    )

    dose_role: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        doc="Pump role key: part_a | part_b | ph_down | generic",
    )

    coverage: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        doc="universal | phase_specific",
    )

    nutrient_phase: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
        doc="NUTRIENT_PHASES key when coverage=phase_specific; NULL for universal",
    )

    components: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONBCompat,
        nullable=False,
        doc=(
            '[{ "name": str, "target_g_per_l": float, '
            '"salt_composition_id": optional UUID soft-ref }, ...]'
        ),
    )

    meta: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONBCompat,
        nullable=False,
        default=dict,
        doc="Caveats, dosing hints, NPK honesty markers (not chemistry solver)",
    )

    # AUT-1419 B2: feedforward NPK / element balance (always marked computed in payload).
    computed_elements: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONBCompat,
        nullable=True,
        doc="Elemental g/L stock (n/p/k/ca/mg/s) — computed, never measured",
    )
    computed_npk: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONBCompat,
        nullable=True,
        doc="N/P/K subset g/L stock — computed feedforward (kind=calculated)",
    )
    npk_status: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
        doc="complete | incomplete (open salt evidence / missing library row)",
    )
    npk_missing_salts: Mapped[Optional[list[Any]]] = mapped_column(
        JSONBCompat,
        nullable=True,
        doc="Salt names that make the NPK result non-authoritative",
    )
    npk_computed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="When computed_npk / computed_elements were last recomputed",
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
        doc="Soft-deactivate without deleting identity",
    )

    __table_args__ = (
        CheckConstraint(_DOSE_ROLE_CHECK, name="ck_stock_mix_recipes_dose_role"),
        CheckConstraint(_COVERAGE_CHECK, name="ck_stock_mix_recipes_coverage"),
        CheckConstraint(_NUTRIENT_PHASE_CHECK, name="ck_stock_mix_recipes_nutrient_phase"),
        CheckConstraint(_COVERAGE_PHASE_CHECK, name="ck_stock_mix_recipes_coverage_phase"),
        CheckConstraint(
            "npk_status IS NULL OR npk_status IN ('complete', 'incomplete')",
            name="ck_stock_mix_recipes_npk_status",
        ),
        Index(
            "uq_stock_mix_recipes_active_role_coverage_phase",
            "dose_role",
            "coverage",
            "nutrient_phase",
            unique=True,
            postgresql_where=text("active IS TRUE"),
        ),
    )
