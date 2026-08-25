"""Add plants, plants_cannabis_extension, plant_lifecycle_events (AUT-222)

Adds three new tables for the Phyta Plants integration plus a nullable
``plant_id`` column on ``sensor_data`` for MultispeQ snapshot association.

OQ-2 decision: ``kaiser_id`` is modelled as a nullable ``VARCHAR(50)``
without an FK constraint (consistent with ``esp_devices.kaiser_id``). No
new tenant concept is introduced; a future migration can promote this to
a formal tenant FK.

Changes:
1. Create ``plants`` table (soft-delete + partial unique indexes).
2. Create ``plants_cannabis_extension`` table (1:1 with plants).
3. Create ``plant_lifecycle_events`` table (append-only event log).
4. Add ``sensor_data.plant_id`` (FK, nullable, indexed).

Revision ID: add_plants_entity_lifecycle_events
Revises: add_multispeq_sensor_kind_virtual_status
Create Date: 2026-04-30

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op


# revision identifiers
revision: str = "add_plants_entity_lifecycle_events"
down_revision: Union[str, None] = "add_multispeq_sensor_kind_virtual_status"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PLANT_PHASES = (
    "invitro_donor",
    "invitro_initiation",
    "invitro_multiplication",
    "invitro_rooting",
    "invitro_acclimatization",
    "clone",
    "veg-frueh",
    "veg-spaet",
    "bluete-stretch",
    "bluete-bulk",
    "bluete-ende",
    "mutter",
    "steckling_wurzelung",
    "steckling_vor_versand",
    "harvested",
    "archived",
)

PLANT_VISIBILITY = ("tenant_private", "open_aggregate", "open_full")

LIFECYCLE_EVENT_TYPES = (
    "clone_taken",
    "roots_established",
    "transplanted",
    "phase_changed",
    "defoliation",
    "topping",
    "training",
    "pest_detected",
    "treatment_applied",
    "emergency_triage",
    "harvest_started",
    "harvest_completed",
    "drying_started",
    "drying_completed",
    "sample_taken",
    "archived",
    "note_added",
    "subzone_moved",
)

_PHASE_CHECK = f"phase IN ({', '.join(repr(p) for p in PLANT_PHASES)})"
_VISIBILITY_CHECK = f"visibility IN ({', '.join(repr(v) for v in PLANT_VISIBILITY)})"
_EVENT_TYPE_CHECK = f"event_type IN ({', '.join(repr(e) for e in LIFECYCLE_EVENT_TYPES)})"


def upgrade() -> None:
    # ---------------------------------------------------------------------
    # 1. plants
    # ---------------------------------------------------------------------
    op.create_table(
        "plants",
        sa.Column("plant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kaiser_id", sa.String(length=50), nullable=True),
        sa.Column("subzone_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("qr_code", sa.String(length=64), nullable=False),
        sa.Column("external_plant_id", sa.String(length=128), nullable=True),
        sa.Column("external_track_trace_id", sa.String(length=128), nullable=True),
        sa.Column("genotype_label", sa.String(length=128), nullable=False),
        sa.Column("cultivar_or_variety", sa.String(length=128), nullable=True),
        sa.Column("lineage_parent_plant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("batch_label", sa.String(length=64), nullable=True),
        sa.Column("planting_date", sa.Date(), nullable=False),
        sa.Column("phase", sa.String(length=32), nullable=False),
        sa.Column("current_position_label", sa.String(length=128), nullable=True),
        sa.Column(
            "visibility",
            sa.String(length=24),
            nullable=False,
            server_default="tenant_private",
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("rooting_success", sa.Boolean(), nullable=True),
        sa.Column("rooting_date", sa.Date(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.Integer(), nullable=True),
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
        sa.PrimaryKeyConstraint("plant_id"),
        sa.ForeignKeyConstraint(
            ["subzone_id"],
            ["subzone_configs.id"],
            ondelete="SET NULL",
            name="fk_plants_subzone_id_subzone_configs",
        ),
        sa.ForeignKeyConstraint(
            ["lineage_parent_plant_id"],
            ["plants.plant_id"],
            ondelete="SET NULL",
            name="fk_plants_lineage_parent_plant_id_plants",
        ),
        sa.ForeignKeyConstraint(
            ["deleted_by"],
            ["user_accounts.id"],
            ondelete="SET NULL",
            name="fk_plants_deleted_by_user_accounts",
        ),
        sa.CheckConstraint(_PHASE_CHECK, name="ck_plants_phase"),
        sa.CheckConstraint(_VISIBILITY_CHECK, name="ck_plants_visibility"),
    )

    op.create_index("idx_plants_kaiser_id", "plants", ["kaiser_id"])
    op.create_index("idx_plants_phase", "plants", ["phase"])
    op.create_index("idx_plants_deleted_at", "plants", ["deleted_at"])
    op.create_index("idx_plants_subzone_id", "plants", ["subzone_id"])

    # Partial UNIQUE indexes (active rows only) — declarative UniqueConstraint
    # cannot express ``WHERE deleted_at IS NULL``.
    op.create_index(
        "uq_plants_qr_code_kaiser",
        "plants",
        ["kaiser_id", "qr_code"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "uq_plants_external_plant_id_kaiser",
        "plants",
        ["kaiser_id", "external_plant_id"],
        unique=True,
        postgresql_where=sa.text(
            "deleted_at IS NULL AND external_plant_id IS NOT NULL"
        ),
    )

    # ---------------------------------------------------------------------
    # 2. plants_cannabis_extension
    # ---------------------------------------------------------------------
    op.create_table(
        "plants_cannabis_extension",
        sa.Column("extension_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kaiser_id", sa.String(length=50), nullable=True),
        sa.Column("harvest_date", sa.Date(), nullable=True),
        sa.Column("drying_end_date", sa.Date(), nullable=True),
        sa.Column("dry_weight_g", sa.Numeric(10, 2), nullable=True),
        sa.Column("harvested_weight_g", sa.Numeric(10, 2), nullable=True),
        sa.Column("thc_content_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column("cbd_content_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column("lab_analysis_ref", sa.String(length=256), nullable=True),
        sa.Column("lab_analysis_date", sa.Date(), nullable=True),
        sa.Column("disposal_reason", sa.String(length=512), nullable=True),
        sa.Column("disposal_date", sa.Date(), nullable=True),
        sa.Column("pflanzenpass_nr", sa.String(length=128), nullable=True),
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
        sa.PrimaryKeyConstraint("extension_id"),
        sa.ForeignKeyConstraint(
            ["plant_id"],
            ["plants.plant_id"],
            ondelete="RESTRICT",
            name="fk_cannabis_extension_plant_id_plants",
        ),
        sa.UniqueConstraint("plant_id", name="uq_cannabis_extension_plant_id"),
    )

    # ---------------------------------------------------------------------
    # 3. plant_lifecycle_events
    # ---------------------------------------------------------------------
    op.create_table(
        "plant_lifecycle_events",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kaiser_id", sa.String(length=50), nullable=True),
        sa.Column("event_type", sa.String(length=48), nullable=False),
        sa.Column(
            "event_timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("previous_phase", sa.String(length=32), nullable=True),
        sa.Column("new_phase", sa.String(length=32), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("linked_sensor_window_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("linked_sensor_window_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("track_trace_export_status", sa.String(length=24), nullable=True),
        sa.Column("created_by_user", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("event_id"),
        sa.ForeignKeyConstraint(
            ["plant_id"],
            ["plants.plant_id"],
            ondelete="RESTRICT",
            name="fk_lifecycle_events_plant_id_plants",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user"],
            ["user_accounts.id"],
            ondelete="RESTRICT",
            name="fk_lifecycle_events_created_by_user_user_accounts",
        ),
        sa.CheckConstraint(_EVENT_TYPE_CHECK, name="ck_lifecycle_event_type"),
    )

    op.create_index(
        "idx_lifecycle_plant_id",
        "plant_lifecycle_events",
        ["plant_id"],
    )
    op.create_index(
        "idx_lifecycle_event_timestamp",
        "plant_lifecycle_events",
        ["event_timestamp"],
    )

    # ---------------------------------------------------------------------
    # 4. sensor_data.plant_id (MultispeQ snapshot association)
    # ---------------------------------------------------------------------
    op.add_column(
        "sensor_data",
        sa.Column(
            "plant_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_sensor_data_plant_id_plants",
        "sensor_data",
        "plants",
        ["plant_id"],
        ["plant_id"],
        ondelete="SET NULL",
    )
    op.create_index("idx_sensor_data_plant_id", "sensor_data", ["plant_id"])


def downgrade() -> None:
    op.drop_index("idx_sensor_data_plant_id", table_name="sensor_data")
    op.drop_constraint(
        "fk_sensor_data_plant_id_plants",
        "sensor_data",
        type_="foreignkey",
    )
    op.drop_column("sensor_data", "plant_id")

    op.drop_index("idx_lifecycle_event_timestamp", table_name="plant_lifecycle_events")
    op.drop_index("idx_lifecycle_plant_id", table_name="plant_lifecycle_events")
    op.drop_table("plant_lifecycle_events")

    op.drop_table("plants_cannabis_extension")

    op.drop_index("uq_plants_external_plant_id_kaiser", table_name="plants")
    op.drop_index("uq_plants_qr_code_kaiser", table_name="plants")
    op.drop_index("idx_plants_subzone_id", table_name="plants")
    op.drop_index("idx_plants_deleted_at", table_name="plants")
    op.drop_index("idx_plants_phase", table_name="plants")
    op.drop_index("idx_plants_kaiser_id", table_name="plants")
    op.drop_table("plants")
