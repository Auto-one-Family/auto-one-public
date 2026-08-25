"""Fill MgSO₄·7H₂O from EPSO Top® label (elemental %) — AUT-1417

Revision ID: update_epso_top_mgso4_label_aut1417
Revises: update_mkp_manufacturer_label_aut1417
Create Date: 2026-07-27

Data-only: replaces stoichiometric MgSO₄·7H₂O seed with EPSO Top®
manufacturer label (MgO 16% → elemental Mg; SO₃ 32,5% = 13% S).
Recipe component name stays "MgSO₄·7H₂O" (match Stock-Mix). Downgrade
restores stoichiometric heptahydrate values.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "update_epso_top_mgso4_label_aut1417"
down_revision: Union[str, None] = "update_mkp_manufacturer_label_aut1417"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# MgO→Mg: 16 × 24.305/(24.305+15.999) = 9.6487
# Label: SO₃ 32,5% (= 13 % S) — elemental S stored as 13.0

_NOTE_LABEL = (
    "EPSO Top® — EG-Düngemittel Magnesiumsulfat 16+32,5; "
    "Hersteller-Etikett: MgO 16% wasserlöslich; SO₃ 32,5% wasserlöslich (= 13% S). "
    "Gespeichert als elementare Massenanteile (Atommassen O=15.999 Mg=24.305): "
    "Mg=16×24.305/(24.305+15.999)=9.6487; S=13.0000 (Etikett); N/P/K/Ca=0. "
    "Bibliotheks-Name bleibt MgSO₄·7H₂O (Rezept-Match); Produkt = EPSO Top®. "
    "NPK am Rezept bleibt berechnet/theoretisch."
)

_NOTE_STOICH = (
    "stöchiometrisch abgeleitet aus MgSO₄·7H₂O; "
    "Atommassen H=1.00784 O=15.999 Mg=24.305 S=32.06; "
    "MM=Mg+S+11O+14H=246.4638 g/mol; "
    "Mg%=24.305/246.4638×100=9.8615; "
    "S%=32.06/246.4638×100=13.0080; N/P/K/Ca=0."
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
                formula = :formula,
                n_pct = 0,
                p_pct = 0,
                k_pct = 0,
                ca_pct = 0,
                mg_pct = :mg_pct,
                s_pct = :s_pct,
                source_type = 'manufacturer_label',
                source_note = :note,
                updated_at = :now
            WHERE name = 'MgSO₄·7H₂O' AND active IS TRUE
            """
        ).bindparams(
            formula="MgSO₄·7H₂O",
            mg_pct=9.6487,
            s_pct=13.0,
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
                n_pct = 0,
                p_pct = 0,
                k_pct = 0,
                ca_pct = 0,
                mg_pct = :mg_pct,
                s_pct = :s_pct,
                source_type = 'stoichiometric',
                source_note = :note,
                updated_at = :now
            WHERE name = 'MgSO₄·7H₂O' AND active IS TRUE
            """
        ).bindparams(
            formula="MgSO₄·7H₂O",
            mg_pct=9.8615,
            s_pct=13.0080,
            note=_NOTE_STOICH,
            now=now,
        )
    )
