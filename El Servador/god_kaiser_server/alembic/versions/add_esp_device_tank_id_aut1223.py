"""Add tank_id FK to esp_devices (AUT-1223 Q2)

Revision ID: add_esp_device_tank_id_aut1223
Revises: add_plan_segments_aut1232
Create Date: 2026-07-22

AUT-1223 (Q2) — n:1 device↔tank assignment. Analogous to
ESPDevice.zone_id (esp.py): nullable FK esp_devices.tank_id -> tanks.id,
ON DELETE SET NULL, indexed. NOT an m:n junction — no multi-tank-from-
one-device measurement scenario exists.

Binding Q1 decision (unaffected by this migration): the canonical tank
EC/pH target remains plan_segment@now via Tank.zone_id +
tank_subzone_assignments. No target_ec/target_ph field is added here.

Purely additive: no DROP, no data migration, no changes to existing
columns.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision: str = "add_esp_device_tank_id_aut1223"
down_revision: Union[str, None] = "add_plan_segments_aut1232"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("esp_devices")}

    if "tank_id" not in columns:
        op.add_column(
            "esp_devices",
            sa.Column(
                "tank_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("tanks.id", ondelete="SET NULL"),
                nullable=True,
                comment="AUT-1223: Assigned tank (n:1, FK to tanks.id)",
            ),
        )

    existing_indexes = {ix["name"] for ix in inspector.get_indexes("esp_devices")}
    if "ix_esp_devices_tank_id" not in existing_indexes:
        op.create_index(
            "ix_esp_devices_tank_id",
            "esp_devices",
            ["tank_id"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_indexes = {ix["name"] for ix in inspector.get_indexes("esp_devices")}
    if "ix_esp_devices_tank_id" in existing_indexes:
        op.drop_index("ix_esp_devices_tank_id", table_name="esp_devices")

    columns = {col["name"] for col in inspector.get_columns("esp_devices")}
    if "tank_id" in columns:
        op.drop_column("esp_devices", "tank_id")
