"""Add data_source field to time-series tables

Revision ID: add_data_source_field
Revises: add_audit_log_indexes
Create Date: 2024-12-24 12:00:00.000000

Adds data_source field to:
- sensor_data: Track origin of sensor readings (production, mock, test, simulation)
- actuator_states: Track origin of actuator state updates
- actuator_history: Track origin of actuator command history

This enables:
- Filtering data by source (exclude mock data in production views)
- Test data retention policies
- Analytics on test vs production data
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_data_source_field'
down_revision = 'add_audit_log_indexes'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # Add data_source column to sensor_data table
    # Default to 'production' for backwards compatibility with existing data
    if 'sensor_data' in existing_tables:
        sensor_columns = {c["name"] for c in inspector.get_columns('sensor_data')}
        if 'data_source' not in sensor_columns:
            op.add_column(
                'sensor_data',
                sa.Column(
                    'data_source',
                    sa.String(20),
                    nullable=False,
                    server_default='production'
                )
            )

        sensor_indexes = {idx["name"] for idx in inspector.get_indexes('sensor_data')}
        if 'idx_data_source_timestamp' not in sensor_indexes:
            op.create_index(
                'idx_data_source_timestamp',
                'sensor_data',
                ['data_source', 'timestamp'],
                unique=False,
            )

    # Add data_source column to actuator_states table
    if 'actuator_states' in existing_tables:
        actuator_state_columns = {c["name"] for c in inspector.get_columns('actuator_states')}
        if 'data_source' not in actuator_state_columns:
            op.add_column(
                'actuator_states',
                sa.Column(
                    'data_source',
                    sa.String(20),
                    nullable=False,
                    server_default='production'
                )
            )

        actuator_state_indexes = {idx["name"] for idx in inspector.get_indexes('actuator_states')}
        if 'idx_actuator_states_data_source' not in actuator_state_indexes:
            op.create_index(
                'idx_actuator_states_data_source',
                'actuator_states',
                ['data_source'],
                unique=False,
            )

    # Add data_source column to actuator_history table
    if 'actuator_history' in existing_tables:
        actuator_history_columns = {c["name"] for c in inspector.get_columns('actuator_history')}
        if 'data_source' not in actuator_history_columns:
            op.add_column(
                'actuator_history',
                sa.Column(
                    'data_source',
                    sa.String(20),
                    nullable=False,
                    server_default='production'
                )
            )

        actuator_history_indexes = {idx["name"] for idx in inspector.get_indexes('actuator_history')}
        if 'idx_actuator_data_source_timestamp' not in actuator_history_indexes:
            op.create_index(
                'idx_actuator_data_source_timestamp',
                'actuator_history',
                ['data_source', 'timestamp'],
                unique=False,
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # Drop indexes first
    if 'actuator_states' in existing_tables:
        actuator_state_indexes = {idx["name"] for idx in inspector.get_indexes('actuator_states')}
        if 'idx_actuator_states_data_source' in actuator_state_indexes:
            op.drop_index('idx_actuator_states_data_source', table_name='actuator_states')

    if 'actuator_history' in existing_tables:
        actuator_history_indexes = {idx["name"] for idx in inspector.get_indexes('actuator_history')}
        if 'idx_actuator_data_source_timestamp' in actuator_history_indexes:
            op.drop_index('idx_actuator_data_source_timestamp', table_name='actuator_history')

    if 'sensor_data' in existing_tables:
        sensor_indexes = {idx["name"] for idx in inspector.get_indexes('sensor_data')}
        if 'idx_data_source_timestamp' in sensor_indexes:
            op.drop_index('idx_data_source_timestamp', table_name='sensor_data')

    # Drop columns
    if 'actuator_history' in existing_tables:
        actuator_history_columns = {c["name"] for c in inspector.get_columns('actuator_history')}
        if 'data_source' in actuator_history_columns:
            op.drop_column('actuator_history', 'data_source')

    if 'actuator_states' in existing_tables:
        actuator_state_columns = {c["name"] for c in inspector.get_columns('actuator_states')}
        if 'data_source' in actuator_state_columns:
            op.drop_column('actuator_states', 'data_source')

    if 'sensor_data' in existing_tables:
        sensor_columns = {c["name"] for c in inspector.get_columns('sensor_data')}
        if 'data_source' in sensor_columns:
            op.drop_column('sensor_data', 'data_source')
