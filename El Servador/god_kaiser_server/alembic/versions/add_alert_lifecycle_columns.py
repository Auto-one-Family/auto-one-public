"""Add alert lifecycle columns to notifications table

Revision ID: add_alert_lifecycle
Revises: a4a7_alert_runtime
Create Date: 2026-03-03 10:00:00.000000

Phase 4B.1.1: Alert-Lifecycle-Spalten fuer ISA-18.2 konformen Alert-Lifecycle.
Adds: status, acknowledged_at, acknowledged_by, resolved_at, correlation_id.

NOTE: parent_notification_id ALREADY EXISTS (Phase 4A cascade suppression).
NOTE: fingerprint ALREADY EXISTS (FIX-07 Grafana dedup).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "add_alert_lifecycle"
down_revision: Union[str, None] = "a4a7_alert_runtime"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Alert lifecycle status (ISA-18.2: active → acknowledged → resolved)
    op.add_column(
        "notifications",
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="active",
            comment="Alert lifecycle status (active, acknowledged, resolved)",
        ),
    )

    # Acknowledge tracking
    op.add_column(
        "notifications",
        sa.Column(
            "acknowledged_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp when alert was acknowledged",
        ),
    )
    op.add_column(
        "notifications",
        sa.Column(
            "acknowledged_by",
            sa.Integer(),
            sa.ForeignKey("user_accounts.id", ondelete="SET NULL"),
            nullable=True,
            comment="User who acknowledged the alert",
        ),
    )

    # Resolve tracking
    op.add_column(
        "notifications",
        sa.Column(
            "resolved_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp when alert was resolved",
        ),
    )

    # Correlation ID for grouping related alerts (e.g., grafana_{fingerprint})
    op.add_column(
        "notifications",
        sa.Column(
            "correlation_id",
            sa.String(128),
            nullable=True,
            comment="Correlation ID for grouping related alerts",
        ),
    )

    # Indexes for Alert-Lifecycle-Queries
    op.create_index(
        "ix_notifications_status_severity",
        "notifications",
        ["status", "severity"],
        postgresql_where=sa.text("resolved_at IS NULL"),
    )
    op.create_index(
        "ix_notifications_correlation",
        "notifications",
        ["correlation_id"],
        postgresql_where=sa.text("correlation_id IS NOT NULL"),
    )

    # Check constraint for valid status values
    op.create_check_constraint(
        "ck_notifications_status",
        "notifications",
        sa.text("status IN ('active', 'acknowledged', 'resolved')"),
    )

    # Set existing notifications to 'resolved' (they are already processed)
    op.execute(
        sa.text(
            "UPDATE notifications SET status = 'resolved', "
            "resolved_at = COALESCE(read_at, updated_at, created_at) "
            "WHERE is_read = true"
        )
    )


def downgrade() -> None:
    op.drop_constraint("ck_notifications_status", "notifications", type_="check")
    op.drop_index("ix_notifications_correlation", table_name="notifications")
    op.drop_index("ix_notifications_status_severity", table_name="notifications")
    op.drop_column("notifications", "correlation_id")
    op.drop_column("notifications", "resolved_at")
    op.drop_column("notifications", "acknowledged_by")
    op.drop_column("notifications", "acknowledged_at")
    op.drop_column("notifications", "status")
