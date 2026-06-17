"""Add fail_safe_on_disconnect column to actuator_configs

Revision ID: add_actuator_fail_safe
Revises: add_plants_entity_lifecycle_events
Create Date: 2026-05-06

AUT-120: Server-side override for ESP32 fail-safe-on-disconnect default.
AUT-482: Product default True on create — manual actuators without offline
rule must turn OFF on MQTT disconnect.

- None  -> omit from config push (legacy rows only)
- True  -> ESP32 must turn the actuator OFF on MQTT disconnect (uncovered)
- False -> ESP32 keeps the last applied state on disconnect
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "add_actuator_fail_safe"
down_revision: Union[str, None] = "add_plants_entity_lifecycle_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("actuator_configs")}
    if "fail_safe_on_disconnect" not in columns:
        op.add_column(
            "actuator_configs",
            sa.Column(
                "fail_safe_on_disconnect",
                sa.Boolean(),
                nullable=True,
                comment=(
                    "AUT-482: Override ESP32 fail-safe-on-disconnect. "
                    "NULL = omit from push, TRUE = force OFF, FALSE = hold."
                ),
            ),
        )
    # Backfill: product decision AUT-482 — uncovered manual actuators → OFF on disconnect
    op.execute(
        "UPDATE actuator_configs SET fail_safe_on_disconnect = TRUE "
        "WHERE fail_safe_on_disconnect IS NULL"
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("actuator_configs")}
    if "fail_safe_on_disconnect" in columns:
        op.drop_column("actuator_configs", "fail_safe_on_disconnect")
