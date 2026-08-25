"""Add computed NPK fields to stock_mix_recipes (AUT-1419 / B2)

Revision ID: add_stock_mix_npk_fields_aut1419
Revises: add_salt_compositions_aut1418
Create Date: 2026-07-27

Additive nullable columns for feedforward NPK/element balance.
No backfill with invented numbers. Downgrade drops columns.
Does not touch calculate_dose_ml / volume_share / actuator stock-reset fields.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision: str = "add_stock_mix_npk_fields_aut1419"
down_revision: Union[str, None] = "add_salt_compositions_aut1418"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "stock_mix_recipes" not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns("stock_mix_recipes")}

    if "computed_elements" not in columns:
        op.add_column(
            "stock_mix_recipes",
            sa.Column(
                "computed_elements",
                postgresql.JSONB(),
                nullable=True,
                comment="AUT-1419: elemental g/L stock (computed feedforward)",
            ),
        )
    if "computed_npk" not in columns:
        op.add_column(
            "stock_mix_recipes",
            sa.Column(
                "computed_npk",
                postgresql.JSONB(),
                nullable=True,
                comment="AUT-1419: N/P/K g/L stock subset, always marked computed",
            ),
        )
    if "npk_status" not in columns:
        op.add_column(
            "stock_mix_recipes",
            sa.Column(
                "npk_status",
                sa.String(length=32),
                nullable=True,
                comment="AUT-1419: complete | incomplete",
            ),
        )
    if "npk_missing_salts" not in columns:
        op.add_column(
            "stock_mix_recipes",
            sa.Column(
                "npk_missing_salts",
                postgresql.JSONB(),
                nullable=True,
                comment="AUT-1419: salt names blocking complete evidence",
            ),
        )
    if "npk_computed_at" not in columns:
        op.add_column(
            "stock_mix_recipes",
            sa.Column(
                "npk_computed_at",
                sa.DateTime(timezone=True),
                nullable=True,
                comment="AUT-1419: last NPK recompute timestamp",
            ),
        )

    # Optional check — only if constraint absent (best-effort; SQLite tests use model).
    existing_cks = {ck["name"] for ck in inspector.get_check_constraints("stock_mix_recipes")}
    if "ck_stock_mix_recipes_npk_status" not in existing_cks:
        op.create_check_constraint(
            "ck_stock_mix_recipes_npk_status",
            "stock_mix_recipes",
            "npk_status IS NULL OR npk_status IN ('complete', 'incomplete')",
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "stock_mix_recipes" not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns("stock_mix_recipes")}
    existing_cks = {ck["name"] for ck in inspector.get_check_constraints("stock_mix_recipes")}

    if "ck_stock_mix_recipes_npk_status" in existing_cks:
        op.drop_constraint(
            "ck_stock_mix_recipes_npk_status",
            "stock_mix_recipes",
            type_="check",
        )
    for col in (
        "npk_computed_at",
        "npk_missing_salts",
        "npk_status",
        "computed_npk",
        "computed_elements",
    ):
        if col in columns:
            op.drop_column("stock_mix_recipes", col)
