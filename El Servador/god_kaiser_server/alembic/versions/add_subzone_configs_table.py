"""Add subzone_configs table

Revision ID: add_subzone_configs
Revises: add_master_zone_id
Create Date: 2025-12-18 14:00:00.000000

Phase: 9 - Subzone Management

Creates subzone_configs table for storing GPIO pin groupings within ESP zones.
Enables feingranulare Kontrolle over individual hardware components.

Subzone Hierarchy:
- ESP → Zone → Subzone → GPIO Pins
- Each subzone groups multiple GPIO pins
- Safe-mode can be controlled per subzone
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = 'add_subzone_configs'
down_revision = 'add_master_zone_id'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create subzone_configs table
    op.create_table(
        'subzone_configs',
        # Primary Key
        sa.Column(
            'id',
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text('gen_random_uuid()'),
            comment='Primary key (UUID)',
        ),
        # Foreign Key to ESP Device
        sa.Column(
            'esp_id',
            sa.String(50),
            sa.ForeignKey('esp_devices.device_id', ondelete='CASCADE'),
            nullable=False,
            index=True,
            comment='ESP device ID (e.g., ESP_AB12CD)',
        ),
        # Subzone Identity
        sa.Column(
            'subzone_id',
            sa.String(50),
            nullable=False,
            index=True,
            comment="Unique subzone identifier (e.g., 'irrigation_section_A')",
        ),
        sa.Column(
            'subzone_name',
            sa.String(100),
            nullable=True,
            comment='Human-readable subzone name',
        ),
        # Zone Hierarchy
        sa.Column(
            'parent_zone_id',
            sa.String(50),
            nullable=False,
            index=True,
            comment="Parent zone ID (must match ESP's zone_id)",
        ),
        # GPIO Assignment
        sa.Column(
            'assigned_gpios',
            sa.JSON,
            nullable=False,
            server_default='[]',
            comment='JSON array of GPIO pin numbers [4, 5, 6]',
        ),
        # Safe-Mode Status
        sa.Column(
            'safe_mode_active',
            sa.Boolean,
            nullable=False,
            server_default=sa.text('true'),
            comment='Whether subzone is currently in safe-mode',
        ),
        # Counts (from ESP ACK)
        sa.Column(
            'sensor_count',
            sa.Integer,
            nullable=False,
            server_default='0',
            comment='Number of sensors in this subzone',
        ),
        sa.Column(
            'actuator_count',
            sa.Integer,
            nullable=False,
            server_default='0',
            comment='Number of actuators in this subzone',
        ),
        # Metadata
        sa.Column(
            'last_ack_at',
            sa.DateTime,
            nullable=True,
            comment='Last ACK timestamp from ESP',
        ),
        # Timestamps
        sa.Column(
            'created_at',
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
            comment='Record creation timestamp',
        ),
        sa.Column(
            'updated_at',
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            comment='Record last update timestamp',
        ),
        # Unique constraint: one subzone_id per ESP
        sa.UniqueConstraint('esp_id', 'subzone_id', name='uq_esp_subzone'),
    )


def downgrade() -> None:
    op.drop_table('subzone_configs')

