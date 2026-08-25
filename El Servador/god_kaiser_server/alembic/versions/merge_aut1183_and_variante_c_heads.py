"""Merge AUT-1183 nutrient_phase and AUT-1173 rule_group_catalog_variante_c heads

Revision ID: merge_aut1183_variante_c
Revises: add_nutrient_phase_to_plants, update_rule_group_catalog_variante_c
Create Date: 2026-07-19

AUT-1183 (add_nutrient_phase_to_plants, via merge_aut1155_aut1156) and AUT-1173
(update_rule_group_catalog_variante_c) were both developed from the same parent
revision (add_rule_group_to_cross_esp_logic) in unrelated, parallel work,
each forming an independent head. This merge migration reunites both branches
into a single head so that alembic upgrade head is unambiguous, following the
same pattern as merge_aut1155_and_aut1156_heads.py.

No schema changes — pure head consolidation.
"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "merge_aut1183_variante_c"
down_revision: Union[str, Sequence[str]] = (
    "add_nutrient_phase_to_plants",
    "update_rule_group_catalog_variante_c",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
