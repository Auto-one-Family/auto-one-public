"""Add discovery approval fields to ESP device

Revision ID: add_discovery_approval
Revises: fix_multivalue_constraint
Create Date: 2026-01-17

Adds fields for Discovery/Approval workflow:
- discovered_at: When device was first discovered via heartbeat
- approved_at: When device was approved by admin
- approved_by: Username of admin who approved
- rejection_reason: Reason for rejection (if rejected)
- last_rejection_at: Timestamp for cooldown calculation

New device status values:
- pending_approval: Device discovered but awaiting admin approval
- approved: Admin approved, waiting for first heartbeat to go online
- rejected: Admin rejected, will rediscover after cooldown (5min)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_discovery_approval'
down_revision: Union[str, None] = 'fix_multivalue_constraint'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add discovery/approval audit fields to esp_devices table."""
    
    # discovered_at: When device was first discovered via heartbeat
    op.add_column(
        'esp_devices',
        sa.Column(
            'discovered_at',
            sa.DateTime(),
            nullable=True,
            comment='Timestamp when device was first discovered via heartbeat',
        )
    )
    
    # approved_at: When device was approved by admin
    op.add_column(
        'esp_devices',
        sa.Column(
            'approved_at',
            sa.DateTime(),
            nullable=True,
            comment='Timestamp when device was approved by admin',
        )
    )
    
    # approved_by: Username of admin who approved
    op.add_column(
        'esp_devices',
        sa.Column(
            'approved_by',
            sa.String(100),
            nullable=True,
            comment='Username of admin who approved the device',
        )
    )
    
    # rejection_reason: Reason for rejection (if status=rejected)
    op.add_column(
        'esp_devices',
        sa.Column(
            'rejection_reason',
            sa.String(500),
            nullable=True,
            comment='Reason for rejection (if status=rejected)',
        )
    )
    
    # last_rejection_at: Timestamp for cooldown calculation
    op.add_column(
        'esp_devices',
        sa.Column(
            'last_rejection_at',
            sa.DateTime(),
            nullable=True,
            comment='Timestamp of last rejection (for cooldown calculation)',
        )
    )


def downgrade() -> None:
    """Remove discovery/approval audit fields from esp_devices table."""
    op.drop_column('esp_devices', 'last_rejection_at')
    op.drop_column('esp_devices', 'rejection_reason')
    op.drop_column('esp_devices', 'approved_by')
    op.drop_column('esp_devices', 'approved_at')
    op.drop_column('esp_devices', 'discovered_at')
