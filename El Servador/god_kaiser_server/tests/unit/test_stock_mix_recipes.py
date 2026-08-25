"""
Unit tests for stock_mix_recipes (AUT-1361 / P9).
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.repositories.stock_mix_recipe_repo import StockMixRecipeRepository
from src.schemas.stock_mix_recipe import StockMixRecipeCreate, StockMixRecipeResponse


@pytest.mark.asyncio
async def test_create_and_lookup_phase_specific(db_session: AsyncSession) -> None:
    repo = StockMixRecipeRepository(db_session)
    recipe = await repo.create(
        label="Stock A — Veg 16-7-20",
        dose_role="part_a",
        coverage="phase_specific",
        nutrient_phase="veg-frueh",
        components=[{"name": "Calcinit", "target_g_per_l": 150.0}],
        meta={"concentration_factor": 250, "caveats": ["A zuerst dann B"]},
        active=True,
    )
    await db_session.flush()

    found = await repo.lookup(dose_role="part_a", nutrient_phase="veg-frueh")
    assert found is not None
    assert found.id == recipe.id
    assert found.components[0]["target_g_per_l"] == 150.0

    resp = StockMixRecipeResponse.model_validate(found)
    assert resp.metadata["concentration_factor"] == 250
    assert resp.dose_role == "part_a"


@pytest.mark.asyncio
async def test_lookup_falls_back_to_universal(db_session: AsyncSession) -> None:
    repo = StockMixRecipeRepository(db_session)
    universal = await repo.create(
        label="Stock B — universal",
        dose_role="part_b",
        coverage="universal",
        nutrient_phase=None,
        components=[
            {"name": "MgSO₄·7H₂O", "target_g_per_l": 87.5},
            {"name": "Kristalon Rot", "target_g_per_l": 137.5},
        ],
        meta={},
        active=True,
    )
    await db_session.flush()

    found = await repo.lookup(dose_role="part_b", nutrient_phase="bluete-bulk")
    assert found is not None
    assert found.id == universal.id
    assert found.coverage == "universal"


@pytest.mark.asyncio
async def test_lookup_prefers_phase_specific_over_universal(
    db_session: AsyncSession,
) -> None:
    repo = StockMixRecipeRepository(db_session)
    await repo.create(
        label="Stock A — universal",
        dose_role="part_a",
        coverage="universal",
        nutrient_phase=None,
        components=[{"name": "Calcinit", "target_g_per_l": 1.0}],
        meta={},
        active=True,
    )
    specific = await repo.create(
        label="Stock A — Blüte",
        dose_role="part_a",
        coverage="phase_specific",
        nutrient_phase="bluete-stretch",
        components=[{"name": "Calcinit", "target_g_per_l": 100.0}],
        meta={},
        active=True,
    )
    await db_session.flush()

    found = await repo.lookup(dose_role="part_a", nutrient_phase="bluete-stretch")
    assert found is not None
    assert found.id == specific.id
    assert found.components[0]["target_g_per_l"] == 100.0


def test_schema_rejects_invalid_dose_role() -> None:
    with pytest.raises(ValidationError):
        StockMixRecipeCreate(
            label="bad",
            dose_role="stock_a",
            coverage="phase_specific",
            nutrient_phase="veg-frueh",
            components=[{"name": "X", "target_g_per_l": 1.0}],
        )


def test_schema_rejects_phase_specific_without_phase() -> None:
    with pytest.raises(ValidationError):
        StockMixRecipeCreate(
            label="bad",
            dose_role="part_a",
            coverage="phase_specific",
            nutrient_phase=None,
            components=[{"name": "X", "target_g_per_l": 1.0}],
        )


def test_f3_veg_b_numbers_exact() -> None:
    """Guardrail: F3 Veg-B targets must stay exact (Issue AUT-1361)."""
    create = StockMixRecipeCreate(
        label="Stock B — Veg 16-7-20",
        dose_role="part_b",
        coverage="phase_specific",
        nutrient_phase="veg-frueh",
        components=[
            {"name": "MgSO₄·7H₂O", "target_g_per_l": 87.5},
            {"name": "Kristalon Rot", "target_g_per_l": 137.5},
        ],
        metadata={
            "concentration_factor": 250,
            "dose_ml_per_l": {"part_a": 4.0, "part_b": 4.0},
            "handling_hint": (
                "Warmes Wasser (~25–30 °C), langsam unter Rühren einlaufen lassen, "
                "leicht sauer halten — dann löst sich alles klar."
            ),
            "solubility_watch": {"role": "part_b", "fallback_factor": 200},
        },
    )
    assert create.components[0].target_g_per_l == 87.5
    assert create.components[1].target_g_per_l == 137.5
    assert create.metadata["concentration_factor"] == 250
    assert "handling_hint" in create.metadata
    assert "200×" not in create.metadata["handling_hint"]


def test_handling_hint_klartext_no_factor_jargon() -> None:
    """AUT-1362: handling_hint is Klartext — no scale factor / %-summe."""
    create = StockMixRecipeCreate(
        label="Stock A — Veg",
        dose_role="part_a",
        coverage="phase_specific",
        nutrient_phase="veg-frueh",
        components=[{"name": "Calcinit", "target_g_per_l": 150.0}],
        metadata={"handling_hint": "In Wasser auflösen, umrühren."},
    )
    hint = create.metadata["handling_hint"]
    assert "auflösen" in hint.lower()
    for banned in ("250×", "200×", "Wachauge", "22,5", "Arbeits-pH", "A zuerst"):
        assert banned not in hint


@pytest.mark.asyncio
async def test_soft_delete_hides_from_lookup(db_session: AsyncSession) -> None:
    repo = StockMixRecipeRepository(db_session)
    recipe = await repo.create(
        label="temp",
        dose_role="ph_down",
        coverage="universal",
        nutrient_phase=None,
        components=[{"name": "pH-Minus", "target_g_per_l": 10.0}],
        meta={},
        active=True,
    )
    await db_session.flush()
    await repo.update_fields(recipe.id, active=False)
    await db_session.flush()

    assert await repo.lookup(dose_role="ph_down", nutrient_phase=None) is None
    assert isinstance(recipe.id, uuid.UUID)
    assert await repo.get_by_id(recipe.id) is not None
