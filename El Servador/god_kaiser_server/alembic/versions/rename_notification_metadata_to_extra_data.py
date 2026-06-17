"""Rename notifications.metadata column to extra_data

Revision ID: rename_metadata_col
Revises: add_alert_lifecycle
Create Date: 2026-03-03 12:00:00.000000

Fix: SQLAlchemy reserves 'metadata' as a declarative attribute name.
Renaming the DB column from 'metadata' to 'extra_data' to match the
Python attribute and avoid the InvalidRequestError.

For fresh installs (migration add_notifications already uses 'extra_data'),
this is a no-op. For existing DBs that ran the old migration, this renames
the column.
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "rename_metadata_col"
down_revision: Union[str, None] = "add_diagnostic_reports"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Only rename if the old 'metadata' column still exists
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col["name"] for col in inspector.get_columns("notifications")]

    if "metadata" in columns and "extra_data" not in columns:
        op.alter_column(
            "notifications",
            "metadata",
            new_column_name="extra_data",
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col["name"] for col in inspector.get_columns("notifications")]

    if "extra_data" in columns and "metadata" not in columns:
        op.alter_column(
            "notifications",
            "extra_data",
            new_column_name="metadata",
        )
