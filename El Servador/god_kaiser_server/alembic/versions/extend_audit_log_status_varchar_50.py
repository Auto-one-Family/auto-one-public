"""Extend audit_logs.status from VARCHAR(20) to VARCHAR(50).

Lifecycle event_type values like 'exit_blocked_config_pending' (26 chars)
exceed the previous VARCHAR(20) limit, causing StringDataRightTruncationError
in IntentOutcomeLifecycleHandler and triggering a permanent reconciliation loop
(retry every 5s, always failing).

Revision ID: extend_audit_log_status_varchar_50
Revises: esp_hb_runtime_telemetry
Create Date: 2026-04-05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "extend_audit_log_status_varchar_50"
down_revision: Union[str, None] = "esp_hb_runtime_telemetry"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PostgreSQL: VARCHAR increase is a metadata-only operation, no table rewrite.
    # Fixes StringDataRightTruncationError for lifecycle event_type values > 20 chars
    # (e.g. "exit_blocked_config_pending" = 26 chars).
    op.alter_column(
        "audit_logs",
        "status",
        existing_type=sa.VARCHAR(20),
        type_=sa.VARCHAR(50),
        existing_nullable=False,
    )


def downgrade() -> None:
    # WARNING: Downgrade will silently truncate any status values longer than 20 chars.
    op.alter_column(
        "audit_logs",
        "status",
        existing_type=sa.VARCHAR(50),
        type_=sa.VARCHAR(20),
        existing_nullable=False,
    )
