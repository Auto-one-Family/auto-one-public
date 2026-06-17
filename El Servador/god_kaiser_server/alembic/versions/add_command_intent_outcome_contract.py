"""Add command intent/outcome contract tables

P0.1/P0.2 persistence:
- command_intents (orchestration-level tracking)
- command_outcomes (terminal contract states)

Revision ID: add_command_intent_outcome_contract
Revises: add_hardware_type_to_actuator_configs
Create Date: 2026-04-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "add_command_intent_outcome_contract"
down_revision: Union[str, None] = "add_hardware_type_to_actuator_configs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "command_intents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("intent_id", sa.String(length=128), nullable=False),
        sa.Column("correlation_id", sa.String(length=128), nullable=False),
        sa.Column("esp_id", sa.String(length=64), nullable=False),
        sa.Column("flow", sa.String(length=32), nullable=False),
        sa.Column("orchestration_state", sa.String(length=32), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_command_intents_intent_id",
        "command_intents",
        ["intent_id"],
        unique=True,
    )
    op.create_index(
        "idx_command_intents_correlation_id",
        "command_intents",
        ["correlation_id"],
        unique=False,
    )
    op.create_index(
        "idx_command_intents_state_created_at",
        "command_intents",
        ["orchestration_state", "created_at"],
        unique=False,
    )

    op.create_table(
        "command_outcomes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("intent_id", sa.String(length=128), nullable=False),
        sa.Column("correlation_id", sa.String(length=128), nullable=False),
        sa.Column("esp_id", sa.String(length=64), nullable=False),
        sa.Column("flow", sa.String(length=32), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=True),
        sa.Column("reason", sa.String(length=512), nullable=True),
        sa.Column("retryable", sa.Boolean(), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=True),
        sa.Column("seq", sa.Integer(), nullable=True),
        sa.Column("epoch", sa.Integer(), nullable=True),
        sa.Column("ttl_ms", sa.Integer(), nullable=True),
        sa.Column("ts", sa.Integer(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("terminal_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_command_outcomes_intent_id",
        "command_outcomes",
        ["intent_id"],
        unique=True,
    )
    op.create_index(
        "idx_command_outcomes_correlation_id",
        "command_outcomes",
        ["correlation_id"],
        unique=False,
    )
    op.create_index(
        "idx_command_outcomes_outcome_created_at",
        "command_outcomes",
        ["outcome", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_command_outcomes_outcome_created_at", table_name="command_outcomes")
    op.drop_index("idx_command_outcomes_correlation_id", table_name="command_outcomes")
    op.drop_index("idx_command_outcomes_intent_id", table_name="command_outcomes")
    op.drop_table("command_outcomes")

    op.drop_index("idx_command_intents_state_created_at", table_name="command_intents")
    op.drop_index("idx_command_intents_correlation_id", table_name="command_intents")
    op.drop_index("idx_command_intents_intent_id", table_name="command_intents")
    op.drop_table("command_intents")
