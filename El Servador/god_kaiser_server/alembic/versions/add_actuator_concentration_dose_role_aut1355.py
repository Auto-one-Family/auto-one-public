"""Add concentration + dose_role to actuator_configs (AUT-1355)

Revision ID: add_actuator_conc_dose_role_aut1355
Revises: add_batch_prior_volume_aut1346
Create Date: 2026-07-25

U4-a: Pump SSOT for empiric concentration (µS/cm rise per ml per L) and
structured recipe role (part_a / part_b / ph_down / generic).

Pattern 1:1 like flow_rate_ml_s — nullable, no backfill, server-only
(never sent to firmware). Downgrade drops both columns.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "add_actuator_conc_dose_role_aut1355"
down_revision: Union[str, None] = "add_batch_prior_volume_aut1346"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("actuator_configs")}
    if "concentration" not in columns:
        op.add_column(
            "actuator_configs",
            sa.Column(
                "concentration",
                sa.Float(),
                nullable=True,
                comment=(
                    "AUT-1355: Empiric µS/cm rise per ml per L (pump SSOT). "
                    "NULL = unset; runtime fallback to dose_config.components[].concentration. "
                    "Server-side only — never sent to firmware."
                ),
            ),
        )
    if "dose_role" not in columns:
        op.add_column(
            "actuator_configs",
            sa.Column(
                "dose_role",
                sa.String(length=32),
                nullable=True,
                comment=(
                    "AUT-1355: Recipe role — part_a | part_b | ph_down | generic. "
                    "NULL = unset. Positional dose match remains; role is explicit identity."
                ),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("actuator_configs")}
    if "dose_role" in columns:
        op.drop_column("actuator_configs", "dose_role")
    if "concentration" in columns:
        op.drop_column("actuator_configs", "concentration")
