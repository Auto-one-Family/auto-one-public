"""Add flow_rate_ml_s calibration column to actuator_configs

Revision ID: add_actuator_flow_rate_cal
Revises: backfill_adc_source_from_calibration_data
Create Date: 2026-07-01

AO-1: Pump calibration field flow_rate_ml_s (ml/s) as first-class column.
NULL = uncalibrated (safe default, no behavior change for existing rows).
Used server-side for duration_s = dose_ml / flow_rate_ml_s (AO-2).
Firmware is NOT notified of this field.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "add_actuator_flow_rate_cal"
down_revision: Union[str, None] = "backfill_adc_source_from_calibration_data"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("actuator_configs")}
    if "flow_rate_ml_s" not in columns:
        op.add_column(
            "actuator_configs",
            sa.Column(
                "flow_rate_ml_s",
                sa.Float(),
                nullable=True,
                comment=(
                    "AO-1: Pump flow rate calibration in ml/s. "
                    "NULL = uncalibrated. Must be > 0 when set. "
                    "Server-side only — never sent to firmware."
                ),
            ),
        )
    # No backfill — NULL is the correct default (uncalibrated)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("actuator_configs")}
    if "flow_rate_ml_s" in columns:
        op.drop_column("actuator_configs", "flow_rate_ml_s")
