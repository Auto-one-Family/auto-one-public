"""Add actuator_subzone_assignments junction table

Revision ID: add_actuator_subzone_assignments
Revises: add_plants_zone_id_aut1073
Create Date: 2026-07-23

n:m Actuator-Subzone-Zuordnung (Verortung / Auswertung):

Creates the `actuator_subzone_assignments` junction table that represents an
explicit, UUID-keyed n:m assignment between actuator_configs and subzone_configs.

Design notes:
- assigned_gpios / get_subzone_by_gpio() remains canonical for ESP32 config-push
  and Logic Engine control-path subzone matching. This table is additive
  Verortung only (Monitor + UI coverage).
- assigned_subzones JSON stays DEPRECATED/dead (AUT-227) — no revive, no drop.
- Purely additive and reversible: no DROP COLUMN, no data migration.
- Pattern: 1:1 after add_sensor_subzone_assignments (AUT-1155).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision: str = "add_actuator_subzone_assignments"
down_revision: Union[str, None] = "add_plants_zone_id_aut1073"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = inspector.get_table_names()

    if "actuator_subzone_assignments" in existing_tables:
        return  # idempotent guard

    op.create_table(
        "actuator_subzone_assignments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            comment="Primary key (UUID)",
        ),
        sa.Column(
            "actuator_config_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("actuator_configs.id", ondelete="CASCADE"),
            nullable=False,
            comment="Foreign key to actuator_configs.id",
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
            "actuator_config_id",
            "subzone_config_id",
            name="uq_actuator_subzone_assignment",
        ),
    )

    op.create_index(
        "idx_actuator_subzone_actuator_config_id",
        "actuator_subzone_assignments",
        ["actuator_config_id"],
        unique=False,
    )
    op.create_index(
        "idx_actuator_subzone_subzone_config_id",
        "actuator_subzone_assignments",
        ["subzone_config_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_actuator_subzone_subzone_config_id",
        table_name="actuator_subzone_assignments",
    )
    op.drop_index(
        "idx_actuator_subzone_actuator_config_id",
        table_name="actuator_subzone_assignments",
    )
    op.drop_table("actuator_subzone_assignments")
