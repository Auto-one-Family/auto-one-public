"""
Applied Setpoint Log Read API (AUT-1236 T6 precondition / AUT-1243 origin)

Endpoints:
- GET /v1/applied-setpoint-logs — list filtered (zone/subzone/domain/measure/rule/window)

Immutable table — read-only. Write path remains T3 (plan_setpoint_resolver).
Muster: plan_segments.py (Router → Repository, kein Service-Zweitpfad).
Schemas: src/schemas/plan_segment.py::AppliedSetpointLogResponse.
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Query

from ...core.logging_config import get_logger
from ...db.repositories.applied_setpoint_log_repo import AppliedSetpointLogRepository
from ...schemas.plan_segment import AppliedSetpointLogResponse
from ..deps import ActiveUser, DBSession

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/applied-setpoint-logs", tags=["applied-setpoint-logs"])


@router.get(
    "",
    response_model=List[AppliedSetpointLogResponse],
    summary="List Applied Setpoint Logs",
    description=(
        "Read-only list of immutable applied_setpoint_logs rows, filtered by "
        "zone_id, subzone_config_id, domain, measure, rule_id, and optional "
        "time window on effective_at ([from_ts, to_ts))."
    ),
)
async def list_applied_setpoint_logs(
    db: DBSession,
    _user: ActiveUser,
    zone_id: Optional[str] = Query(None, description="Filter by zone_id"),
    subzone_config_id: Optional[UUID] = Query(
        None, description="Filter by subzone_config_id"
    ),
    domain: Optional[str] = Query(None, description="Filter by domain"),
    measure: Optional[str] = Query(None, description="Filter by measure"),
    rule_id: Optional[UUID] = Query(None, description="Filter by consuming rule id"),
    from_ts: Optional[datetime] = Query(
        None, description="Window start (inclusive) on effective_at"
    ),
    to_ts: Optional[datetime] = Query(
        None, description="Window end (exclusive) on effective_at"
    ),
    limit: int = Query(500, ge=1, le=2000, description="Max rows (cap 2000)"),
) -> List[AppliedSetpointLogResponse]:
    repo = AppliedSetpointLogRepository(db)
    rows = await repo.list_filtered(
        zone_id=zone_id,
        subzone_config_id=subzone_config_id,
        domain=domain,
        measure=measure,
        rule_id=rule_id,
        from_ts=from_ts,
        to_ts=to_ts,
        limit=limit,
    )
    return [AppliedSetpointLogResponse.model_validate(r) for r in rows]
