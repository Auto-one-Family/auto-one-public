"""Add logic_hysteresis_states table for persistent hysteresis state

L2 Hysterese-Härtung: Hysteresis state survives server restarts.
Without persistence, active states reset to inactive on restart,
leaving actuators running uncontrolled until next threshold crossing.

Revision ID: add_logic_hysteresis_states
Revises: fix_null_coalesce_unique
Create Date: 2026-03-30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "add_logic_hysteresis_states"
down_revision: Union[str, None] = "fix_null_coalesce_unique"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if "logic_hysteresis_states" not in existing_tables:
        op.create_table(
            "logic_hysteresis_states",
            sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
            sa.Column(
                "rule_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("cross_esp_logic.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("condition_index", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("last_value", sa.Float(), nullable=True),
            sa.Column("last_activation", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_deactivation", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.UniqueConstraint(
                "rule_id", "condition_index", name="uq_hysteresis_state_rule_cond"
            ),
        )


def downgrade() -> None:
    op.drop_table("logic_hysteresis_states")
