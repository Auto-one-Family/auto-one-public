"""Add temp_sensor_config_id to sensor_configs (AUT-299)

Revision ID: aut299_temp_sensor_config_id
Revises: add_api_keys_table
Create Date: 2026-05-08

Adds an optional self-referential FK on sensor_configs so that EC sensors
can be explicitly linked to a temperature sensor for automatic temperature
compensation (ATC) across ESP devices.  NULL = use same-ESP auto-discovery
(existing behavior, unchanged).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "aut299_temp_sensor_config_id"
down_revision: Union[str, None] = "add_api_keys_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add temp_sensor_config_id column + index to sensor_configs."""
    op.add_column(
        "sensor_configs",
        sa.Column(
            "temp_sensor_config_id",
            UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_sensor_configs_temp_sensor_config_id",
        "sensor_configs",
        "sensor_configs",
        ["temp_sensor_config_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_sensor_configs_temp_sensor_config_id",
        "sensor_configs",
        ["temp_sensor_config_id"],
        unique=False,
    )


def downgrade() -> None:
    """Remove temp_sensor_config_id column and its index/FK from sensor_configs."""
    op.drop_index("ix_sensor_configs_temp_sensor_config_id", table_name="sensor_configs")
    op.drop_constraint(
        "fk_sensor_configs_temp_sensor_config_id",
        "sensor_configs",
        type_="foreignkey",
    )
    op.drop_column("sensor_configs", "temp_sensor_config_id")
