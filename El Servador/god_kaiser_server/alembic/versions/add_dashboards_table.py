"""Add dashboards table

Revision ID: add_dashboards
Revises: b2c3d4e5f6a7
Create Date: 2026-03-01 20:00:00.000000

Dashboard Layout Persistence.

Creates dashboards table for storing custom dashboard layouts
with widget configurations, ownership, and sharing support.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = "add_dashboards"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dashboards",
        # Primary Key
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            comment="Primary key (UUID)",
        ),
        # Identity
        sa.Column(
            "name",
            sa.String(200),
            nullable=False,
            comment="Dashboard display name",
        ),
        sa.Column(
            "description",
            sa.Text,
            nullable=True,
            comment="Optional dashboard description",
        ),
        # Ownership
        sa.Column(
            "owner_id",
            sa.Integer,
            sa.ForeignKey("user_accounts.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
            comment="Foreign key to user who created the dashboard",
        ),
        sa.Column(
            "is_shared",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
            comment="Whether dashboard is visible to all users",
        ),
        # Widget Configuration (JSONB)
        sa.Column(
            "widgets",
            sa.JSON,
            nullable=False,
            server_default="[]",
            comment="JSON array of widget configurations",
        ),
        # Scope
        sa.Column(
            "scope",
            sa.String(20),
            nullable=True,
            comment="Dashboard scope: zone, cross-zone, or sensor-detail",
        ),
        sa.Column(
            "zone_id",
            sa.String(100),
            nullable=True,
            comment="Associated zone ID (for zone-scoped dashboards)",
        ),
        sa.Column(
            "auto_generated",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
            comment="Whether dashboard was auto-generated from zone devices",
        ),
        sa.Column(
            "sensor_id",
            sa.String(100),
            nullable=True,
            comment="Associated sensor ID (for sensor-detail dashboards)",
        ),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="Record creation timestamp (UTC)",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            comment="Record last update timestamp (UTC)",
        ),
    )

    # Indices
    op.create_index("idx_dashboard_shared", "dashboards", ["is_shared"])
    op.create_index("idx_dashboard_scope_zone", "dashboards", ["scope", "zone_id"])


def downgrade() -> None:
    op.drop_index("idx_dashboard_scope_zone", table_name="dashboards")
    op.drop_index("idx_dashboard_shared", table_name="dashboards")
    op.drop_table("dashboards")
