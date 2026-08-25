"""Add salt_compositions table + F3 salt seed (AUT-1418 / B1)

Revision ID: add_salt_compositions_aut1418
Revises: add_actuator_stock_identity_aut1410
Create Date: 2026-07-27

Purely additive table + deterministic seed (MgSO₄·7H₂O + MKP stoichiometric;
Calcinit + Kristalon Rot from manufacturer labels as elemental %). Downgrade
drops seed then table. No change to stock_mix_recipes.
Element % = elemental mass fraction (not oxide).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision: str = "add_salt_compositions_aut1418"
down_revision: Union[str, None] = "add_actuator_stock_identity_aut1410"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Deterministic UUIDs for tests / recipe name wiring.
_SEED_NS = uuid.UUID("a1418418-0000-4000-8000-000000000001")


def _sid(name: str) -> uuid.UUID:
    return uuid.uuid5(_SEED_NS, name)


# Atomic masses (IUPAC-common): H=1.00784 N=14.0067 O=15.999 Mg=24.305
# P=30.973762 S=32.06 K=39.0983 Ca=40.078
#
# Ca(NO3)2·4H2O MM=236.1441 → N%=11.8628 Ca%=16.9718
# MgSO4·7H2O    MM=246.4638 → Mg%=9.8615  S%=13.0080
# KH2PO4        MM=136.0837 → P%=22.7608  K%=28.7311

# YaraLiva Calcinit label (Geprillt): N 15.5% / CaO 26% → elemental Ca.
# CaO→Ca with O=15.999 Ca=40.078: 26×40.078/56.077=18.5821
_NOTE_CALCINIT = (
    "YaraLiva Calcinit (Geprillt) — Hersteller-Etikett: "
    "N 15.5% (Nitrat-N 14.4%, Ammonium-N 1.1%); CaO 26%. "
    "Gespeichert als elementare Massenanteile: N=15.5000; "
    "Ca=26×40.078/(40.078+15.999)=18.5821; P/K/Mg/S=0. "
    "Handelsname Calcinit — nicht gleich stöchiometrischem Ca(NO₃)₂·4H₂O. "
    "NPK am Rezept bleibt berechnet/theoretisch."
)

_NOTE_MGSO4 = (
    "EPSO Top® — EG-Düngemittel Magnesiumsulfat 16+32,5; "
    "Hersteller-Etikett: MgO 16% wasserlöslich; SO₃ 32,5% wasserlöslich (= 13% S). "
    "Gespeichert als elementare Massenanteile: "
    "Mg=16×24.305/(24.305+15.999)=9.6487; S=13.0000; N/P/K/Ca=0. "
    "Bibliotheks-Name bleibt MgSO₄·7H₂O (Rezept-Match); Produkt = EPSO Top®. "
    "NPK am Rezept bleibt berechnet/theoretisch."
)

_NOTE_MKP = (
    "MKP (Monokaliumphosphat) — Hersteller-Zusammensetzungstabelle: "
    "P₂O₅ 52,0%; P 22,7%; K₂O 34,0%; K 28,7%; pH (5%-Lösung) 4,2; "
    "Schüttdichte 1,2 kg/l (pH/Dichte nur dokumentiert, keine Spalten). "
    "Gespeichert als elementare Massenanteile laut Etikett: "
    "P=22.7000; K=28.7000; N/Ca/Mg/S=0. "
    "NPK am Rezept bleibt berechnet/theoretisch."
)

# YaraTera Kristalon Rot label (Pulver): N 12% / P₂O₅ 12% / K₂O 36% / MgO 1% / S 1%.
# Oxide → elemental with same atomic masses as stoichiometric seeds above.
_NOTE_KRISTALON = (
    "YaraTera Kristalon Rot (Pulver, chloridarm) — Hersteller-Etikett: "
    "N 12% (Nitrat-N 10.1%, Ammonium-N 1.9%); P₂O₅ 12%; K₂O 36%; MgO 1%; S 1%; "
    "Spurenelemente Fe 0.07% B 0.025% Cu 0.01% Zn 0.025% Mn 0.04% Mo 0.004% "
    "(nur dokumentiert, keine Spalten). "
    "Gespeichert als elementare Massenanteile: N=12.0000; "
    "P=12×(2×30.973762)/(2×30.973762+5×15.999)=5.2371; "
    "K=36×(2×39.0983)/(2×39.0983+15.999)=29.8854; "
    "Mg=1×24.305/(24.305+15.999)=0.6030; S=1.0000; Ca=0. "
    "NPK am Rezept bleibt berechnet/theoretisch."
)


def _seed_rows() -> list[dict[str, Any]]:
    # Explicit timestamps: bulk_insert does not apply column server_defaults.
    now = datetime.now(timezone.utc)
    return [
        {
            "id": _sid("Calcinit"),
            "name": "Calcinit",
            "formula": None,
            "n_pct": 15.5,
            "p_pct": 0.0,
            "k_pct": 0.0,
            "ca_pct": 18.5821,
            "mg_pct": 0.0,
            "s_pct": 0.0,
            "source_type": "manufacturer_label",
            "source_note": _NOTE_CALCINIT,
            "active": True,
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": _sid("MgSO₄·7H₂O"),
            "name": "MgSO₄·7H₂O",
            "formula": "MgSO₄·7H₂O",
            "n_pct": 0.0,
            "p_pct": 0.0,
            "k_pct": 0.0,
            "ca_pct": 0.0,
            "mg_pct": 9.6487,
            "s_pct": 13.0,
            "source_type": "manufacturer_label",
            "source_note": _NOTE_MGSO4,
            "active": True,
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": _sid("MKP"),
            "name": "MKP",
            "formula": "KH₂PO₄",
            "n_pct": 0.0,
            "p_pct": 22.7,
            "k_pct": 28.7,
            "ca_pct": 0.0,
            "mg_pct": 0.0,
            "s_pct": 0.0,
            "source_type": "manufacturer_label",
            "source_note": _NOTE_MKP,
            "active": True,
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": _sid("Kristalon Rot"),
            "name": "Kristalon Rot",
            "formula": None,
            "n_pct": 12.0,
            "p_pct": 5.2371,
            "k_pct": 29.8854,
            "ca_pct": 0.0,
            "mg_pct": 0.6030,
            "s_pct": 1.0,
            "source_type": "manufacturer_label",
            "source_note": _NOTE_KRISTALON,
            "active": True,
            "created_at": now,
            "updated_at": now,
        },
    ]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = inspector.get_table_names()

    if "salt_compositions" not in existing:
        op.create_table(
            "salt_compositions",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("formula", sa.String(length=120), nullable=True),
            sa.Column("n_pct", sa.Numeric(8, 4), nullable=True),
            sa.Column("p_pct", sa.Numeric(8, 4), nullable=True),
            sa.Column("k_pct", sa.Numeric(8, 4), nullable=True),
            sa.Column("ca_pct", sa.Numeric(8, 4), nullable=True),
            sa.Column("mg_pct", sa.Numeric(8, 4), nullable=True),
            sa.Column("s_pct", sa.Numeric(8, 4), nullable=True),
            sa.Column("source_type", sa.String(length=32), nullable=False),
            sa.Column(
                "source_note",
                sa.String(length=2000),
                nullable=False,
                server_default=sa.text("''"),
            ),
            sa.Column(
                "active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
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
            sa.CheckConstraint(
                "source_type IN ('stoichiometric', 'manufacturer_label', 'beleg_offen')",
                name="ck_salt_compositions_source_type",
            ),
        )
        op.create_index(
            "uq_salt_compositions_active_name",
            "salt_compositions",
            ["name"],
            unique=True,
            postgresql_where=sa.text("active IS TRUE"),
        )

    salts = sa.table(
        "salt_compositions",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.String),
        sa.column("formula", sa.String),
        sa.column("n_pct", sa.Numeric),
        sa.column("p_pct", sa.Numeric),
        sa.column("k_pct", sa.Numeric),
        sa.column("ca_pct", sa.Numeric),
        sa.column("mg_pct", sa.Numeric),
        sa.column("s_pct", sa.Numeric),
        sa.column("source_type", sa.String),
        sa.column("source_note", sa.String),
        sa.column("active", sa.Boolean),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )

    existing_ids = set()
    if "salt_compositions" in inspector.get_table_names():
        result = bind.execute(sa.text("SELECT id FROM salt_compositions"))
        existing_ids = {row[0] for row in result}

    to_insert = [row for row in _seed_rows() if row["id"] not in existing_ids]
    if to_insert:
        op.bulk_insert(salts, to_insert)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "salt_compositions" not in inspector.get_table_names():
        return

    for row in _seed_rows():
        op.execute(
            sa.text("DELETE FROM salt_compositions WHERE id = CAST(:id AS uuid)").bindparams(
                id=str(row["id"])
            )
        )

    op.drop_index(
        "uq_salt_compositions_active_name",
        table_name="salt_compositions",
    )
    op.drop_table("salt_compositions")
