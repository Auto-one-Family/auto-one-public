"""Soft-delete devices, preserve sensor data (T02-Fix1)

Adds soft-delete support to esp_devices and changes FK behavior on
time-series tables from CASCADE to SET NULL so that historical data
(sensor_data, heartbeat logs, actuator states/history, AI predictions)
is preserved when a device is deleted.

Changes:
1. esp_devices: Add deleted_at (TIMESTAMPTZ) and deleted_by (VARCHAR) columns
2. sensor_data: Add device_name column, change FK to SET NULL + nullable
3. esp_heartbeat_logs: Change FK to SET NULL + nullable
4. actuator_states: Change FK to SET NULL + nullable
5. actuator_history: Change FK to SET NULL + nullable
6. ai_predictions: Change FK to SET NULL (already nullable)

Revision ID: soft_delete_devices_preserve_sensor_data
Revises: add_zones_table
Create Date: 2026-03-07

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision: str = "soft_delete_devices_preserve_sensor_data"
down_revision: Union[str, None] = "extend_onewire_address_varchar32"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _alter_fk(
    table: str,
    column: str,
    constraint_name: str,
    new_ondelete: str,
    nullable: bool,
) -> None:
    """Helper: drop old FK, alter nullable, create new FK with new ondelete."""
    # Drop existing FK constraint
    op.drop_constraint(constraint_name, table, type_="foreignkey")
    # Alter nullable if needed
    op.alter_column(table, column, nullable=nullable)
    # Create new FK with updated ondelete behavior
    op.create_foreign_key(
        constraint_name,
        table,
        "esp_devices",
        [column],
        ["id"],
        ondelete=new_ondelete,
    )


def _restore_fk(
    table: str,
    column: str,
    constraint_name: str,
    original_ondelete: str,
    nullable: bool,
) -> None:
    """Helper: restore original FK."""
    op.drop_constraint(constraint_name, table, type_="foreignkey")
    op.alter_column(table, column, nullable=nullable)
    op.create_foreign_key(
        constraint_name,
        table,
        "esp_devices",
        [column],
        ["id"],
        ondelete=original_ondelete,
    )


def upgrade() -> None:
    # 1. esp_devices: Add soft-delete columns
    op.add_column(
        "esp_devices",
        sa.Column(
            "deleted_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "esp_devices",
        sa.Column(
            "deleted_by",
            sa.String(64),
            nullable=True,
        ),
    )
    op.create_index("idx_esp_devices_deleted_at", "esp_devices", ["deleted_at"])

    # 2. sensor_data: Add device_name column
    op.add_column(
        "sensor_data",
        sa.Column("device_name", sa.String(128), nullable=True),
    )

    # 3. Change FKs from CASCADE to SET NULL on time-series tables
    _alter_fk(
        "sensor_data",
        "esp_id",
        "sensor_data_esp_id_fkey",
        "SET NULL",
        nullable=True,
    )
    _alter_fk(
        "esp_heartbeat_logs",
        "esp_id",
        "esp_heartbeat_logs_esp_id_fkey",
        "SET NULL",
        nullable=True,
    )
    _alter_fk(
        "actuator_states",
        "esp_id",
        "actuator_states_esp_id_fkey",
        "SET NULL",
        nullable=True,
    )
    _alter_fk(
        "actuator_history",
        "esp_id",
        "actuator_history_esp_id_fkey",
        "SET NULL",
        nullable=True,
    )
    _alter_fk(
        "ai_predictions",
        "target_esp_id",
        "ai_predictions_target_esp_id_fkey",
        "SET NULL",
        nullable=True,  # Already nullable
    )


def downgrade() -> None:
    # Restore FKs to CASCADE
    _restore_fk(
        "ai_predictions",
        "target_esp_id",
        "ai_predictions_target_esp_id_fkey",
        "CASCADE",
        nullable=True,  # Was already nullable
    )
    _restore_fk(
        "actuator_history",
        "esp_id",
        "actuator_history_esp_id_fkey",
        "CASCADE",
        nullable=False,
    )
    _restore_fk(
        "actuator_states",
        "esp_id",
        "actuator_states_esp_id_fkey",
        "CASCADE",
        nullable=False,
    )
    _restore_fk(
        "esp_heartbeat_logs",
        "esp_id",
        "esp_heartbeat_logs_esp_id_fkey",
        "CASCADE",
        nullable=False,
    )
    _restore_fk(
        "sensor_data",
        "esp_id",
        "sensor_data_esp_id_fkey",
        "CASCADE",
        nullable=False,
    )

    # Remove device_name from sensor_data
    op.drop_column("sensor_data", "device_name")

    # Remove soft-delete columns from esp_devices
    op.drop_index("idx_esp_devices_deleted_at", table_name="esp_devices")
    op.drop_column("esp_devices", "deleted_by")
    op.drop_column("esp_devices", "deleted_at")
