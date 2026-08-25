"""Add stock_mix_recipes table + F3 seed (AUT-1361)

Revision ID: add_stock_mix_recipes_aut1361
Revises: add_actuator_conc_dose_role_aut1355
Create Date: 2026-07-25

Purely additive table + deterministic F3 seed rows (phase_specific).
Downgrade drops seed then table. No Markenname in seed labels.
"""

from __future__ import annotations

import uuid
from typing import Any, Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision: str = "add_stock_mix_recipes_aut1361"
down_revision: Union[str, None] = "add_actuator_conc_dose_role_aut1355"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Deterministic UUIDs for recipe_ref wiring / tests.
_SEED_NS = uuid.UUID("a1361361-0000-4000-8000-000000000001")


def _rid(dose_role: str, nutrient_phase: str) -> uuid.UUID:
    return uuid.uuid5(_SEED_NS, f"{dose_role}:{nutrient_phase}")


# AUT-1369: display-only recipe volume intent (ml Stock A/B per L tank), NOT the
# runtime dose. Actual ml come from volume_share × concentration (AUT-1367).
_DOSE_ML = {"part_a": 4.0, "part_b": 4.0}

# AUT-1362: UI shows only handling_hint (Klartext). No chemistry/%/factor jargon in UI.
# A/B dosing order + Arbeits-pH belong to tank/dose layer — not Ansetz-Rechner.
_HANDLING_HINTS = {
    "part_a": "In Wasser auflösen, umrühren.",
    "part_b": (
        "Warmes Wasser (~25–30 °C), langsam unter Rühren einlaufen lassen, "
        "leicht sauer halten — dann löst sich alles klar."
    ),
    "ph_down": "Säure vorsichtig zugeben; nicht mit Stock A/B mischen.",
    "generic": "Nach Rezeptauflösung umrühren.",
}

# Internal honesty marker only (not shown in Ansetz-Rechner).
_UEBERGANG_HONESTY = (
    'Etikett „8-6-12" ist locker — real N:P₂O₅:K₂O ≈ 8:5,3:10,2 '
    "(bewusst treu an den Stammmengen; nicht als exakt-NPK behaupten)."
)

# F3 component tables (exact Issue AUT-1361 numbers).
_VEG_A = [{"name": "Calcinit", "target_g_per_l": 150.0}]
_VEG_B = [
    {"name": "MgSO₄·7H₂O", "target_g_per_l": 87.5},
    {"name": "Kristalon Rot", "target_g_per_l": 137.5},
]
_UEBERGANG_A = [{"name": "Calcinit", "target_g_per_l": 87.5}]
_UEBERGANG_B = [
    {"name": "MgSO₄·7H₂O", "target_g_per_l": 55.0},
    {"name": "Kristalon Rot", "target_g_per_l": 62.5},
    {"name": "MKP", "target_g_per_l": 12.5},
]
_BLUETE_A = [{"name": "Calcinit", "target_g_per_l": 100.0}]
_BLUETE_B = [
    {"name": "MgSO₄·7H₂O", "target_g_per_l": 62.5},
    {"name": "Kristalon Rot", "target_g_per_l": 50.0},
    {"name": "MKP", "target_g_per_l": 50.0},
]

# F3 bucket → NUTRIENT_PHASES keys (Verify-Plan Delta).
_PHASE_BUCKETS: list[tuple[str, str, list[str], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]] = [
    (
        "veg",
        "Veg 16-7-20",
        ["veg-frueh", "veg-spaet"],
        _VEG_A,
        _VEG_B,
        {
            "npk_label": "16-7-20",
            "concentration_factor": 250,
            "dose_ml_per_l": _DOSE_ML,
            # Internal only — FE Auto-Recompute; never show factor to user (AUT-1362).
            "solubility_watch": {
                "role": "part_b",
                "fallback_factor": 200,
            },
        },
    ),
    (
        "uebergang",
        "Übergang 8-6-12",
        ["uebergang-vorbluete"],
        _UEBERGANG_A,
        _UEBERGANG_B,
        {
            "npk_label": "8-6-12",
            "concentration_factor": 250,
            "dose_ml_per_l": _DOSE_ML,
            "npk_honesty": _UEBERGANG_HONESTY,
        },
    ),
    (
        "bluete",
        "Blüte 8-11-16",
        ["bluete-stretch", "bluete-bulk", "bluete-ende"],
        _BLUETE_A,
        _BLUETE_B,
        {
            "npk_label": "8-11-16",
            "concentration_factor": 250,
            "dose_ml_per_l": _DOSE_ML,
        },
    ),
]


def _seed_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for _bucket, bucket_label, phases, comps_a, comps_b, base_meta in _PHASE_BUCKETS:
        for phase in phases:
            for role, comps in (("part_a", comps_a), ("part_b", comps_b)):
                meta = dict(base_meta)
                meta["handling_hint"] = _HANDLING_HINTS[role]
                # solubility_watch only on Veg part_b (optional dilute toggle).
                watch = meta.get("solubility_watch")
                if not (
                    role == "part_b"
                    and isinstance(watch, dict)
                    and watch.get("role") == "part_b"
                ):
                    meta.pop("solubility_watch", None)
                rows.append(
                    {
                        "id": _rid(role, phase),
                        "label": f"Stock {'A' if role == 'part_a' else 'B'} — {bucket_label}",
                        "dose_role": role,
                        "coverage": "phase_specific",
                        "nutrient_phase": phase,
                        "components": comps,
                        "metadata": meta,
                        "active": True,
                    }
                )
    return rows


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = inspector.get_table_names()

    if "stock_mix_recipes" not in existing:
        op.create_table(
            "stock_mix_recipes",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("label", sa.String(length=200), nullable=False),
            sa.Column("dose_role", sa.String(length=32), nullable=False),
            sa.Column("coverage", sa.String(length=32), nullable=False),
            sa.Column("nutrient_phase", sa.String(length=32), nullable=True),
            sa.Column("components", postgresql.JSONB(), nullable=False),
            sa.Column(
                "metadata",
                postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column(
                "active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.CheckConstraint(
                "dose_role IN ('part_a', 'part_b', 'ph_down', 'generic')",
                name="ck_stock_mix_recipes_dose_role",
            ),
            sa.CheckConstraint(
                "coverage IN ('universal', 'phase_specific')",
                name="ck_stock_mix_recipes_coverage",
            ),
            sa.CheckConstraint(
                "(coverage = 'universal' AND nutrient_phase IS NULL) OR "
                "(coverage = 'phase_specific' AND nutrient_phase IS NOT NULL)",
                name="ck_stock_mix_recipes_coverage_phase",
            ),
        )
        op.create_index(
            "uq_stock_mix_recipes_active_role_coverage_phase",
            "stock_mix_recipes",
            ["dose_role", "coverage", "nutrient_phase"],
            unique=True,
            postgresql_where=sa.text("active IS TRUE"),
        )

    recipes = sa.table(
        "stock_mix_recipes",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("label", sa.String),
        sa.column("dose_role", sa.String),
        sa.column("coverage", sa.String),
        sa.column("nutrient_phase", sa.String),
        sa.column("components", postgresql.JSONB),
        sa.column("metadata", postgresql.JSONB),
        sa.column("active", sa.Boolean),
    )

    # Idempotent: skip rows whose deterministic id already exists.
    existing_ids = set()
    if "stock_mix_recipes" in inspector.get_table_names():
        result = bind.execute(sa.text("SELECT id FROM stock_mix_recipes"))
        existing_ids = {row[0] for row in result}

    to_insert = []
    for row in _seed_rows():
        if row["id"] in existing_ids:
            continue
        to_insert.append(
            {
                "id": row["id"],
                "label": row["label"],
                "dose_role": row["dose_role"],
                "coverage": row["coverage"],
                "nutrient_phase": row["nutrient_phase"],
                "components": row["components"],
                "metadata": row["metadata"],
                "active": True,
            }
        )
    if to_insert:
        op.bulk_insert(recipes, to_insert)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "stock_mix_recipes" not in inspector.get_table_names():
        return

    for row in _seed_rows():
        op.execute(
            sa.text("DELETE FROM stock_mix_recipes WHERE id = CAST(:id AS uuid)").bindparams(
                id=str(row["id"])
            )
        )

    op.drop_index(
        "uq_stock_mix_recipes_active_role_coverage_phase",
        table_name="stock_mix_recipes",
    )
    op.drop_table("stock_mix_recipes")
