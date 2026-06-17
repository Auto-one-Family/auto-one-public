"""
Zone Context REST API

Phase: K3 - Zone-Context Data Model
Status: IMPLEMENTED (refactored to use Service layer)

Provides REST endpoints for zone-level business context:
plants, variety, substrate, growth phase, cycle archival.

Endpoints:
- GET /zone/context - List all zone contexts
- GET /zone/context/{zone_id} - Get context for a zone
- PUT /zone/context/{zone_id} - Create or update (upsert)
- PATCH /zone/context/{zone_id} - Partial update
- POST /zone/context/{zone_id}/archive-cycle - Archive current cycle
- GET /zone/context/{zone_id}/history - Get cycle history
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query

from ..deps import ActiveUser, DBSession, OperatorUser
from ...schemas.zone_context import (
    CycleArchiveResponse,
    CycleHistoryResponse,
    ZoneContextListResponse,
    ZoneContextResponse,
    ZoneContextUpdate,
)
from ...services.zone_context_service import ZoneContextService, model_to_response
from ...services.zone_kpi_service import ZoneKPIService

router = APIRouter(
    prefix="/v1/zone/context",
    tags=["zone-context"],
)


# =============================================================================
# List Endpoint
# =============================================================================


@router.get(
    "",
    response_model=ZoneContextListResponse,
    summary="List all zone contexts",
    description="Get all zone contexts with optional pagination.",
)
async def list_zone_contexts(
    session: DBSession,
    _user: ActiveUser,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
) -> ZoneContextListResponse:
    """List all zone contexts."""
    service = ZoneContextService(session)
    contexts, total = await service.get_all(page, page_size)

    return ZoneContextListResponse(
        success=True,
        data=[model_to_response(ctx) for ctx in contexts],
        total_count=total,
    )


# =============================================================================
# Single Zone Endpoints
# =============================================================================


@router.get(
    "/{zone_id}",
    response_model=ZoneContextResponse,
    summary="Get zone context",
    description="Get the business context for a specific zone.",
    responses={404: {"description": "Zone context not found"}},
)
async def get_zone_context(
    zone_id: Annotated[str, Path(description="Zone identifier", max_length=50)],
    session: DBSession,
    _user: ActiveUser,
) -> ZoneContextResponse:
    """Get context for a specific zone."""
    service = ZoneContextService(session)
    ctx = await service.get_by_zone_id(zone_id)

    if not ctx:
        raise HTTPException(status_code=404, detail=f"Zone context for '{zone_id}' not found")

    return model_to_response(ctx)


@router.put(
    "/{zone_id}",
    response_model=ZoneContextResponse,
    summary="Create or update zone context (upsert)",
    description="Create a new zone context or fully replace an existing one.",
)
async def upsert_zone_context(
    zone_id: Annotated[str, Path(description="Zone identifier", max_length=50)],
    body: ZoneContextUpdate,
    session: DBSession,
    user: OperatorUser,
) -> ZoneContextResponse:
    """Create or update zone context (upsert)."""
    service = ZoneContextService(session)
    update_data = body.model_dump(exclude_unset=False, exclude_none=False)
    ctx = await service.upsert(zone_id, update_data, user.username)

    await session.commit()
    await session.refresh(ctx)

    return model_to_response(ctx)


@router.patch(
    "/{zone_id}",
    response_model=ZoneContextResponse,
    summary="Partial update zone context",
    description="Update specific fields of a zone context. Only provided fields are updated.",
    responses={404: {"description": "Zone context not found"}},
)
async def patch_zone_context(
    zone_id: Annotated[str, Path(description="Zone identifier", max_length=50)],
    body: ZoneContextUpdate,
    session: DBSession,
    user: OperatorUser,
) -> ZoneContextResponse:
    """Partial update of zone context."""
    service = ZoneContextService(session)
    update_data = body.model_dump(exclude_unset=True)
    ctx = await service.patch(zone_id, update_data, user.username)

    if not ctx:
        raise HTTPException(status_code=404, detail=f"Zone context for '{zone_id}' not found")

    await session.commit()
    await session.refresh(ctx)

    return model_to_response(ctx)


# =============================================================================
# Cycle Management
# =============================================================================


@router.post(
    "/{zone_id}/archive-cycle",
    response_model=CycleArchiveResponse,
    summary="Archive current growing cycle",
    description="""
    Archive the current growing cycle and reset cycle-specific fields.

    **What happens:**
    1. Current cycle data (variety, planted_date, etc.) is saved to cycle_history
    2. Cycle-specific fields are reset to NULL
    3. Zone context remains, ready for next cycle

    **Archived fields:** variety, substrate, growth_phase, planted_date,
    expected_harvest, plant_count, notes, custom_data
    """,
    responses={404: {"description": "Zone context not found"}},
)
async def archive_cycle(
    zone_id: Annotated[str, Path(description="Zone identifier", max_length=50)],
    session: DBSession,
    user: OperatorUser,
) -> CycleArchiveResponse:
    """Archive current cycle and reset fields."""
    service = ZoneContextService(session)
    archived_cycle = await service.archive_cycle(zone_id, user.username)

    if archived_cycle is None:
        raise HTTPException(status_code=404, detail=f"Zone context for '{zone_id}' not found")

    await session.commit()

    ctx = await service.get_by_zone_id(zone_id)
    cycle_count = len(ctx.cycle_history) if ctx else 0

    return CycleArchiveResponse(
        success=True,
        message="Zyklus erfolgreich archiviert",
        zone_id=zone_id,
        archived_cycle=archived_cycle,
        cycle_number=cycle_count,
    )


@router.get(
    "/{zone_id}/history",
    response_model=CycleHistoryResponse,
    summary="Get cycle history",
    description="Get the history of archived growing cycles for a zone.",
    responses={404: {"description": "Zone context not found"}},
)
async def get_cycle_history(
    zone_id: Annotated[str, Path(description="Zone identifier", max_length=50)],
    session: DBSession,
    _user: ActiveUser,
) -> CycleHistoryResponse:
    """Get archived cycle history."""
    service = ZoneContextService(session)
    cycles = await service.get_cycle_history(zone_id)

    if cycles is None:
        raise HTTPException(status_code=404, detail=f"Zone context for '{zone_id}' not found")

    return CycleHistoryResponse(
        success=True,
        zone_id=zone_id,
        cycles=cycles,
        total_count=len(cycles),
    )


# =============================================================================
# Zone KPIs (Phase 5)
# =============================================================================


@router.get(
    "/{zone_id}/kpis",
    summary="Get zone KPIs",
    description="Calculated KPIs: VPD, DLI, growth progress, zone health score.",
)
async def get_zone_kpis(
    zone_id: Annotated[str, Path(description="Zone identifier", max_length=50)],
    session: DBSession,
    _user: ActiveUser,
) -> dict:
    """Get real-time calculated KPIs for a zone."""
    kpi_service = ZoneKPIService(session)
    return await kpi_service.get_all_kpis(zone_id)
