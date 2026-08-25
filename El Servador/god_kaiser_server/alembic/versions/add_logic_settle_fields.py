"""Add settle_after_rule_id + settle_seconds columns to cross_esp_logic

Revision ID: add_logic_settle_fields
Revises: add_dashboard_user_assignments
Create Date: 2026-07-16

AUT-1115 (S5, A10 EC-Dosier-Welle): lets a rule wait for a settle window after
the LAST EXECUTION OF A DIFFERENT rule (e.g. EC-Verduennen waits after
Nachfuellen) before it evaluates again. NULL/NULL = current behavior
unchanged (only the existing cooldown_seconds check applies).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision: str = "add_logic_settle_fields"
down_revision: Union[str, None] = "add_dashboard_user_assignments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("cross_esp_logic")}
    if "settle_after_rule_id" not in columns:
        op.add_column(
            "cross_esp_logic",
            sa.Column(
                "settle_after_rule_id",
                postgresql.UUID(as_uuid=True),
                nullable=True,
                comment=(
                    "AUT-1115: Wait for settle_seconds after the last execution of THIS "
                    "other rule before evaluating. NULL = no settle dependency."
                ),
            ),
        )
    if "settle_seconds" not in columns:
        op.add_column(
            "cross_esp_logic",
            sa.Column(
                "settle_seconds",
                sa.Integer(),
                nullable=True,
                comment=(
                    "AUT-1115: Settle window in seconds, evaluated against "
                    "settle_after_rule_id's last execution. NULL = no settle wait."
                ),
            ),
        )
    # No backfill — NULL/NULL is the correct default (no behavior change for existing rows)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("cross_esp_logic")}
    if "settle_seconds" in columns:
        op.drop_column("cross_esp_logic", "settle_seconds")
    if "settle_after_rule_id" in columns:
        op.drop_column("cross_esp_logic", "settle_after_rule_id")
