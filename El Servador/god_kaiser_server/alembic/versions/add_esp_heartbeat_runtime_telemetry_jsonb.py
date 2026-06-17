"""Add JSONB runtime_telemetry to esp_heartbeat_logs (firmware 2026-04 heartbeat extras).

Revision ID: esp_hb_runtime_telemetry
Revises: add_contract_shadow_fields_to_command_outcomes

Strategy (Option B): store firmware-specific booleans/counters/reason strings in one JSONB
column to avoid wide schema churn; core heap/rssi/uptime columns stay query-optimized.

"""

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "esp_hb_runtime_telemetry"
down_revision: Union[str, None] = "add_contract_shadow_fields_to_command_outcomes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "esp_heartbeat_logs",
        sa.Column(
            "runtime_telemetry",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("esp_heartbeat_logs", "runtime_telemetry")
