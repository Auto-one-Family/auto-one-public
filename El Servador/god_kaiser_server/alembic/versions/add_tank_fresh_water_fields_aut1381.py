"""Add tanks.fresh_water_ec_us_cm and fresh_water_ph (AUT-1381 W3)

Revision ID: add_tank_fresh_water_fields_aut1381
Revises: update_stock_mix_handling_hints_aut1362
Create Date: 2026-07-25

One place for fresh-water quality on the tank — no silent DEFAULT_EC_WASSER.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "add_tank_fresh_water_fields_aut1381"
down_revision: Union[str, None] = "update_stock_mix_handling_hints_aut1362"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tanks",
        sa.Column(
            "fresh_water_ec_us_cm",
            sa.Float(),
            nullable=True,
            comment="Configured fresh-water EC (µS/cm); NULL = not configured",
        ),
    )
    op.add_column(
        "tanks",
        sa.Column(
            "fresh_water_ph",
            sa.Float(),
            nullable=True,
            comment="Configured fresh-water pH; NULL = not configured",
        ),
    )


def downgrade() -> None:
    op.drop_column("tanks", "fresh_water_ph")
    op.drop_column("tanks", "fresh_water_ec_us_cm")
