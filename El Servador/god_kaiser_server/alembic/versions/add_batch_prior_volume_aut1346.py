"""Add nullable prior_volume_l / prior_ec_ms_cm to nutrient_solution_batches (AUT-1346)

Revision ID: add_batch_prior_volume_aut1346
Revises: add_subzone_position_label_aut1241
Create Date: 2026-07-25

PKG-04 — additive ledger columns for composition reconstruction:

- ``prior_volume_l``: tank volume (L) immediately before this ledger entry
- ``prior_ec_ms_cm``: last known EC before this entry (same numeric convention
  as ``ec_measured_after``; assist layer uses µS/cm for System-EC)

Both nullable. No backfill — existing rows stay NULL and remain valid.
Downgrade drops the columns (reversible).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision: str = "add_batch_prior_volume_aut1346"
down_revision: Union[str, None] = "add_subzone_position_label_aut1241"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "nutrient_solution_batches"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if _TABLE not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns(_TABLE)}
    if "prior_volume_l" not in columns:
        op.add_column(
            _TABLE,
            sa.Column(
                "prior_volume_l",
                sa.Float(),
                nullable=True,
                comment="Tank volume (L) before this entry (AUT-1346); NULL = unknown",
            ),
        )
    if "prior_ec_ms_cm" not in columns:
        op.add_column(
            _TABLE,
            sa.Column(
                "prior_ec_ms_cm",
                sa.Float(),
                nullable=True,
                comment="Last known EC before this entry (AUT-1346); NULL = unknown",
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if _TABLE not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns(_TABLE)}
    if "prior_ec_ms_cm" in columns:
        op.drop_column(_TABLE, "prior_ec_ms_cm")
    if "prior_volume_l" in columns:
        op.drop_column(_TABLE, "prior_volume_l")
