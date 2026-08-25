"""Add plan_segments, junction, applied_setpoint_logs + CrossESPLogic plan abo

Revision ID: add_plan_segments_aut1232
Revises: add_nutrient_solution_batches
Create Date: 2026-07-22

AUT-1232 (Welle 5 T2) — additive interval-setpoint data model:
- plan_segments (+ optional plan_segment_subzone_assignments)
- applied_setpoint_logs with origin (plan_segment | static_fallback)
- CrossESPLogic follows_plan (default false) + plan_* reference columns

Purely additive: no DROP, no data migration, no rewrite of existing rule
setpoints. Existing rules remain non-subscribing (follows_plan=false).
Do NOT apply against production DB without explicit operator go-ahead.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision: str = "add_plan_segments_aut1232"
down_revision: Union[str, None] = "add_nutrient_solution_batches"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DOMAIN_CHECK = "domain IN ('nutrient_solution', 'climate')"
_MEASURE_CHECK = (
    "measure IN ('target_ec', 'target_ph', 'target_temperature', "
    "'target_humidity', 'target_co2', 'light_regime', 'recipe_ref')"
)
_INTERP_CHECK = "interp IN ('step', 'linear')"
_STATUS_CHECK = "status IN ('planned', 'active', 'occurred', 'withdrawn')"
_ORIGIN_CHECK = "origin IN ('plan_segment', 'static_fallback')"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "plan_segments" not in existing_tables:
        op.create_table(
            "plan_segments",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                nullable=False,
                comment="Primary key (UUID)",
            ),
            sa.Column(
                "zone_id",
                sa.String(length=50),
                sa.ForeignKey("zones.zone_id", ondelete="RESTRICT"),
                nullable=False,
                comment="Zone identifier (FK to zones.zone_id)",
            ),
            sa.Column(
                "domain",
                sa.String(length=32),
                nullable=False,
                comment="Functional domain (PLAN_DOMAINS)",
            ),
            sa.Column(
                "measure",
                sa.String(length=32),
                nullable=False,
                comment="Setpoint measure (PLAN_MEASURES)",
            ),
            sa.Column(
                "value",
                sa.Float(),
                nullable=True,
                comment="Planned numeric setpoint",
            ),
            sa.Column(
                "recipe_ref",
                sa.String(length=100),
                nullable=True,
                comment="Reserved recipe-profile reference (unwired in v1)",
            ),
            sa.Column(
                "from_ts",
                sa.DateTime(timezone=True),
                nullable=False,
                comment="Interval start inclusive UTC",
            ),
            sa.Column(
                "to_ts",
                sa.DateTime(timezone=True),
                nullable=True,
                comment="Interval end exclusive UTC; NULL = open-ended",
            ),
            sa.Column(
                "interp",
                sa.String(length=16),
                nullable=False,
                server_default="step",
                comment="Transition: step | linear",
            ),
            sa.Column(
                "phase_ref",
                sa.String(length=64),
                nullable=True,
                comment="Optional phase label",
            ),
            sa.Column(
                "status",
                sa.String(length=20),
                nullable=False,
                server_default="planned",
                comment="Segment truth status",
            ),
            sa.Column(
                "tolerance",
                sa.Float(),
                nullable=True,
                comment="Optional ± tolerance (unevaluated in v1)",
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
            sa.CheckConstraint(_DOMAIN_CHECK, name="ck_plan_segments_domain"),
            sa.CheckConstraint(_MEASURE_CHECK, name="ck_plan_segments_measure"),
            sa.CheckConstraint(_INTERP_CHECK, name="ck_plan_segments_interp"),
            sa.CheckConstraint(_STATUS_CHECK, name="ck_plan_segments_status"),
        )
        op.create_index("ix_plan_segments_zone_id", "plan_segments", ["zone_id"])
        op.create_index(
            "idx_plan_segments_zone_domain_measure_from",
            "plan_segments",
            ["zone_id", "domain", "measure", "from_ts"],
        )

    existing_tables = set(inspect(bind).get_table_names())
    if "plan_segment_subzone_assignments" not in existing_tables:
        op.create_table(
            "plan_segment_subzone_assignments",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                nullable=False,
            ),
            sa.Column(
                "plan_segment_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("plan_segments.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "subzone_config_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("subzone_configs.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "assigned_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.UniqueConstraint(
                "plan_segment_id",
                "subzone_config_id",
                name="uq_plan_segment_subzone_assignment",
            ),
        )
        op.create_index(
            "idx_plan_segment_subzone_segment_id",
            "plan_segment_subzone_assignments",
            ["plan_segment_id"],
        )
        op.create_index(
            "idx_plan_segment_subzone_config_id",
            "plan_segment_subzone_assignments",
            ["subzone_config_id"],
        )

    existing_tables = set(inspect(bind).get_table_names())
    if "applied_setpoint_logs" not in existing_tables:
        op.create_table(
            "applied_setpoint_logs",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                nullable=False,
            ),
            sa.Column(
                "zone_id",
                sa.String(length=50),
                sa.ForeignKey("zones.zone_id", ondelete="RESTRICT"),
                nullable=False,
            ),
            sa.Column(
                "subzone_config_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("subzone_configs.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("domain", sa.String(length=32), nullable=False),
            sa.Column("measure", sa.String(length=32), nullable=False),
            sa.Column("applied_value", sa.Float(), nullable=False),
            sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column(
                "rule_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("cross_esp_logic.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "segment_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("plan_segments.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("origin", sa.String(length=32), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.CheckConstraint(_ORIGIN_CHECK, name="ck_applied_setpoint_logs_origin"),
            sa.CheckConstraint(_DOMAIN_CHECK, name="ck_applied_setpoint_logs_domain"),
            sa.CheckConstraint(_MEASURE_CHECK, name="ck_applied_setpoint_logs_measure"),
        )
        op.create_index(
            "ix_applied_setpoint_logs_zone_id",
            "applied_setpoint_logs",
            ["zone_id"],
        )
        op.create_index(
            "idx_applied_setpoint_logs_zone_domain_measure_at",
            "applied_setpoint_logs",
            ["zone_id", "domain", "measure", "effective_at"],
        )

    # CrossESPLogic plan subscription — additive, default false for all rows
    columns = {col["name"] for col in inspect(bind).get_columns("cross_esp_logic")}
    if "follows_plan" not in columns:
        op.add_column(
            "cross_esp_logic",
            sa.Column(
                "follows_plan",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
                comment="AUT-1232: Opt-in plan subscription (default false)",
            ),
        )
    if "plan_zone_id" not in columns:
        op.add_column(
            "cross_esp_logic",
            sa.Column(
                "plan_zone_id",
                sa.String(length=50),
                sa.ForeignKey("zones.zone_id", ondelete="SET NULL"),
                nullable=True,
                comment="AUT-1232: Plan subscription zone",
            ),
        )
    if "plan_subzone_config_id" not in columns:
        op.add_column(
            "cross_esp_logic",
            sa.Column(
                "plan_subzone_config_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("subzone_configs.id", ondelete="SET NULL"),
                nullable=True,
                comment="AUT-1232: Optional plan subscription subzone",
            ),
        )
    if "plan_domain" not in columns:
        op.add_column(
            "cross_esp_logic",
            sa.Column(
                "plan_domain",
                sa.String(length=32),
                nullable=True,
                comment="AUT-1232: Plan subscription domain",
            ),
        )
    if "plan_measure" not in columns:
        op.add_column(
            "cross_esp_logic",
            sa.Column(
                "plan_measure",
                sa.String(length=32),
                nullable=True,
                comment="AUT-1232: Plan subscription measure",
            ),
        )

    # Drop server_default on follows_plan after backfill so ORM default remains source of truth
    # (server_default already set false for existing rows).
    op.alter_column(
        "cross_esp_logic",
        "follows_plan",
        server_default=None,
        existing_type=sa.Boolean(),
        existing_nullable=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("cross_esp_logic")}
    for col in (
        "plan_measure",
        "plan_domain",
        "plan_subzone_config_id",
        "plan_zone_id",
        "follows_plan",
    ):
        if col in columns:
            op.drop_column("cross_esp_logic", col)

    existing_tables = set(inspect(bind).get_table_names())
    if "applied_setpoint_logs" in existing_tables:
        op.drop_table("applied_setpoint_logs")
    if "plan_segment_subzone_assignments" in existing_tables:
        op.drop_table("plan_segment_subzone_assignments")
    if "plan_segments" in existing_tables:
        op.drop_table("plan_segments")
