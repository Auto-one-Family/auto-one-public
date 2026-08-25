"""Add sensor_subzone_assignments junction table

Revision ID: add_sensor_subzone_assignments
Revises: add_logic_settle_fields
Create Date: 2026-07-18

AUT-1155 [B1] n:m Sensor-Subzone-Zuordnung:

Creates the `sensor_subzone_assignments` junction table that represents an
explicit, UUID-keyed n:m assignment between sensor_configs and subzone_configs.

Design notes:
- assigned_gpios on subzone_configs remains canonical for the ESP32 config-push
  flow.  All existing get_subzone_by_gpio() call-sites are unaffected.
- Purely additive: no DROP COLUMN, no data migration.
- down_revision = "add_logic_settle_fields" (committed HEAD at time of writing).
  The parallel unmerged branch "allow_null_parent_zone_id_subzone_configs"
  (AUT-1156) branched from "add_rule_group_to_cross_esp_logic" and is a
  separate head; a merge-migration will be required once both are committed
  (see merge_aut120_aut227_merge_aut120_fail_safe_and_aut227_.py as precedent).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision: str = "add_sensor_subzone_assignments"
down_revision: Union[str, None] = "add_logic_settle_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = inspector.get_table_names()

    if "sensor_subzone_assignments" in existing_tables:
        return  # idempotent guard

    op.create_table(
        "sensor_subzone_assignments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            comment="Primary key (UUID)",
        ),
        sa.Column(
            "sensor_config_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sensor_configs.id", ondelete="CASCADE"),
            nullable=False,
            comment="Foreign key to sensor_configs.id",
        ),
        sa.Column(
            "subzone_config_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("subzone_configs.id", ondelete="CASCADE"),
            nullable=False,
            comment="Foreign key to subzone_configs.id",
        ),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="UTC timestamp of assignment creation",
        ),
        sa.Column(
            "assigned_by",
            sa.Integer,
            sa.ForeignKey("user_accounts.id", ondelete="SET NULL"),
            nullable=True,
            comment="User ID of the operator who created the assignment",
        ),
        sa.UniqueConstraint(
            "sensor_config_id",
            "subzone_config_id",
            name="uq_sensor_subzone_assignment",
        ),
    )

    op.create_index(
        "idx_sensor_subzone_sensor_config_id",
        "sensor_subzone_assignments",
        ["sensor_config_id"],
        unique=False,
    )
    op.create_index(
        "idx_sensor_subzone_subzone_config_id",
        "sensor_subzone_assignments",
        ["subzone_config_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_sensor_subzone_subzone_config_id",
        table_name="sensor_subzone_assignments",
    )
    op.drop_index(
        "idx_sensor_subzone_sensor_config_id",
        table_name="sensor_subzone_assignments",
    )
    op.drop_table("sensor_subzone_assignments")
