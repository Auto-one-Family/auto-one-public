"""
Dashboard Repository

CRUD operations for dashboard layouts with owner/shared filtering.
"""

import uuid
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.dashboard import Dashboard
from .base_repo import BaseRepository


def _widget_references_esp(widget: dict, esp_id: str, prefix: str) -> bool:
    config = widget.get("config") if isinstance(widget, dict) else {}
    if not isinstance(config, dict):
        return False
    if config.get("espId") == esp_id:
        return True
    sensor_id = config.get("sensorId") or ""
    if isinstance(sensor_id, str) and sensor_id.startswith(prefix):
        return True
    actuator_id = config.get("actuatorId") or ""
    if isinstance(actuator_id, str) and actuator_id.startswith(prefix):
        return True
    return False


class DashboardRepository(BaseRepository[Dashboard]):
    """
    Dashboard Repository with dashboard-specific queries.

    Provides methods for querying dashboards by owner, shared status,
    scope, and zone.
    """

    def __init__(self, session: AsyncSession):
        super().__init__(Dashboard, session)

    async def get_user_dashboards(
        self,
        owner_id: int,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Dashboard]:
        """
        Get dashboards owned by a user OR shared dashboards.

        Args:
            owner_id: User ID
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of Dashboard instances (owned + shared)
        """
        stmt = (
            select(Dashboard)
            .where(
                or_(
                    Dashboard.owner_id == owner_id,
                    Dashboard.is_shared == True,
                )
            )
            .order_by(Dashboard.updated_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_user_dashboards(self, owner_id: int) -> int:
        """
        Count dashboards visible to a user (owned + shared).

        Args:
            owner_id: User ID

        Returns:
            Total count
        """
        stmt = (
            select(func.count())
            .select_from(Dashboard)
            .where(
                or_(
                    Dashboard.owner_id == owner_id,
                    Dashboard.is_shared == True,
                )
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def get_by_zone(
        self,
        zone_id: str,
        owner_id: Optional[int] = None,
    ) -> list[Dashboard]:
        """
        Get dashboards for a specific zone.

        Args:
            zone_id: Zone identifier
            owner_id: Optional owner filter

        Returns:
            List of zone-scoped Dashboard instances
        """
        conditions = [
            Dashboard.scope == "zone",
            Dashboard.zone_id == zone_id,
        ]
        if owner_id is not None:
            conditions.append(
                or_(
                    Dashboard.owner_id == owner_id,
                    Dashboard.is_shared == True,
                )
            )

        stmt = select(Dashboard).where(*conditions).order_by(Dashboard.updated_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_auto_generated(
        self,
        zone_id: str,
    ) -> Optional[Dashboard]:
        """
        Get auto-generated dashboard for a zone.

        Args:
            zone_id: Zone identifier

        Returns:
            Auto-generated Dashboard or None
        """
        stmt = (
            select(Dashboard)
            .where(
                Dashboard.auto_generated == True,
                Dashboard.scope == "zone",
                Dashboard.zone_id == zone_id,
            )
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def is_owner(self, dashboard_id: uuid.UUID, user_id: int) -> bool:
        """
        Check if a user owns a dashboard.

        Args:
            dashboard_id: Dashboard UUID
            user_id: User ID

        Returns:
            True if user owns the dashboard
        """
        stmt = (
            select(func.count())
            .select_from(Dashboard)
            .where(
                Dashboard.id == dashboard_id,
                Dashboard.owner_id == user_id,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one() > 0

    async def remove_widgets_by_esp_id(self, esp_id: str) -> int:
        """
        Remove all dashboard widgets that reference a given ESP device.

        Scans all dashboards and filters out widgets whose config references
        the device by espId, sensorId or actuatorId.

        Args:
            esp_id: ESP device identifier

        Returns:
            Total number of widgets removed across all dashboards
        """
        stmt = select(Dashboard)
        result = await self.session.execute(stmt)
        all_dashboards = list(result.scalars().all())
        prefix = f"{esp_id}:"
        total_removed = 0
        for dashboard in all_dashboards:
            widgets: list = dashboard.widgets or []
            kept = [w for w in widgets if not _widget_references_esp(w, esp_id, prefix)]
            removed = len(widgets) - len(kept)
            if removed > 0:
                dashboard.widgets = kept
                await self.session.flush()
                total_removed += removed
        return total_removed
