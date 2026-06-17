"""Fix sensor unique constraint for OneWire bus-sharing support

OneWire Bus-Sharing Fix:
- Changes unique constraint from (esp_id, gpio, sensor_type)
  to (esp_id, gpio, sensor_type, onewire_address)
- Allows multiple DS18B20 sensors on the same GPIO (OneWire bus sharing)
- onewire_address is nullable → NULL != NULL in UNIQUE (PostgreSQL + SQLite)
- Adds default 'ANALOG' for interface_type column

Revision ID: fix_onewire_constraint
Revises: fix_multivalue_constraint
Create Date: 2026-01-27
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'fix_onewire_constraint'
down_revision: Union[str, None] = 'fix_multivalue_constraint'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Extend sensor unique constraint for OneWire bus-sharing.

    Before: UniqueConstraint(esp_id, gpio, sensor_type)
    After:  UniqueConstraint(esp_id, gpio, sensor_type, onewire_address)

    This allows multiple DS18B20 sensors on the same GPIO pin,
    differentiated by their unique OneWire ROM address.
    """
    # Drop the old constraint
    op.drop_constraint('unique_esp_gpio_sensor_type', 'sensor_configs', type_='unique')

    # Create new constraint with onewire_address included
    op.create_unique_constraint(
        'unique_esp_gpio_sensor_type_onewire',
        'sensor_configs',
        ['esp_id', 'gpio', 'sensor_type', 'onewire_address']
    )

    # Set default for interface_type on existing rows without value
    op.execute(
        "UPDATE sensor_configs SET interface_type = 'ANALOG' WHERE interface_type IS NULL"
    )


def downgrade() -> None:
    """
    Revert to 3-column unique constraint.

    WARNING: This will fail if multiple DS18B20 sensors share the same GPIO!
    """
    op.drop_constraint('unique_esp_gpio_sensor_type_onewire', 'sensor_configs', type_='unique')

    op.create_unique_constraint(
        'unique_esp_gpio_sensor_type',
        'sensor_configs',
        ['esp_id', 'gpio', 'sensor_type']
    )
