"""Add master_zone_id to ESP Device

Revision ID: add_master_zone_id
Revises: add_audit_log_indexes
Create Date: 2025-12-18 12:00:00.000000

Adds master_zone_id column to esp_devices table for hierarchical zone management.
ESPs can now be assigned to a parent master zone in addition to their primary zone_id.

Zone Hierarchy:
- kaiser_id: God-Kaiser Server managing this ESP
- master_zone_id: Parent zone for hierarchical organization (e.g., "greenhouse_master")
- zone_id: Primary zone identifier (e.g., "greenhouse_zone_1")
- subzone_id: Stored per sensor/actuator (not in ESP table)
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_master_zone_id'
down_revision = 'add_audit_log_indexes'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add master_zone_id column for hierarchical zone organization
    op.add_column(
        'esp_devices',
        sa.Column(
            'master_zone_id',
            sa.String(50),
            nullable=True,
            comment='Parent master zone ID for hierarchical organization',
        )
    )

    # Add index for efficient master zone queries
    # Enables fast lookups of all ESPs in a master zone
    op.create_index(
        'ix_esp_devices_master_zone_id',
        'esp_devices',
        ['master_zone_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_esp_devices_master_zone_id', table_name='esp_devices')
    op.drop_column('esp_devices', 'master_zone_id')
