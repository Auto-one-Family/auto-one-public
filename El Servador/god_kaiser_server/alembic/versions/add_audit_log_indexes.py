"""Add audit log performance indexes

Revision ID: add_audit_log_indexes
Revises: add_token_version_to_user
Create Date: 2024-12-18 10:00:00.000000

Adds performance indexes for audit_logs table:
- ix_audit_logs_created_at: Time-range queries and retention cleanup
- ix_audit_logs_severity_created_at: Severity-based time queries
- ix_audit_logs_source_created_at: Source-based time queries
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_audit_log_indexes'
down_revision = 'add_token_version_to_user'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create indexes for audit_logs table
    # These improve performance for:
    # - Time-range queries (dashboard, reporting)
    # - Retention cleanup operations
    # - Severity-based filtering
    # - Source-based lookups
    
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if 'audit_logs' not in inspector.get_table_names():
        return

    existing_indexes = {idx["name"] for idx in inspector.get_indexes('audit_logs')}

    if 'ix_audit_logs_created_at' not in existing_indexes:
        op.create_index(
            'ix_audit_logs_created_at',
            'audit_logs',
            ['created_at'],
            unique=False,
        )
    
    if 'ix_audit_logs_severity_created_at' not in existing_indexes:
        op.create_index(
            'ix_audit_logs_severity_created_at',
            'audit_logs',
            ['severity', 'created_at'],
            unique=False,
        )
    
    if 'ix_audit_logs_source_created_at' not in existing_indexes:
        op.create_index(
            'ix_audit_logs_source_created_at',
            'audit_logs',
            ['source_type', 'source_id', 'created_at'],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if 'audit_logs' not in inspector.get_table_names():
        return

    existing_indexes = {idx["name"] for idx in inspector.get_indexes('audit_logs')}
    if 'ix_audit_logs_source_created_at' in existing_indexes:
        op.drop_index('ix_audit_logs_source_created_at', table_name='audit_logs')
    if 'ix_audit_logs_severity_created_at' in existing_indexes:
        op.drop_index('ix_audit_logs_severity_created_at', table_name='audit_logs')
    if 'ix_audit_logs_created_at' in existing_indexes:
        op.drop_index('ix_audit_logs_created_at', table_name='audit_logs')


















