"""Add fingerprint column to notifications table

Revision ID: add_notification_fingerprint
Revises: add_notifications
Create Date: 2026-03-02 14:00:00.000000

FIX-07: Grafana alert deduplication via unique fingerprint.
Adds VARCHAR(64) column with partial unique index (WHERE fingerprint IS NOT NULL).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "add_notification_fingerprint"
down_revision: Union[str, None] = "add_notifications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "notifications",
        sa.Column(
            "fingerprint",
            sa.String(64),
            nullable=True,
            comment="Unique fingerprint for Grafana alert deduplication",
        ),
    )
    op.create_index(
        "ix_notifications_fingerprint_unique",
        "notifications",
        ["fingerprint"],
        unique=True,
        postgresql_where=sa.text("fingerprint IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_notifications_fingerprint_unique",
        table_name="notifications",
    )
    op.drop_column("notifications", "fingerprint")
