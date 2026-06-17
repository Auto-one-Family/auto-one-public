"""Add token_blacklist table for JWT revocation

Revision ID: a1b2c3d4e5f6
Revises: c6fb9c8567b5
Create Date: 2025-12-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'c6fb9c8567b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create token_blacklist table for JWT token revocation."""
    op.create_table(
        'token_blacklist',
        # Primary Key
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        # Token Identification
        sa.Column('token_hash', sa.String(64), nullable=False),
        sa.Column('token_type', sa.String(20), nullable=False),
        # User Reference
        sa.Column('user_id', sa.Integer(), nullable=False),
        # Timestamps
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('blacklisted_at', sa.DateTime(timezone=True), nullable=False),
        # Metadata
        sa.Column('reason', sa.String(50), nullable=True),
        # TimestampMixin columns
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        # Constraints
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token_hash'),
    )

    # Create indices for efficient lookups
    op.create_index(
        'ix_token_blacklist_token_hash',
        'token_blacklist',
        ['token_hash'],
        unique=True
    )
    op.create_index(
        'ix_token_blacklist_user_id',
        'token_blacklist',
        ['user_id'],
        unique=False
    )
    op.create_index(
        'ix_token_blacklist_expires_at',
        'token_blacklist',
        ['expires_at'],
        unique=False
    )
    # Composite index for cleanup queries
    op.create_index(
        'idx_blacklist_expires_at_user',
        'token_blacklist',
        ['expires_at', 'user_id'],
        unique=False
    )


def downgrade() -> None:
    """Drop token_blacklist table."""
    op.drop_index('idx_blacklist_expires_at_user', table_name='token_blacklist')
    op.drop_index('ix_token_blacklist_expires_at', table_name='token_blacklist')
    op.drop_index('ix_token_blacklist_user_id', table_name='token_blacklist')
    op.drop_index('ix_token_blacklist_token_hash', table_name='token_blacklist')
    op.drop_table('token_blacklist')
