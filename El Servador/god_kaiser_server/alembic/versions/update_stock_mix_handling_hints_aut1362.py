"""AUT-1362: handling_hint Klartext + strip UI jargon from stock_mix metadata

Revision ID: update_stock_mix_handling_hints_aut1362
Revises: add_stock_mix_recipes_aut1361
Create Date: 2026-07-25

Idempotent JSONB update for F3 seed rows. Fresh installs already get
handling_hint from add_stock_mix_recipes_aut1361; this covers DBs that
seeded the older caveat wording.
"""

from __future__ import annotations

import json
from typing import Any, Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "update_stock_mix_handling_hints_aut1362"
down_revision: Union[str, None] = "add_stock_mix_recipes_aut1361"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_HANDLING = {
    "part_a": "In Wasser auflösen, umrühren.",
    "part_b": (
        "Warmes Wasser (~25–30 °C), langsam unter Rühren einlaufen lassen, "
        "leicht sauer halten — dann löst sich alles klar."
    ),
}


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        text(
            "SELECT id, dose_role, nutrient_phase, metadata "
            "FROM stock_mix_recipes WHERE active IS TRUE"
        )
    ).mappings().all()
    for row in rows:
        meta: dict[str, Any] = dict(row["metadata"] or {})
        role = row["dose_role"]
        if role in _HANDLING:
            meta["handling_hint"] = _HANDLING[role]
        # Remove UI-hostile caveat dump; keep internal keys.
        meta.pop("caveats", None)
        watch = meta.get("solubility_watch")
        phase = row["nutrient_phase"] or ""
        is_veg_b = role == "part_b" and str(phase).startswith("veg-")
        if is_veg_b:
            meta["solubility_watch"] = {
                "role": "part_b",
                "fallback_factor": 200,
            }
        elif isinstance(watch, dict):
            meta.pop("solubility_watch", None)
        conn.execute(
            text("UPDATE stock_mix_recipes SET metadata = CAST(:meta AS jsonb) WHERE id = :id"),
            {"meta": json.dumps(meta), "id": str(row["id"])},
        )


def downgrade() -> None:
    # Non-destructive: leave handling_hint in place (additive UX field).
    pass
