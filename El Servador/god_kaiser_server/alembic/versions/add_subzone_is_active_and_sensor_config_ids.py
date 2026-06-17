"""Add is_active and assigned_sensor_config_ids to subzone_configs

Revision ID: add_subzone_is_active_sensor_ids
Revises: add_device_zone_changes
Create Date: 2026-03-09

T13-R1 Phase 2/4:
- Add is_active column (subzone lifecycle within zone)
- Add assigned_sensor_config_ids (I2C gpio=0 sensor assignment)

Idempotent: Safe to run when DATABASE_AUTO_INIT has pre-created columns.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers
revision: str = "add_subzone_is_active_sensor_ids"
down_revision: Union[str, None] = "add_device_zone_changes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    """Check if a column already exists (for idempotent migrations)."""
    bind = op.get_bind()
    insp = inspect(bind)
    columns = [c["name"] for c in insp.get_columns(table)]
    return column in columns


def upgrade() -> None:
    # 1. Add is_active column (default True)
    if not _column_exists("subzone_configs", "is_active"):
        op.add_column(
            "subzone_configs",
            sa.Column(
                "is_active",
                sa.Boolean(),
                server_default="true",
                nullable=False,
            ),
        )

    # 2. Add assigned_sensor_config_ids column (JSON array, default [])
    if not _column_exists("subzone_configs", "assigned_sensor_config_ids"):
        op.add_column(
            "subzone_configs",
            sa.Column(
                "assigned_sensor_config_ids",
                sa.JSON(),
                server_default="[]",
                nullable=False,
            ),
        )


def downgrade() -> None:
    op.drop_column("subzone_configs", "assigned_sensor_config_ids")
    op.drop_column("subzone_configs", "is_active")
