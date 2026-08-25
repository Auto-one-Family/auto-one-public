"""
Plan Segment CRUD API (AUT-1232 Lücke / Vorbedingung AUT-1235 T5)

Endpoints:
- POST   /v1/plan-segments              — create segment (nutrient + climate)
- GET    /v1/plan-segments              — list filtered (zone/subzone/domain/measure/window)
- GET    /v1/plan-segments/climate-at   — climate Soll@at + derived VPD band (AUT-1239)
- GET    /v1/plan-segments/{segment_id} — get by id
- PATCH  /v1/plan-segments/{segment_id} — partial update
- DELETE /v1/plan-segments/{segment_id} — delete

Muster: zones.py (Router → PlanSegmentRepository direkt, kein Service-Zweitpfad).
Climate write = same POST body with domain=climate / measure=target_*.
Schemas: src/schemas/plan_segment.py. Keine Überlappungs-/Engine-Logik.
"""

from datetime import datetime
from typing import Annotated, List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, Query, status

from ...core.logging_config import get_logger
from ...db.repositories.plan_segment_repo import PlanSegmentRepository
from ...schemas.plan_segment import (
    ClimateMeasureTargetResponse,
    ClimateTargetsAtResponse,
    PlanSegmentCreate,
    PlanSegmentResponse,
    PlanSegmentUpdate,
    PlannedVpdBandResponse,
)
from ...services.planned_climate import resolve_climate_targets_at
from ..deps import ActiveUser, DBSession, OperatorUser

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/plan-segments", tags=["plan-segments"])


@router.post(
    "",
    response_model=PlanSegmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Plan Segment",
    description="Create a plan_segment (zone-mandatory; subzone assignments separate).",
    responses={
        201: {"description": "Segment created"},
    },
)
async def create_plan_segment(
    request: PlanSegmentCreate,
    db: DBSession,
    current_user: OperatorUser,
) -> PlanSegmentResponse:
    repo = PlanSegmentRepository(db)
    segment = await repo.create(**request.model_dump())
    await db.commit()
    await db.refresh(segment)

    logger.info(
        "Plan segment created by %s: id=%s zone_id=%s domain=%s measure=%s",
        current_user.username,
        segment.id,
        segment.zone_id,
        segment.domain,
        segment.measure,
    )
    return PlanSegmentResponse.model_validate(segment)


@router.get(
    "",
    response_model=List[PlanSegmentResponse],
    summary="List Plan Segments",
    description=(
        "List plan_segments filtered by zone_id, subzone_config_id, domain, "
        "measure, and optional time window (overlapping [from_ts, to_ts))."
    ),
)
async def list_plan_segments(
    db: DBSession,
    _user: ActiveUser,
    zone_id: Optional[str] = Query(None, description="Filter by zone_id"),
    subzone_config_id: Optional[UUID] = Query(
        None, description="Filter by subzone assignment (includes zone-wide)"
    ),
    domain: Optional[str] = Query(None, description="Filter by domain"),
    measure: Optional[str] = Query(None, description="Filter by measure"),
    from_ts: Optional[datetime] = Query(
        None, description="Window start (inclusive); overlapping segments"
    ),
    to_ts: Optional[datetime] = Query(
        None, description="Window end (exclusive); overlapping segments"
    ),
) -> List[PlanSegmentResponse]:
    repo = PlanSegmentRepository(db)
    segments = await repo.list_filtered(
        zone_id=zone_id,
        subzone_config_id=subzone_config_id,
        domain=domain,
        measure=measure,
        from_ts=from_ts,
        to_ts=to_ts,
    )
    return [PlanSegmentResponse.model_validate(s) for s in segments]


@router.get(
    "/climate-at",
    response_model=ClimateTargetsAtResponse,
    summary="Climate targets at timestamp + derived VPD band",
    description=(
        "Resolve domain=climate plan_segments (target_temperature + "
        "target_humidity) at `at` via the same resolve_at path as EC/pH. "
        "VPD is derived from the two planned values (vpd_calculator) — "
        "never stored as its own measure (AUT-1239)."
    ),
)
async def get_climate_targets_at(
    db: DBSession,
    _user: ActiveUser,
    zone_id: str = Query(..., description="Zone identifier"),
    at: Optional[datetime] = Query(None, description="Evaluation time (UTC); default = now"),
    subzone_config_id: Optional[UUID] = Query(
        None, description="Optional subzone scope (includes zone-wide segments)"
    ),
) -> ClimateTargetsAtResponse:
    result = await resolve_climate_targets_at(
        session=db,
        zone_id=zone_id,
        at=at,
        subzone_config_id=subzone_config_id,
    )
    return ClimateTargetsAtResponse(
        zone_id=result.zone_id,
        subzone_config_id=result.subzone_config_id,
        at=result.at,
        domain=result.domain,
        targets=[
            ClimateMeasureTargetResponse(
                measure=t.measure,
                value=t.value,
                tolerance=t.tolerance,
                segment_id=t.segment_id,
                from_ts=t.from_ts,
                to_ts=t.to_ts,
                resolved_via=t.resolved_via,
            )
            for t in result.targets
        ],
        vpd_band=PlannedVpdBandResponse(
            computable=result.vpd_band.computable,
            reason=result.vpd_band.reason,
            vpd_kpa=result.vpd_band.vpd_kpa,
            vpd_min_kpa=result.vpd_band.vpd_min_kpa,
            vpd_max_kpa=result.vpd_band.vpd_max_kpa,
            source=result.vpd_band.source,
        ),
    )


@router.get(
    "/{segment_id}",
    response_model=PlanSegmentResponse,
    summary="Get Plan Segment",
    description="Get a single plan_segment by id.",
    responses={
        200: {"description": "Segment found"},
        404: {"description": "Segment not found"},
    },
)
async def get_plan_segment(
    segment_id: Annotated[UUID, Path(description="Plan segment UUID")],
    db: DBSession,
    _user: ActiveUser,
) -> PlanSegmentResponse:
    repo = PlanSegmentRepository(db)
    segment = await repo.get_by_id(segment_id)
    if segment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan segment '{segment_id}' not found",
        )
    return PlanSegmentResponse.model_validate(segment)


@router.patch(
    "/{segment_id}",
    response_model=PlanSegmentResponse,
    summary="Update Plan Segment",
    description="Partially update a plan_segment. Only provided fields are changed.",
    responses={
        200: {"description": "Segment updated"},
        400: {"description": "No fields to update"},
        404: {"description": "Segment not found"},
    },
)
async def update_plan_segment(
    segment_id: Annotated[UUID, Path(description="Plan segment UUID")],
    request: PlanSegmentUpdate,
    db: DBSession,
    current_user: OperatorUser,
) -> PlanSegmentResponse:
    update_data = request.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    repo = PlanSegmentRepository(db)
    updated = await repo.update(id=segment_id, **update_data)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan segment '{segment_id}' not found",
        )

    await db.commit()
    await db.refresh(updated)

    logger.info(
        "Plan segment updated by %s: id=%s fields=%s",
        current_user.username,
        segment_id,
        list(update_data.keys()),
    )
    return PlanSegmentResponse.model_validate(updated)


@router.delete(
    "/{segment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Plan Segment",
    description="Delete a plan_segment by id.",
    responses={
        204: {"description": "Segment deleted"},
        404: {"description": "Segment not found"},
    },
)
async def delete_plan_segment(
    segment_id: Annotated[UUID, Path(description="Plan segment UUID")],
    db: DBSession,
    current_user: OperatorUser,
) -> None:
    repo = PlanSegmentRepository(db)
    deleted = await repo.delete(segment_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan segment '{segment_id}' not found",
        )

    await db.commit()
    logger.info(
        "Plan segment deleted by %s: id=%s",
        current_user.username,
        segment_id,
    )
