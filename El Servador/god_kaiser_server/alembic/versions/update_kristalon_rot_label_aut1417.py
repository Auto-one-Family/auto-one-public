"""Fill Kristalon Rot from YaraTera label (elemental %) — AUT-1417 label input

Revision ID: update_kristalon_rot_label_aut1417
Revises: add_stock_mix_npk_fields_aut1419
Create Date: 2026-07-27

Data-only: updates seed row "Kristalon Rot" from beleg_offen/NULL to
manufacturer_label with elemental mass % derived from the product label
(oxide → element conversion documented in source_note).
No schema change. Downgrade restores beleg_offen + NULL elements.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "update_kristalon_rot_label_aut1417"
down_revision: Union[str, None] = "add_stock_mix_npk_fields_aut1419"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Atomic masses aligned with add_salt_compositions_aut1418 seed:
# O=15.999 P=30.973762 K=39.0983 Mg=24.305
# P₂O₅→P: 12 × (2P)/(2P+5O) = 5.2371
# K₂O→K:  36 × (2K)/(2K+O)   = 29.8854
# MgO→Mg:  1 × Mg/(Mg+O)     = 0.6030

_NOTE = (
    "YaraTera Kristalon Rot (Pulver, chloridarm) — Hersteller-Etikett: "
    "N 12% (Nitrat-N 10.1%, Ammonium-N 1.9%); P₂O₅ 12%; K₂O 36%; MgO 1%; S 1%; "
    "Spurenelemente Fe 0.07% B 0.025% Cu 0.01% Zn 0.025% Mn 0.04% Mo 0.004% "
    "(nur dokumentiert, keine Spalten). "
    "Gespeichert als elementare Massenanteile (Atommassen O=15.999 P=30.973762 "
    "K=39.0983 Mg=24.305): N=12.0000; "
    "P=12×(2×30.973762)/(2×30.973762+5×15.999)=5.2371; "
    "K=36×(2×39.0983)/(2×39.0983+15.999)=29.8854; "
    "Mg=1×24.305/(24.305+15.999)=0.6030; S=1.0000; Ca=0. "
    "NPK am Rezept bleibt berechnet/theoretisch."
)

_NOTE_OPEN = (
    "[BELEG offen] — handelsüblicher Mischdünger; Elementanteile nur aus "
    "Hersteller-Etikett der tatsächlich verwendeten Charge zulässig. "
    "Kein Schätzwert, keine Übernahme typischer NPK-Angaben ähnlicher Produkte."
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
                n_pct = :n_pct,
                p_pct = :p_pct,
                k_pct = :k_pct,
                ca_pct = :ca_pct,
                mg_pct = :mg_pct,
                s_pct = :s_pct,
                source_type = 'manufacturer_label',
                source_note = :note,
                updated_at = :now
            WHERE name = 'Kristalon Rot' AND active IS TRUE
            """
        ).bindparams(
            n_pct=12.0,
            p_pct=5.2371,
            k_pct=29.8854,
            ca_pct=0.0,
            mg_pct=0.6030,
            s_pct=1.0,
            note=_NOTE,
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
                n_pct = NULL,
                p_pct = NULL,
                k_pct = NULL,
                ca_pct = NULL,
                mg_pct = NULL,
                s_pct = NULL,
                source_type = 'beleg_offen',
                source_note = :note,
                updated_at = :now
            WHERE name = 'Kristalon Rot' AND active IS TRUE
            """
        ).bindparams(note=_NOTE_OPEN, now=now)
    )
