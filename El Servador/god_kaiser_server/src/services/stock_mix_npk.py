"""
Stock-mix NPK / element balance compute (AUT-1419 / B2).

Feedforward only — theoretical from salt library × target_g_per_l.
Does not touch calculate_dose_ml / volume_share / K2 calibration.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping, Optional, Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models.salt_composition import SaltComposition
from ..db.models.stock_mix_recipe import StockMixRecipe
from ..db.repositories.salt_composition_repo import SaltCompositionRepository
from ..db.repositories.stock_mix_recipe_repo import StockMixRecipeRepository

_ELEMENTS: tuple[str, ...] = ("n", "p", "k", "ca", "mg", "s")
_PCT_ATTR = {
    "n": "n_pct",
    "p": "p_pct",
    "k": "k_pct",
    "ca": "ca_pct",
    "mg": "mg_pct",
    "s": "s_pct",
}


def _as_float(value: object) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value)  # type: ignore[arg-type]


@dataclass(frozen=True)
class NpkComputeResult:
    computed_elements: dict[str, Any]
    computed_npk: dict[str, Any]
    npk_status: str  # complete | incomplete
    npk_missing_salts: list[str]
    npk_computed_at: datetime


def compute_npk_from_components(
    components: Sequence[Mapping[str, Any]],
    salts_by_id: Mapping[UUID, SaltComposition],
    salts_by_name: Mapping[str, SaltComposition],
) -> NpkComputeResult:
    """Pure compute: components + resolved salt rows → persisted-shaped result."""
    totals = {el: 0.0 for el in _ELEMENTS}
    missing: list[str] = []

    for raw in components:
        name = str(raw.get("name") or "").strip() or "unbekannt"
        try:
            g_per_l = float(raw.get("target_g_per_l") or 0.0)
        except (TypeError, ValueError):
            g_per_l = 0.0

        salt: Optional[SaltComposition] = None
        sid_raw = raw.get("salt_composition_id")
        if sid_raw:
            try:
                sid = sid_raw if isinstance(sid_raw, UUID) else UUID(str(sid_raw))
                salt = salts_by_id.get(sid)
            except (TypeError, ValueError):
                salt = None
        if salt is None:
            salt = salts_by_name.get(name)

        if salt is None:
            if name not in missing:
                missing.append(name)
            continue

        if salt.source_type == "beleg_offen":
            if name not in missing:
                missing.append(name)
            # No invented contribution from open-evidence rows.
            continue

        incomplete_row = False
        for el in _ELEMENTS:
            pct = _as_float(getattr(salt, _PCT_ATTR[el]))
            if pct is None:
                incomplete_row = True
                continue
            totals[el] += g_per_l * (pct / 100.0)
        if incomplete_row and name not in missing:
            missing.append(name)

    status = "incomplete" if missing else "complete"
    elements_payload = {
        **{el: round(totals[el], 6) for el in _ELEMENTS},
        "unit": "g_per_l_stock",
        "computed": True,
    }
    npk_payload = {
        "n": round(totals["n"], 6),
        "p": round(totals["p"], 6),
        "k": round(totals["k"], 6),
        "unit": "g_per_l_stock",
        "computed": True,
        "kind": "calculated",
    }

    return NpkComputeResult(
        computed_elements=elements_payload,
        computed_npk=npk_payload,
        npk_status=status,
        npk_missing_salts=missing,
        npk_computed_at=datetime.now(timezone.utc),
    )


async def _load_salt_maps(
    session: AsyncSession,
) -> tuple[dict[UUID, SaltComposition], dict[str, SaltComposition]]:
    repo = SaltCompositionRepository(session)
    rows = await repo.list_filtered(active_only=True)
    by_id = {row.id: row for row in rows}
    by_name = {row.name: row for row in rows}
    return by_id, by_name


async def recompute_and_persist_recipe(
    session: AsyncSession,
    recipe: StockMixRecipe,
) -> StockMixRecipe:
    """Compute NPK/elements for recipe and write additive columns in-place."""
    by_id, by_name = await _load_salt_maps(session)
    result = compute_npk_from_components(
        list(recipe.components or []),
        by_id,
        by_name,
    )
    recipe.computed_elements = result.computed_elements
    recipe.computed_npk = result.computed_npk
    recipe.npk_status = result.npk_status
    recipe.npk_missing_salts = list(result.npk_missing_salts)
    recipe.npk_computed_at = result.npk_computed_at
    await session.flush()
    await session.refresh(recipe)
    return recipe


async def recompute_recipe_by_id(
    session: AsyncSession,
    recipe_id: UUID,
) -> Optional[StockMixRecipe]:
    repo = StockMixRecipeRepository(session)
    recipe = await repo.get_by_id(recipe_id)
    if recipe is None:
        return None
    return await recompute_and_persist_recipe(session, recipe)
