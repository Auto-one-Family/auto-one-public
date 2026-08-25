"""Add uebergang-vorbluete to the light/growth phase axis

AUT-1209 added uebergang-vorbluete only on the nutrient axis, assuming a
"transition" concept does not exist on a binary 18/6 vs 12/12 light cycle.
Real grow operation needs the same value on the light/growth axis: after
photoperiod flip (12/12 induction) and before visible bluete-stretch.

Purely additive: extends ck_plants_phase; no data rewritten.

Revision ID: add_uebergang_vorbluete_light_phase
Revises: update_epso_top_mgso4_label_aut1417
Create Date: 2026-07-27
"""

from typing import Sequence, Union

from alembic import op

revision: str = "add_uebergang_vorbluete_light_phase"
down_revision: Union[str, None] = "update_epso_top_mgso4_label_aut1417"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PLANT_PHASES_OLD = (
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

_PLANT_PHASES_NEW = (
    "invitro_donor",
    "invitro_initiation",
    "invitro_multiplication",
    "invitro_rooting",
    "invitro_acclimatization",
    "clone",
    "veg-frueh",
    "veg-spaet",
    "uebergang-vorbluete",
    "bluete-stretch",
    "bluete-bulk",
    "bluete-ende",
    "mutter",
    "steckling_wurzelung",
    "steckling_vor_versand",
    "harvested",
    "archived",
)


def _phase_check_sql(values: tuple[str, ...]) -> str:
    return f"phase IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    op.drop_constraint("ck_plants_phase", "plants", type_="check")
    op.create_check_constraint(
        "ck_plants_phase",
        "plants",
        _phase_check_sql(_PLANT_PHASES_NEW),
    )


def downgrade() -> None:
    # Rows with phase='uebergang-vorbluete' will violate the restored constraint.
    op.drop_constraint("ck_plants_phase", "plants", type_="check")
    op.create_check_constraint(
        "ck_plants_phase",
        "plants",
        _phase_check_sql(_PLANT_PHASES_OLD),
    )
