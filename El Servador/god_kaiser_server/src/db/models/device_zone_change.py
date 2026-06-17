"""
Device Zone Change Audit Model

Phase: T13-R1 - Zone Consolidation
Status: IMPLEMENTED

Tracks every zone assignment change for a device.
Records old/new zone, subzone strategy, and affected subzones.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, JSON, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class DeviceZoneChange(Base):
    """
    Audit log for device zone changes.

    Records every zone assignment change including the subzone
    transfer strategy used and which subzones were affected.

    Attributes:
        id: Primary key (UUID)
        esp_id: Device ID (e.g., 'ESP_12AB34CD')
        old_zone_id: Previous zone (None if first assignment)
        new_zone_id: New zone ID
        subzone_strategy: Strategy used ('transfer', 'copy', 'reset')
        affected_subzones: JSON list of affected subzone details
        changed_by: Username or 'system'
        changed_at: Timestamp of the change
    """

    __tablename__ = "device_zone_changes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Primary key (UUID)",
    )

    esp_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        doc="ESP device ID (e.g., ESP_12AB34CD)",
    )

    old_zone_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        doc="Previous zone_id (None if first assignment)",
    )

    new_zone_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        doc="New zone_id after the change",
    )

    subzone_strategy: Mapped[str] = mapped_column(
        String(20),
        default="transfer",
        server_default="transfer",
        nullable=False,
        doc="Subzone strategy: 'transfer', 'copy', 'reset'",
    )

    affected_subzones: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        doc="JSON list of affected subzones [{subzone_id, old_parent, new_parent}]",
    )

    change_type: Mapped[str] = mapped_column(
        String(20),
        default="zone_switch",
        server_default="zone_switch",
        nullable=False,
        doc="Change type: 'zone_switch', 'context_change', 'scope_change', 'zones_update'",
    )

    changed_by: Mapped[str] = mapped_column(
        String(100),
        default="system",
        server_default="system",
        nullable=False,
        doc="Username who initiated the change or 'system'",
    )

    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        doc="Timestamp of the zone change (UTC)",
    )

    def __repr__(self) -> str:
        return (
            f"<DeviceZoneChange(esp_id='{self.esp_id}', "
            f"{self.old_zone_id} -> {self.new_zone_id}, "
            f"strategy='{self.subzone_strategy}')>"
        )
