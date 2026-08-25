"""add settle_after_rule_id and settle_seconds to cross_esp_logic

AUT-1115 (settle_after_rule_id/settle_seconds on CrossESPLogic) shipped as a
model change without a migration (commit b72fd77c). Autogenerate also picked
up unrelated pre-existing drift (index expression reflection, column comment
diffs, a sensor_configs unique index) that is explicitly OUT OF SCOPE here —
trimmed to only the two columns AUT-1115 actually added.

Revision ID: 5666263e2602
Revises: backfill_esp_device_domains
Create Date: 2026-07-17 07:03:09.696600

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5666263e2602'
down_revision: Union[str, None] = 'backfill_esp_device_domains'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('cross_esp_logic', sa.Column('settle_after_rule_id', sa.UUID(), nullable=True))
    op.add_column('cross_esp_logic', sa.Column('settle_seconds', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('cross_esp_logic', 'settle_seconds')
    op.drop_column('cross_esp_logic', 'settle_after_rule_id')
