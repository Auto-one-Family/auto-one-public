"""Add critical-rule degraded-handling fields to cross_esp_logic

Revision ID: add_critical_degraded
Revises: add_sensor_lifecycle
Create Date: 2026-04-22

AUT-111: Critical-Rule Degraded-Handling.
Adds: is_critical, escalation_policy, degraded_since, degraded_reason.
Partial index on (is_critical, degraded_since) WHERE degraded_since IS NOT NULL.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "add_critical_degraded"
down_revision: Union[str, None] = "add_sensor_lifecycle"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "cross_esp_logic",
        sa.Column(
            "is_critical",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="Whether this rule is safety-critical",
        ),
    )
    op.add_column(
        "cross_esp_logic",
        sa.Column(
            "escalation_policy",
            sa.JSON(),
            nullable=True,
            comment="Escalation policy for critical rules when degraded",
        ),
    )
    op.add_column(
        "cross_esp_logic",
        sa.Column(
            "degraded_since",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp when rule entered degraded state",
        ),
    )
    op.add_column(
        "cross_esp_logic",
        sa.Column(
            "degraded_reason",
            sa.String(64),
            nullable=True,
            comment="Reason for degraded state",
        ),
    )
    op.create_index(
        "idx_rule_degraded_critical",
        "cross_esp_logic",
        ["is_critical", "degraded_since"],
        postgresql_where=sa.text("degraded_since IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_rule_degraded_critical", table_name="cross_esp_logic")
    op.drop_column("cross_esp_logic", "degraded_reason")
    op.drop_column("cross_esp_logic", "degraded_since")
    op.drop_column("cross_esp_logic", "escalation_policy")
    op.drop_column("cross_esp_logic", "is_critical")
