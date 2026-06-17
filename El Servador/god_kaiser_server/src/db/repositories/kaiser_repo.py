"""
Kaiser Repository: Database Operations for KaiserRegistry and ESPOwnership

Phase 1: Kaiser hierarchy implementation.
Status: IMPLEMENTED

Provides CRUD operations for Kaiser relay nodes and their ESP assignments.
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from ..models.kaiser import ESPOwnership, KaiserRegistry


class KaiserRepository:
    """Kaiser-specific queries for KaiserRegistry and ESPOwnership."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ── KaiserRegistry CRUD ──────────────────────────────────────────────

    async def get_by_kaiser_id(self, kaiser_id: str) -> Optional[KaiserRegistry]:
        stmt = select(KaiserRegistry).where(KaiserRegistry.kaiser_id == kaiser_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all(self) -> List[KaiserRegistry]:
        stmt = select(KaiserRegistry).order_by(KaiserRegistry.kaiser_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(
        self,
        kaiser_id: str,
        zone_ids: Optional[list] = None,
        capabilities: Optional[dict] = None,
        ip_address: Optional[str] = None,
        mac_address: Optional[str] = None,
        status: str = "online",
        kaiser_metadata: Optional[dict] = None,
    ) -> KaiserRegistry:
        kaiser = KaiserRegistry(
            kaiser_id=kaiser_id,
            zone_ids=zone_ids or [],
            capabilities=capabilities or {"max_esps": 100, "features": ["mqtt_relay"]},
            ip_address=ip_address,
            mac_address=mac_address,
            status=status,
            last_seen=datetime.now(timezone.utc),
            kaiser_metadata=kaiser_metadata or {},
        )
        self.session.add(kaiser)
        await self.session.flush()
        await self.session.refresh(kaiser)
        return kaiser

    async def update_status(
        self, kaiser_id: str, status: str, last_seen: Optional[datetime] = None
    ) -> Optional[KaiserRegistry]:
        kaiser = await self.get_by_kaiser_id(kaiser_id)
        if not kaiser:
            return None
        kaiser.status = status
        kaiser.last_seen = last_seen or datetime.now(timezone.utc)
        await self.session.flush()
        return kaiser

    async def add_zone(self, kaiser_id: str, zone_id: str) -> Optional[KaiserRegistry]:
        kaiser = await self.get_by_kaiser_id(kaiser_id)
        if not kaiser:
            return None
        zones = list(kaiser.zone_ids or [])
        if zone_id not in zones:
            zones.append(zone_id)
            kaiser.zone_ids = zones
            flag_modified(kaiser, "zone_ids")
            await self.session.flush()
        return kaiser

    async def remove_zone(self, kaiser_id: str, zone_id: str) -> Optional[KaiserRegistry]:
        kaiser = await self.get_by_kaiser_id(kaiser_id)
        if not kaiser:
            return None
        zones = list(kaiser.zone_ids or [])
        if zone_id in zones:
            zones.remove(zone_id)
            kaiser.zone_ids = zones
            flag_modified(kaiser, "zone_ids")
            await self.session.flush()
        return kaiser

    # ── ESPOwnership ─────────────────────────────────────────────────────

    async def get_esp_assignments(self, kaiser_id: str) -> List[ESPOwnership]:
        kaiser = await self.get_by_kaiser_id(kaiser_id)
        if not kaiser:
            return []
        stmt = (
            select(ESPOwnership)
            .where(ESPOwnership.kaiser_id == kaiser.id)
            .order_by(ESPOwnership.priority)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def assign_esp(
        self, kaiser_id: str, esp_uuid: uuid.UUID, priority: int = 100
    ) -> Optional[ESPOwnership]:
        kaiser = await self.get_by_kaiser_id(kaiser_id)
        if not kaiser:
            return None

        existing = await self.session.execute(
            select(ESPOwnership).where(
                and_(ESPOwnership.kaiser_id == kaiser.id, ESPOwnership.esp_id == esp_uuid)
            )
        )
        if existing.scalar_one_or_none():
            return None  # Already assigned

        ownership = ESPOwnership(
            kaiser_id=kaiser.id,
            esp_id=esp_uuid,
            priority=priority,
        )
        self.session.add(ownership)
        await self.session.flush()
        await self.session.refresh(ownership)
        return ownership

    async def unassign_esp(self, kaiser_id: str, esp_uuid: uuid.UUID) -> bool:
        kaiser = await self.get_by_kaiser_id(kaiser_id)
        if not kaiser:
            return False
        result = await self.session.execute(
            select(ESPOwnership).where(
                and_(ESPOwnership.kaiser_id == kaiser.id, ESPOwnership.esp_id == esp_uuid)
            )
        )
        ownership = result.scalar_one_or_none()
        if not ownership:
            return False
        await self.session.delete(ownership)
        await self.session.flush()
        return True
