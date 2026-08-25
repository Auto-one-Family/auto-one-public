"""Add dose_ml and flow_rate_ml_s_snapshot to logic_execution_history

Revision ID: add_logic_history_dose_fields
Revises: add_actuator_flow_rate_cal
Create Date: 2026-07-01

AO-5: Dosier-Audit. NULL = nicht-Dosier-Ausführung (sicherer Default).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "add_logic_history_dose_fields"
down_revision: Union[str, None] = "add_actuator_flow_rate_cal"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("logic_execution_history")}
    if "dose_ml" not in columns:
        op.add_column(
            "logic_execution_history",
            sa.Column(
                "dose_ml",
                sa.Float(),
                nullable=True,
                comment="AO-5: Dispensed volume ml. NULL = time-only dispatch.",
            ),
        )
    if "flow_rate_ml_s_snapshot" not in columns:
        op.add_column(
            "logic_execution_history",
            sa.Column(
                "flow_rate_ml_s_snapshot",
                sa.Float(),
                nullable=True,
                comment="AO-5: Flow rate snapshot ml/s at execution time.",
            ),
        )
    # No backfill — NULL correct for all existing rows


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("logic_execution_history")}
    if "dose_ml" in columns:
        op.drop_column("logic_execution_history", "dose_ml")
    if "flow_rate_ml_s_snapshot" in columns:
        op.drop_column("logic_execution_history", "flow_rate_ml_s_snapshot")
