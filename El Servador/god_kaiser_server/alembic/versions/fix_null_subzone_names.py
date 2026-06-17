"""Fix NULL subzone_name values in subzone_configs

Revision ID: fix_null_subzone_names
Revises: change_extra_data_jsonb
Create Date: 2026-03-08 14:30:00.000000

BUG-09: 5 of 7 subzone_configs had subzone_name = NULL because the
assignment flow did not always provide a name. This migration backfills
auto-generated names ('Subzone 1', 'Subzone 2', ...) partitioned by esp_id.
"""

from typing import Union

from alembic import op

revision: str = "fix_null_subzone_names"
down_revision: Union[str, None] = "change_extra_data_jsonb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Backfill NULL subzone names with sequential 'Subzone N' per ESP
    op.execute("""
        UPDATE subzone_configs sc
        SET subzone_name = 'Subzone ' || numbered.rn
        FROM (
            SELECT id,
                   ROW_NUMBER() OVER (PARTITION BY esp_id ORDER BY id) AS rn
            FROM subzone_configs
            WHERE subzone_name IS NULL
        ) numbered
        WHERE sc.id = numbered.id
    """)


def downgrade() -> None:
    # No-op: we can't distinguish which names were auto-generated
    pass
