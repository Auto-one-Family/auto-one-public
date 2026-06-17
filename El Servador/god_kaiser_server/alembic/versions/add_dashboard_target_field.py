"""Add target field to dashboards table

Revision ID: add_dashboard_target
Revises: add_dashboards
Create Date: 2026-03-01 22:00:00.000000

Adds nullable JSON 'target' column to dashboards table for display
target configuration (view, placement, anchor, panel settings).
Backwards-compatible: existing dashboards without target continue working.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "add_dashboard_target"
down_revision: Union[str, None] = "add_dashboards"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "dashboards",
        sa.Column(
            "target",
            sa.JSON,
            nullable=True,
            comment="Display target config: { view, placement, anchor, panelPosition, panelWidth, order }",
        ),
    )


def downgrade() -> None:
    op.drop_column("dashboards", "target")
