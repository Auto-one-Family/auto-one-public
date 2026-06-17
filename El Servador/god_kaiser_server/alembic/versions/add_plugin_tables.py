"""Add plugin_configs and plugin_executions tables

Revision ID: add_plugin_tables
Revises: add_alert_lifecycle
Create Date: 2026-03-03 14:00:00.000000

Phase 4C.1.1: Plugin-System DB-Persistenz.
Erstellt Tabellen fuer Plugin-Konfiguration und Ausfuehrungshistorie.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "add_plugin_tables"
down_revision: Union[str, None] = "add_alert_lifecycle"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    # Plugin configuration table (may already exist via create_all)
    if "plugin_configs" not in existing_tables:
        op.create_table(
            "plugin_configs",
            sa.Column("plugin_id", sa.String(100), primary_key=True),
            sa.Column("display_name", sa.String(255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("category", sa.String(50), nullable=True),
            sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("config", postgresql.JSONB(), nullable=False, server_default="{}"),
            sa.Column("config_schema", postgresql.JSONB(), nullable=False, server_default="{}"),
            sa.Column("capabilities", postgresql.ARRAY(sa.String()), nullable=True),
            sa.Column("schedule", sa.String(100), nullable=True),
            sa.Column(
                "created_by",
                sa.Integer(),
                sa.ForeignKey("user_accounts.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
        )

    # Plugin execution history table (may already exist via create_all)
    if "plugin_executions" not in existing_tables:
        op.create_table(
            "plugin_executions",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column(
                "plugin_id",
                sa.String(100),
                sa.ForeignKey("plugin_configs.plugin_id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "started_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "status",
                sa.String(20),
                nullable=False,
                server_default="running",
            ),
            sa.Column("triggered_by", sa.String(50), nullable=True),
            sa.Column(
                "triggered_by_user",
                sa.Integer(),
                sa.ForeignKey("user_accounts.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("triggered_by_rule", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("result", postgresql.JSONB(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("duration_seconds", sa.Float(), nullable=True),
        )

    # Indexes (safe: PostgreSQL ignores IF NOT EXISTS semantics via try/except)
    existing_indexes = {
        idx["name"]
        for tbl in existing_tables
        for idx in inspector.get_indexes(tbl)
        if idx.get("name")
    }

    if "ix_plugin_executions_plugin_id" not in existing_indexes:
        op.create_index(
            "ix_plugin_executions_plugin_id",
            "plugin_executions",
            ["plugin_id"],
        )
    if "ix_plugin_executions_started_at" not in existing_indexes:
        op.create_index(
            "ix_plugin_executions_started_at",
            "plugin_executions",
            [sa.text("started_at DESC")],
        )

    # Check constraint for execution status (safe: skip if table existed)
    if "plugin_executions" not in existing_tables:
        op.create_check_constraint(
            "ck_plugin_executions_status",
            "plugin_executions",
            sa.text("status IN ('running', 'success', 'error', 'cancelled')"),
        )


def downgrade() -> None:
    op.drop_constraint("ck_plugin_executions_status", "plugin_executions", type_="check")
    op.drop_index("ix_plugin_executions_started_at", table_name="plugin_executions")
    op.drop_index("ix_plugin_executions_plugin_id", table_name="plugin_executions")
    op.drop_table("plugin_executions")
    op.drop_table("plugin_configs")
