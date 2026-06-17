"""Add request_id to audit_log

Revision ID: 24e8638e14a5
Revises: 245078bda463
Create Date: 2026-01-27 18:08:21.581508

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '24e8638e14a5'
down_revision: Union[str, None] = '245078bda463'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('audit_logs', sa.Column('request_id', sa.String(36), nullable=True))
    op.create_index('ix_audit_logs_request_id', 'audit_logs', ['request_id'])


def downgrade() -> None:
    op.drop_index('ix_audit_logs_request_id', table_name='audit_logs')
    op.drop_column('audit_logs', 'request_id')
