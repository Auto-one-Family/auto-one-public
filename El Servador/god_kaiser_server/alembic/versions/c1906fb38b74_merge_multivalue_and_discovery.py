"""merge_multivalue_and_discovery

Revision ID: c1906fb38b74
Revises: 001_multi_value, add_discovery_approval
Create Date: 2026-01-17 10:53:50.652787

"""
from typing import Sequence, Union



# revision identifiers, used by Alembic.
revision: str = 'c1906fb38b74'
down_revision: Union[str, None] = ('001_multi_value', 'add_discovery_approval')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass