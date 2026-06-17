"""Add email_log table for email delivery tracking

Revision ID: add_email_log
Revises: make_checks_nullable
Create Date: 2026-03-03 21:00:00.000000

Phase C V1.1: Email-Status-Tracking.
Tracks email delivery status per notification (Resend/SMTP providers).
Used by NotificationRouter, DigestService, and admin API endpoints.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "add_email_log"
down_revision: Union[str, None] = "make_checks_nullable"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if "email_log" not in existing_tables:
        op.create_table(
            "email_log",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column(
                "notification_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("notifications.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("to_address", sa.String(255), nullable=False),
            sa.Column("subject", sa.String(500), nullable=False),
            sa.Column("template", sa.String(100), nullable=True),
            sa.Column("provider", sa.String(50), nullable=False),
            sa.Column(
                "status",
                sa.String(50),
                nullable=False,
                server_default="pending",
            ),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
        )

        # Index on notification_id for FK lookups
        op.create_index(
            "ix_email_log_notification_id",
            "email_log",
            ["notification_id"],
        )

        # Expression indexes via raw SQL (sa.text in create_index is unreliable)
        op.execute(
            "CREATE INDEX ix_email_log_status_created "
            "ON email_log (status, created_at DESC)"
        )
        op.execute(
            "CREATE INDEX ix_email_log_created_at "
            "ON email_log (created_at DESC)"
        )


def downgrade() -> None:
    op.drop_index("ix_email_log_created_at", table_name="email_log")
    op.drop_index("ix_email_log_status_created", table_name="email_log")
    op.drop_index("ix_email_log_notification_id", table_name="email_log")
    op.drop_table("email_log")
