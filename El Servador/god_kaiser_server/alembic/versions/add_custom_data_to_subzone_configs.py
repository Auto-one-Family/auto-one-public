"""Add custom_data JSONB to subzone_configs

Revision ID: add_subzone_custom_data
Revises: add_zone_context, add_email_log
Create Date: 2026-03-03 23:00:00.000000

Phase 3: Subzone-Metadaten.
Adds custom_data JSONB column to subzone_configs for subzone-specific
metadata (plant info, material, notes — more specific than zone-level context).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "add_subzone_custom_data"
down_revision: Union[str, None] = ("add_zone_context", "add_email_log")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "subzone_configs",
        sa.Column(
            "custom_data",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("subzone_configs", "custom_data")
