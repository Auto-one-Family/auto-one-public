"""add sensor_data zone_id and subzone_id

Phase 0.1: Zone/Subzone zum Messzeitpunkt.
Speichert zone_id und subzone_id in sensor_data für Logic Engine Subzone-Matching (Phase 2.4).

Revision ID: add_sensor_data_zone_subzone
Revises: add_subzone_custom_data
Create Date: 2026-03-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision: str = "add_sensor_data_zone_subzone"
down_revision: Union[str, None] = "add_subzone_custom_data"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sensor_data",
        sa.Column("zone_id", sa.String(50), nullable=True),
    )
    op.add_column(
        "sensor_data",
        sa.Column("subzone_id", sa.String(50), nullable=True),
    )
    op.create_index(
        "idx_sensor_data_zone_timestamp",
        "sensor_data",
        ["zone_id", "timestamp"],
        unique=False,
    )
    op.create_index(
        "idx_sensor_data_subzone_timestamp",
        "sensor_data",
        ["subzone_id", "timestamp"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_sensor_data_subzone_timestamp", table_name="sensor_data")
    op.drop_index("idx_sensor_data_zone_timestamp", table_name="sensor_data")
    op.drop_column("sensor_data", "subzone_id")
    op.drop_column("sensor_data", "zone_id")
