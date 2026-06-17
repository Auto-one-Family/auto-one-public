"""Add api_keys table for DB-backed API key validation (AUT-290)

Revision ID: add_api_keys_table
Revises: merge_aut120_aut227
Create Date: 2026-05-08

Replaces prefix-only API key validation with a proper DB-backed table.
Keys are stored as SHA256 hashes — plaintext is never persisted.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "add_api_keys_table"
down_revision: Union[str, None] = "merge_aut120_aut227"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create api_keys table for secure API key management."""
    op.create_table(
        "api_keys",
        # Primary Key (UUID v4)
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # Key identification (SHA256 hash, never plaintext)
        sa.Column("key_hash", sa.String(64), nullable=False),
        # Human-readable prefix (e.g. "esp_", "god_")
        sa.Column("key_prefix", sa.String(8), nullable=False),
        # Owner classification
        sa.Column("owner_type", sa.String(16), nullable=False),
        # Optional specific owner reference
        sa.Column("owner_id", sa.String(64), nullable=True),
        # Permission scopes as JSON array
        sa.Column("scopes", sa.JSON(), nullable=False, server_default="[]"),
        # Creator reference
        sa.Column("created_by", sa.Integer(), nullable=True),
        # Usage tracking
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        # Revocation timestamp (None = active)
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        # TimestampMixin columns
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        # Constraints
        sa.PrimaryKeyConstraint("id"),
    )

    # Unique index on key_hash for fast O(1) lookups during auth
    op.create_index(
        "ix_api_keys_key_hash",
        "api_keys",
        ["key_hash"],
        unique=True,
    )

    # Non-unique index on owner_type for administrative queries
    op.create_index(
        "ix_api_keys_owner_type",
        "api_keys",
        ["owner_type"],
        unique=False,
    )


def downgrade() -> None:
    """Drop api_keys table and its indices."""
    op.drop_index("ix_api_keys_owner_type", table_name="api_keys")
    op.drop_index("ix_api_keys_key_hash", table_name="api_keys")
    op.drop_table("api_keys")
