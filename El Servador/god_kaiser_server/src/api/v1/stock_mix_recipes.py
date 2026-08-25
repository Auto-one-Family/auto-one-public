"""
Stock Mix Recipe CRUD + Lookup (AUT-1361 / P9)

Endpoints:
- POST   /v1/stock-mix-recipes
- GET    /v1/stock-mix-recipes
- GET    /v1/stock-mix-recipes/lookup
- GET    /v1/stock-mix-recipes/{recipe_id}
- PATCH  /v1/stock-mix-recipes/{recipe_id}
- DELETE /v1/stock-mix-recipes/{recipe_id}  (soft: active=false)

Muster: plan_segments.py (Router → Repository, kein Service-Zweitpfad).
"""

from __future__ import annotations

from typing import Annotated, List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, Query, status

from ...core.logging_config import get_logger
from ...db.repositories.stock_mix_recipe_repo import StockMixRecipeRepository
from ...schemas.stock_mix_recipe import (
    StockMixPhaseResolveResponse,
    StockMixRecipeCreate,
    StockMixRecipeResponse,
    StockMixRecipeUpdate,
)
from ...services.stock_mix_npk import recompute_and_persist_recipe
from ..deps import ActiveUser, DBSession, OperatorUser

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/stock-mix-recipes", tags=["stock-mix-recipes"])


def _to_response(recipe) -> StockMixRecipeResponse:
    return StockMixRecipeResponse.model_validate(recipe)


def _components_as_dicts(components: list) -> list:
    return [c if isinstance(c, dict) else c for c in components]


@router.post(
    "",
    response_model=StockMixRecipeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create stock mix recipe",
)
async def create_stock_mix_recipe(
    request: StockMixRecipeCreate,
    db: DBSession,
    current_user: OperatorUser,
) -> StockMixRecipeResponse:
    repo = StockMixRecipeRepository(db)
    # mode=json → UUID soft-refs as strings for JSONB storage
    payload = request.model_dump(mode="json")
    # ORM attribute is ``meta``; API field is ``metadata``.
    payload["meta"] = payload.pop("metadata", {})
    payload["components"] = _components_as_dicts(payload["components"])
    # components already dicts from model_dump
    recipe = await repo.create(**payload)
    # AUT-1419 B2: recompute feedforward NPK after content write.
    recipe = await recompute_and_persist_recipe(db, recipe)
    await db.commit()
    await db.refresh(recipe)
    logger.info(
        "Stock mix recipe created by %s: id=%s role=%s phase=%s npk_status=%s",
        current_user.username,
        recipe.id,
        recipe.dose_role,
        recipe.nutrient_phase,
        recipe.npk_status,
    )
    return _to_response(recipe)


@router.get(
    "",
    response_model=List[StockMixRecipeResponse],
    summary="List stock mix recipes",
)
async def list_stock_mix_recipes(
    db: DBSession,
    _user: ActiveUser,
    dose_role: Optional[str] = Query(None),
    nutrient_phase: Optional[str] = Query(None),
    coverage: Optional[str] = Query(None),
    include_inactive: bool = Query(False),
) -> List[StockMixRecipeResponse]:
    repo = StockMixRecipeRepository(db)
    rows = await repo.list_filtered(
        dose_role=dose_role,
        nutrient_phase=nutrient_phase,
        coverage=coverage,
        active_only=not include_inactive,
    )
    return [_to_response(r) for r in rows]


@router.get(
    "/lookup",
    response_model=StockMixRecipeResponse,
    summary="Lookup recipe by dose_role × nutrient_phase",
)
async def lookup_stock_mix_recipe(
    db: DBSession,
    _user: ActiveUser,
    dose_role: str = Query(..., description="part_a | part_b | ph_down | generic"),
    nutrient_phase: Optional[str] = Query(
        None, description="NUTRIENT_PHASES key; falls back to universal"
    ),
) -> StockMixRecipeResponse:
    repo = StockMixRecipeRepository(db)
    recipe = await repo.lookup(dose_role=dose_role, nutrient_phase=nutrient_phase)
    if recipe is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No stock mix recipe for dose_role={dose_role!r} phase={nutrient_phase!r}",
        )
    return _to_response(recipe)


@router.get(
    "/resolve-phase",
    response_model=StockMixPhaseResolveResponse,
    summary="Resolve Stock A/B recipes for a nutrient phase (AUT-1420 B3)",
)
async def resolve_stock_mix_phase(
    db: DBSession,
    _user: ActiveUser,
    nutrient_phase: Optional[str] = Query(
        None, description="NUTRIENT_PHASES / plan_segments.phase_ref key"
    ),
) -> StockMixPhaseResolveResponse:
    """
    Option-1 Lesepfad für Wochenraster: reuse repo.lookup for part_a + part_b.
    No second lookup logic. Explicit unresolved when both roles missing.
    """
    if not nutrient_phase or not nutrient_phase.strip():
        return StockMixPhaseResolveResponse(
            nutrient_phase=nutrient_phase,
            resolved=False,
            detail="keine Rezeptur hinterlegt",
        )
    phase = nutrient_phase.strip()
    repo = StockMixRecipeRepository(db)
    part_a = await repo.lookup(dose_role="part_a", nutrient_phase=phase)
    part_b = await repo.lookup(dose_role="part_b", nutrient_phase=phase)
    if part_a is None and part_b is None:
        return StockMixPhaseResolveResponse(
            nutrient_phase=phase,
            resolved=False,
            detail="keine Rezeptur hinterlegt",
        )
    # Lazy fill B2 fields for pre-existing seed rows (read path, then persist once).
    dirty = False
    if part_a is not None and part_a.npk_computed_at is None:
        part_a = await recompute_and_persist_recipe(db, part_a)
        dirty = True
    if part_b is not None and part_b.npk_computed_at is None:
        part_b = await recompute_and_persist_recipe(db, part_b)
        dirty = True
    if dirty:
        await db.commit()
    return StockMixPhaseResolveResponse(
        nutrient_phase=phase,
        part_a=_to_response(part_a) if part_a is not None else None,
        part_b=_to_response(part_b) if part_b is not None else None,
        resolved=True,
        detail=None,
    )


@router.get(
    "/{recipe_id}",
    response_model=StockMixRecipeResponse,
    summary="Get stock mix recipe by id",
)
async def get_stock_mix_recipe(
    db: DBSession,
    _user: ActiveUser,
    recipe_id: Annotated[UUID, Path()],
) -> StockMixRecipeResponse:
    repo = StockMixRecipeRepository(db)
    recipe = await repo.get_by_id(recipe_id)
    if recipe is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found")
    return _to_response(recipe)


@router.patch(
    "/{recipe_id}",
    response_model=StockMixRecipeResponse,
    summary="Update stock mix recipe",
)
async def update_stock_mix_recipe(
    request: StockMixRecipeUpdate,
    db: DBSession,
    current_user: OperatorUser,
    recipe_id: Annotated[UUID, Path()],
) -> StockMixRecipeResponse:
    repo = StockMixRecipeRepository(db)
    fields = request.model_dump(mode="json", exclude_unset=True)
    if "metadata" in fields:
        fields["meta"] = fields.pop("metadata")
    if "components" in fields and fields["components"] is not None:
        fields["components"] = _components_as_dicts(fields["components"])
    recipe = await repo.update_fields(recipe_id, **fields)
    if recipe is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found")
    # AUT-1419 B2: always recompute after PATCH (content or metadata may change).
    recipe = await recompute_and_persist_recipe(db, recipe)
    await db.commit()
    await db.refresh(recipe)
    logger.info(
        "Stock mix recipe updated by %s: id=%s npk_status=%s",
        current_user.username,
        recipe.id,
        recipe.npk_status,
    )
    return _to_response(recipe)


@router.delete(
    "/{recipe_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete stock mix recipe (active=false)",
)
async def delete_stock_mix_recipe(
    db: DBSession,
    current_user: OperatorUser,
    recipe_id: Annotated[UUID, Path()],
) -> None:
    repo = StockMixRecipeRepository(db)
    recipe = await repo.update_fields(recipe_id, active=False)
    if recipe is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found")
    await db.commit()
    logger.info(
        "Stock mix recipe soft-deleted by %s: id=%s",
        current_user.username,
        recipe_id,
    )
