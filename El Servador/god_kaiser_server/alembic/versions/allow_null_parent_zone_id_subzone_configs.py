"""Allow NULL parent_zone_id in subzone_configs

Revision ID: allow_null_parent_zone_id_subzone_configs
Revises: add_rule_group_to_cross_esp_logic
Create Date: 2026-07-18

AUT-1156 [B3] Subzone ohne Zone anlegen:

Removes the NOT NULL constraint on subzone_configs.parent_zone_id so that
subzones can be created before their zone exists (free-order provisioning:
Zone / Subzone / Plant / Sensor in any order).

Design decision: Weg (a) — loosen the column rather than introduce a
default-zone placeholder record.  The column had no FK to begin with
(documented in AUT-1152), so loosening nullable is purely additive.

Downgrade: ALTER back to NOT NULL.  This will fail with a PostgreSQL error
if any row has parent_zone_id IS NULL at the time of downgrade.  That is
acceptable: the operator must either reassign those subzones or accept that
the downgrade is blocked until no NULL rows remain.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "allow_null_parent_zone_id_subzone_configs"
down_revision: Union[str, None] = "add_rule_group_to_cross_esp_logic"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"]: col for col in inspector.get_columns("subzone_configs")}
    col = columns.get("parent_zone_id")
    if col is not None and not col.get("nullable", False):
        op.alter_column(
            "subzone_configs",
            "parent_zone_id",
            existing_type=sa.String(50),
            nullable=True,
        )


def downgrade() -> None:
    # NOTE: Fails at the DB level if any row still has parent_zone_id IS NULL.
    # Operator must resolve NULL rows before downgrading.
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"]: col for col in inspector.get_columns("subzone_configs")}
    col = columns.get("parent_zone_id")
    if col is not None and col.get("nullable", True):
        op.alter_column(
            "subzone_configs",
            "parent_zone_id",
            existing_type=sa.String(50),
            nullable=False,
        )
