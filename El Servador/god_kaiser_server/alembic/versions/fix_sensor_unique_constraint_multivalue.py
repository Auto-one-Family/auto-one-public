"""Fix sensor unique constraint for multi-value support

Multi-Value Sensor Pattern Fix:
- Changes unique constraint from (esp_id, gpio) to (esp_id, gpio, sensor_type)
- Allows multiple sensor_types on the same GPIO (e.g., SHT31: sht31_temp + sht31_humidity)
- Required for proper multi-value sensor support

Revision ID: fix_multivalue_constraint
Revises: ee8733fb484d
Create Date: 2026-01-09
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'fix_multivalue_constraint'
down_revision: Union[str, None] = 'ee8733fb484d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Change sensor unique constraint to support multi-value sensors.

    Before: UniqueConstraint(esp_id, gpio) - Only 1 sensor per GPIO
    After:  UniqueConstraint(esp_id, gpio, sensor_type) - Multiple sensor_types per GPIO

    This allows multi-value sensors like SHT31 to have both:
    - sht31_temp on GPIO 21
    - sht31_humidity on GPIO 21
    """
    # Drop the old constraint
    op.drop_constraint('unique_esp_gpio_sensor', 'sensor_configs', type_='unique')

    # Create new constraint with sensor_type included
    op.create_unique_constraint(
        'unique_esp_gpio_sensor_type',
        'sensor_configs',
        ['esp_id', 'gpio', 'sensor_type']
    )


def downgrade() -> None:
    """
    Revert to single sensor per GPIO constraint.

    WARNING: This will fail if multi-value sensors exist in the database!
    Any sensor_configs with duplicate (esp_id, gpio) combinations must be
    deleted before downgrading.
    """
    # Drop the new constraint
    op.drop_constraint('unique_esp_gpio_sensor_type', 'sensor_configs', type_='unique')

    # Recreate the old constraint
    # WARNING: This may fail if multi-value sensors exist!
    op.create_unique_constraint(
        'unique_esp_gpio_sensor',
        'sensor_configs',
        ['esp_id', 'gpio']
    )
