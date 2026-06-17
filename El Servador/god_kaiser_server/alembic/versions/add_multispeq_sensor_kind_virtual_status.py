"""Add sensor_kind column to sensor_configs (AUT-211)

Adds the `sensor_kind` column that distinguishes between continuous-stream
sensors (default, MQTT-driven) and snapshot sensors (manual / HTTP import,
e.g. MultispeQ photosynthesis measurements).

Changes:
1. sensor_configs: Add sensor_kind VARCHAR(20) NOT NULL DEFAULT 'continuous'
2. sensor_configs: Add CHECK constraint sensor_kind IN ('continuous', 'snapshot')

Revision ID: add_multispeq_sensor_kind_virtual_status
Revises: add_critical_degraded
Create Date: 2026-04-30

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision: str = "add_multispeq_sensor_kind_virtual_status"
down_revision: Union[str, None] = "add_critical_degraded"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CHECK_CONSTRAINT_NAME = "ck_sensor_configs_sensor_kind"


def upgrade() -> None:
    op.add_column(
        "sensor_configs",
        sa.Column(
            "sensor_kind",
            sa.String(length=20),
            nullable=False,
            server_default="continuous",
        ),
    )
    op.create_check_constraint(
        CHECK_CONSTRAINT_NAME,
        "sensor_configs",
        "sensor_kind IN ('continuous', 'snapshot')",
    )


def downgrade() -> None:
    op.drop_constraint(CHECK_CONSTRAINT_NAME, "sensor_configs", type_="check")
    op.drop_column("sensor_configs", "sensor_kind")
