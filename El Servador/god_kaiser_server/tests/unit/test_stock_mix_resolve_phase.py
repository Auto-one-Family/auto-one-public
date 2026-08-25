"""
Unit tests for resolve-phase Lesepfad (AUT-1420 / B3).
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.repositories.stock_mix_recipe_repo import StockMixRecipeRepository
from src.schemas.stock_mix_recipe import StockMixPhaseResolveResponse


@pytest.mark.asyncio
async def test_resolve_phase_reuses_lookup(db_session: AsyncSession) -> None:
    repo = StockMixRecipeRepository(db_session)
    a = await repo.create(
        label="Stock A — Veg",
        dose_role="part_a",
        coverage="phase_specific",
        nutrient_phase="veg-frueh",
        components=[{"name": "Calcinit", "target_g_per_l": 150.0}],
        meta={"dose_ml_per_l": {"part_a": 4.0, "part_b": 4.0}},
        active=True,
        computed_npk={"n": 1.0, "p": 0.0, "k": 0.0, "computed": True, "kind": "calculated"},
        npk_status="complete",
        npk_missing_salts=[],
    )
    b = await repo.create(
        label="Stock B — Veg",
        dose_role="part_b",
        coverage="phase_specific",
        nutrient_phase="veg-frueh",
        components=[{"name": "MgSO₄·7H₂O", "target_g_per_l": 87.5}],
        meta={"dose_ml_per_l": {"part_a": 4.0, "part_b": 4.0}},
        active=True,
        computed_npk={"n": 0.0, "p": 0.0, "k": 0.0, "computed": True, "kind": "calculated"},
        npk_status="incomplete",
        npk_missing_salts=["Kristalon Rot"],
    )
    await db_session.flush()

    part_a = await repo.lookup(dose_role="part_a", nutrient_phase="veg-frueh")
    part_b = await repo.lookup(dose_role="part_b", nutrient_phase="veg-frueh")
    assert part_a is not None and part_a.id == a.id
    assert part_b is not None and part_b.id == b.id

    payload = StockMixPhaseResolveResponse(
        nutrient_phase="veg-frueh",
        part_a=part_a,
        part_b=part_b,
        resolved=True,
    )
    assert payload.resolved is True
    assert payload.part_a is not None
    assert payload.part_b is not None
    assert payload.part_b.npk_status == "incomplete"


@pytest.mark.asyncio
async def test_resolve_phase_unresolved_when_missing(db_session: AsyncSession) -> None:
    repo = StockMixRecipeRepository(db_session)
    found = await repo.lookup(dose_role="part_a", nutrient_phase="bluete-ende")
    assert found is None
    payload = StockMixPhaseResolveResponse(
        nutrient_phase="bluete-ende",
        resolved=False,
        detail="keine Rezeptur hinterlegt",
    )
    assert payload.resolved is False
    assert payload.detail == "keine Rezeptur hinterlegt"
