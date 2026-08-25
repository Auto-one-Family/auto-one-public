"""Add tanks table and tank_subzone_assignments junction table

Revision ID: add_tanks_table
Revises: add_event_status_to_lifecycle_events
Create Date: 2026-07-20

AUT-1211 — Tank entity foundation for a future nutrient-balance ledger and
plant-lifecycle-event docking (both out of scope here).

Design notes (verify-plan, Stufe 2):
- Cardinality: tank n:1 zone (mandatory FK, analogous to esp_devices.zone_id),
  tank n:m subzone via a dedicated junction table. The known pilot is one
  tank feeding two subzones of the same zone, but the structure must not be
  pinned to exactly one tank per zone (future: multiple tanks per zone, or
  rarely one tank across zones) — hence n:m rather than a single FK column
  on either side.
- assigned_subzones (sensor.py/actuator.py) is DEPRECATED/read-only per
  AUT-227 (DB Legacy-Cleanup) and belongs to a different domain (sensor/
  actuator scope). This migration does NOT depend on it; the junction table
  is modelled 1:1 after sensor_subzone_assignments (AUT-1155) instead.
- Purely additive: no DROP COLUMN, no data migration, both tables start empty.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision: str = "add_tanks_table"
down_revision: Union[str, None] = "add_event_status_to_lifecycle_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TANK_OPERATION_MODES = ("drain_to_waste", "recirculating")
_OPERATION_MODE_CHECK = (
    f"operation_mode IN ({', '.join(repr(m) for m in TANK_OPERATION_MODES)})"
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = inspector.get_table_names()

    if "tanks" not in existing_tables:
        op.create_table(
            "tanks",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                nullable=False,
                comment="Primary key (UUID)",
            ),
            sa.Column(
                "zone_id",
                sa.String(length=50),
                sa.ForeignKey("zones.zone_id", ondelete="RESTRICT"),
                nullable=False,
                comment="Zone identifier (FK to zones.zone_id)",
            ),
            sa.Column(
                "name",
                sa.String(length=100),
                nullable=False,
                comment="Human-readable tank name/identifier",
            ),
            sa.Column(
                "nominal_volume_l",
                sa.Float(),
                nullable=True,
                comment="Optional nominal volume in liters (NULL if not precisely known)",
            ),
            sa.Column(
                "operation_mode",
                sa.String(length=20),
                nullable=False,
                comment="Operation mode: 'drain_to_waste' or 'recirculating'",
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.CheckConstraint(_OPERATION_MODE_CHECK, name="ck_tanks_operation_mode"),
        )
        op.create_index("idx_tanks_zone_id", "tanks", ["zone_id"])

    if "tank_subzone_assignments" not in existing_tables:
        op.create_table(
            "tank_subzone_assignments",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                nullable=False,
                comment="Primary key (UUID)",
            ),
            sa.Column(
                "tank_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("tanks.id", ondelete="CASCADE"),
                nullable=False,
                comment="Foreign key to tanks.id",
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
                sa.Integer(),
                sa.ForeignKey("user_accounts.id", ondelete="SET NULL"),
                nullable=True,
                comment="User ID of the operator who created the assignment",
            ),
            sa.UniqueConstraint(
                "tank_id",
                "subzone_config_id",
                name="uq_tank_subzone_assignment",
            ),
        )
        op.create_index(
            "idx_tank_subzone_tank_id", "tank_subzone_assignments", ["tank_id"]
        )
        op.create_index(
            "idx_tank_subzone_subzone_config_id",
            "tank_subzone_assignments",
            ["subzone_config_id"],
        )


def downgrade() -> None:
    op.drop_index("idx_tank_subzone_subzone_config_id", table_name="tank_subzone_assignments")
    op.drop_index("idx_tank_subzone_tank_id", table_name="tank_subzone_assignments")
    op.drop_table("tank_subzone_assignments")

    op.drop_index("idx_tanks_zone_id", table_name="tanks")
    op.drop_table("tanks")
