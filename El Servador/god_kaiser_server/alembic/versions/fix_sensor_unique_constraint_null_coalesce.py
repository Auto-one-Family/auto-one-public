"""Fix sensor unique constraint: COALESCE for NULL-safe dedup (V19-F02+F13)

The existing UniqueConstraint unique_esp_gpio_sensor_interface on
(esp_id, gpio, sensor_type, onewire_address, i2c_address) does NOT
prevent duplicates when onewire_address or i2c_address is NULL, because
PostgreSQL treats NULL != NULL in UNIQUE constraints.

This migration:
1. Removes duplicate sensor_configs (keeps the oldest row per group)
2. Drops the old constraint
3. Creates an expression-based UNIQUE INDEX using COALESCE to treat
   NULL as empty string, making the constraint effective for VPD
   (virtual, both NULL) and SHT31 (i2c_address was incorrectly NULL).

Revision ID: fix_null_coalesce_unique
Revises: 78002fde47ca
Create Date: 2026-03-26
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "fix_null_coalesce_unique"
down_revision: Union[str, None] = "78002fde47ca"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Replace nullable UNIQUE constraint with COALESCE expression index."""
    conn = op.get_bind()

    # Step 1: Remove duplicate sensor_configs, keeping the oldest (MIN id by created_at)
    # This uses a CTE to find the keeper ID per duplicate group, then deletes the rest.
    conn.execute(sa.text("""
        DELETE FROM sensor_configs
        WHERE id NOT IN (
            SELECT DISTINCT ON (
                esp_id, gpio, sensor_type,
                COALESCE(onewire_address, ''),
                COALESCE(i2c_address::text, '')
            ) id
            FROM sensor_configs
            ORDER BY
                esp_id, gpio, sensor_type,
                COALESCE(onewire_address, ''),
                COALESCE(i2c_address::text, ''),
                created_at ASC,
                id ASC
        )
    """))

    # Step 2: Drop old constraint (NULL-unsafe)
    with op.batch_alter_table("sensor_configs", schema=None) as batch_op:
        batch_op.drop_constraint("unique_esp_gpio_sensor_interface", type_="unique")

    # Step 3: Create expression-based UNIQUE INDEX with COALESCE
    # This treats NULL values as '' for uniqueness comparison,
    # preventing duplicate rows when onewire_address/i2c_address are NULL.
    op.execute(sa.text("""
        CREATE UNIQUE INDEX unique_esp_gpio_sensor_interface_v2
        ON sensor_configs (
            esp_id,
            gpio,
            sensor_type,
            COALESCE(onewire_address, ''),
            COALESCE(i2c_address::text, '')
        )
    """))


def downgrade() -> None:
    """Revert to old nullable UNIQUE constraint."""
    # Drop expression index
    op.execute(sa.text("DROP INDEX IF EXISTS unique_esp_gpio_sensor_interface_v2"))

    # Recreate old constraint
    with op.batch_alter_table("sensor_configs", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "unique_esp_gpio_sensor_interface",
            ["esp_id", "gpio", "sensor_type", "onewire_address", "i2c_address"],
        )
