"""Add alert_config and runtime_stats JSONB fields

Phase 4A.7: alert_config on sensor_configs, actuator_configs, esp_devices
Phase 4A.8: runtime_stats on sensor_configs, actuator_configs

Revision ID: a4a7_alert_runtime
Revises: add_notification_fingerprint
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a4a7_alert_runtime"
down_revision: Union[str, None] = "add_notification_fingerprint"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Phase 4A.7: alert_config JSONB on 3 tables
    op.add_column(
        "sensor_configs",
        sa.Column("alert_config", sa.JSON(), nullable=True),
    )
    op.add_column(
        "actuator_configs",
        sa.Column("alert_config", sa.JSON(), nullable=True),
    )
    op.add_column(
        "esp_devices",
        sa.Column("alert_config", sa.JSON(), nullable=True),
    )

    # Phase 4A.8: runtime_stats JSONB on 2 tables
    op.add_column(
        "sensor_configs",
        sa.Column("runtime_stats", sa.JSON(), nullable=True),
    )
    op.add_column(
        "actuator_configs",
        sa.Column("runtime_stats", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("actuator_configs", "runtime_stats")
    op.drop_column("sensor_configs", "runtime_stats")
    op.drop_column("esp_devices", "alert_config")
    op.drop_column("actuator_configs", "alert_config")
    op.drop_column("sensor_configs", "alert_config")
