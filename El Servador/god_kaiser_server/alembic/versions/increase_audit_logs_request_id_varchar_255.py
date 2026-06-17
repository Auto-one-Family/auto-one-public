"""Increase audit_logs request_id to VARCHAR(255)

MQTT-generated request IDs like 'unknown:heartbeat:no-seq:{timestamp}'
exceed the previous VARCHAR(36) limit (UUID length), causing
StringDataRightTruncation errors that roll back the entire transaction
including device registration.

Revision ID: b2c3d4e5f6a7
Revises: 950ad9ce87bb
Create Date: 2026-02-25 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "950ad9ce87bb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PostgreSQL 9.2+: VARCHAR increase is metadata-only, no table rewrite
    op.alter_column(
        "audit_logs",
        "request_id",
        existing_type=sa.VARCHAR(36),
        type_=sa.VARCHAR(255),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "audit_logs",
        "request_id",
        existing_type=sa.VARCHAR(255),
        type_=sa.VARCHAR(36),
        existing_nullable=True,
    )
