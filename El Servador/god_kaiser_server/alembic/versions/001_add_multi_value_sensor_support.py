"""Add multi-value sensor support

Revision ID: 001_multi_value
Revises: add_audit_log_indexes
Create Date: 2026-01-14

Changes:
- Make gpio nullable (I2C/OneWire don't have device-specific GPIO)
- Add interface_type (I2C, ONEWIRE, ANALOG, DIGITAL)
- Add i2c_address (for I2C sensors)
- Add onewire_address (for OneWire sensors)
- Add provides_values (JSON array of value_types)
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON


# revision identifiers, used by Alembic.
revision = '001_multi_value'
down_revision = 'fix_multivalue_constraint'
branch_labels = None
depends_on = None


def upgrade():
    """
    Add multi-value sensor support fields.

    This migration adds fields required for proper I2C/OneWire multi-value
    sensor support (e.g., SHT31 with temperature + humidity).
    """

    # Step 1: Add new columns (all nullable initially for safe migration)
    op.add_column('sensor_configs',
                  sa.Column('interface_type', sa.String(20), nullable=True))

    op.add_column('sensor_configs',
                  sa.Column('i2c_address', sa.Integer(), nullable=True))

    op.add_column('sensor_configs',
                  sa.Column('onewire_address', sa.String(16), nullable=True))

    op.add_column('sensor_configs',
                  sa.Column('provides_values', JSON, nullable=True))

    # Step 2: Backfill existing data with inferred interface_type
    # This ensures existing sensors work after migration
    connection = op.get_bind()

    # I2C Sensors (sht31, bmp280, bme280, etc.)
    connection.execute(sa.text("""
        UPDATE sensor_configs
        SET interface_type = 'I2C'
        WHERE sensor_type LIKE 'sht31%'
           OR sensor_type LIKE 'bmp280%'
           OR sensor_type LIKE 'bme280%'
           OR sensor_type LIKE 'bh1750%'
           OR sensor_type LIKE 'veml7700%'
    """))

    # OneWire Sensors (ds18b20)
    connection.execute(sa.text("""
        UPDATE sensor_configs
        SET interface_type = 'ONEWIRE'
        WHERE sensor_type LIKE 'ds18b20%'
    """))

    # Analog Sensors (soil, ph, ec, ldr, etc.)
    connection.execute(sa.text("""
        UPDATE sensor_configs
        SET interface_type = 'ANALOG'
        WHERE interface_type IS NULL
          AND (sensor_type LIKE 'soil%'
           OR sensor_type LIKE 'ph%'
           OR sensor_type LIKE 'ec%'
           OR sensor_type LIKE 'ldr%'
           OR sensor_type LIKE 'moisture%')
    """))

    # Digital Sensors (rest)
    connection.execute(sa.text("""
        UPDATE sensor_configs
        SET interface_type = 'DIGITAL'
        WHERE interface_type IS NULL
    """))

    # Step 3: Make interface_type NOT NULL after backfill
    op.alter_column('sensor_configs', 'interface_type',
                    nullable=False)

    # Step 4: Make gpio nullable (I2C/OneWire don't need device-specific GPIO)
    # Note: For existing sensors, gpio will remain set (e.g., GPIO 21 for I2C)
    # New sensors can use NULL for gpio and identify via i2c_address instead
    op.alter_column('sensor_configs', 'gpio',
                    existing_type=sa.Integer(),
                    nullable=True)

    # Step 5: Add index on i2c_address for faster lookups
    # This is critical for validating I2C address conflicts
    op.create_index('idx_sensor_configs_i2c_address',
                    'sensor_configs',
                    ['esp_id', 'i2c_address'])


def downgrade():
    """
    Remove multi-value sensor support fields.

    WARNING: This will lose data in the new columns!
    Also, sensors with gpio=NULL will fail the NOT NULL constraint.
    """

    # Remove index
    op.drop_index('idx_sensor_configs_i2c_address', 'sensor_configs')

    # Make gpio NOT NULL again (may fail if any sensors have gpio=NULL)
    op.alter_column('sensor_configs', 'gpio',
                    existing_type=sa.Integer(),
                    nullable=False)

    # Remove new columns
    op.drop_column('sensor_configs', 'provides_values')
    op.drop_column('sensor_configs', 'onewire_address')
    op.drop_column('sensor_configs', 'i2c_address')
    op.drop_column('sensor_configs', 'interface_type')
