"""Add mount geometry columns to sensor_configs (AUT-1555)

Revision ID: add_sensor_mount_geometry_aut1555
Revises: add_lifecycle_spatial_phase_vocab
Create Date: 2026-08-25

A1: three nullable first-class columns on the existing sensor_configs row.
Server-only — never sent to firmware / MQTT / NVS.
Unique unique_esp_gpio_sensor_interface_v3 is not touched.
No backfill; old rows stay valid (NULL).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "add_sensor_mount_geometry_aut1555"
down_revision: Union[str, None] = "add_lifecycle_spatial_phase_vocab"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("sensor_configs")}
    if "mount_height_cm" not in columns:
        op.add_column(
            "sensor_configs",
            sa.Column(
                "mount_height_cm",
                sa.Float(),
                nullable=True,
                comment=(
                    "AUT-1555: Mount height in cm. NULL = unset. "
                    "Server-side only — never sent to firmware."
                ),
            ),
        )
    if "mount_medium" not in columns:
        op.add_column(
            "sensor_configs",
            sa.Column(
                "mount_medium",
                sa.String(length=16),
                nullable=True,
                comment=(
                    "AUT-1555: Mount medium — air | canopy | substrate | solution. "
                    "NULL = unset."
                ),
            ),
        )
    if "mount_angle_deg" not in columns:
        op.add_column(
            "sensor_configs",
            sa.Column(
                "mount_angle_deg",
                sa.Float(),
                nullable=True,
                comment=(
                    "AUT-1555: Mount angle in degrees. NULL = unset. "
                    "Server-side only — never sent to firmware."
                ),
            ),
        )
    existing_cks = {ck["name"] for ck in inspector.get_check_constraints("sensor_configs")}
    if "ck_sensor_configs_mount_medium" not in existing_cks:
        op.create_check_constraint(
            "ck_sensor_configs_mount_medium",
            "sensor_configs",
            "mount_medium IS NULL OR mount_medium IN "
            "('air', 'canopy', 'substrate', 'solution')",
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_cks = {ck["name"] for ck in inspector.get_check_constraints("sensor_configs")}
    if "ck_sensor_configs_mount_medium" in existing_cks:
        op.drop_constraint(
            "ck_sensor_configs_mount_medium",
            "sensor_configs",
            type_="check",
        )
    columns = {col["name"] for col in inspector.get_columns("sensor_configs")}
    if "mount_angle_deg" in columns:
        op.drop_column("sensor_configs", "mount_angle_deg")
    if "mount_medium" in columns:
        op.drop_column("sensor_configs", "mount_medium")
    if "mount_height_cm" in columns:
        op.drop_column("sensor_configs", "mount_height_cm")
