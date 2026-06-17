"""Add sensor lifecycle columns (measurement_freshness_hours, calibration_interval_days)

Adds measurement freshness and calibration interval fields to both
sensor_type_defaults and sensor_configs tables for the Sensor-Lifecycle
Vereinheitlichung sprint.

Also seeds default values for known sensor types:
- pH/EC: 24h freshness, 30d calibration interval
- moisture: 2h freshness, 90d calibration interval

Revision ID: add_sensor_lifecycle
Revises: ea85866bc66e
Create Date: 2026-04-15

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "add_sensor_lifecycle"
down_revision: Union[str, None] = "ea85866bc66e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Seed data: sensor_type -> (measurement_freshness_hours, calibration_interval_days)
_LIFECYCLE_SEEDS = {
    "ph": (24, 30),
    "ec": (24, 30),
    "moisture": (2, 90),
}


def upgrade() -> None:
    # sensor_type_defaults: add lifecycle columns
    op.add_column(
        "sensor_type_defaults",
        sa.Column("measurement_freshness_hours", sa.Integer(), nullable=True),
    )
    op.add_column(
        "sensor_type_defaults",
        sa.Column("calibration_interval_days", sa.Integer(), nullable=True),
    )

    # sensor_configs: add lifecycle columns (instance overrides)
    op.add_column(
        "sensor_configs",
        sa.Column("measurement_freshness_hours", sa.Integer(), nullable=True),
    )
    op.add_column(
        "sensor_configs",
        sa.Column("calibration_interval_days", sa.Integer(), nullable=True),
    )

    # Seed default values for existing sensor type rows
    sensor_type_defaults = sa.table(
        "sensor_type_defaults",
        sa.column("sensor_type", sa.String),
        sa.column("measurement_freshness_hours", sa.Integer),
        sa.column("calibration_interval_days", sa.Integer),
    )
    for stype, (freshness, calibration) in _LIFECYCLE_SEEDS.items():
        op.execute(
            sensor_type_defaults.update()
            .where(sensor_type_defaults.c.sensor_type == stype)
            .values(
                measurement_freshness_hours=freshness,
                calibration_interval_days=calibration,
            )
        )


def downgrade() -> None:
    op.drop_column("sensor_configs", "calibration_interval_days")
    op.drop_column("sensor_configs", "measurement_freshness_hours")
    op.drop_column("sensor_type_defaults", "calibration_interval_days")
    op.drop_column("sensor_type_defaults", "measurement_freshness_hours")
