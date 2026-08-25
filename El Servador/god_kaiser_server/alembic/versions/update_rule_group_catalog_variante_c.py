"""Update rule_group CHECK constraint to the Variante C catalog

Revision ID: update_rule_group_catalog_variante_c
Revises: add_rule_group_to_cross_esp_logic
Create Date: 2026-07-19

AUT-1173 (TAX-5, Logic M1 Gruppenkarten): replaces the 6-value rule_group catalog
(klima/zeitplan/alarm/sicherheit/dosierung/sonstiges) with the 12-value Variante-C
catalog (ph/ec/bodenfeuchte/luftfeuchte/temperatur/co2/luftdruck/licht/durchfluss/
zeitplan/sicherheit/sonstiges — see RULE_GROUP_CATALOG in db/models/logic.py). Only
the CHECK constraint changes; the column itself (nullable String(20)) is untouched.
No backfill: all real rows have rule_group=NULL today and remain so — the effective
group is computed by LogicService.derive_rule_group() when NULL.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "update_rule_group_catalog_variante_c"
down_revision: Union[str, None] = "add_rule_group_to_cross_esp_logic"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_RULE_GROUP_CHECK = (
    "rule_group IN ('klima', 'zeitplan', 'alarm', 'sicherheit', 'dosierung', 'sonstiges')"
)
_NEW_RULE_GROUP_CHECK = (
    "rule_group IN ('ph', 'ec', 'bodenfeuchte', 'luftfeuchte', 'temperatur', 'co2', "
    "'luftdruck', 'licht', 'durchfluss', 'zeitplan', 'sicherheit', 'sonstiges')"
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    constraints = {c["name"] for c in inspector.get_check_constraints("cross_esp_logic")}
    if "ck_cross_esp_logic_rule_group" in constraints:
        op.drop_constraint("ck_cross_esp_logic_rule_group", "cross_esp_logic", type_="check")
    op.create_check_constraint(
        "ck_cross_esp_logic_rule_group",
        "cross_esp_logic",
        sa.text(_NEW_RULE_GROUP_CHECK),
    )
    # No backfill — rule_group is NULL on every existing row (no behavior change).


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    constraints = {c["name"] for c in inspector.get_check_constraints("cross_esp_logic")}
    if "ck_cross_esp_logic_rule_group" in constraints:
        op.drop_constraint("ck_cross_esp_logic_rule_group", "cross_esp_logic", type_="check")
    op.create_check_constraint(
        "ck_cross_esp_logic_rule_group",
        "cross_esp_logic",
        sa.text(_OLD_RULE_GROUP_CHECK),
    )
