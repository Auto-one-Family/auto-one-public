"""Add ADS1115 external ADC source fields + channel-aware unique index

Adds per-sensor external-ADC acquisition fields to sensor_configs so pH/EC
can OPTIONALLY be read via an external 16-bit I2C ADC (ADS1115) instead of the
internal ESP32 12-bit ADC. The internal ADC stays the default; only the
acquisition source changes — the RAW value flows through the identical
conversion/calibration path.

New columns:
1. adc_source   (String(20), NOT NULL, server_default 'internal')
2. adc_channel  (Integer, nullable)  — ADS1115 single-ended channel 0-3
3. pga_gain     (String(16), nullable) — ADS1115 PGA full-scale range, e.g. '4.096'

Unique index:
- Replaces unique_esp_gpio_sensor_interface_v2 with _v3 that additionally
  COALESCEs adc_channel into the key. Without this, two pH/EC sensors on the
  SAME ADS1115 (same esp_id, gpio=0, i2c_address, sensor_type) but different
  channels would collide.

Revision ID: add_adc_source_channel_pga
Revises: aut299_cal_session_metadata
Create Date: 2026-06-14
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "add_adc_source_channel_pga"
down_revision: Union[str, None] = "aut299_cal_session_metadata"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add ADS1115 ADC fields and rebuild the unique index to include adc_channel."""
    # Step 1: Add new columns (additive, non-breaking — existing rows default to 'internal')
    op.add_column(
        "sensor_configs",
        sa.Column(
            "adc_source",
            sa.String(length=20),
            nullable=False,
            server_default="internal",
        ),
    )
    op.add_column(
        "sensor_configs",
        sa.Column("adc_channel", sa.Integer(), nullable=True),
    )
    op.add_column(
        "sensor_configs",
        sa.Column("pga_gain", sa.String(length=16), nullable=True),
    )

    # Step 2: Drop the previous channel-unaware unique index
    op.execute(sa.text("DROP INDEX IF EXISTS unique_esp_gpio_sensor_interface_v2"))

    # Step 3: Create channel-aware unique index (COALESCE NULLs -> '')
    op.execute(sa.text("""
        CREATE UNIQUE INDEX unique_esp_gpio_sensor_interface_v3
        ON sensor_configs (
            esp_id,
            gpio,
            sensor_type,
            COALESCE(onewire_address, ''),
            COALESCE(i2c_address::text, ''),
            COALESCE(adc_channel::text, '')
        )
    """))


def downgrade() -> None:
    """Revert to the channel-unaware unique index and drop the new columns."""
    op.execute(sa.text("DROP INDEX IF EXISTS unique_esp_gpio_sensor_interface_v3"))

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

    op.drop_column("sensor_configs", "pga_gain")
    op.drop_column("sensor_configs", "adc_channel")
    op.drop_column("sensor_configs", "adc_source")
