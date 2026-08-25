"""Add domain column to esp_devices

AUT-1085: Report/grouping metadata field on ESP devices.
The column is server-side only — never pushed to firmware.

Revision ID: add_domain_to_esp_devices
Revises: add_polarity_to_sensor_configs
Create Date: 2026-07-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision: str = "add_domain_to_esp_devices"
down_revision: Union[str, None] = "add_polarity_to_sensor_configs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add nullable domain column + index to esp_devices."""
    op.add_column(
        "esp_devices",
        sa.Column(
            "domain",
            sa.String(length=20),
            nullable=True,
        ),
    )
    op.create_index("ix_esp_devices_domain", "esp_devices", ["domain"])


def downgrade() -> None:
    """Remove domain index + column from esp_devices."""
    op.drop_index("ix_esp_devices_domain", table_name="esp_devices")
    op.drop_column("esp_devices", "domain")
