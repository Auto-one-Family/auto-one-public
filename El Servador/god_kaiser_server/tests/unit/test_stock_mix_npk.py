"""
Unit tests for stock-mix NPK compute + persist (AUT-1419 / B2).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.repositories.salt_composition_repo import SaltCompositionRepository
from src.db.repositories.stock_mix_recipe_repo import StockMixRecipeRepository
from src.services.stock_mix_npk import (
    compute_npk_from_components,
    recompute_and_persist_recipe,
)


async def _seed_salts(db_session: AsyncSession) -> dict[str, uuid.UUID]:
    repo = SaltCompositionRepository(db_session)
    calc = await repo.create(
        name="Calcinit",
        formula=None,
        n_pct=15.5,
        p_pct=0.0,
        k_pct=0.0,
        ca_pct=18.5821,
        mg_pct=0.0,
        s_pct=0.0,
        source_type="manufacturer_label",
        source_note="YaraLiva label",
        active=True,
    )
    mg = await repo.create(
        name="MgSO₄·7H₂O",
        formula="MgSO₄·7H₂O",
        n_pct=0.0,
        p_pct=0.0,
        k_pct=0.0,
        ca_pct=0.0,
        mg_pct=9.6487,
        s_pct=13.0,
        source_type="manufacturer_label",
        source_note="EPSO Top® test",
        active=True,
    )
    krist = await repo.create(
        name="Kristalon Rot",
        formula=None,
        n_pct=12.0,
        p_pct=5.2371,
        k_pct=29.8854,
        ca_pct=0.0,
        mg_pct=0.6030,
        s_pct=1.0,
        source_type="manufacturer_label",
        source_note="YaraTera label",
        active=True,
    )
    offen = await repo.create(
        name="Open Evidence Salt",
        formula=None,
        n_pct=None,
        p_pct=None,
        k_pct=None,
        ca_pct=None,
        mg_pct=None,
        s_pct=None,
        source_type="beleg_offen",
        source_note="[BELEG offen]",
        active=True,
    )
    await db_session.flush()
    return {
        "Calcinit": calc.id,
        "MgSO₄·7H₂O": mg.id,
        "Kristalon Rot": krist.id,
        "Open Evidence Salt": offen.id,
    }


@pytest.mark.asyncio
async def test_complete_recipe_computes_npk(db_session: AsyncSession) -> None:
    ids = await _seed_salts(db_session)
    recipe_repo = StockMixRecipeRepository(db_session)
    recipe = await recipe_repo.create(
        label="Stock A — test",
        dose_role="part_a",
        coverage="phase_specific",
        nutrient_phase="veg-frueh",
        components=[
            {
                "name": "Calcinit",
                "target_g_per_l": 100.0,
                "salt_composition_id": str(ids["Calcinit"]),
            }
        ],
        meta={"dose_ml_per_l": {"part_a": 4.0, "part_b": 4.0}, "npk_label": "16-7-20"},
        active=True,
    )
    await db_session.flush()

    updated = await recompute_and_persist_recipe(db_session, recipe)
    assert updated.npk_status == "complete"
    assert updated.npk_missing_salts == []
    assert updated.computed_npk is not None
    assert updated.computed_npk["computed"] is True
    assert updated.computed_npk["kind"] == "calculated"
    # 100 g/L × 15.5% = 15.5 g N / L stock
    assert updated.computed_npk["n"] == pytest.approx(15.5, abs=1e-4)
    assert updated.computed_elements["ca"] == pytest.approx(18.5821, abs=1e-4)
    assert updated.npk_computed_at is not None
    # Human label untouched
    assert updated.meta["npk_label"] == "16-7-20"
    assert updated.meta["dose_ml_per_l"]["part_a"] == 4.0


@pytest.mark.asyncio
async def test_incomplete_when_component_beleg_offen(db_session: AsyncSession) -> None:
    await _seed_salts(db_session)
    recipe_repo = StockMixRecipeRepository(db_session)
    recipe = await recipe_repo.create(
        label="Stock B — veg",
        dose_role="part_b",
        coverage="phase_specific",
        nutrient_phase="veg-frueh",
        components=[
            {"name": "MgSO₄·7H₂O", "target_g_per_l": 87.5},
            {"name": "Open Evidence Salt", "target_g_per_l": 10.0},
        ],
        meta={},
        active=True,
    )
    await db_session.flush()

    updated = await recompute_and_persist_recipe(db_session, recipe)
    assert updated.npk_status == "incomplete"
    assert "Open Evidence Salt" in (updated.npk_missing_salts or [])
    # Mg contribution still counted from complete salt
    assert updated.computed_elements["mg"] == pytest.approx(87.5 * 9.6487 / 100.0, abs=1e-4)
    assert updated.computed_npk["computed"] is True


@pytest.mark.asyncio
async def test_kristalon_label_completes_stock_b(db_session: AsyncSession) -> None:
    await _seed_salts(db_session)
    recipe_repo = StockMixRecipeRepository(db_session)
    recipe = await recipe_repo.create(
        label="Stock B — veg",
        dose_role="part_b",
        coverage="phase_specific",
        nutrient_phase="veg-frueh",
        components=[
            {"name": "MgSO₄·7H₂O", "target_g_per_l": 87.5},
            {"name": "Kristalon Rot", "target_g_per_l": 137.5},
        ],
        meta={},
        active=True,
    )
    await db_session.flush()

    updated = await recompute_and_persist_recipe(db_session, recipe)
    assert updated.npk_status == "complete"
    assert updated.npk_missing_salts == []
    assert updated.computed_npk is not None
    assert updated.computed_npk["kind"] == "calculated"
    # N from Kristalon only: 137.5 × 12% = 16.5 g/L stock
    assert updated.computed_npk["n"] == pytest.approx(137.5 * 0.12, abs=1e-4)
    assert updated.computed_npk["k"] == pytest.approx(137.5 * 0.298854, abs=1e-3)


def test_pure_compute_missing_library_row() -> None:
    result = compute_npk_from_components(
        [{"name": "Unknown Salt", "target_g_per_l": 10.0}],
        salts_by_id={},
        salts_by_name={},
    )
    assert result.npk_status == "incomplete"
    assert result.npk_missing_salts == ["Unknown Salt"]
    assert result.computed_npk["kind"] == "calculated"


@pytest.mark.asyncio
async def test_name_fallback_without_salt_composition_id(
    db_session: AsyncSession,
) -> None:
    await _seed_salts(db_session)
    recipe_repo = StockMixRecipeRepository(db_session)
    recipe = await recipe_repo.create(
        label="Stock A — name fallback",
        dose_role="part_a",
        coverage="universal",
        nutrient_phase=None,
        components=[{"name": "Calcinit", "target_g_per_l": 150.0}],
        meta={},
        active=True,
    )
    await db_session.flush()
    updated = await recompute_and_persist_recipe(db_session, recipe)
    assert updated.npk_status == "complete"
    assert updated.computed_npk["n"] == pytest.approx(150.0 * 15.5 / 100.0, abs=1e-4)
