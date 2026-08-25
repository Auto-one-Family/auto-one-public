"""Add nutrient_solution_batches table

Revision ID: add_nutrient_solution_batches
Revises: add_uebergang_vorbluete_nutrient_phase
Create Date: 2026-07-20

AUT-1211 follow-up — event log of tank mix/refill/withdrawal/remeasurement
entries (verify-plan, Stufe 2). Purely additive: no DROP COLUMN, no data
migration, table starts empty.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision: str = "add_nutrient_solution_batches"
down_revision: Union[str, None] = "add_uebergang_vorbluete_nutrient_phase"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NUTRIENT_BATCH_ENTRY_TYPES = (
    "full_reset",
    "top_up_dose",
    "fresh_water_refill",
    "withdrawal",
    "remeasurement_only",
    "system_incident",
)
_ENTRY_TYPE_CHECK = (
    f"entry_type IN ({', '.join(repr(e) for e in NUTRIENT_BATCH_ENTRY_TYPES)})"
)

NUTRIENT_BATCH_ACQUISITION_METHODS = (
    "measured_flow",
    "measured_level",
    "computed_runtime_x_rate",
    "manual_entry",
)
_ACQUISITION_METHOD_CHECK = (
    f"acquisition_method IN ({', '.join(repr(m) for m in NUTRIENT_BATCH_ACQUISITION_METHODS)})"
)

NUTRIENT_BATCH_QUALIFIERS = ("precise", "approximate", "estimated")
_QUALIFIER_CHECK = f"qualifier IN ({', '.join(repr(q) for q in NUTRIENT_BATCH_QUALIFIERS)})"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = inspector.get_table_names()

    if "nutrient_solution_batches" not in existing_tables:
        op.create_table(
            "nutrient_solution_batches",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                nullable=False,
                comment="Primary key (UUID)",
            ),
            sa.Column(
                "tank_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("tanks.id", ondelete="RESTRICT"),
                nullable=False,
                comment="Foreign key to tanks.id",
            ),
            sa.Column(
                "entry_type",
                sa.String(length=32),
                nullable=False,
                comment="Entry type (see NUTRIENT_BATCH_ENTRY_TYPES)",
            ),
            sa.Column(
                "occurred_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
                comment="Backdatable wall-clock time the entry occurred (UTC)",
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
                comment="Server insert timestamp (UTC), never backdated",
            ),
            sa.Column(
                "recipe_label",
                sa.String(length=200),
                nullable=True,
                comment="Optional free-text recipe/profile name",
            ),
            sa.Column(
                "volume_l",
                sa.Float(),
                nullable=False,
                comment="Volume in liters this entry represents",
            ),
            sa.Column(
                "components",
                postgresql.JSONB(),
                nullable=False,
                comment="List of fertilizer-product and/or salt-recipe component dicts",
            ),
            sa.Column(
                "ec_measured_after",
                sa.Float(),
                nullable=True,
                comment="Measured EC (mS/cm) after this entry, if any",
            ),
            sa.Column(
                "ec_was_measured",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
                comment="Whether EC was actually measured (NULL-vs-0 disambiguation)",
            ),
            sa.Column(
                "ph_measured_after",
                sa.Float(),
                nullable=True,
                comment="Measured pH after this entry, if any",
            ),
            sa.Column(
                "ph_was_measured",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
                comment="Whether pH was actually measured (NULL-vs-0 disambiguation)",
            ),
            sa.Column(
                "acquisition_method",
                sa.String(length=32),
                nullable=False,
                comment="How volume_l was determined (see NUTRIENT_BATCH_ACQUISITION_METHODS)",
            ),
            sa.Column(
                "qualifier",
                sa.String(length=16),
                nullable=False,
                comment="Confidence qualifier for this entry (see NUTRIENT_BATCH_QUALIFIERS)",
            ),
            sa.CheckConstraint(_ENTRY_TYPE_CHECK, name="ck_nutrient_solution_batches_entry_type"),
            sa.CheckConstraint(
                _ACQUISITION_METHOD_CHECK,
                name="ck_nutrient_solution_batches_acquisition_method",
            ),
            sa.CheckConstraint(_QUALIFIER_CHECK, name="ck_nutrient_solution_batches_qualifier"),
        )
        op.create_index(
            "idx_nutrient_solution_batches_tank_id",
            "nutrient_solution_batches",
            ["tank_id"],
        )
        op.create_index(
            "idx_nutrient_solution_batches_occurred_at",
            "nutrient_solution_batches",
            ["occurred_at"],
        )


def downgrade() -> None:
    op.drop_index(
        "idx_nutrient_solution_batches_occurred_at",
        table_name="nutrient_solution_batches",
    )
    op.drop_index(
        "idx_nutrient_solution_batches_tank_id",
        table_name="nutrient_solution_batches",
    )
    op.drop_table("nutrient_solution_batches")
