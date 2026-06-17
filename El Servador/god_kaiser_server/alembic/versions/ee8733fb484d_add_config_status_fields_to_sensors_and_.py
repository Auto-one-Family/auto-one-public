"""Add config_status fields to sensors and actuators Phase 4

Phase 4: Detailed Config Feedback
- config_status: pending, applied, failed
- config_error: Error code (e.g., GPIO_CONFLICT)
- config_error_detail: Detailed error message

Revision ID: ee8733fb484d
Revises: add_sensor_operating_modes
Create Date: 2026-01-08 04:06:53.033932

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ee8733fb484d'
down_revision: Union[str, None] = 'add_sensor_operating_modes'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add config_status fields to sensor_configs and actuator_configs."""
    # Sensor config status fields
    op.add_column('sensor_configs', sa.Column('config_status', sa.String(length=20), nullable=True))
    op.add_column('sensor_configs', sa.Column('config_error', sa.String(length=50), nullable=True))
    op.add_column('sensor_configs', sa.Column('config_error_detail', sa.String(length=200), nullable=True))

    # Actuator config status fields
    op.add_column('actuator_configs', sa.Column('config_status', sa.String(length=20), nullable=True))
    op.add_column('actuator_configs', sa.Column('config_error', sa.String(length=50), nullable=True))
    op.add_column('actuator_configs', sa.Column('config_error_detail', sa.String(length=200), nullable=True))

    # Set default value for existing rows
    op.execute("UPDATE sensor_configs SET config_status = 'pending' WHERE config_status IS NULL")
    op.execute("UPDATE actuator_configs SET config_status = 'pending' WHERE config_status IS NULL")


def downgrade() -> None:
    """Remove config_status fields from sensor_configs and actuator_configs."""
    op.drop_column('actuator_configs', 'config_error_detail')
    op.drop_column('actuator_configs', 'config_error')
    op.drop_column('actuator_configs', 'config_status')
    op.drop_column('sensor_configs', 'config_error_detail')
    op.drop_column('sensor_configs', 'config_error')
    op.drop_column('sensor_configs', 'config_status')
