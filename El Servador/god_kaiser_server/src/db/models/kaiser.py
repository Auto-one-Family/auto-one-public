"""
Kaiser Models: KaiserRegistry, ESPOwnership
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin, _utc_now


class KaiserRegistry(Base, TimestampMixin):
    """
    Kaiser Registry Model (Pi Zero Relay Nodes).

    Stores registration and status of Kaiser relay nodes. Kaisers act as
    intermediary nodes for scaling to 100+ ESPs per zone.

    Attributes:
        id: Primary key (UUID)
        kaiser_id: Unique Kaiser identifier (e.g., KAISER_A1B2C3)
        ip_address: Current IP address
        mac_address: Hardware MAC address
        zone_ids: JSON array of zone IDs this Kaiser manages
        status: Kaiser status (online, offline, error, unknown)
        last_seen: Last heartbeat timestamp
        capabilities: JSON capabilities (max_esps, features, etc.)
        metadata: Additional Kaiser metadata
    """

    __tablename__ = "kaiser_registry"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Primary key (UUID)",
    )

    # Identity
    kaiser_id: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        index=True,
        nullable=False,
        doc="Unique Kaiser identifier (e.g., KAISER_A1B2C3)",
    )

    # Network Information
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45),
        nullable=True,
        doc="Current IPv4 address",
    )

    mac_address: Mapped[Optional[str]] = mapped_column(
        String(17),
        nullable=True,
        unique=True,
        doc="Hardware MAC address (format: XX:XX:XX:XX:XX:XX)",
    )

    # Zone Management (CRITICAL!)
    zone_ids: Mapped[list] = mapped_column(
        JSON,
        default=list,
        nullable=False,
        doc="List of zone IDs this Kaiser manages",
    )

    # Status Tracking
    status: Mapped[str] = mapped_column(
        String(20),
        default="offline",
        nullable=False,
        index=True,
        doc="Kaiser status (online, offline, error, unknown)",
    )

    last_seen: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        doc="Last heartbeat timestamp (UTC)",
    )

    # Capabilities (CRITICAL!)
    capabilities: Mapped[dict] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
        doc="Kaiser capabilities (max_esps, mqtt_broker, features)",
    )

    # Metadata
    kaiser_metadata: Mapped[dict] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
        doc="Additional Kaiser metadata",
    )

    # Indices
    __table_args__ = (Index("idx_kaiser_status_lastseen", "status", "last_seen"),)

    def __repr__(self) -> str:
        return f"<KaiserRegistry(kaiser_id='{self.kaiser_id}', status='{self.status}')>"

    @property
    def is_online(self) -> bool:
        """Check if Kaiser is currently online"""
        return self.status == "online"

    @property
    def max_esps(self) -> int:
        """Get maximum number of ESPs from capabilities"""
        return self.capabilities.get("max_esps", 0)


class ESPOwnership(Base, TimestampMixin):
    """
    ESP Ownership Model (Kaiser-ESP Assignment).

    Tracks which Kaiser manages which ESPs. Many-to-Many relationship
    with priority-based assignment for failover scenarios.

    Attributes:
        id: Primary key (UUID)
        kaiser_id: Foreign key to Kaiser
        esp_id: Foreign key to ESP device
        assigned_at: Assignment timestamp
        priority: Assignment priority (lower = higher priority)
        metadata: Additional ownership metadata
    """

    __tablename__ = "esp_ownership"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Primary key (UUID)",
    )

    # Foreign Keys
    kaiser_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("kaiser_registry.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Foreign key to Kaiser",
    )

    esp_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("esp_devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Foreign key to ESP device",
    )

    # Assignment Information
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        nullable=False,
        doc="Assignment timestamp (UTC)",
    )

    priority: Mapped[int] = mapped_column(
        Integer,
        default=100,
        nullable=False,
        doc="Assignment priority (lower = higher priority, for failover)",
    )

    # Metadata
    ownership_metadata: Mapped[dict] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
        doc="Additional ownership metadata (assignment_reason, etc.)",
    )

    # Table Constraints
    __table_args__ = (
        UniqueConstraint("kaiser_id", "esp_id", name="unique_kaiser_esp_ownership"),
        Index("idx_esp_priority", "esp_id", "priority"),
    )

    def __repr__(self) -> str:
        return f"<ESPOwnership(kaiser_id='{self.kaiser_id}', esp_id='{self.esp_id}', priority={self.priority})>"
