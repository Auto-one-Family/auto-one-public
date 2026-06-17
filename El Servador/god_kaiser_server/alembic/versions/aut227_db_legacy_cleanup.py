"""AUT-227 DB legacy cleanup: device_scope CheckConstraints + assigned_subzones deprecation comment

Revision ID: aut227_db_legacy_cleanup
Revises: add_plants_entity_lifecycle_events
Create Date: 2026-05-05

AUT-227 Server Cleanup D: DB Legacy-Cleanup.

Changes:
- D3: Add CheckConstraint on `sensor_configs.device_scope` and
       `actuator_configs.device_scope` to enforce the valid enum values
       ('zone_local', 'multi_zone', 'mobile').
- D1: Mark `sensor_configs.assigned_subzones` and
       `actuator_configs.assigned_subzones` as DEPRECATED via column comment.
       The column is no longer consumed by any business-logic layer
       (LogicEngine, ConfigBuilder, NotificationRouter, SafetyService).
       Subzone assignment is owned by `subzone_configs.assigned_gpios`.
       NO `DROP COLUMN` here — that requires an evidence period and live-data
       review (see Linear AUT-227, candidate for a future migration).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "aut227_db_legacy_cleanup"
down_revision: Union[str, None] = "add_plants_entity_lifecycle_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_DEPRECATED_COMMENT = (
    "DEPRECATED (AUT-227): legacy field, not consumed by business logic. "
    "Subzone assignment is owned by subzone_configs.assigned_gpios. "
    "Candidate for DROP COLUMN after evidence period."
)


def upgrade() -> None:
    # D3: enforce valid device_scope values at the DB layer.
    op.create_check_constraint(
        "ck_sensor_configs_device_scope",
        "sensor_configs",
        sa.text("device_scope IN ('zone_local', 'multi_zone', 'mobile')"),
    )
    op.create_check_constraint(
        "ck_actuator_configs_device_scope",
        "actuator_configs",
        sa.text("device_scope IN ('zone_local', 'multi_zone', 'mobile')"),
    )

    # D1: deprecation comment for assigned_subzones (kept as-is for backwards compat).
    op.alter_column(
        "sensor_configs",
        "assigned_subzones",
        existing_type=sa.JSON(),
        existing_nullable=True,
        comment=_DEPRECATED_COMMENT,
    )
    op.alter_column(
        "actuator_configs",
        "assigned_subzones",
        existing_type=sa.JSON(),
        existing_nullable=True,
        comment=_DEPRECATED_COMMENT,
    )


def downgrade() -> None:
    # D1 rollback: clear the deprecation comment.
    op.alter_column(
        "actuator_configs",
        "assigned_subzones",
        existing_type=sa.JSON(),
        existing_nullable=True,
        comment=None,
    )
    op.alter_column(
        "sensor_configs",
        "assigned_subzones",
        existing_type=sa.JSON(),
        existing_nullable=True,
        comment=None,
    )

    # D3 rollback: drop CheckConstraints.
    op.drop_constraint(
        "ck_actuator_configs_device_scope",
        "actuator_configs",
        type_="check",
    )
    op.drop_constraint(
        "ck_sensor_configs_device_scope",
        "sensor_configs",
        type_="check",
    )
