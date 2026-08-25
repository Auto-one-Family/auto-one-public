"""Snapshot zone/subzone on lifecycle events; normalize zone_contexts.growth_phase

Adds WHERE snapshot columns on plant_lifecycle_events so executed actions
keep the zone/subzone they were recorded against. Rewrites legacy
zone_contexts.growth_phase strings (flower_week_5, vegetative, …) onto
the shared PLANT_PHASES vocabulary.

Revision ID: add_lifecycle_spatial_phase_vocab
Revises: add_uebergang_vorbluete_light_phase
Create Date: 2026-08-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "add_lifecycle_spatial_phase_vocab"
down_revision: Union[str, None] = "add_uebergang_vorbluete_light_phase"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_LEGACY_MAP = {
    "seedling": "clone",
    "clone": "clone",
    "vegetative": "veg-frueh",
    "veg": "veg-frueh",
    "pre_flower": "uebergang-vorbluete",
    "pre-flower": "uebergang-vorbluete",
    "flower": "bluete-stretch",
    "flower_early": "bluete-stretch",
    "flower_late": "bluete-bulk",
    "flower_week_1": "bluete-stretch",
    "flower_week_2": "bluete-stretch",
    "flower_week_3": "bluete-stretch",
    "flower_week_4": "bluete-stretch",
    "flower_week_5": "bluete-bulk",
    "flower_week_6": "bluete-bulk",
    "flower_week_7": "bluete-bulk",
    "flower_week_8": "bluete-bulk",
    "flower_week_9": "bluete-ende",
    "flower_week_10": "bluete-ende",
    "flush": "bluete-ende",
    "harvest": "harvested",
    "harvested": "harvested",
    "drying": "harvested",
    "curing": "harvested",
}


def upgrade() -> None:
    op.add_column(
        "plant_lifecycle_events",
        sa.Column("zone_id", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "plant_lifecycle_events",
        sa.Column("subzone_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_lifecycle_events_zone_id",
        "plant_lifecycle_events",
        "zones",
        ["zone_id"],
        ["zone_id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_lifecycle_events_subzone_id",
        "plant_lifecycle_events",
        "subzone_configs",
        ["subzone_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "idx_lifecycle_zone_id", "plant_lifecycle_events", ["zone_id"]
    )
    op.create_index(
        "idx_lifecycle_subzone_id", "plant_lifecycle_events", ["subzone_id"]
    )

    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, growth_phase FROM zone_contexts WHERE growth_phase IS NOT NULL")
    ).fetchall()
    for row_id, raw in rows:
        if raw is None:
            continue
        key = str(raw).strip().lower().replace(" ", "_")
        mapped = _LEGACY_MAP.get(key)
        if mapped is None and key.startswith("flower_week_"):
            suffix = key.removeprefix("flower_week_")
            try:
                week = int(suffix)
            except ValueError:
                mapped = "bluete-stretch"
            else:
                if week <= 4:
                    mapped = "bluete-stretch"
                elif week <= 8:
                    mapped = "bluete-bulk"
                else:
                    mapped = "bluete-ende"
        if mapped and mapped != raw:
            conn.execute(
                sa.text(
                    "UPDATE zone_contexts SET growth_phase = :phase WHERE id = :id"
                ),
                {"phase": mapped, "id": row_id},
            )


def downgrade() -> None:
    op.drop_index("idx_lifecycle_subzone_id", table_name="plant_lifecycle_events")
    op.drop_index("idx_lifecycle_zone_id", table_name="plant_lifecycle_events")
    op.drop_constraint(
        "fk_lifecycle_events_subzone_id",
        "plant_lifecycle_events",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_lifecycle_events_zone_id",
        "plant_lifecycle_events",
        type_="foreignkey",
    )
    op.drop_column("plant_lifecycle_events", "subzone_id")
    op.drop_column("plant_lifecycle_events", "zone_id")
