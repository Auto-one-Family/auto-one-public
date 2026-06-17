"""
Zone Model: Independent Zone Entity

Phase: 0.3 - Zone as DB Entity
Status: IMPLEMENTED
Updated: T13-R1 — Zone Consolidation (status, deleted_at, FK)

Zones are logical areas (greenhouse, office, balcony) that exist
independently of devices. Zones are the Single Source of Truth for
zone assignments. esp_devices.zone_id references zones.zone_id via FK.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class Zone(Base, TimestampMixin):
    """
    Zone Model.

    Represents a logical zone (area) that exists independently of devices.
    esp_devices.zone_id references zones.zone_id via FK constraint.

    Attributes:
        id: Primary key (UUID)
        zone_id: Unique human-readable identifier (e.g., 'greenhouse_zone_1')
        name: Display name (e.g., 'Greenhouse Section 1')
        description: Optional description
        status: Zone lifecycle status ('active', 'archived', 'deleted')
        deleted_at: Soft-delete timestamp (set when status='deleted')
        deleted_by: Username who soft-deleted this zone
    """

    __tablename__ = "zones"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Primary key (UUID)",
    )

    zone_id: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
        doc="Unique human-readable zone identifier (e.g., 'greenhouse_zone_1')",
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        doc="Display name for the zone",
    )

    description: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        doc="Optional zone description",
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default="active",
        server_default="active",
        nullable=False,
        index=True,
        doc="Zone lifecycle: 'active', 'archived', 'deleted'",
    )

    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Soft-delete timestamp (set when status='deleted')",
    )

    deleted_by: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        doc="Username who soft-deleted this zone",
    )

    @property
    def is_active(self) -> bool:
        """Check if zone is in active state."""
        return self.status == "active"

    @property
    def is_archived(self) -> bool:
        """Check if zone is archived."""
        return self.status == "archived"

    def __repr__(self) -> str:
        return f"<Zone(zone_id='{self.zone_id}', name='{self.name}', status='{self.status}')>"
