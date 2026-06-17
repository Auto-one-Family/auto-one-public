"""Add session_metadata to calibration_sessions (AUT-299)

Revision ID: aut299_cal_session_metadata
Revises: aut299_temp_sensor_config_id
Create Date: 2026-05-08

Adds a JSONB session_metadata column to calibration_sessions so that
calibration-time parameters (e.g. solution temperature for EC ATC) can be
persisted alongside the session and used during finalize().
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "aut299_cal_session_metadata"
down_revision: Union[str, None] = "aut299_temp_sensor_config_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add session_metadata JSONB column to calibration_sessions."""
    op.add_column(
        "calibration_sessions",
        sa.Column(
            "session_metadata",
            sa.JSON(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Remove session_metadata column from calibration_sessions."""
    op.drop_column("calibration_sessions", "session_metadata")
