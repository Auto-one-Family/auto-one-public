"""Add event_status (truth status) to plant_lifecycle_events (AUT-1207)

The lifecycle-event log is append-only: there was previously no way to mark
an event as never having happened, planned-but-not-yet-occurred, or a
test/debug artefact. All events were implicitly treated as "occurred". Three
concrete cases in the real dataset needed this: a topping event that was
tested but never carried out, two development debug entries, and this
migration's own downstream live-verify artefacts.

Changes
-------
1. ``plant_lifecycle_events.event_status`` — VARCHAR(24) NOT NULL DEFAULT
   'occurred', CHECK against ('occurred', 'planned', 'reverted',
   'test_data'). Existing rows default to 'occurred' — purely additive,
   matches today's implicit behaviour exactly.
2. ``plant_lifecycle_events.status_reason`` — TEXT NULLABLE. Short
   justification, required at the API layer when transitioning to
   'reverted'.
3. ``plant_lifecycle_events.status_changed_at`` — TIMESTAMPTZ NULLABLE. Set
   when the status is changed via the dedicated status-update endpoint;
   NULL for events whose status was set at creation and never changed
   since.

No existing data is modified; this migration is purely additive.

Revision ID: add_event_status_to_lifecycle_events
Revises: merge_aut1183_variante_c
Create Date: 2026-07-20

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers
revision: str = "add_event_status_to_lifecycle_events"
down_revision: Union[str, None] = "merge_aut1183_variante_c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Kept local so the migration is self-contained and does not import from
# application code (migration portability principle, see
# add_nutrient_phase_to_plants.py).
EVENT_STATUSES = (
    "occurred",
    "planned",
    "reverted",
    "test_data",
)


def _event_status_check_sql(statuses: tuple[str, ...]) -> str:
    return f"event_status IN ({', '.join(repr(s) for s in statuses)})"


def upgrade() -> None:
    op.add_column(
        "plant_lifecycle_events",
        sa.Column(
            "event_status",
            sa.String(length=24),
            nullable=False,
            server_default="occurred",
            comment=(
                "Truth status of this event (AUT-1207): 'occurred' (default, "
                "matches prior implicit behaviour), 'planned', 'reverted', "
                "'test_data'."
            ),
        ),
    )
    op.create_check_constraint(
        "ck_lifecycle_event_status",
        "plant_lifecycle_events",
        _event_status_check_sql(EVENT_STATUSES),
    )

    op.add_column(
        "plant_lifecycle_events",
        sa.Column(
            "status_reason",
            sa.Text(),
            nullable=True,
            comment="Short justification for a non-default event_status (e.g. why reverted).",
        ),
    )
    op.add_column(
        "plant_lifecycle_events",
        sa.Column(
            "status_changed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When event_status was last changed via the status-update endpoint.",
        ),
    )


def downgrade() -> None:
    op.drop_column("plant_lifecycle_events", "status_changed_at")
    op.drop_column("plant_lifecycle_events", "status_reason")
    op.drop_constraint("ck_lifecycle_event_status", "plant_lifecycle_events", type_="check")
    op.drop_column("plant_lifecycle_events", "event_status")
