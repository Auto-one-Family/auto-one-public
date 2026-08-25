"""Fill Calcinit from YaraLiva label (elemental %) — AUT-1417 label input

Revision ID: update_calcinit_yaraliva_label_aut1417
Revises: update_kristalon_rot_label_aut1417
Create Date: 2026-07-27

Data-only: replaces stoichiometric Ca(NO₃)₂·4H₂O seed for "Calcinit"
with YaraLiva Calcinit manufacturer label (N 15.5%, CaO 26% → elemental Ca).
Downgrade restores stoichiometric tetrahydrate values.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "update_calcinit_yaraliva_label_aut1417"
down_revision: Union[str, None] = "update_kristalon_rot_label_aut1417"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# CaO→Ca with O=15.999 Ca=40.078: 26 × 40.078/56.077 = 18.5821

_NOTE_LABEL = (
    "YaraLiva Calcinit (Geprillt) — Hersteller-Etikett: "
    "N 15.5% (Nitrat-N 14.4%, Ammonium-N 1.1%); CaO 26%. "
    "Gespeichert als elementare Massenanteile (Atommassen O=15.999 Ca=40.078): "
    "N=15.5000; Ca=26×40.078/(40.078+15.999)=18.5821; P/K/Mg/S=0. "
    "Handelsname Calcinit — nicht gleich stöchiometrischem Ca(NO₃)₂·4H₂O. "
    "NPK am Rezept bleibt berechnet/theoretisch."
)

_NOTE_STOICH = (
    "stöchiometrisch abgeleitet aus Ca(NO₃)₂·4H₂O; "
    "Atommassen H=1.00784 N=14.0067 O=15.999 Ca=40.078; "
    "MM=Ca+2N+10O+8H=236.1441 g/mol; "
    "N%=2×14.0067/236.1441×100=11.8628; "
    "Ca%=40.078/236.1441×100=16.9718; P/K/Mg/S=0. "
    "Handelsname Calcinit — chemisch Calciumnitrat-Tetrahydrat."
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "salt_compositions" not in inspector.get_table_names():
        return

    now = datetime.now(timezone.utc)
    op.execute(
        sa.text(
            """
            UPDATE salt_compositions
            SET
                formula = NULL,
                n_pct = :n_pct,
                p_pct = 0,
                k_pct = 0,
                ca_pct = :ca_pct,
                mg_pct = 0,
                s_pct = 0,
                source_type = 'manufacturer_label',
                source_note = :note,
                updated_at = :now
            WHERE name = 'Calcinit' AND active IS TRUE
            """
        ).bindparams(
            n_pct=15.5,
            ca_pct=18.5821,
            note=_NOTE_LABEL,
            now=now,
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "salt_compositions" not in inspector.get_table_names():
        return

    now = datetime.now(timezone.utc)
    op.execute(
        sa.text(
            """
            UPDATE salt_compositions
            SET
                formula = :formula,
                n_pct = :n_pct,
                p_pct = 0,
                k_pct = 0,
                ca_pct = :ca_pct,
                mg_pct = 0,
                s_pct = 0,
                source_type = 'stoichiometric',
                source_note = :note,
                updated_at = :now
            WHERE name = 'Calcinit' AND active IS TRUE
            """
        ).bindparams(
            formula="Ca(NO₃)₂·4H₂O",
            n_pct=11.8628,
            ca_pct=16.9718,
            note=_NOTE_STOICH,
            now=now,
        )
    )
