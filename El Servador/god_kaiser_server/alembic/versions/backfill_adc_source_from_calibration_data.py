"""Backfill adc_source/pga_gain from calibration_data.derived (AUT-948)

For sensor_configs rows whose adc_source column still holds the server-default
'internal' but whose calibration_data.derived already carries adc_source='ads1115'
(i.e. the sensor was correctly calibrated for ADS1115 but the column was never
explicitly set), copy the descriptor from the calibration JSON into the column.

After this migration the column is the authoritative routing SSOT and the
sensor_handler.py fix (AUT-948 B1) can safely read from it without regression.

Idempotent: the WHERE clause filters on adc_source='internal', so rows that were
already backfilled (now adc_source='ads1115') are skipped on re-run.

downgrade is a no-op: reverting the column back to 'internal' would silently
restore the original mis-measurement — never do that.

Revision ID: backfill_adc_source_from_calibration_data
Revises: widen_alembic_version_col
Create Date: 2026-06-29
"""

from __future__ import annotations

from typing import Union

from alembic import op
import sqlalchemy as sa

revision: str = "backfill_adc_source_from_calibration_data"
down_revision: Union[str, None] = "widen_alembic_version_col"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE sensor_configs
            SET
                adc_source = calibration_data->'derived'->>'adc_source',
                pga_gain   = COALESCE(
                                 calibration_data->'derived'->>'pga_gain',
                                 pga_gain
                             )
            WHERE
                adc_source = 'internal'
                AND calibration_data IS NOT NULL
                AND calibration_data->'derived'->>'adc_source' = 'ads1115'
            """
        )
    )


def downgrade() -> None:
    # Reverting to 'internal' would silently restore wrong normalization for
    # ADS1115 sensors. Intentionally a no-op.
    pass
