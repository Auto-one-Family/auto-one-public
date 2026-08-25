"""Add device_domain_changes audit table

AUT-1085: Tracks every domain assignment change for an ESP device.
Records old/new domain and timestamp; change_type is always 'manual'
because the only write path is the PATCH /devices/{esp_id} endpoint.

Idempotent: Safe to run when DATABASE_AUTO_INIT has pre-created the table
via Base.metadata.create_all() during server startup.

Revision ID: add_device_domain_changes_table
Revises: add_domain_to_esp_devices
Create Date: 2026-07-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy import inspect, text
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers
revision: str = "add_device_domain_changes_table"
down_revision: Union[str, None] = "add_domain_to_esp_devices"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table: str) -> bool:
    """Check if a table already exists (for idempotent migrations)."""
    bind = op.get_bind()
    insp = inspect(bind)
    return table in insp.get_table_names()


def _index_exists(index_name: str) -> bool:
    """Check if an index already exists."""
    bind = op.get_bind()
    result = bind.execute(
        text("SELECT 1 FROM pg_indexes WHERE indexname = :name"),
        {"name": index_name},
    )
    return result.fetchone() is not None


def upgrade() -> None:
    if not _table_exists("device_domain_changes"):
        op.create_table(
            "device_domain_changes",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("esp_id", sa.String(50), nullable=False),
            sa.Column("old_domain", sa.String(20), nullable=True),
            sa.Column("new_domain", sa.String(20), nullable=True),
            sa.Column(
                "change_type",
                sa.String(20),
                server_default="manual",
                nullable=False,
            ),
            sa.Column(
                "changed_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _index_exists("ix_device_domain_changes_esp_id"):
        op.create_index(
            "ix_device_domain_changes_esp_id", "device_domain_changes", ["esp_id"]
        )


def downgrade() -> None:
    op.drop_index("ix_device_domain_changes_esp_id", table_name="device_domain_changes")
    op.drop_table("device_domain_changes")
