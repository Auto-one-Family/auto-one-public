"""Add is_skip to logic_execution_history

AUT-1020 follow-up: get_last_execution() previously returned the
chronologically last row regardless of whether it was a real execution
attempt or a self-generated cooldown/settle/rate-limit skip marker. Since
skip markers are written on every blocked evaluation, the cooldown
reference timestamp kept sliding forward on its own skip entries and the
cooldown window never actually expired (observed live: PH MINUS rule
stuck in a self-extending 150s cooldown, 44 skips/hour).

Adds an explicit is_skip column so get_last_execution() can filter skip
markers out without touching `success` semantics (success=False is also
used for genuine failed execution attempts — conflict-blocked, dose-ml
failure, exception — which must keep surfacing via last_execution_success
in the REST API / frontend).

Revision ID: add_logic_exec_skip_flag
Revises: 5666263e2602
Create Date: 2026-07-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "add_logic_exec_skip_flag"
down_revision: Union[str, None] = "5666263e2602"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "logic_execution_history",
        sa.Column(
            "is_skip",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="True for self-generated cooldown/settle/rate-limit skip markers (AUT-1020)",
        ),
    )


def downgrade() -> None:
    op.drop_column("logic_execution_history", "is_skip")
