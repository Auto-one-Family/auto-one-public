"""Fix actuator DateTime columns missing timezone=True

Revision ID: fix_actuator_datetime_tz
Revises: add_device_scope_and_context
Create Date: 2026-03-10

BUG-001: actuator_states.last_command_timestamp and actuator_history.timestamp
were defined as DateTime() without timezone=True. Code was fixed to
DateTime(timezone=True), but existing DB columns still lack timezone support.

Migration is lossless: PostgreSQL converts existing TIMESTAMP values to
TIMESTAMPTZ by assuming the server timezone (UTC).
"""

from typing import Union

from alembic import op
import sqlalchemy as sa

revision: str = "fix_actuator_datetime_tz"
down_revision: Union[str, None] = "add_device_scope_and_context"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "actuator_states",
        "last_command_timestamp",
        type_=sa.DateTime(timezone=True),
        existing_type=sa.DateTime(),
        existing_nullable=True,
    )
    op.alter_column(
        "actuator_history",
        "timestamp",
        type_=sa.DateTime(timezone=True),
        existing_type=sa.DateTime(),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "actuator_history",
        "timestamp",
        type_=sa.DateTime(),
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
    )
    op.alter_column(
        "actuator_states",
        "last_command_timestamp",
        type_=sa.DateTime(),
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=True,
    )
