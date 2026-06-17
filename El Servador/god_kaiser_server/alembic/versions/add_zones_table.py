"""Add zones table

Revision ID: add_zones_table
Revises: add_sensor_data_zone_subzone
Create Date: 2026-03-07

Phase 0.3: Zone as independent DB entity.
Creates the zones table and migrates existing DISTINCT zone_id values
from esp_devices into the new table (name = zone_id as default).

NOTE: FK constraint from esp_devices.zone_id -> zones.zone_id is
intentionally NOT added here. Planned for a follow-up migration to
avoid breaking existing data with zone_ids that might not migrate cleanly.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op


# revision identifiers
revision: str = "add_zones_table"
down_revision: Union[str, None] = "add_sensor_data_zone_subzone"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create zones table
    op.create_table(
        "zones",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("zone_id", sa.String(50), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_zones_zone_id", "zones", ["zone_id"], unique=True)

    # 2. Migrate existing DISTINCT zone_id values from esp_devices
    # Uses gen_random_uuid() for PostgreSQL UUID generation
    # name defaults to zone_id value
    op.execute(
        """
        INSERT INTO zones (id, zone_id, name, created_at, updated_at)
        SELECT
            gen_random_uuid(),
            e.zone_id,
            e.zone_id,
            now(),
            now()
        FROM (
            SELECT DISTINCT zone_id
            FROM esp_devices
            WHERE zone_id IS NOT NULL AND zone_id != ''
        ) e
        """
    )


def downgrade() -> None:
    op.drop_index("ix_zones_zone_id", table_name="zones")
    op.drop_table("zones")
