"""Add dashboard_user_assignments table

AUT-1095: n:m assignment of dashboards to users.
Additive alongside the existing owner_id/is_shared model.
Operators can explicitly grant individual users access to dashboards
that they neither own nor that are globally shared.

Idempotent: _table_exists() / _index_exists() guards make re-running safe.

Revision ID: add_dashboard_user_assignments
Revises: backfill_esp_device_domains
Create Date: 2026-07-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy import inspect, text
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_dashboard_user_assignments"
down_revision: Union[str, None] = "backfill_esp_device_domains"
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
    if not _table_exists("dashboard_user_assignments"):
        op.create_table(
            "dashboard_user_assignments",
            # Primary Key
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                nullable=False,
                comment="Primary key (UUID)",
            ),
            # Foreign Keys
            sa.Column(
                "dashboard_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("dashboards.id", ondelete="CASCADE"),
                nullable=False,
                comment="Foreign key to the assigned dashboard",
            ),
            sa.Column(
                "user_id",
                sa.Integer,
                sa.ForeignKey("user_accounts.id", ondelete="CASCADE"),
                nullable=False,
                comment="Foreign key to the assigned user",
            ),
            # Assignment metadata
            sa.Column(
                "assigned_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
                comment="Timestamp when the assignment was created (UTC)",
            ),
            sa.Column(
                "assigned_by",
                sa.Integer,
                sa.ForeignKey("user_accounts.id", ondelete="SET NULL"),
                nullable=True,
                comment="User ID of the operator who created the assignment",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "dashboard_id",
                "user_id",
                name="uq_dashboard_user_assignment",
            ),
        )

    if not _index_exists("idx_dashboard_assignment_dashboard_id"):
        op.create_index(
            "idx_dashboard_assignment_dashboard_id",
            "dashboard_user_assignments",
            ["dashboard_id"],
        )

    if not _index_exists("idx_dashboard_assignment_user_id"):
        op.create_index(
            "idx_dashboard_assignment_user_id",
            "dashboard_user_assignments",
            ["user_id"],
        )


def downgrade() -> None:
    op.drop_index(
        "idx_dashboard_assignment_user_id",
        table_name="dashboard_user_assignments",
    )
    op.drop_index(
        "idx_dashboard_assignment_dashboard_id",
        table_name="dashboard_user_assignments",
    )
    op.drop_table("dashboard_user_assignments")
