"""Add zone_context table

Revision ID: add_zone_context
Revises: make_checks_nullable
Create Date: 2026-03-03 22:00:00.000000

Phase K3: Zone-Context Data Model.
Stores per-zone business context (plants, variety, substrate, growth phase,
cycle history) for AI-ready export and zone management.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "add_zone_context"
down_revision: Union[str, None] = "make_checks_nullable"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "zone_contexts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("zone_id", sa.String(50), nullable=False),
        sa.Column("zone_name", sa.String(100), nullable=True),
        sa.Column("plant_count", sa.Integer(), nullable=True),
        sa.Column("variety", sa.String(200), nullable=True),
        sa.Column("substrate", sa.String(200), nullable=True),
        sa.Column("growth_phase", sa.String(50), nullable=True),
        sa.Column("planted_date", sa.Date(), nullable=True),
        sa.Column("expected_harvest", sa.Date(), nullable=True),
        sa.Column("responsible_person", sa.String(100), nullable=True),
        sa.Column("work_hours_weekly", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "custom_data",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "cycle_history",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_zone_contexts_zone_id", "zone_contexts", ["zone_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_zone_contexts_zone_id", table_name="zone_contexts")
    op.drop_table("zone_contexts")
