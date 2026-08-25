"""
Zone Context Service — Business Logic for Zone-Level Metadata

Phase: K3 → Phase 2 Refactoring
Status: IMPLEMENTED

Provides:
- CRUD operations for zone business context (plant info, material, work)
- Zone-name synchronisation with ESPDevice assignments
- Context summary for device inheritance (Phase 4)
- Cycle archival

Used by:
- REST API (api/v1/zone_context.py)
- ZoneService (zone-name sync on assign)
- ESP API (device context inheritance — Phase 4)
"""

from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logging_config import get_logger
from ..db.models.zone_context import ZoneContext
from ..db.repositories.plant_repo import PlantRepository
from ..db.repositories.zone_context_repo import ZoneContextRepository
from ..schemas.zone_context import ZoneContextResponse
from .growth_phase_vocabulary import majority_phase, normalize_growth_phase

logger = get_logger(__name__)


def model_to_response(
    ctx: ZoneContext,
    *,
    resolved_growth_phase: Optional[str] = None,
    growth_phase_source: Optional[str] = None,
    active_plant_id: Optional[str] = None,
) -> ZoneContextResponse:
    """Convert SQLAlchemy model to Pydantic response with computed fields."""
    stored = normalize_growth_phase(ctx.growth_phase) or ctx.growth_phase
    return ZoneContextResponse(
        id=ctx.id,
        zone_id=ctx.zone_id,
        zone_name=ctx.zone_name,
        plant_count=ctx.plant_count,
        variety=ctx.variety,
        substrate=ctx.substrate,
        growth_phase=stored,
        planted_date=ctx.planted_date,
        expected_harvest=ctx.expected_harvest,
        responsible_person=ctx.responsible_person,
        work_hours_weekly=ctx.work_hours_weekly,
        notes=ctx.notes,
        custom_data=ctx.custom_data or {},
        cycle_history=ctx.cycle_history or [],
        created_at=ctx.created_at,
        updated_at=ctx.updated_at,
        plant_age_days=ctx.plant_age_days,
        days_to_harvest=ctx.days_to_harvest,
        resolved_growth_phase=resolved_growth_phase or stored,
        growth_phase_source=growth_phase_source or ("zone_context" if stored else None),
        active_plant_id=active_plant_id,
    )


class ZoneContextService:
    """
    Zone context business logic.

    Manages zone-level metadata: plants, substrate, growth phase,
    responsible person, cycle history, and custom fields.
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = ZoneContextRepository(session)

    async def get_by_zone_id(self, zone_id: str) -> Optional[ZoneContext]:
        return await self.repo.get_by_zone_id(zone_id)

    async def get_all(self, page: int = 1, page_size: int = 50) -> tuple[List[ZoneContext], int]:
        return await self.repo.get_all(page, page_size)

    async def resolve_zone_phase(
        self, zone_id: str
    ) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """Return (phase, source, plant_id) without writing plants."""
        plant_repo = PlantRepository(self.session)
        plants = await plant_repo.get_active(zone_id=zone_id, limit=500)
        majority = majority_phase([p.phase for p in plants])
        if majority is not None:
            match = next(
                (p for p in plants if normalize_growth_phase(p.phase) == majority),
                None,
            )
            plant_id = str(match.plant_id) if match is not None else None
            return majority, "plant", plant_id
        ctx = await self.repo.get_by_zone_id(zone_id)
        stored = normalize_growth_phase(ctx.growth_phase) if ctx else None
        if stored is not None:
            return stored, "zone_context", None
        return None, None, None

    async def sync_growth_phase_from_plants(self, zone_id: str) -> Optional[str]:
        """Cache the active plant phase on zone_contexts — never the reverse."""
        phase, source, _plant_id = await self.resolve_zone_phase(zone_id)
        if source != "plant" or phase is None:
            return phase
        ctx = await self.repo.get_by_zone_id(zone_id)
        if ctx is None:
            await self.repo.upsert(zone_id, {"growth_phase": phase})
            return phase
        if ctx.growth_phase != phase:
            ctx.growth_phase = phase
            await self.session.flush()
        return phase

    def _prepare_write(self, data: Dict[str, Any], *, plant_phase: Optional[str]) -> Dict[str, Any]:
        """Keep spatial/context writes on ZoneContext; phase SSOT is the plant."""
        prepared = dict(data)
        if "growth_phase" in prepared:
            raw = prepared["growth_phase"]
            if raw is None or raw == "":
                prepared["growth_phase"] = None
            else:
                prepared["growth_phase"] = normalize_growth_phase(raw) or raw
        if plant_phase is not None:
            # Plants exist: zone save must not invent a second phase object.
            prepared["growth_phase"] = plant_phase
        return prepared

    async def upsert(self, zone_id: str, data: Dict[str, Any], username: str) -> ZoneContext:
        logger.info(f"Zone context upsert for '{zone_id}' by {username}")
        plant_phase, _source, _pid = await self.resolve_zone_phase(zone_id)
        return await self.repo.upsert(zone_id, self._prepare_write(data, plant_phase=plant_phase))

    async def patch(
        self, zone_id: str, data: Dict[str, Any], username: str
    ) -> Optional[ZoneContext]:
        logger.info(f"Zone context patch for '{zone_id}' by {username}")
        plant_phase, _source, _pid = await self.resolve_zone_phase(zone_id)
        return await self.repo.patch(zone_id, self._prepare_write(data, plant_phase=plant_phase))

    async def archive_cycle(self, zone_id: str, username: str) -> Optional[dict]:
        logger.info(f"Cycle archive for zone '{zone_id}' by {username}")
        return await self.repo.archive_cycle(zone_id, username)

    async def get_cycle_history(self, zone_id: str) -> Optional[list]:
        ctx = await self.repo.get_by_zone_id(zone_id)
        if not ctx:
            return None
        return ctx.cycle_history or []

    # -----------------------------------------------------------------
    # Zone-name synchronisation (called from ZoneService on assign)
    # -----------------------------------------------------------------

    async def sync_zone_name(self, zone_id: str, zone_name: Optional[str]) -> None:
        """Keep ZoneContext.zone_name in sync when zone is assigned."""
        await self.repo.sync_zone_name(zone_id, zone_name)

    # -----------------------------------------------------------------
    # Device context inheritance (Phase 4)
    # -----------------------------------------------------------------

    async def get_context_summary(self, zone_id: str) -> Optional[dict]:
        """Lightweight context dict suitable for embedding in device responses."""
        return await self.repo.get_context_summary(zone_id)

    async def get_zones_by_growth_phase(self, phase: str) -> List[ZoneContext]:
        return await self.repo.get_zones_by_growth_phase(phase)
