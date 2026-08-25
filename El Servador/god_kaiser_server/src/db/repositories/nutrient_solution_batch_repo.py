"""
Nutrient Solution Batch Repository

AUT-1217 — append-only ledger writes for tank chemistry bookkeeping.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.nutrient_solution_batch import NutrientSolutionBatch
from .base_repo import BaseRepository


class NutrientSolutionBatchRepository(BaseRepository[NutrientSolutionBatch]):
    """Repository for NutrientSolutionBatch ledger entries."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(NutrientSolutionBatch, session)

    async def get_by_tank(
        self, tank_id: uuid.UUID, *, limit: int = 100
    ) -> List[NutrientSolutionBatch]:
        """Return ledger entries for a tank, newest first."""
        stmt = (
            select(NutrientSolutionBatch)
            .where(NutrientSolutionBatch.tank_id == tank_id)
            .order_by(NutrientSolutionBatch.occurred_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_entry(
        self,
        *,
        tank_id: uuid.UUID,
        entry_type: str,
        volume_l: float,
        components: List[Dict[str, Any]],
        acquisition_method: str,
        qualifier: str,
        occurred_at: Optional[datetime] = None,
        recipe_label: Optional[str] = None,
        ec_measured_after: Optional[float] = None,
        ec_was_measured: bool = False,
        ph_measured_after: Optional[float] = None,
        ph_was_measured: bool = False,
        prior_volume_l: Optional[float] = None,
        prior_ec_ms_cm: Optional[float] = None,
    ) -> NutrientSolutionBatch:
        """
        Persist a new ledger entry and return the flushed/refreshed row.

        Return shape is intentionally the ORM instance so a later EC control
        anchor (AUT-1218 / S7) can dock without reshaping this method.

        AUT-1346: ``prior_volume_l`` / ``prior_ec_ms_cm`` are optional and
        nullable — omit (None) when unknown; never invent values.
        """
        kwargs: Dict[str, Any] = {
            "tank_id": tank_id,
            "entry_type": entry_type,
            "volume_l": volume_l,
            "components": components,
            "acquisition_method": acquisition_method,
            "qualifier": qualifier,
            "recipe_label": recipe_label,
            "ec_measured_after": ec_measured_after,
            "ec_was_measured": ec_was_measured,
            "ph_measured_after": ph_measured_after,
            "ph_was_measured": ph_was_measured,
            "prior_volume_l": prior_volume_l,
            "prior_ec_ms_cm": prior_ec_ms_cm,
        }
        if occurred_at is not None:
            kwargs["occurred_at"] = occurred_at
        return await self.create(**kwargs)
