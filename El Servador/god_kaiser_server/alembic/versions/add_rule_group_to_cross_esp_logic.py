"""Add rule_group column + CHECK constraint to cross_esp_logic

Revision ID: add_rule_group_to_cross_esp_logic
Revises: add_logic_exec_skip_flag
Create Date: 2026-07-18

AUT-1145 (S0, Logic M1 Gruppenkarten): nullable display-group override for the
new Gruppenkarten UI (klima/zeitplan/alarm/sicherheit/dosierung/sonstiges,
see RULE_GROUP_CATALOG in db/models/logic.py). NULL is the default and
remains valid for every existing row — the effective group is computed by
LogicService.derive_rule_group() when NULL, never backfilled here.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "add_rule_group_to_cross_esp_logic"
down_revision: Union[str, None] = "add_logic_exec_skip_flag"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RULE_GROUP_CHECK = (
    "rule_group IN ('klima', 'zeitplan', 'alarm', 'sicherheit', 'dosierung', 'sonstiges')"
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("cross_esp_logic")}
    if "rule_group" not in columns:
        op.add_column(
            "cross_esp_logic",
            sa.Column(
                "rule_group",
                sa.String(20),
                nullable=True,
                comment="Explicit rule_group override (see RULE_GROUP_CATALOG). NULL = auto-derived.",
            ),
        )
    constraints = {c["name"] for c in inspector.get_check_constraints("cross_esp_logic")}
    if "ck_cross_esp_logic_rule_group" not in constraints:
        op.create_check_constraint(
            "ck_cross_esp_logic_rule_group",
            "cross_esp_logic",
            sa.text(_RULE_GROUP_CHECK),
        )
    # No backfill — NULL is the correct, common default (no behavior change for existing rows)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    constraints = {c["name"] for c in inspector.get_check_constraints("cross_esp_logic")}
    if "ck_cross_esp_logic_rule_group" in constraints:
        op.drop_constraint("ck_cross_esp_logic_rule_group", "cross_esp_logic", type_="check")
    columns = {col["name"] for col in inspector.get_columns("cross_esp_logic")}
    if "rule_group" in columns:
        op.drop_column("cross_esp_logic", "rule_group")
