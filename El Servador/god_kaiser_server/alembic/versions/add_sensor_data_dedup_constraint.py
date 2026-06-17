"""Add UNIQUE constraint to sensor_data for MQTT QoS 1 deduplication

Revision ID: add_sensor_data_dedup
Revises: fix_actuator_datetime_tz
Create Date: 2026-03-10

Prevents duplicate sensor_data rows caused by MQTT QoS 1 redelivery.
Constraint: (esp_id, gpio, sensor_type, timestamp).

NOTE: Does not cover orphaned rows with esp_id=NULL after device soft-delete
(NULL != NULL in PostgreSQL/SQLite UNIQUE constraints). For live MQTT data
esp_id is always set, so this is acceptable.

Step 1: Remove existing duplicates (keep row with smallest id).
Step 2: Create UNIQUE constraint.
"""

from typing import Union

from alembic import op

revision: str = "add_sensor_data_dedup"
down_revision: Union[str, None] = "fix_actuator_datetime_tz"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Step 1: Remove existing duplicates (keep row with smallest id)
    # PostgreSQL-specific DELETE ... USING syntax
    op.execute(
        """
        DELETE FROM sensor_data a
        USING sensor_data b
        WHERE a.id > b.id
          AND a.esp_id = b.esp_id
          AND a.gpio = b.gpio
          AND a.sensor_type = b.sensor_type
          AND a.timestamp = b.timestamp
        """
    )

    # Step 2: Add UNIQUE constraint
    op.create_unique_constraint(
        "uq_sensor_data_esp_gpio_type_timestamp",
        "sensor_data",
        ["esp_id", "gpio", "sensor_type", "timestamp"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_sensor_data_esp_gpio_type_timestamp",
        "sensor_data",
        type_="unique",
    )
