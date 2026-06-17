"""
Dashboard Layout API Endpoints

Provides:
- GET /dashboards - List dashboards (own + shared)
- POST /dashboards - Create dashboard
- GET /dashboards/{dashboard_id} - Get dashboard details
- PUT /dashboards/{dashboard_id} - Update dashboard
- DELETE /dashboards/{dashboard_id} - Delete dashboard
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from ...core.exceptions import DashboardNotFoundException
from ...core.logging_config import get_logger
from ...schemas.common import PaginationMeta
from ...schemas.dashboard import (
    DashboardCreate,
    DashboardDataResponse,
    DashboardListResponse,
    DashboardResponse,
    DashboardUpdate,
)
from ...services.dashboard_service import DashboardService
from ..deps import ActiveUser, DBSession, OperatorUser

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/dashboards", tags=["dashboards"])


# =============================================================================
# List Dashboards
# =============================================================================


@router.get(
    "",
    response_model=DashboardListResponse,
    summary="List dashboards",
    description="Get all dashboards owned by the current user plus shared dashboards.",
)
async def list_dashboards(
    db: DBSession,
    current_user: ActiveUser,
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 50,
) -> DashboardListResponse:
    """List dashboards visible to the current user."""
    service = DashboardService(db)
    dashboards, total = await service.list_dashboards(
        user_id=current_user.id,
        page=page,
        page_size=page_size,
    )

    return DashboardListResponse(
        success=True,
        data=[DashboardResponse.model_validate(d) for d in dashboards],
        pagination=PaginationMeta.from_pagination(
            page=page,
            page_size=page_size,
            total_items=total,
        ),
    )


# =============================================================================
# Get Dashboard
# =============================================================================


@router.get(
    "/{dashboard_id}",
    response_model=DashboardDataResponse,
    summary="Get dashboard",
    description="Get a single dashboard by ID.",
)
async def get_dashboard(
    dashboard_id: uuid.UUID,
    db: DBSession,
    current_user: ActiveUser,
) -> DashboardDataResponse:
    """Get a single dashboard by ID."""
    service = DashboardService(db)
    dashboard = await service.get_dashboard(
        dashboard_id=dashboard_id,
        user_id=current_user.id,
        is_admin=current_user.is_admin,
    )

    if dashboard is None:
        raise DashboardNotFoundException(dashboard_id)

    return DashboardDataResponse(
        success=True,
        data=DashboardResponse.model_validate(dashboard),
    )


# =============================================================================
# Create Dashboard
# =============================================================================


@router.post(
    "",
    response_model=DashboardDataResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create dashboard",
    description="Create a new dashboard layout.",
)
async def create_dashboard(
    data: DashboardCreate,
    db: DBSession,
    current_user: OperatorUser,
) -> DashboardDataResponse:
    """Create a new dashboard."""
    service = DashboardService(db)
    dashboard = await service.create_dashboard(
        data=data,
        owner_id=current_user.id,
    )

    return DashboardDataResponse(
        success=True,
        message="Dashboard created",
        data=DashboardResponse.model_validate(dashboard),
    )


# =============================================================================
# Update Dashboard
# =============================================================================


@router.put(
    "/{dashboard_id}",
    response_model=DashboardDataResponse,
    summary="Update dashboard",
    description="Update an existing dashboard. Only owner or admin can update.",
)
async def update_dashboard(
    dashboard_id: uuid.UUID,
    data: DashboardUpdate,
    db: DBSession,
    current_user: OperatorUser,
) -> DashboardDataResponse:
    """Update an existing dashboard."""
    service = DashboardService(db)
    dashboard = await service.update_dashboard(
        dashboard_id=dashboard_id,
        data=data,
        user_id=current_user.id,
        is_admin=current_user.is_admin,
    )

    if dashboard is None:
        raise DashboardNotFoundException(dashboard_id)

    return DashboardDataResponse(
        success=True,
        message="Dashboard updated",
        data=DashboardResponse.model_validate(dashboard),
    )


# =============================================================================
# Delete Dashboard
# =============================================================================


@router.delete(
    "/{dashboard_id}",
    response_model=DashboardDataResponse,
    summary="Delete dashboard",
    description="Delete a dashboard. Only owner or admin can delete.",
)
async def delete_dashboard(
    dashboard_id: uuid.UUID,
    db: DBSession,
    current_user: OperatorUser,
) -> DashboardDataResponse:
    """Delete a dashboard."""
    service = DashboardService(db)
    deleted = await service.delete_dashboard(
        dashboard_id=dashboard_id,
        user_id=current_user.id,
        is_admin=current_user.is_admin,
    )

    if not deleted:
        raise DashboardNotFoundException(dashboard_id)

    return DashboardDataResponse(
        success=True,
        message="Dashboard deleted",
    )
