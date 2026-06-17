"""Merge fix_datetime_timezone_naive and fix_null_subzone_names

Revision ID: merge_datetime_null_subzones
Revises: fix_datetime_timezone_naive, fix_null_subzone_names
Create Date: 2026-03-09
"""

from typing import Sequence, Union

# revision identifiers
revision: str = "merge_datetime_null_subzones"
down_revision: Union[str, Sequence[str]] = (
    "fix_datetime_timezone_naive",
    "fix_null_subzone_names",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
