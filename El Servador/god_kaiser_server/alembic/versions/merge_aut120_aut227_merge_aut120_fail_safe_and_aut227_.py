"""merge_aut120_fail_safe_and_aut227_legacy_cleanup

Revision ID: merge_aut120_aut227
Revises: add_actuator_fail_safe, aut227_db_legacy_cleanup
Create Date: 2026-05-07 07:52:12.646060

"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = 'merge_aut120_aut227'
down_revision: Union[str, None] = ('add_actuator_fail_safe', 'aut227_db_legacy_cleanup')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass