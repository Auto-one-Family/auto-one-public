"""Widen alembic_version.version_num to VARCHAR(255)

Alembic creates alembic_version.version_num as VARCHAR(32) by default. This
repo already has revision IDs longer than that (e.g. the 41-char
"backfill_adc_source_from_calibration_data"); running a real step-by-step
`alembic upgrade` (not the create_all() bootstrap shortcut in env.py for
truly empty databases) fails on the final stamp with
StringDataRightTruncationError as soon as it reaches such a revision.

Unrelated to any ESP32/MQTT identifier limit: alembic_version is pure
server-side migration bookkeeping and is never transmitted to firmware,
MQTT topics/payloads, or the broker (verified: no reference to
alembic_version/version_num anywhere outside this alembic/ package). The
ESP32's own esp_id (used as its MQTT client_id) is generated independently
in El Trabajante/src/services/config/config_manager.cpp and stays well
under its own 32-byte buffer — do not conflate the two when reading this.

Must run BEFORE backfill_adc_source_from_calibration_data: that migration's
own revision id is 41 chars, so stamping it under the still-narrow VARCHAR(32)
fails before this widening migration would ever get a chance to run. Inserted
directly after add_adc_source_channel_pga instead of at the tip of the chain.

Revision ID: widen_alembic_version_col
Revises: add_adc_source_channel_pga
Create Date: 2026-07-01
"""

from __future__ import annotations

from typing import Union

from alembic import op

revision: str = "widen_alembic_version_col"
down_revision: Union[str, None] = "add_adc_source_channel_pga"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(255)")


def downgrade() -> None:
    # Narrowing back to VARCHAR(32) would immediately break on the existing
    # >32-char revision ids already in this repo's history. Intentionally a
    # no-op — never narrow this column.
    pass
