"""Fill MKP from manufacturer composition table (elemental %) — AUT-1417

Revision ID: update_mkp_manufacturer_label_aut1417
Revises: update_calcinit_yaraliva_label_aut1417
Create Date: 2026-07-27

Data-only: replaces stoichiometric KH₂PO₄ seed for "MKP" with manufacturer
label elemental values (P 22.7%, K 28.7%; oxide guarantees P₂O₅ 52%, K₂O 34%
documented in source_note). Downgrade restores stoichiometric values.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "update_mkp_manufacturer_label_aut1417"
down_revision: Union[str, None] = "update_calcinit_yaraliva_label_aut1417"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NOTE_LABEL = (
    "MKP (Monokaliumphosphat) — Hersteller-Zusammensetzungstabelle: "
    "P₂O₅ 52,0%; P 22,7%; K₂O 34,0%; K 28,7%; pH (5%-Lösung) 4,2; "
    "Schüttdichte 1,2 kg/l (pH/Dichte nur dokumentiert, keine Spalten). "
    "Gespeichert als elementare Massenanteile laut Etikett: "
    "P=22.7000; K=28.7000; N/Ca/Mg/S=0. "
    "Oxide→Element-Kontrolle (Atommassen O=15.999 P=30.973762 K=39.0983): "
    "P=52×(2×30.973762)/(2×30.973762+5×15.999)=22.6928≈22,7; "
    "K=34×(2×39.0983)/(2×39.0983+15.999)=28.2234 (Etikett listet elementar K 28,7). "
    "NPK am Rezept bleibt berechnet/theoretisch."
)

_NOTE_STOICH = (
    "stöchiometrisch abgeleitet aus KH₂PO₄ (MKP); "
    "Atommassen H=1.00784 O=15.999 P=30.973762 K=39.0983; "
    "MM=K+2H+P+4O=136.0837 g/mol; "
    "P%=30.973762/136.0837×100=22.7608; "
    "K%=39.0983/136.0837×100=28.7311; N/Ca/Mg/S=0. "
    "Werte als elementarer Massenanteil (nicht P₂O₅/K₂O)."
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
                p_pct = :p_pct,
                k_pct = :k_pct,
                ca_pct = 0,
                mg_pct = 0,
                s_pct = 0,
                source_type = 'manufacturer_label',
                source_note = :note,
                updated_at = :now
            WHERE name = 'MKP' AND active IS TRUE
            """
        ).bindparams(
            formula="KH₂PO₄",
            p_pct=22.7,
            k_pct=28.7,
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
                p_pct = :p_pct,
                k_pct = :k_pct,
                ca_pct = 0,
                mg_pct = 0,
                s_pct = 0,
                source_type = 'stoichiometric',
                source_note = :note,
                updated_at = :now
            WHERE name = 'MKP' AND active IS TRUE
            """
        ).bindparams(
            formula="KH₂PO₄",
            p_pct=22.7608,
            k_pct=28.7311,
            note=_NOTE_STOICH,
            now=now,
        )
    )
