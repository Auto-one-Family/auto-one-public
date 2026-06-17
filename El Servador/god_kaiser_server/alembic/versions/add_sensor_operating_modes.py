"""Add sensor operating modes - Phase 2A

Revision ID: add_sensor_operating_modes
Revises: 06ee633a722f, add_audit_log_indexes
Create Date: 2026-01-07 12:00:00.000000

Phase: 2A - Sensor Operating Modes

Creates sensor_type_defaults table and adds operating mode columns to sensor_configs.
Implements hierarchical configuration system:
- SensorConfig (instance-level) → SensorTypeDefaults (DB) → Sensor Library (Python) → System Default

Operating Modes:
- continuous: Regular interval-based reading (default)
- on_demand: Only read when explicitly requested (pH, EC sensors)
- scheduled: Time-based schedules (e.g., every hour at :00)
- paused: Temporarily disabled
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = 'add_sensor_operating_modes'
down_revision: Union[str, tuple, None] = ('06ee633a722f', 'add_audit_log_indexes')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # =========================================================================
    # 1. Create sensor_type_defaults table
    # =========================================================================
    op.create_table(
        'sensor_type_defaults',
        # Primary Key
        sa.Column(
            'id',
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text('gen_random_uuid()'),
            comment='Primary key (UUID)',
        ),
        # Sensor Type (Unique)
        sa.Column(
            'sensor_type',
            sa.String(50),
            nullable=False,
            unique=True,
            index=True,
            comment='Unique sensor type identifier (e.g., ds18b20, sht31_temp, ph)',
        ),
        # Operating Mode Configuration
        sa.Column(
            'operating_mode',
            sa.String(20),
            nullable=False,
            server_default='continuous',
            comment='Default operating mode: continuous, on_demand, scheduled, paused',
        ),
        sa.Column(
            'measurement_interval_seconds',
            sa.Integer,
            nullable=False,
            server_default='30',
            comment='Measurement interval in seconds (for continuous mode)',
        ),
        sa.Column(
            'timeout_seconds',
            sa.Integer,
            nullable=False,
            server_default='180',
            comment='Timeout in seconds (0 = no timeout, for on_demand mode)',
        ),
        sa.Column(
            'timeout_warning_enabled',
            sa.Boolean,
            nullable=False,
            server_default=sa.text('true'),
            comment='Whether timeout warnings are enabled',
        ),
        sa.Column(
            'supports_on_demand',
            sa.Boolean,
            nullable=False,
            server_default=sa.text('false'),
            comment='Whether sensor supports on_demand mode',
        ),
        # Schedule Configuration (for scheduled mode)
        sa.Column(
            'schedule_config',
            sa.JSON,
            nullable=True,
            comment='JSON config for scheduled mode (cron expression, time slots)',
        ),
        # Description
        sa.Column(
            'description',
            sa.Text,
            nullable=True,
            comment='Human-readable description of this sensor type configuration',
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
    )

    # =========================================================================
    # 2. Add operating mode columns to sensor_configs table
    # =========================================================================
    # Operating mode (instance-level override)
    op.add_column(
        'sensor_configs',
        sa.Column(
            'operating_mode',
            sa.String(20),
            nullable=True,
            comment='Operating mode override: continuous, on_demand, scheduled, paused (NULL = use type default)',
        ),
    )

    # Timeout (instance-level override)
    op.add_column(
        'sensor_configs',
        sa.Column(
            'timeout_seconds',
            sa.Integer,
            nullable=True,
            comment='Timeout override in seconds (NULL = use type default)',
        ),
    )

    # Timeout warning enabled (instance-level override)
    op.add_column(
        'sensor_configs',
        sa.Column(
            'timeout_warning_enabled',
            sa.Boolean,
            nullable=True,
            comment='Timeout warning override (NULL = use type default)',
        ),
    )

    # Schedule configuration (instance-level, for scheduled mode)
    op.add_column(
        'sensor_configs',
        sa.Column(
            'schedule_config',
            sa.JSON,
            nullable=True,
            comment='Schedule configuration override for scheduled mode (NULL = use type default)',
        ),
    )

    # Last manual request timestamp (for on_demand mode tracking)
    op.add_column(
        'sensor_configs',
        sa.Column(
            'last_manual_request',
            sa.DateTime,
            nullable=True,
            comment='Timestamp of last manual read request (for on_demand mode)',
        ),
    )

    # =========================================================================
    # 3. Create index for operating_mode filtering
    # =========================================================================
    op.create_index(
        'ix_sensor_configs_operating_mode',
        'sensor_configs',
        ['operating_mode'],
        unique=False,
    )


def downgrade() -> None:
    # Remove index
    op.drop_index('ix_sensor_configs_operating_mode', table_name='sensor_configs')

    # Remove columns from sensor_configs
    op.drop_column('sensor_configs', 'last_manual_request')
    op.drop_column('sensor_configs', 'schedule_config')
    op.drop_column('sensor_configs', 'timeout_warning_enabled')
    op.drop_column('sensor_configs', 'timeout_seconds')
    op.drop_column('sensor_configs', 'operating_mode')

    # Drop sensor_type_defaults table
    op.drop_table('sensor_type_defaults')
