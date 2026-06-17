"""
Device Scope Service

T13-R2: Business logic for multi-zone device scope and active context management.
Provides in-memory cache for active context lookups (hot path in sensor_handler).

T13-Phase3: Cache stores plain data (ActiveContextData) instead of ORM objects
to avoid detached-instance issues across sessions.
"""

import time
import uuid
from datetime import datetime
from typing import NamedTuple, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logging_config import get_logger
from ..db.models.device_context import DeviceActiveContext
from ..db.models.device_zone_change import DeviceZoneChange
from ..db.repositories.device_context_repo import DeviceActiveContextRepository
from ..db.repositories.zone_repo import ZoneRepository

logger = get_logger(__name__)

# Valid device_scope values
VALID_SCOPES = frozenset({"zone_local", "multi_zone", "mobile"})
VALID_CONTEXT_SOURCES = frozenset({"manual", "sequence", "mqtt"})

# Cache TTL in seconds
CONTEXT_CACHE_TTL_SECONDS = 30


class ActiveContextData(NamedTuple):
    """Session-independent cache value for active context lookups."""

    active_zone_id: Optional[str]
    active_subzone_id: Optional[str]
    context_source: Optional[str]
    context_since: Optional[datetime] = None


class _CachedContext:
    """Cached active context with TTL."""

    __slots__ = ("context", "expires_at")

    def __init__(self, context: Optional[ActiveContextData], ttl: float):
        self.context = context
        self.expires_at = time.monotonic() + ttl


class DeviceScopeService:
    """
    Manages device_scope configuration and active_context runtime state.

    Features:
    - Set/get/clear active context for multi_zone and mobile devices
    - Validate assigned_zones against zones table
    - In-memory cache for active context (30s TTL, invalidated on update)
    - Audit trail via device_zone_changes
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.context_repo = DeviceActiveContextRepository(session)
        self.zone_repo = ZoneRepository(session)

    # Class-level cache shared across service instances within same process
    _context_cache: dict[str, _CachedContext] = {}

    @staticmethod
    def _cache_key(config_type: str, config_id: uuid.UUID) -> str:
        return f"{config_type}:{config_id}"

    def _invalidate_cache(self, config_type: str, config_id: uuid.UUID) -> None:
        key = self._cache_key(config_type, config_id)
        self._context_cache.pop(key, None)

    async def get_active_context(
        self, config_type: str, config_id: uuid.UUID
    ) -> Optional[ActiveContextData]:
        """
        Get active context with in-memory cache (30s TTL).

        Returns None if no context set (zone_local devices won't have one).
        Returns ActiveContextData (NamedTuple) — session-independent, safe to cache
        across different DB sessions.
        """
        key = self._cache_key(config_type, config_id)
        cached = self._context_cache.get(key)

        if cached and cached.expires_at > time.monotonic():
            return cached.context

        # Cache miss or expired — query DB, store plain data (not ORM object)
        orm_context = await self.context_repo.get_active_context(config_type, config_id)
        data = (
            ActiveContextData(
                active_zone_id=orm_context.active_zone_id,
                active_subzone_id=orm_context.active_subzone_id,
                context_source=orm_context.context_source,
                context_since=orm_context.context_since,
            )
            if orm_context
            else None
        )
        self._context_cache[key] = _CachedContext(data, CONTEXT_CACHE_TTL_SECONDS)
        return data

    async def set_active_context(
        self,
        config_type: str,
        config_id: uuid.UUID,
        active_zone_id: Optional[str],
        active_subzone_id: Optional[str] = None,
        context_source: str = "manual",
        changed_by: str = "system",
    ) -> DeviceActiveContext:
        """
        Set the active zone context for a multi_zone or mobile device.

        Validates:
        - config_type is 'sensor' or 'actuator'
        - context_source is valid
        - active_zone_id exists in zones table (if provided)

        Args:
            config_type: 'sensor' or 'actuator'
            config_id: UUID of the sensor_config or actuator_config
            active_zone_id: Zone to activate (None = all zones / static)
            active_subzone_id: Optional subzone
            context_source: 'manual', 'sequence', or 'mqtt'
            changed_by: Username for audit trail

        Returns:
            Updated DeviceActiveContext

        Raises:
            ValueError: If validation fails
        """
        if config_type not in ("sensor", "actuator"):
            raise ValueError(f"config_type must be 'sensor' or 'actuator', got '{config_type}'")

        if context_source not in VALID_CONTEXT_SOURCES:
            raise ValueError(f"context_source must be one of {VALID_CONTEXT_SOURCES}")

        # Validate zone exists
        if active_zone_id:
            zone = await self.zone_repo.get_by_zone_id(active_zone_id)
            if not zone:
                raise ValueError(f"Zone '{active_zone_id}' does not exist")
            if not zone.is_active:
                raise ValueError(f"Zone '{active_zone_id}' is not active (status: {zone.status})")

        # Get old context for audit
        old_context = await self.context_repo.get_active_context(config_type, config_id)
        old_zone_id = old_context.active_zone_id if old_context else None

        # Upsert context
        context = await self.context_repo.upsert_context(
            config_type=config_type,
            config_id=config_id,
            active_zone_id=active_zone_id,
            active_subzone_id=active_subzone_id,
            context_source=context_source,
        )

        # Invalidate cache
        self._invalidate_cache(config_type, config_id)

        # Audit trail
        if old_zone_id != active_zone_id:
            audit = DeviceZoneChange(
                esp_id=f"{config_type}:{config_id}",
                old_zone_id=old_zone_id,
                new_zone_id=active_zone_id or "",
                subzone_strategy="context",
                change_type="context_change",
                changed_by=changed_by,
            )
            self.session.add(audit)

        logger.info(
            "Active context set: %s:%s -> zone=%s (source=%s, by=%s)",
            config_type,
            config_id,
            active_zone_id,
            context_source,
            changed_by,
        )

        return context

    async def clear_active_context(
        self,
        config_type: str,
        config_id: uuid.UUID,
        changed_by: str = "system",
    ) -> bool:
        """
        Clear the active context (return to default/fallback behavior).

        Returns:
            True if context was deleted, False if not found
        """
        # Get old context for audit
        old_context = await self.context_repo.get_active_context(config_type, config_id)

        deleted = await self.context_repo.delete_context(config_type, config_id)
        self._invalidate_cache(config_type, config_id)

        if deleted and old_context:
            audit = DeviceZoneChange(
                esp_id=f"{config_type}:{config_id}",
                old_zone_id=old_context.active_zone_id or "",
                new_zone_id="",
                subzone_strategy="context",
                change_type="context_change",
                changed_by=changed_by,
            )
            self.session.add(audit)

        return deleted

    async def validate_assigned_zones(self, zone_ids: list[str]) -> list[str]:
        """
        Validate that all zone_ids exist in the zones table.

        Returns:
            List of invalid zone_ids (empty = all valid)
        """
        invalid = []
        for zone_id in zone_ids:
            zone = await self.zone_repo.get_by_zone_id(zone_id)
            if not zone or not zone.is_active:
                invalid.append(zone_id)
        return invalid

    async def validate_zone_in_assigned(
        self, active_zone_id: str, assigned_zones: list[str]
    ) -> bool:
        """
        Check if active_zone_id is in assigned_zones.

        If assigned_zones is empty, any zone is allowed (for mobile devices
        that can go anywhere).
        """
        if not assigned_zones:
            return True
        return active_zone_id in assigned_zones
