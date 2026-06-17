"""Fix DateTime columns missing timezone=True

Revision ID: fix_datetime_timezone_naive
Revises: change_extra_data_jsonb
Create Date: 2026-03-08 16:00:00.000000

BUG-02: 5 DateTime columns were defined without timezone=True, causing
TypeError when comparing naive DB timestamps with aware Python datetimes.
Violates api-rules.md: "DateTime ohne timezone=True in Models → DB liefert
naive Timestamps. Immer DateTime(timezone=True)."

Affected columns:
- subzone_configs.last_ack_at (BUG-02 root cause)
- sensor_configs.last_manual_request
- sensor_data.timestamp (CRITICAL time-series column)
- cross_esp_logic.last_triggered
- ai_predictions.timestamp

Migration is lossless: PostgreSQL converts existing TIMESTAMP values to
TIMESTAMPTZ by assuming UTC (the server timezone).
"""

from typing import Union

from alembic import op
import sqlalchemy as sa

revision: str = "fix_datetime_timezone_naive"
down_revision: Union[str, None] = "change_extra_data_jsonb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "subzone_configs",
        "last_ack_at",
        type_=sa.DateTime(timezone=True),
        existing_type=sa.DateTime(),
        existing_nullable=True,
    )
    op.alter_column(
        "sensor_configs",
        "last_manual_request",
        type_=sa.DateTime(timezone=True),
        existing_type=sa.DateTime(),
        existing_nullable=True,
    )
    op.alter_column(
        "sensor_data",
        "timestamp",
        type_=sa.DateTime(timezone=True),
        existing_type=sa.DateTime(),
        existing_nullable=False,
    )
    op.alter_column(
        "cross_esp_logic",
        "last_triggered",
        type_=sa.DateTime(timezone=True),
        existing_type=sa.DateTime(),
        existing_nullable=True,
    )
    op.alter_column(
        "ai_predictions",
        "timestamp",
        type_=sa.DateTime(timezone=True),
        existing_type=sa.DateTime(),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "ai_predictions",
        "timestamp",
        type_=sa.DateTime(),
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
    )
    op.alter_column(
        "cross_esp_logic",
        "last_triggered",
        type_=sa.DateTime(),
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=True,
    )
    op.alter_column(
        "sensor_data",
        "timestamp",
        type_=sa.DateTime(),
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
    )
    op.alter_column(
        "sensor_configs",
        "last_manual_request",
        type_=sa.DateTime(),
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=True,
    )
    op.alter_column(
        "subzone_configs",
        "last_ack_at",
        type_=sa.DateTime(),
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=True,
    )
