"""Add calibration_sessions table

Revision ID: ea85866bc66e
Revises: extend_audit_log_status_varchar_50
Create Date: 2026-04-06 07:51:36.686109

Notes:
    - This migration is intentionally scoped to calibration_sessions only.
    - It is idempotent for existing deployments where create_all already created the table.
    - It avoids unrelated schema drift changes from autogenerate output.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "ea85866bc66e"
down_revision: Union[str, None] = "extend_audit_log_status_varchar_50"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(idx.get("name") == index_name for idx in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if "calibration_sessions" not in existing_tables:
        op.create_table(
            "calibration_sessions",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("esp_id", sa.String(length=24), nullable=False),
            sa.Column("gpio", sa.Integer(), nullable=False),
            sa.Column("sensor_type", sa.String(length=50), nullable=False),
            sa.Column("sensor_config_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("status", sa.String(length=10), nullable=False),
            sa.Column("method", sa.String(length=30), nullable=False),
            sa.Column("expected_points", sa.Integer(), nullable=False),
            sa.Column("calibration_points", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("calibration_result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("correlation_id", sa.String(length=64), nullable=True),
            sa.Column("initiated_by", sa.String(length=100), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("failure_reason", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["sensor_config_id"],
                ["sensor_configs.id"],
                ondelete="SET NULL",
            ),
            sa.PrimaryKeyConstraint("id"),
        )

    # Ensure all required indexes exist, even if table pre-existed.
    if not _index_exists("calibration_sessions", "idx_cal_sessions_sensor"):
        op.create_index(
            "idx_cal_sessions_sensor",
            "calibration_sessions",
            ["esp_id", "gpio", "sensor_type"],
            unique=False,
        )
    if not _index_exists("calibration_sessions", "idx_cal_sessions_status"):
        op.create_index(
            "idx_cal_sessions_status",
            "calibration_sessions",
            ["status"],
            unique=False,
        )
    if not _index_exists("calibration_sessions", "idx_cal_sessions_created"):
        op.create_index(
            "idx_cal_sessions_created",
            "calibration_sessions",
            ["created_at"],
            unique=False,
        )
    if not _index_exists("calibration_sessions", "idx_cal_sessions_active"):
        op.create_index(
            "idx_cal_sessions_active",
            "calibration_sessions",
            ["esp_id", "gpio", "status"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()
    if "calibration_sessions" not in existing_tables:
        return

    if _index_exists("calibration_sessions", "idx_cal_sessions_active"):
        op.drop_index("idx_cal_sessions_active", table_name="calibration_sessions")
    if _index_exists("calibration_sessions", "idx_cal_sessions_created"):
        op.drop_index("idx_cal_sessions_created", table_name="calibration_sessions")
    if _index_exists("calibration_sessions", "idx_cal_sessions_status"):
        op.drop_index("idx_cal_sessions_status", table_name="calibration_sessions")
    if _index_exists("calibration_sessions", "idx_cal_sessions_sensor"):
        op.drop_index("idx_cal_sessions_sensor", table_name="calibration_sessions")

    op.drop_table("calibration_sessions")
