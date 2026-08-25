"""Add daily dose/execution limits to cross_esp_logic

Revision ID: add_daily_limits_cross_esp_logic
Revises: add_logic_history_dose_fields
Create Date: 2026-07-01

AO-4/AUT-993: Tages-Sicherheitsdeckel für Dosier-Regeln.
Adds: max_executions_per_day, max_dose_ml_per_day (beide nullable, NULL = kein Limit).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "add_daily_limits_cross_esp_logic"
down_revision: Union[str, None] = "add_logic_history_dose_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("cross_esp_logic")}
    if "max_executions_per_day" not in columns:
        op.add_column(
            "cross_esp_logic",
            sa.Column(
                "max_executions_per_day",
                sa.Integer(),
                nullable=True,
                comment="AUT-993: Maximum executions per day (rolling 24h window)",
            ),
        )
    if "max_dose_ml_per_day" not in columns:
        op.add_column(
            "cross_esp_logic",
            sa.Column(
                "max_dose_ml_per_day",
                sa.Float(),
                nullable=True,
                comment="AUT-993: Maximum total dose ml per day (rolling 24h, requires AO-5 dose_ml)",
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("cross_esp_logic")}
    if "max_dose_ml_per_day" in columns:
        op.drop_column("cross_esp_logic", "max_dose_ml_per_day")
    if "max_executions_per_day" in columns:
        op.drop_column("cross_esp_logic", "max_executions_per_day")
