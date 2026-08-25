"""Add stock_recipe_ref + stock_prepared_at to actuator_configs (AUT-1410)

Revision ID: add_actuator_stock_identity_aut1410
Revises: add_tank_fresh_water_fields_aut1381
Create Date: 2026-07-27

SR-1: Pump identity/traceability for „Stock neu angesetzt".
Pure display fields — not a concentration memory. Soft UUID reference to
stock_mix_recipes.id (no hard FK; AUT-1361 still in review).

Pattern 1:1 like add_actuator_concentration_dose_role_aut1355 — nullable,
no backfill, server-only (never sent to firmware). Downgrade drops both.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision: str = "add_actuator_stock_identity_aut1410"
down_revision: Union[str, None] = "add_tank_fresh_water_fields_aut1381"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("actuator_configs")}
    if "stock_recipe_ref" not in columns:
        op.add_column(
            "actuator_configs",
            sa.Column(
                "stock_recipe_ref",
                postgresql.UUID(as_uuid=True),
                nullable=True,
                comment=(
                    "AUT-1410: Soft ref to stock_mix_recipes.id (which recipe is "
                    "physically attached to this pump). Display/traceability only — "
                    "never used to derive concentration. No hard FK."
                ),
            ),
        )
    if "stock_prepared_at" not in columns:
        op.add_column(
            "actuator_configs",
            sa.Column(
                "stock_prepared_at",
                sa.DateTime(timezone=True),
                nullable=True,
                comment=(
                    "AUT-1410: When Robin last confirmed „Stock neu angesetzt\" "
                    "for this pump. Display/traceability only."
                ),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("actuator_configs")}
    if "stock_prepared_at" in columns:
        op.drop_column("actuator_configs", "stock_prepared_at")
    if "stock_recipe_ref" in columns:
        op.drop_column("actuator_configs", "stock_recipe_ref")
