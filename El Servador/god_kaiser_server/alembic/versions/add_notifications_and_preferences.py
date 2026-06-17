"""Add notifications and notification_preferences tables

Revision ID: add_notifications
Revises: add_dashboard_target
Create Date: 2026-03-02 10:00:00.000000

Phase 4A.1: Notification-Stack Backend.

Creates:
- notifications table (UUID PK, user_id FK, channel, severity, category, etc.)
- notification_preferences table (user_id PK+FK, email/ws/digest settings)
- 4 performance indexes on notifications
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = "add_notifications"
down_revision: Union[str, None] = "add_dashboard_target"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- notifications table ----
    op.create_table(
        "notifications",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            comment="Primary key (UUID)",
        ),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("user_accounts.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
            comment="Target user ID",
        ),
        sa.Column(
            "channel",
            sa.String(20),
            nullable=False,
            comment="Delivery channel (websocket, email, webhook)",
        ),
        sa.Column(
            "severity",
            sa.String(20),
            nullable=False,
            server_default="info",
            comment="Severity (critical, warning, info, resolved)",
        ),
        sa.Column(
            "category",
            sa.String(50),
            nullable=False,
            server_default="system",
            comment="Alert category",
        ),
        sa.Column(
            "title",
            sa.String(255),
            nullable=False,
            comment="Short notification title",
        ),
        sa.Column(
            "body",
            sa.Text,
            nullable=True,
            comment="Full notification body",
        ),
        sa.Column(
            "extra_data",
            sa.JSON,
            nullable=False,
            server_default="{}",
            comment="JSON context (esp_id, sensor_type, etc.)",
        ),
        sa.Column(
            "source",
            sa.String(50),
            nullable=False,
            comment="Notification origin",
        ),
        sa.Column(
            "is_read",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
            comment="Whether user has read this",
        ),
        sa.Column(
            "is_archived",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
            comment="Whether archived",
        ),
        sa.Column(
            "digest_sent",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
            comment="Whether included in digest email",
        ),
        sa.Column(
            "parent_notification_id",
            UUID(as_uuid=True),
            sa.ForeignKey("notifications.id", ondelete="SET NULL"),
            nullable=True,
            comment="Parent notification for cascade suppression",
        ),
        sa.Column(
            "read_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When user read this notification",
        ),
        # TimestampMixin columns
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="Record creation timestamp (UTC)",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="Record last update timestamp (UTC)",
        ),
    )

    # Performance indexes
    op.create_index(
        "ix_notifications_user_unread",
        "notifications",
        ["user_id", "is_read", "is_archived"],
    )
    op.create_index(
        "ix_notifications_created_at",
        "notifications",
        ["created_at"],
    )
    op.create_index(
        "ix_notifications_source_category",
        "notifications",
        ["source", "category"],
    )
    op.create_index(
        "ix_notifications_severity",
        "notifications",
        ["severity"],
    )

    # ---- notification_preferences table ----
    op.create_table(
        "notification_preferences",
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("user_accounts.id", ondelete="CASCADE"),
            primary_key=True,
            comment="User ID (PK + FK)",
        ),
        sa.Column(
            "websocket_enabled",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("true"),
            comment="WebSocket notifications enabled",
        ),
        sa.Column(
            "email_enabled",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
            comment="Email notifications enabled",
        ),
        sa.Column(
            "email_address",
            sa.String(255),
            nullable=True,
            comment="Override email (uses user.email if NULL)",
        ),
        sa.Column(
            "email_severities",
            sa.JSON,
            nullable=False,
            server_default='["critical", "warning"]',
            comment="Severities that trigger email",
        ),
        sa.Column(
            "quiet_hours_enabled",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
            comment="Quiet hours active",
        ),
        sa.Column(
            "quiet_hours_start",
            sa.String(5),
            nullable=True,
            server_default="22:00",
            comment="Quiet hours start (HH:MM)",
        ),
        sa.Column(
            "quiet_hours_end",
            sa.String(5),
            nullable=True,
            server_default="07:00",
            comment="Quiet hours end (HH:MM)",
        ),
        sa.Column(
            "digest_interval_minutes",
            sa.Integer,
            nullable=False,
            server_default="60",
            comment="Digest interval in minutes (0 = disabled)",
        ),
        sa.Column(
            "browser_notifications",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
            comment="Browser notification permission",
        ),
        # TimestampMixin columns
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="Record creation timestamp (UTC)",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="Record last update timestamp (UTC)",
        ),
    )


def downgrade() -> None:
    op.drop_table("notification_preferences")
    op.drop_index("ix_notifications_severity", table_name="notifications")
    op.drop_index("ix_notifications_source_category", table_name="notifications")
    op.drop_index("ix_notifications_created_at", table_name="notifications")
    op.drop_index("ix_notifications_user_unread", table_name="notifications")
    op.drop_table("notifications")
