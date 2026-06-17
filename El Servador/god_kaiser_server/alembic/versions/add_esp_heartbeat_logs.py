"""Add ESP Heartbeat Logs table

ESP-Heartbeat-Persistierung:
- Creates esp_heartbeat_logs table for time-series heartbeat data
- Optimized indexes for time-range queries
- Supports device health trending and monitoring

Revision ID: add_esp_heartbeat_logs
Revises: c1906fb38b74
Create Date: 2026-01-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = 'add_esp_heartbeat_logs'
down_revision: Union[str, None] = 'c1906fb38b74'  # Korrigiert: aktueller HEAD (merge_multivalue_and_discovery)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Create esp_heartbeat_logs table for time-series heartbeat data.

    This table stores historical heartbeat data from ESP32 devices:
    - Device health metrics (heap, wifi, uptime)
    - Time-series optimized with proper indexes
    - Supports retention policy (default: 7 days)
    """
    op.create_table(
        'esp_heartbeat_logs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('esp_id', UUID(as_uuid=True), nullable=False),
        sa.Column('device_id', sa.String(50), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('heap_free', sa.Integer, nullable=False),
        sa.Column('wifi_rssi', sa.Integer, nullable=False),
        sa.Column('uptime', sa.Integer, nullable=False),
        sa.Column('sensor_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('actuator_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('gpio_reserved_count', sa.Integer, nullable=True, server_default='0'),
        sa.Column('data_source', sa.String(20), nullable=False, server_default='production'),
        sa.Column('health_status', sa.String(20), nullable=False, server_default='healthy'),
        # ForeignKey with CASCADE DELETE - deleting ESP removes all its heartbeat logs
        sa.ForeignKeyConstraint(['esp_id'], ['esp_devices.id'], ondelete='CASCADE'),
    )

    # Primary indexes for single-column lookups
    op.create_index('ix_esp_heartbeat_logs_esp_id', 'esp_heartbeat_logs', ['esp_id'])
    op.create_index('ix_esp_heartbeat_logs_device_id', 'esp_heartbeat_logs', ['device_id'])
    op.create_index('ix_esp_heartbeat_logs_timestamp', 'esp_heartbeat_logs', ['timestamp'])
    op.create_index('ix_esp_heartbeat_logs_data_source', 'esp_heartbeat_logs', ['data_source'])

    # Composite indexes for time-series queries (CRITICAL for performance)
    op.create_index(
        'idx_heartbeat_esp_timestamp',
        'esp_heartbeat_logs',
        ['esp_id', 'timestamp']
    )
    op.create_index(
        'idx_heartbeat_device_timestamp',
        'esp_heartbeat_logs',
        ['device_id', 'timestamp']
    )
    op.create_index(
        'idx_heartbeat_data_source_timestamp',
        'esp_heartbeat_logs',
        ['data_source', 'timestamp']
    )
    op.create_index(
        'idx_heartbeat_health_status',
        'esp_heartbeat_logs',
        ['health_status', 'timestamp']
    )


def downgrade() -> None:
    """
    Drop esp_heartbeat_logs table and all indexes.

    This will permanently delete all heartbeat history data.
    """
    # Drop composite indexes
    op.drop_index('idx_heartbeat_health_status', table_name='esp_heartbeat_logs')
    op.drop_index('idx_heartbeat_data_source_timestamp', table_name='esp_heartbeat_logs')
    op.drop_index('idx_heartbeat_device_timestamp', table_name='esp_heartbeat_logs')
    op.drop_index('idx_heartbeat_esp_timestamp', table_name='esp_heartbeat_logs')

    # Drop primary indexes
    op.drop_index('ix_esp_heartbeat_logs_data_source', table_name='esp_heartbeat_logs')
    op.drop_index('ix_esp_heartbeat_logs_timestamp', table_name='esp_heartbeat_logs')
    op.drop_index('ix_esp_heartbeat_logs_device_id', table_name='esp_heartbeat_logs')
    op.drop_index('ix_esp_heartbeat_logs_esp_id', table_name='esp_heartbeat_logs')

    # Drop table
    op.drop_table('esp_heartbeat_logs')
