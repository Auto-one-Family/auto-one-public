"""
Device Active Context Model

Phase: T13-R2 - Multi-Zone Device Scope and Data Routing
Status: IMPLEMENTED

Stores the runtime active zone/subzone context for multi_zone
and mobile sensors/actuators. Used to determine which zone
a measurement belongs to at the time of reading.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class DeviceActiveContext(Base):
    """
    Runtime active context for multi-zone and mobile devices.

    Tracks which zone/subzone a sensor or actuator is currently
    serving. Updated when a device switches to a new zone
    (manually, via sequence, or via MQTT).

    Attributes:
        id: Primary key (UUID)
        config_type: 'sensor' or 'actuator'
        config_id: FK to sensor_configs.id or actuator_configs.id
        active_zone_id: Currently active zone (NULL = all assigned zones)
        active_subzone_id: Currently active subzone (optional)
        context_source: How the context was set ('manual', 'sequence', 'mqtt')
        context_since: When this context became active
        updated_at: Last update timestamp
    """

    __tablename__ = "device_active_context"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Primary key (UUID)",
    )

    config_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        doc="Config type: 'sensor' or 'actuator'",
    )

    config_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        doc="FK to sensor_configs.id or actuator_configs.id (application-level)",
    )

    active_zone_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        doc="Currently active zone_id (NULL = all assigned zones / static multi-zone)",
    )

    active_subzone_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        doc="Currently active subzone_id (optional)",
    )

    context_source: Mapped[str] = mapped_column(
        String(20),
        default="manual",
        server_default="manual",
        nullable=False,
        doc="How context was set: 'manual', 'sequence', 'mqtt'",
    )

    context_since: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        doc="When this context became active (UTC)",
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
        doc="Last update timestamp (UTC)",
    )

    __table_args__ = (
        UniqueConstraint(
            "config_type",
            "config_id",
            name="unique_device_active_context",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<DeviceActiveContext({self.config_type}:{self.config_id}, "
            f"zone={self.active_zone_id}, source={self.context_source})>"
        )
