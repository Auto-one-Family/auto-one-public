"""
Dashboard Service

Business logic for dashboard CRUD operations.
Handles ownership checks and shared dashboard access.
"""

import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logging_config import get_logger
from ..db.models.dashboard import Dashboard
from ..db.repositories.dashboard_repo import DashboardRepository
from ..schemas.dashboard import DashboardCreate, DashboardUpdate

logger = get_logger(__name__)


class DashboardService:
    """
    Dashboard Service with CRUD operations and ownership enforcement.

    All mutations require ownership verification (or admin role).
    """

    def __init__(self, session: AsyncSession):
        self.repo = DashboardRepository(session)
        self.session = session

    async def list_dashboards(
        self,
        user_id: int,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[Dashboard], int]:
        """
        List dashboards visible to a user (owned + shared).

        Args:
            user_id: Current user ID
            page: Page number (1-indexed)
            page_size: Items per page

        Returns:
            Tuple of (dashboards list, total count)
        """
        skip = (page - 1) * page_size
        dashboards = await self.repo.get_user_dashboards(
            owner_id=user_id,
            skip=skip,
            limit=page_size,
        )
        total = await self.repo.count_user_dashboards(user_id)
        return dashboards, total

    async def get_dashboard(
        self,
        dashboard_id: uuid.UUID,
        user_id: int,
        is_admin: bool = False,
    ) -> Optional[Dashboard]:
        """
        Get a single dashboard by ID.

        Returns the dashboard if user owns it, it's shared, or user is admin.

        Args:
            dashboard_id: Dashboard UUID
            user_id: Current user ID
            is_admin: Whether user has admin role

        Returns:
            Dashboard instance or None if not found/not accessible
        """
        dashboard = await self.repo.get_by_id(dashboard_id)
        if dashboard is None:
            return None

        # Access check: owner, shared, or admin
        if dashboard.owner_id == user_id or dashboard.is_shared or is_admin:
            return dashboard

        logger.warning(
            f"User {user_id} attempted to access dashboard {dashboard_id} "
            f"owned by {dashboard.owner_id}"
        )
        return None

    async def create_dashboard(
        self,
        data: DashboardCreate,
        owner_id: int,
    ) -> Dashboard:
        """
        Create a new dashboard.

        Args:
            data: Dashboard creation data
            owner_id: ID of the creating user

        Returns:
            Created Dashboard instance
        """
        # Convert widgets to plain dicts for JSON storage
        widgets_json = [w.model_dump() for w in data.widgets]

        dashboard = await self.repo.create(
            name=data.name,
            description=data.description,
            owner_id=owner_id,
            is_shared=data.is_shared,
            widgets=widgets_json,
            scope=data.scope,
            zone_id=data.zone_id,
            auto_generated=data.auto_generated,
            sensor_id=data.sensor_id,
            target=data.target,
        )
        await self.session.commit()

        logger.info(f"Dashboard created: {dashboard.id} by user {owner_id}")
        return dashboard

    async def update_dashboard(
        self,
        dashboard_id: uuid.UUID,
        data: DashboardUpdate,
        user_id: int,
        is_admin: bool = False,
    ) -> Optional[Dashboard]:
        """
        Update an existing dashboard.

        Only owner or admin can update.

        Args:
            dashboard_id: Dashboard UUID
            data: Update data (partial)
            user_id: Current user ID
            is_admin: Whether user has admin role

        Returns:
            Updated Dashboard instance or None if not found/not authorized
        """
        dashboard = await self.repo.get_by_id(dashboard_id)
        if dashboard is None:
            return None

        # Authorization check
        if dashboard.owner_id != user_id and not is_admin:
            logger.warning(
                f"User {user_id} attempted to update dashboard {dashboard_id} "
                f"owned by {dashboard.owner_id}"
            )
            return None

        # Build update dict from non-None fields
        update_data: dict = {}
        if data.name is not None:
            update_data["name"] = data.name
        if data.description is not None:
            update_data["description"] = data.description
        if data.widgets is not None:
            update_data["widgets"] = [w.model_dump() for w in data.widgets]
        if data.is_shared is not None:
            update_data["is_shared"] = data.is_shared
        if data.scope is not None:
            update_data["scope"] = data.scope
        if data.zone_id is not None:
            update_data["zone_id"] = data.zone_id
        if data.auto_generated is not None:
            update_data["auto_generated"] = data.auto_generated
        if data.sensor_id is not None:
            update_data["sensor_id"] = data.sensor_id
        # target uses UNSET sentinel: None means "clear target", missing means "don't change"
        if "target" in (data.model_fields_set or set()):
            update_data["target"] = data.target

        if not update_data:
            return dashboard

        updated = await self.repo.update(dashboard_id, **update_data)
        await self.session.commit()

        logger.info(f"Dashboard updated: {dashboard_id} by user {user_id}")
        return updated

    async def delete_dashboard(
        self,
        dashboard_id: uuid.UUID,
        user_id: int,
        is_admin: bool = False,
    ) -> bool:
        """
        Delete a dashboard.

        Only owner or admin can delete.

        Args:
            dashboard_id: Dashboard UUID
            user_id: Current user ID
            is_admin: Whether user has admin role

        Returns:
            True if deleted, False if not found/not authorized
        """
        dashboard = await self.repo.get_by_id(dashboard_id)
        if dashboard is None:
            return False

        # Authorization check
        if dashboard.owner_id != user_id and not is_admin:
            logger.warning(
                f"User {user_id} attempted to delete dashboard {dashboard_id} "
                f"owned by {dashboard.owner_id}"
            )
            return False

        deleted = await self.repo.delete(dashboard_id)
        await self.session.commit()

        logger.info(f"Dashboard deleted: {dashboard_id} by user {user_id}")
        return deleted
