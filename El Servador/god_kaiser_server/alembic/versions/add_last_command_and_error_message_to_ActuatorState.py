"""Add last_command and error_message to ActuatorState

Revision ID: c6fb9c8567b5
Revises: 
Create Date: 2024-12-03

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c6fb9c8567b5'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add last_command and error_message columns to actuator_states table."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "actuator_states" not in inspector.get_table_names():
        # Fresh schema paths can legitimately miss this legacy table at this
        # revision point. Keep migration chain forward-only and non-failing.
        return

    existing_columns = {column["name"] for column in inspector.get_columns("actuator_states")}

    if "last_command" not in existing_columns:
        op.add_column(
            "actuator_states",
            sa.Column("last_command", sa.String(50), nullable=True),
        )

    if "error_message" not in existing_columns:
        op.add_column(
            "actuator_states",
            sa.Column("error_message", sa.String(500), nullable=True),
        )


def downgrade() -> None:
    """Remove last_command and error_message columns from actuator_states table."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "actuator_states" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("actuator_states")}

    if "error_message" in existing_columns:
        op.drop_column("actuator_states", "error_message")
    if "last_command" in existing_columns:
        op.drop_column("actuator_states", "last_command")
