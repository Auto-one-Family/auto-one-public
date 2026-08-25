"""
Stock Mix Recipe Repository (AUT-1361 / P9).
"""

from __future__ import annotations

from typing import List, Optional
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.stock_mix_recipe import StockMixRecipe
from .base_repo import BaseRepository


class StockMixRecipeRepository(BaseRepository[StockMixRecipe]):
    """Data access for stock_mix_recipes."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(StockMixRecipe, session)

    async def list_filtered(
        self,
        *,
        dose_role: Optional[str] = None,
        nutrient_phase: Optional[str] = None,
        coverage: Optional[str] = None,
        active_only: bool = True,
    ) -> List[StockMixRecipe]:
        conditions = []
        if active_only:
            conditions.append(StockMixRecipe.active.is_(True))
        if dose_role is not None:
            conditions.append(StockMixRecipe.dose_role == dose_role)
        if nutrient_phase is not None:
            conditions.append(StockMixRecipe.nutrient_phase == nutrient_phase)
        if coverage is not None:
            conditions.append(StockMixRecipe.coverage == coverage)

        stmt = select(StockMixRecipe)
        if conditions:
            stmt = stmt.where(*conditions)
        stmt = stmt.order_by(
            StockMixRecipe.dose_role.asc(),
            StockMixRecipe.nutrient_phase.asc().nullsfirst(),
            StockMixRecipe.label.asc(),
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def lookup(
        self,
        *,
        dose_role: str,
        nutrient_phase: Optional[str] = None,
    ) -> Optional[StockMixRecipe]:
        """
        Resolve recipe for dose_role × phase.

        Preference: active phase_specific match, else active universal for role.
        """
        if nutrient_phase is not None:
            stmt = (
                select(StockMixRecipe)
                .where(
                    StockMixRecipe.active.is_(True),
                    StockMixRecipe.dose_role == dose_role,
                    StockMixRecipe.coverage == "phase_specific",
                    StockMixRecipe.nutrient_phase == nutrient_phase,
                )
                .limit(1)
            )
            result = await self.session.execute(stmt)
            row = result.scalar_one_or_none()
            if row is not None:
                return row

        stmt = (
            select(StockMixRecipe)
            .where(
                StockMixRecipe.active.is_(True),
                StockMixRecipe.dose_role == dose_role,
                StockMixRecipe.coverage == "universal",
                StockMixRecipe.nutrient_phase.is_(None),
            )
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_fields(
        self,
        recipe_id: uuid.UUID,
        **fields: object,
    ) -> Optional[StockMixRecipe]:
        """Patch provided fields (caller passes exclude_unset dump)."""
        recipe = await self.get_by_id(recipe_id)
        if recipe is None:
            return None
        for key, value in fields.items():
            setattr(recipe, key, value)
        await self.session.flush()
        await self.session.refresh(recipe)
        return recipe
