"""Merge multiple head revisions (add_data_source_field and add_subzone_configs)

Revision ID: 06ee633a722f
Revises: add_data_source_field, add_subzone_configs
Create Date: 2025-12-27 00:16:41.560554

"""
from typing import Sequence, Union



# revision identifiers, used by Alembic.
revision: str = '06ee633a722f'
down_revision: Union[str, None] = ('add_data_source_field', 'add_subzone_configs')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
