"""Merge AUT-1155 sensor_subzone_assignments and AUT-1156 allow_null_parent_zone_id

Revision ID: merge_aut1155_aut1156
Revises: add_sensor_subzone_assignments, allow_null_parent_zone_id_subzone_configs
Create Date: 2026-07-18

AUT-1155 (add_sensor_subzone_assignments) and AUT-1156
(allow_null_parent_zone_id_subzone_configs) were developed in parallel from
two different parent revisions (add_logic_settle_fields and
add_rule_group_to_cross_esp_logic respectively), each forming an independent
head.  AUT-1156 was committed first (6de2b0af); this merge migration reunites
both branches into a single head so that alembic upgrade head is unambiguous.

No schema changes — pure head consolidation.
"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "merge_aut1155_aut1156"
down_revision: Union[str, Sequence[str]] = (
    "add_sensor_subzone_assignments",
    "allow_null_parent_zone_id_subzone_configs",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
