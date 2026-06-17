"""merge_heads

Revision ID: 245078bda463
Revises: add_esp_heartbeat_logs, fix_onewire_constraint
Create Date: 2026-01-27 18:08:01.001609

"""
from typing import Sequence, Union



# revision identifiers, used by Alembic.
revision: str = '245078bda463'
down_revision: Union[str, None] = ('add_esp_heartbeat_logs', 'fix_onewire_constraint')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass