"""
Dashboard Layout API Endpoints

Provides:
- GET /dashboards - List dashboards (own + shared + explicitly assigned)
- POST /dashboards - Create dashboard
- GET /dashboards/{dashboard_id} - Get dashboard details
- PUT /dashboards/{dashboard_id} - Update dashboard
- DELETE /dashboards/{dashboard_id} - Delete dashboard
- POST /dashboards/{dashboard_id}/assignments - Assign user (AUT-1095)
- DELETE /dashboards/{dashboard_id}/assignments/{user_id} - Unassign user (AUT-1095)
- GET /dashboards/{dashboard_id}/assignments - List assignments (AUT-1095)
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from ...core.exceptions import DashboardNotFoundException
from ...core.logging_config import get_logger
from ...schemas.common import PaginationMeta
from ...schemas.dashboard import (
    DashboardAssignmentCreate,
    DashboardAssignmentListResponse,
    DashboardAssignmentResponse,
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


# =============================================================================
# Dashboard User Assignments (AUT-1095)
# =============================================================================


@router.post(
    "/{dashboard_id}/assignments",
    response_model=DashboardAssignmentListResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Assign user to dashboard",
    description=(
        "Explicitly assign a user to a dashboard. "
        "The user will see the dashboard even if it is not shared. "
        "Requires operator or admin role. Returns 409 if the assignment already exists."
    ),
)
async def assign_user_to_dashboard(
    dashboard_id: uuid.UUID,
    data: DashboardAssignmentCreate,
    db: DBSession,
    current_user: OperatorUser,
) -> DashboardAssignmentListResponse:
    """Assign a user to a dashboard (operator only)."""
    service = DashboardService(db)
    try:
        assignment = await service.assign_user(
            dashboard_id=dashboard_id,
            user_id=data.user_id,
            operator_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )

    if assignment is None:
        raise DashboardNotFoundException(dashboard_id)

    return DashboardAssignmentListResponse(
        success=True,
        message="User assigned to dashboard",
        data=[DashboardAssignmentResponse.model_validate(assignment)],
    )


@router.delete(
    "/{dashboard_id}/assignments/{user_id}",
    response_model=DashboardAssignmentListResponse,
    summary="Unassign user from dashboard",
    description=(
        "Remove a user's explicit assignment from a dashboard. " "Requires operator or admin role."
    ),
)
async def unassign_user_from_dashboard(
    dashboard_id: uuid.UUID,
    user_id: int,
    db: DBSession,
    current_user: OperatorUser,
) -> DashboardAssignmentListResponse:
    """Remove a user's explicit assignment from a dashboard (operator only)."""
    service = DashboardService(db)
    deleted = await service.unassign_user(
        dashboard_id=dashboard_id,
        user_id=user_id,
        operator_id=current_user.id,
    )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assignment for user {user_id} on dashboard {dashboard_id} not found",
        )

    return DashboardAssignmentListResponse(
        success=True,
        message="User unassigned from dashboard",
        data=[],
    )


@router.get(
    "/{dashboard_id}/assignments",
    response_model=DashboardAssignmentListResponse,
    summary="List dashboard assignments",
    description=(
        "List all explicit user assignments for a dashboard. " "Requires operator or admin role."
    ),
)
async def list_dashboard_assignments(
    dashboard_id: uuid.UUID,
    db: DBSession,
    current_user: OperatorUser,
) -> DashboardAssignmentListResponse:
    """List all explicit user assignments for a dashboard (operator only)."""
    service = DashboardService(db)
    assignments = await service.list_assignments(dashboard_id=dashboard_id)

    if assignments is None:
        raise DashboardNotFoundException(dashboard_id)

    return DashboardAssignmentListResponse(
        success=True,
        data=[DashboardAssignmentResponse.model_validate(a) for a in assignments],
    )
