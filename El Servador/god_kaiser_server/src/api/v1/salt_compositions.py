"""
Salt Composition CRUD (AUT-1418 / B1)

Endpoints:
- POST   /v1/salt-compositions
- GET    /v1/salt-compositions
- GET    /v1/salt-compositions/{salt_id}
- PATCH  /v1/salt-compositions/{salt_id}
- DELETE /v1/salt-compositions/{salt_id}  (soft: active=false)

Muster: stock_mix_recipes.py (Router → Repository, kein Service-Zweitpfad).
"""

from __future__ import annotations

from typing import Annotated, List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, Query, status

from ...core.logging_config import get_logger
from ...db.repositories.salt_composition_repo import SaltCompositionRepository
from ...db.repositories.stock_mix_recipe_repo import StockMixRecipeRepository
from ...schemas.salt_composition import (
    SaltCompositionCreate,
    SaltCompositionResponse,
    SaltCompositionUpdate,
)
from ...services.stock_mix_npk import recompute_and_persist_recipe
from ..deps import ActiveUser, DBSession, OperatorUser

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/salt-compositions", tags=["salt-compositions"])


def _to_response(row) -> SaltCompositionResponse:
    return SaltCompositionResponse.model_validate(row)


@router.post(
    "",
    response_model=SaltCompositionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create salt composition",
)
async def create_salt_composition(
    request: SaltCompositionCreate,
    db: DBSession,
    current_user: OperatorUser,
) -> SaltCompositionResponse:
    repo = SaltCompositionRepository(db)
    existing = await repo.get_by_name(request.name, active_only=True)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Active salt composition already exists for name={request.name!r}",
        )
    row = await repo.create(**request.model_dump())
    await db.commit()
    await db.refresh(row)
    logger.info(
        "Salt composition created by %s: id=%s name=%s source=%s",
        current_user.username,
        row.id,
        row.name,
        row.source_type,
    )
    return _to_response(row)


@router.get(
    "",
    response_model=List[SaltCompositionResponse],
    summary="List salt compositions",
)
async def list_salt_compositions(
    db: DBSession,
    _user: ActiveUser,
    source_type: Optional[str] = Query(None),
    include_inactive: bool = Query(False),
) -> List[SaltCompositionResponse]:
    repo = SaltCompositionRepository(db)
    rows = await repo.list_filtered(
        source_type=source_type,
        active_only=not include_inactive,
    )
    return [_to_response(r) for r in rows]


@router.get(
    "/{salt_id}",
    response_model=SaltCompositionResponse,
    summary="Get salt composition by id",
)
async def get_salt_composition(
    db: DBSession,
    _user: ActiveUser,
    salt_id: Annotated[UUID, Path()],
) -> SaltCompositionResponse:
    repo = SaltCompositionRepository(db)
    row = await repo.get_by_id(salt_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Salt not found")
    return _to_response(row)


@router.patch(
    "/{salt_id}",
    response_model=SaltCompositionResponse,
    summary="Update salt composition",
)
async def update_salt_composition(
    request: SaltCompositionUpdate,
    db: DBSession,
    current_user: OperatorUser,
    salt_id: Annotated[UUID, Path()],
) -> SaltCompositionResponse:
    repo = SaltCompositionRepository(db)
    fields = request.model_dump(exclude_unset=True)
    if "name" in fields:
        conflict = await repo.get_by_name(fields["name"], active_only=True)
        if conflict is not None and conflict.id != salt_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Active salt composition already exists for name={fields['name']!r}",
            )
    row = await repo.update_fields(salt_id, **fields)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Salt not found")

    # Label/composition edits invalidate feedforward NPK on recipes using this salt.
    recipe_repo = StockMixRecipeRepository(db)
    salt_name = row.name
    salt_id_str = str(row.id)
    for recipe in await recipe_repo.list_filtered(active_only=True):
        comps = list(recipe.components or [])
        uses = False
        for raw in comps:
            if not isinstance(raw, dict):
                continue
            if str(raw.get("name") or "").strip() == salt_name:
                uses = True
                break
            sid = raw.get("salt_composition_id")
            if sid is not None and str(sid) == salt_id_str:
                uses = True
                break
        if uses:
            await recompute_and_persist_recipe(db, recipe)

    await db.commit()
    await db.refresh(row)
    logger.info(
        "Salt composition updated by %s: id=%s (NPK recompute for matching recipes)",
        current_user.username,
        row.id,
    )
    return _to_response(row)


@router.delete(
    "/{salt_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete salt composition (active=false)",
)
async def delete_salt_composition(
    db: DBSession,
    current_user: OperatorUser,
    salt_id: Annotated[UUID, Path()],
) -> None:
    repo = SaltCompositionRepository(db)
    row = await repo.update_fields(salt_id, active=False)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Salt not found")
    await db.commit()
    logger.info(
        "Salt composition soft-deleted by %s: id=%s",
        current_user.username,
        salt_id,
    )
