"""Add diagnostic_reports table

Revision ID: add_diagnostic_reports
Revises: add_plugin_tables
Create Date: 2026-03-03 18:00:00.000000

Phase 4D.1.1: Diagnostics Hub DB-Persistenz.
Erstellt Tabelle fuer Diagnose-Reports mit Check-Ergebnissen.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "add_diagnostic_reports"
down_revision: Union[str, None] = "add_plugin_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    # Diagnostic reports table (may already exist via create_all)
    if "diagnostic_reports" not in existing_tables:
        op.create_table(
            "diagnostic_reports",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column("overall_status", sa.String(20), nullable=False),
            sa.Column(
                "started_at",
                sa.DateTime(timezone=True),
                nullable=False,
            ),
            sa.Column(
                "finished_at",
                sa.DateTime(timezone=True),
                nullable=False,
            ),
            sa.Column("duration_seconds", sa.Float(), nullable=True),
            sa.Column("checks", postgresql.JSONB(), nullable=False),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column(
                "triggered_by",
                sa.String(50),
                nullable=False,
                server_default="manual",
            ),
            sa.Column(
                "triggered_by_user",
                sa.Integer(),
                sa.ForeignKey("user_accounts.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("exported_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("export_path", sa.Text(), nullable=True),
        )

        # Expression index via raw SQL (sa.text in create_index is unreliable)
        op.execute(
            "CREATE INDEX ix_diagnostic_reports_started "
            "ON diagnostic_reports (started_at DESC)"
        )

        # Check constraint for overall_status
        op.create_check_constraint(
            "ck_diagnostic_reports_status",
            "diagnostic_reports",
            sa.text("overall_status IN ('healthy', 'warning', 'critical', 'error')"),
        )


def downgrade() -> None:
    op.drop_constraint("ck_diagnostic_reports_status", "diagnostic_reports", type_="check")
    op.drop_index("ix_diagnostic_reports_started", table_name="diagnostic_reports")
    op.drop_table("diagnostic_reports")
