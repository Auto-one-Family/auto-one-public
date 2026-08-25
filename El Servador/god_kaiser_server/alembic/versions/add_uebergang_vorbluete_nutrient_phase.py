"""Add uebergang-vorbluete to the nutrient phase axis, split from PLANT_PHASES (AUT-1209)

The nutrient/fertilizer phase axis (AUT-1183) has so far shared its valid-values
list with the light/growth axis (NUTRIENT_PHASES was a plain alias of
PLANT_PHASES). A real operating case exposed the gap: a grower running a
transition/pre-flower nutrient profile ("Uebergang/Vorbluete") had no
matching value and used a light-axis value ('veg-spaet') as a workaround.

This migration splits ck_plants_nutrient_phase from ck_plants_phase's value
list (they were already separately named for exactly this — see
db/models/plant.py comment history) and adds the missing value. The
light/growth axis (ck_plants_phase, PLANT_PHASES) is untouched — a
"transition" concept does not exist on a binary 18/6 or 12/12 light cycle.

Purely additive: no existing value is removed, no data is modified.

Revision ID: add_uebergang_vorbluete_nutrient_phase
Revises: add_tanks_table
Create Date: 2026-07-20

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers
revision: str = "add_uebergang_vorbluete_nutrient_phase"
down_revision: Union[str, None] = "add_tanks_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# Local constants — kept self-contained so the migration does not depend on
# application code (migration portability principle, see
# add_nutrient_phase_to_plants.py).
# ---------------------------------------------------------------------------

_NUTRIENT_PHASES_OLD = (
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

_NUTRIENT_PHASES_NEW = (
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


def _nutrient_phase_check_sql(values: tuple[str, ...]) -> str:
    return f"nutrient_phase IS NULL OR nutrient_phase IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    # PostgreSQL has no ALTER CONSTRAINT for CHECK — drop and recreate.
    op.drop_constraint("ck_plants_nutrient_phase", "plants", type_="check")
    op.create_check_constraint(
        "ck_plants_nutrient_phase",
        "plants",
        _nutrient_phase_check_sql(_NUTRIENT_PHASES_NEW),
    )


def downgrade() -> None:
    # NOTE: rows with nutrient_phase='uebergang-vorbluete' will violate the
    # restored constraint — ensure no such rows exist before downgrading.
    op.drop_constraint("ck_plants_nutrient_phase", "plants", type_="check")
    op.create_check_constraint(
        "ck_plants_nutrient_phase",
        "plants",
        _nutrient_phase_check_sql(_NUTRIENT_PHASES_OLD),
    )
