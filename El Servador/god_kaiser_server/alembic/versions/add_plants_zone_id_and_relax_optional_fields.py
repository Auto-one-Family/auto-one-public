"""Add plants.zone_id + relax genotype/planting_date; phase default (AUT-1073)

Revision ID: add_plants_zone_id_aut1073
Revises: add_esp_device_tank_id_aut1223
Create Date: 2026-07-22

AUT-1073 [EV-14] — Plants may belong directly to a zone without an
Ortseinheit (subzone). Adds ``plants.zone_id`` as a first-class,
nullable FK to ``zones.zone_id`` (pattern: ``esp_devices.zone_id``).

Effective zone at read time is
``COALESCE(subzone_configs.parent_zone_id, plants.zone_id)`` — the
Ortseinheit parent wins when present; ``plants.zone_id`` is the fallback.
This column is intentionally NOT a denormalised copy of the Ortseinheit
parent zone.

Also:
- ``genotype_label`` / ``planting_date``: DROP NOT NULL
- ``phase``: keep NOT NULL, set server_default ``'clone'`` (not the first
  PLANT_PHASES tuple element). CHECK ``ck_plants_phase`` unchanged.

NO BACKFILL of ``zone_id`` from Ortseinheit parents — that would turn the
column into the denormalisation this issue explicitly rejects.

Downgrade: schema-reversible, but NOT loss-free — direct zone assignments
are dropped with the column, and re-tightening NOT NULL on genotype/planting
fails once NULL rows exist.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision: str = "add_plants_zone_id_aut1073"
down_revision: Union[str, None] = "add_esp_device_tank_id_aut1223"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("plants")}

    if "zone_id" not in columns:
        op.add_column(
            "plants",
            sa.Column(
                "zone_id",
                sa.String(length=50),
                sa.ForeignKey("zones.zone_id", ondelete="SET NULL"),
                nullable=True,
                comment=(
                    "AUT-1073: Direct zone assignment (fallback; not a "
                    "denormalised Ortseinheit parent copy)"
                ),
            ),
        )

    existing_indexes = {ix["name"] for ix in inspector.get_indexes("plants")}
    if "idx_plants_zone_id" not in existing_indexes:
        op.create_index(
            "idx_plants_zone_id",
            "plants",
            ["zone_id"],
            unique=False,
        )

    # Relax optional capture fields (AUT-1073)
    op.alter_column(
        "plants",
        "genotype_label",
        existing_type=sa.String(length=128),
        nullable=True,
    )
    op.alter_column(
        "plants",
        "planting_date",
        existing_type=sa.Date(),
        nullable=True,
    )

    # phase stays NOT NULL; server_default = 'clone' (chosen from PLANT_PHASES,
    # explicitly not the first tuple element invitro_donor).
    op.alter_column(
        "plants",
        "phase",
        existing_type=sa.String(length=32),
        nullable=False,
        server_default="clone",
    )


def downgrade() -> None:
    """Schema rollback only — not data-loss-free (see module docstring)."""
    bind = op.get_bind()
    inspector = inspect(bind)

    op.alter_column(
        "plants",
        "phase",
        existing_type=sa.String(length=32),
        nullable=False,
        server_default=None,
    )

    # Re-tightening NOT NULL will fail if any NULL rows exist after upgrade.
    op.alter_column(
        "plants",
        "planting_date",
        existing_type=sa.Date(),
        nullable=False,
    )
    op.alter_column(
        "plants",
        "genotype_label",
        existing_type=sa.String(length=128),
        nullable=False,
    )

    existing_indexes = {ix["name"] for ix in inspector.get_indexes("plants")}
    if "idx_plants_zone_id" in existing_indexes:
        op.drop_index("idx_plants_zone_id", table_name="plants")

    columns = {col["name"] for col in inspector.get_columns("plants")}
    if "zone_id" in columns:
        op.drop_column("plants", "zone_id")
