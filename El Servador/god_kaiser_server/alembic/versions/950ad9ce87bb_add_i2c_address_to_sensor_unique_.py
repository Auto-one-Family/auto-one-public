"""Add i2c_address to sensor unique constraint

I2C Multi-Sensor Support:
- Changes unique constraint from (esp_id, gpio, sensor_type)
  to (esp_id, gpio, sensor_type, onewire_address, i2c_address)
- Allows multiple I2C sensors on the same bus with different addresses
  (e.g., 2x SHT31 on addresses 0x44 and 0x45)
- Combined with existing OneWire bus-sharing support
- Both i2c_address and onewire_address are nullable
  -> NULL != NULL in UNIQUE (PostgreSQL + SQLite)

Revision ID: 950ad9ce87bb
Revises: 24e8638e14a5
Create Date: 2026-02-04 04:05:52.388175
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '950ad9ce87bb'
down_revision: Union[str, None] = '24e8638e14a5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Extend sensor unique constraint for I2C multi-sensor support.

    Before: UniqueConstraint(esp_id, gpio, sensor_type)
    After:  UniqueConstraint(esp_id, gpio, sensor_type, onewire_address, i2c_address)

    This allows:
    - Multiple DS18B20 sensors on the same OneWire GPIO (differentiated by onewire_address)
    - Multiple I2C sensors at different addresses on the same I2C bus (differentiated by i2c_address)
    - e.g., 2x SHT31 on GPIO 21/22 (I2C) with addresses 0x44 and 0x45
    """
    # Use batch mode for SQLite compatibility
    # SQLite doesn't support ALTER TABLE ... DROP CONSTRAINT directly
    # The existing constraint is 'unique_esp_gpio_sensor_type' (3 columns)
    with op.batch_alter_table('sensor_configs', schema=None) as batch_op:
        # Drop the existing 3-column constraint
        batch_op.drop_constraint('unique_esp_gpio_sensor_type', type_='unique')

        # Create new 5-column constraint including onewire_address and i2c_address
        batch_op.create_unique_constraint(
            'unique_esp_gpio_sensor_interface',
            ['esp_id', 'gpio', 'sensor_type', 'onewire_address', 'i2c_address']
        )


def downgrade() -> None:
    """
    Revert to 3-column unique constraint.

    WARNING: This will fail if:
    - Multiple DS18B20 sensors share the same GPIO (OneWire bus sharing)
    - Multiple I2C sensors exist at different addresses on the same bus
    """
    with op.batch_alter_table('sensor_configs', schema=None) as batch_op:
        batch_op.drop_constraint('unique_esp_gpio_sensor_interface', type_='unique')

        # Restore the original 3-column constraint
        batch_op.create_unique_constraint(
            'unique_esp_gpio_sensor_type',
            ['esp_id', 'gpio', 'sensor_type']
        )
