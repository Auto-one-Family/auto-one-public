"""
Scheduler Health API (AUT-194 — AC8).

Exposes the in-memory CentralScheduler status (job counts per category, total
executions, total errors). Useful for verifying that DailyAnalysisJob is wired
in alongside maintenance/monitor/sensor_schedule jobs.

Auth: ActiveUser (read-only operational visibility).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ...core.logging_config import get_logger
from ...core.scheduler import CentralScheduler, JobCategory, get_central_scheduler
from ..deps import ActiveUser

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/scheduler", tags=["scheduler"])


@router.get(
    "/health",
    summary="CentralScheduler health snapshot",
    description=(
        "Returns the in-memory scheduler status: total jobs, jobs grouped by "
        "category (mock, maintenance, monitor, custom, sensor_schedule, "
        "daily_analysis), total executions and total errors."
    ),
)
async def get_scheduler_health(
    _user: ActiveUser,
    scheduler: CentralScheduler = Depends(get_central_scheduler),
) -> dict[str, Any]:
    """GET /api/v1/scheduler/health — scheduler.get_scheduler_status()."""
    status = scheduler.get_scheduler_status()
    daily_jobs = scheduler.get_jobs_by_category(JobCategory.DAILY_ANALYSIS)
    status["daily_analysis_jobs"] = daily_jobs
    return status
