"""Add nutrient_phase column and nutrient_phase_changed event type (AUT-1183)

Introduces a second, independent phase axis on the plants table for the
nutrient/fertilizer schedule.  A Cannabis grower deliberately runs the light
cycle and the nutrient programme out of phase — e.g. 12/12 light (=Blüte)
while still on a transition-formula Nährlösung.  A single ``phase`` column
cannot represent both states simultaneously.

Changes
-------
1. ``plants.nutrient_phase`` — VARCHAR(32) NULLABLE, CHECK against the same
   16-value list as the existing ``phase`` column (PLANT_PHASES).  Existing
   rows default to NULL (light-axis-only plants are unaffected).
2. ``idx_plants_nutrient_phase`` — B-tree index for filter queries.
3. ``ck_lifecycle_event_type`` (plants_lifecycle_events) — drop and recreate
   with the new value ``'nutrient_phase_changed'`` inserted after
   ``'phase_changed'`` in the enumeration.

No existing data is modified; this migration is purely additive.

Revision ID: add_nutrient_phase_to_plants
Revises: merge_aut1155_aut1156
Create Date: 2026-07-19

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op


# revision identifiers
revision: str = "add_nutrient_phase_to_plants"
down_revision: Union[str, None] = "merge_aut1155_aut1156"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# Shared constants — kept local so the migration is self-contained and does
# not import from application code (migration portability principle).
# ---------------------------------------------------------------------------

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

# Nutrient axis reuses the identical value list — same phases, independent column.
NUTRIENT_PHASES = PLANT_PHASES

# Original event types (before this migration — used for downgrade).
_LIFECYCLE_EVENT_TYPES_OLD = (
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

# New event types (after this migration).
_LIFECYCLE_EVENT_TYPES_NEW = (
    "clone_taken",
    "roots_established",
    "transplanted",
    "phase_changed",
    "nutrient_phase_changed",  # AUT-1183: nutrient/fertilizer axis transition
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


def _event_type_check_sql(event_types: tuple[str, ...]) -> str:
    return f"event_type IN ({', '.join(repr(e) for e in event_types)})"


def _nutrient_phase_check_sql(phases: tuple[str, ...]) -> str:
    return (
        f"nutrient_phase IS NULL OR nutrient_phase IN ({', '.join(repr(p) for p in phases)})"
    )


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Add nutrient_phase column to plants (nullable, CHECK constrained)
    # ------------------------------------------------------------------
    op.add_column(
        "plants",
        sa.Column(
            "nutrient_phase",
            sa.String(length=32),
            nullable=True,
            comment="Nutrient/fertilizer phase axis (AUT-1183). NULL = not set.",
        ),
    )
    op.create_check_constraint(
        "ck_plants_nutrient_phase",
        "plants",
        _nutrient_phase_check_sql(NUTRIENT_PHASES),
    )

    # ------------------------------------------------------------------
    # 2. Index for nutrient_phase filter queries
    # ------------------------------------------------------------------
    op.create_index("idx_plants_nutrient_phase", "plants", ["nutrient_phase"])

    # ------------------------------------------------------------------
    # 3. Extend the CHECK constraint on plant_lifecycle_events to accept
    #    the new 'nutrient_phase_changed' event type.
    #    PostgreSQL does not support ALTER CONSTRAINT — drop and recreate.
    # ------------------------------------------------------------------
    op.drop_constraint(
        "ck_lifecycle_event_type",
        "plant_lifecycle_events",
        type_="check",
    )
    op.create_check_constraint(
        "ck_lifecycle_event_type",
        "plant_lifecycle_events",
        _event_type_check_sql(_LIFECYCLE_EVENT_TYPES_NEW),
    )


def downgrade() -> None:
    # Restore original event-type constraint (without nutrient_phase_changed).
    # NOTE: rows with event_type='nutrient_phase_changed' will violate the
    # restored constraint — ensure no such rows exist before downgrading.
    op.drop_constraint(
        "ck_lifecycle_event_type",
        "plant_lifecycle_events",
        type_="check",
    )
    op.create_check_constraint(
        "ck_lifecycle_event_type",
        "plant_lifecycle_events",
        _event_type_check_sql(_LIFECYCLE_EVENT_TYPES_OLD),
    )

    op.drop_index("idx_plants_nutrient_phase", table_name="plants")
    op.drop_constraint("ck_plants_nutrient_phase", "plants", type_="check")
    op.drop_column("plants", "nutrient_phase")
