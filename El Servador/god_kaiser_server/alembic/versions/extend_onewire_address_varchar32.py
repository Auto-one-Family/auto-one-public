"""Extend onewire_address from varchar(16) to varchar(32)

Revision ID: extend_onewire_address_varchar32
Revises: add_zones_table
Create Date: 2026-03-07

Bug B2 Fix: AUTO_ prefix + 16 hex chars = 21 chars exceeded varchar(16).
Extended to varchar(32) for safety margin. Also shortened auto-generated
addresses to SIM_ + 12 hex = 16 chars.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "extend_onewire_address_varchar32"
down_revision: Union[str, None] = "add_zones_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "sensor_configs",
        "onewire_address",
        existing_type=sa.String(16),
        type_=sa.String(32),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "sensor_configs",
        "onewire_address",
        existing_type=sa.String(32),
        type_=sa.String(16),
        existing_nullable=True,
    )
