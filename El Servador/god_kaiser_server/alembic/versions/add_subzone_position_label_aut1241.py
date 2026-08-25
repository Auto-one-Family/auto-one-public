"""Add optional position_label to subzone_configs (AUT-1241)

Revision ID: add_subzone_position_label_aut1241
Revises: add_actuator_subzone_assignments
Create Date: 2026-07-23

AUT-1241 Option B — leichtes Positions-/Layout-Feld:

Adds nullable ``position_label`` (VARCHAR 128) to ``subzone_configs`` for a
coarse operator-facing spatial hint (e.g. "Reihe 2, oberes Regal").

Design decision (Freitext vs. Reihe/Spalte/Ebene-Tripel):
- Single nullable String mirrors ``plants.current_position_label`` and keeps
  the diff minimal (one column, no partial-triple null semantics).
- Not a display-sort / order column; not CAD/XY coordinates (Option A deferred).
- Unrelated to deprecated ``assigned_subzones`` (AUT-227).

Purely additive and reversible: downgrade drops the column.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision: str = "add_subzone_position_label_aut1241"
down_revision: Union[str, None] = "add_actuator_subzone_assignments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("subzone_configs")}
    if "position_label" not in columns:
        op.add_column(
            "subzone_configs",
            sa.Column(
                "position_label",
                sa.String(length=128),
                nullable=True,
                comment="Optional free-text spatial position (AUT-1241)",
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("subzone_configs")}
    if "position_label" in columns:
        op.drop_column("subzone_configs", "position_label")
