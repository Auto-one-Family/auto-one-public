"""Add token_version column to user_accounts table.

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f6
Create Date: 2025-12-11

This migration adds the token_version column which is used for
invalidating all user tokens on logout-all-devices.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "add_token_version_to_user"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add token_version column to user_accounts table."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "user_accounts" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("user_accounts")}
    if "token_version" not in existing_columns:
        op.add_column(
            "user_accounts",
            sa.Column(
                "token_version",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )


def downgrade() -> None:
    """Remove token_version column from user_accounts table."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "user_accounts" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("user_accounts")}
    if "token_version" in existing_columns:
        op.drop_column("user_accounts", "token_version")
