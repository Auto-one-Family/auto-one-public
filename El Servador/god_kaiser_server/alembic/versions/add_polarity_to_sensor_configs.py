"""Add polarity field to sensor_configs (liquid_level PNP/NPN support)

Adds a per-sensor signal polarity field so digital switch sensors (currently
liquid_level) can be configured for PNP (active_high, e.g. XKC-Y26S-PNP) or
NPN (active_low, e.g. XKC-Y25-NPN, default) without a firmware code change.

New column:
1. polarity (String(16), NOT NULL, server_default 'active_low')

polarity is NOT an identity field — it is not added to
unique_esp_gpio_sensor_interface_v3 (two sensors differing only in polarity
on the same GPIO would be a config error, not two valid sensors).

Revision ID: add_polarity_to_sensor_configs
Revises: add_daily_limits_cross_esp_logic
Create Date: 2026-07-02
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "add_polarity_to_sensor_configs"
down_revision: Union[str, None] = "add_daily_limits_cross_esp_logic"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add polarity column (additive, non-breaking — existing rows default to 'active_low')."""
    op.add_column(
        "sensor_configs",
        sa.Column(
            "polarity",
            sa.String(length=16),
            nullable=False,
            server_default="active_low",
        ),
    )


def downgrade() -> None:
    """Drop polarity column."""
    op.drop_column("sensor_configs", "polarity")
