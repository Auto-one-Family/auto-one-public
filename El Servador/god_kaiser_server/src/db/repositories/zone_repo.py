"""
Zone Repository: Database Operations for Zone Entity

Phase: 0.3 - Zone as DB Entity
Updated: T13-R1 — Status-Queries, archive/reactivate, soft-delete

Provides CRUD operations for the Zone model.
Uses UUID primary key but zone_id (unique string) is the primary lookup key,
so this doesn't extend BaseRepository (same pattern as ZoneContextRepository).
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.esp import ESPDevice
from ..models.zone import Zone
from ..models.zone_context import ZoneContext


class ZoneRepository:
    """
    Zone Repository with zone-specific queries.

    Zone uses UUID PK but zone_id (unique string) is the primary lookup key.
    T13-R1: Added status management (active/archived/deleted).
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        zone_id: str,
        name: str,
        description: Optional[str] = None,
    ) -> Zone:
        """Create a new zone (status defaults to 'active')."""
        zone = Zone(
            zone_id=zone_id,
            name=name,
            description=description,
        )
        self.session.add(zone)
        await self.session.flush()
        await self.session.refresh(zone)
        return zone

    async def get_by_id(self, id: uuid.UUID) -> Optional[Zone]:
        """Get zone by UUID primary key."""
        stmt = select(Zone).where(Zone.id == id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_zone_id(self, zone_id: str) -> Optional[Zone]:
        """Get zone by human-readable zone_id string."""
        stmt = select(Zone).where(Zone.zone_id == zone_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(self) -> list[Zone]:
        """Get all zones ordered by zone_id (excludes soft-deleted)."""
        stmt = select(Zone).where(Zone.status != "deleted").order_by(Zone.zone_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_active(self) -> list[Zone]:
        """Get only active zones."""
        stmt = select(Zone).where(Zone.status == "active").order_by(Zone.zone_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_status(self, status: str) -> list[Zone]:
        """Get zones by status ('active', 'archived', 'deleted')."""
        stmt = select(Zone).where(Zone.status == status).order_by(Zone.zone_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update(
        self,
        id: uuid.UUID,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Optional[Zone]:
        """Update zone fields. Only provided (non-None) values are updated."""
        zone = await self.get_by_id(id)
        if not zone:
            return None

        if name is not None:
            zone.name = name
        if description is not None:
            zone.description = description

        await self.session.flush()
        await self.session.refresh(zone)
        return zone

    async def archive(self, zone_id: str) -> Optional[Zone]:
        """Archive a zone (status -> 'archived'). Returns None if not found."""
        zone = await self.get_by_zone_id(zone_id)
        if not zone:
            return None

        zone.status = "archived"
        await self.session.flush()
        await self.session.refresh(zone)
        return zone

    async def reactivate(self, zone_id: str) -> Optional[Zone]:
        """Reactivate an archived zone (status -> 'active'). Returns None if not found."""
        zone = await self.get_by_zone_id(zone_id)
        if not zone:
            return None

        zone.status = "active"
        await self.session.flush()
        await self.session.refresh(zone)
        return zone

    async def soft_delete(
        self,
        zone_id: str,
        deleted_by: str = "system",
    ) -> Optional[Zone]:
        """Soft-delete a zone (status -> 'deleted', set deleted_at)."""
        zone = await self.get_by_zone_id(zone_id)
        if not zone:
            return None

        zone.status = "deleted"
        zone.deleted_at = datetime.now(timezone.utc)
        zone.deleted_by = deleted_by
        await self.session.flush()
        await self.session.refresh(zone)
        return zone

    async def delete(self, id: uuid.UUID) -> bool:
        """Hard-delete zone by UUID. Returns True if deleted, False if not found."""
        zone = await self.get_by_id(id)
        if not zone:
            return False

        await self.session.delete(zone)
        await self.session.flush()
        return True

    async def count(self) -> int:
        """Count total non-deleted zones."""
        stmt = select(func.count()).select_from(Zone).where(Zone.status != "deleted")
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def exists_by_zone_id(self, zone_id: str) -> bool:
        """Check if a zone with the given zone_id exists (any status)."""
        stmt = select(func.count()).select_from(Zone).where(Zone.zone_id == zone_id)
        result = await self.session.execute(stmt)
        return result.scalar_one() > 0

    async def is_active(self, zone_id: str) -> bool:
        """Check if a zone exists and is active."""
        zone = await self.get_by_zone_id(zone_id)
        return zone is not None and zone.status == "active"

    async def list_with_device_counts(
        self,
        status_filter: Optional[str] = None,
    ) -> list[dict]:
        """
        List zones enriched with device/sensor/actuator counts and ZoneContext names.

        Args:
            status_filter: Optional status filter ('active', 'archived', 'deleted').
                           Default: all non-deleted zones.

        Returns:
            List of dicts with keys: zone_id, zone_name, status,
            device_count, sensor_count, actuator_count.
        """
        # 1. Load zones
        zone_stmt = select(Zone)
        if status_filter:
            zone_stmt = zone_stmt.where(Zone.status == status_filter)
        else:
            zone_stmt = zone_stmt.where(Zone.status != "deleted")
        zone_stmt = zone_stmt.order_by(Zone.zone_id)

        zone_result = await self.session.execute(zone_stmt)
        all_zones = zone_result.scalars().all()

        zone_map: dict[str, dict] = {}
        for z in all_zones:
            zone_map[z.zone_id] = {
                "zone_id": z.zone_id,
                "zone_name": z.name,
                "status": z.status,
                "device_count": 0,
                "sensor_count": 0,
                "actuator_count": 0,
            }

        # 2. Count devices/sensors/actuators per zone
        dev_stmt = (
            select(ESPDevice)
            .where(ESPDevice.zone_id.isnot(None))
            .where(ESPDevice.deleted_at.is_(None))
            .options(
                selectinload(ESPDevice.sensors),
                selectinload(ESPDevice.actuators),
            )
        )
        dev_result = await self.session.execute(dev_stmt)
        for device in dev_result.scalars().all():
            zid = device.zone_id
            if not zid or zid not in zone_map:
                continue
            zone_map[zid]["device_count"] += 1
            zone_map[zid]["sensor_count"] += len(device.sensors) if device.sensors else 0
            zone_map[zid]["actuator_count"] += len(device.actuators) if device.actuators else 0

        # 3. Enrich zone names from ZoneContext (if name equals zone_id)
        ctx_stmt = select(ZoneContext)
        ctx_result = await self.session.execute(ctx_stmt)
        for ctx in ctx_result.scalars().all():
            if ctx.zone_id in zone_map and ctx.zone_name:
                entry = zone_map[ctx.zone_id]
                if entry["zone_name"] == entry["zone_id"]:
                    entry["zone_name"] = ctx.zone_name

        return sorted(zone_map.values(), key=lambda z: z["zone_name"] or z["zone_id"])

    async def sync_zone_name_to_devices(self, zone_id: str, new_name: str) -> int:
        """Sync esp_devices.zone_name for all devices in this zone.

        zone_name is a denormalized performance copy. When a zone is renamed,
        this copy must be updated to keep API responses consistent.

        Returns:
            Number of updated device rows.
        """
        stmt = (
            update(ESPDevice)
            .where(ESPDevice.zone_id == zone_id, ESPDevice.deleted_at.is_(None))
            .values(zone_name=new_name)
        )
        result = await self.session.execute(stmt)
        return result.rowcount
