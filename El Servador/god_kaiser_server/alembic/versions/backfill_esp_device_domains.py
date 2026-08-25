"""Backfill domain values for known ESP devices (AUT-1085)

Populates the domain column on esp_devices for the four known devices
in the dev-local environment. ESP_E58280 is a pure actuator device and
intentionally remains NULL.

Targets (by device_id string):
  ESP_57E1D4  -> wasser
  ESP_70705C  -> luft
  ESP_AEAE64  -> wasser
  ESP_E58280  -> NULL  (no-op — already NULL, not touched)

Idempotent: WHERE clause limits updates to rows where domain IS NULL,
so re-running is safe.

downgrade: Resets the three backfilled devices back to NULL.

Revision ID: backfill_esp_device_domains
Revises: add_device_domain_changes_table
Create Date: 2026-07-12
"""

from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "backfill_esp_device_domains"
down_revision: Union[str, None] = "add_device_domain_changes_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE esp_devices
            SET domain = CASE device_id
                WHEN 'ESP_57E1D4' THEN 'wasser'
                WHEN 'ESP_70705C' THEN 'luft'
                WHEN 'ESP_AEAE64' THEN 'wasser'
            END
            WHERE device_id IN ('ESP_57E1D4', 'ESP_70705C', 'ESP_AEAE64')
              AND domain IS NULL
            """
        )
    )


def downgrade() -> None:
    # Reset the three backfilled devices back to NULL.
    op.execute(
        sa.text(
            """
            UPDATE esp_devices
            SET domain = NULL
            WHERE device_id IN ('ESP_57E1D4', 'ESP_70705C', 'ESP_AEAE64')
            """
        )
    )
