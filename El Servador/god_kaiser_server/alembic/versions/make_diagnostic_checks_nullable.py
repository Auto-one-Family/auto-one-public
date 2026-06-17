"""Make diagnostic_reports.checks column nullable

Revision ID: make_checks_nullable
Revises: rename_metadata_col
Create Date: 2026-03-03 20:00:00.000000

Phase B V2.2: Report-Retention requires setting checks=NULL on archived reports.
The original migration created checks as NOT NULL (JSONB).
This migration allows NULL so archived reports keep summary but drop check details.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "make_checks_nullable"
down_revision: Union[str, None] = "rename_metadata_col"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "diagnostic_reports",
        "checks",
        nullable=True,
    )


def downgrade() -> None:
    # Before downgrading, ensure no NULL values exist
    op.execute("UPDATE diagnostic_reports SET checks = '[]'::jsonb WHERE checks IS NULL")
    op.alter_column(
        "diagnostic_reports",
        "checks",
        nullable=False,
    )
