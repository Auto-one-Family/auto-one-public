"""Add contract shadow fields to command_outcomes.

AP-03A requires dual-contract metadata fields to allow v1/v2
coexistence during migration windows.

Revision ID: add_contract_shadow_fields_to_command_outcomes
Revises: add_command_intent_outcome_contract
Create Date: 2026-04-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_contract_shadow_fields_to_command_outcomes"
down_revision: Union[str, None] = "add_command_intent_outcome_contract"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "command_outcomes",
        sa.Column(
            "contract_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )
    op.add_column(
        "command_outcomes",
        sa.Column(
            "semantic_mode",
            sa.String(length=16),
            nullable=False,
            server_default="legacy",
        ),
    )
    op.add_column(
        "command_outcomes",
        sa.Column("legacy_status", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "command_outcomes",
        sa.Column("target_status", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "command_outcomes",
        sa.Column(
            "is_final",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    op.execute("UPDATE command_outcomes SET legacy_status = outcome WHERE legacy_status IS NULL")
    op.execute("UPDATE command_outcomes SET target_status = outcome WHERE target_status IS NULL")
    op.execute(
        "UPDATE command_outcomes SET is_final = true "
        "WHERE outcome IN ('persisted', 'rejected', 'failed', 'expired')"
    )

    op.alter_column("command_outcomes", "contract_version", server_default=None)
    op.alter_column("command_outcomes", "semantic_mode", server_default=None)
    op.alter_column("command_outcomes", "is_final", server_default=None)


def downgrade() -> None:
    op.drop_column("command_outcomes", "is_final")
    op.drop_column("command_outcomes", "target_status")
    op.drop_column("command_outcomes", "legacy_status")
    op.drop_column("command_outcomes", "semantic_mode")
    op.drop_column("command_outcomes", "contract_version")
