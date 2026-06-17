"""
Dashboard Layout Model

Stores custom dashboard layouts with widget configurations.
Supports user-owned and shared dashboards, zone-scoped and cross-zone layouts.
"""

import uuid
from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class Dashboard(Base, TimestampMixin):
    """
    Dashboard Layout Model.

    Stores dashboard configurations including widget positions, sizes,
    and individual widget settings. Supports both user-created and
    auto-generated dashboards.

    Attributes:
        id: Primary key (UUID)
        name: Dashboard display name
        description: Optional description
        owner_id: Foreign key to user who created the dashboard
        is_shared: Whether dashboard is visible to all users
        widgets: JSON array of widget configurations (type, position, size, config)
        scope: Dashboard scope (zone, cross-zone, sensor-detail)
        zone_id: Associated zone ID (for zone-scoped dashboards)
        auto_generated: Whether dashboard was auto-generated
        sensor_id: Associated sensor ID (for sensor-detail dashboards)
    """

    __tablename__ = "dashboards"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Primary key (UUID)",
    )

    # Identity
    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        doc="Dashboard display name",
    )

    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Optional dashboard description",
    )

    # Ownership
    owner_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("user_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Foreign key to user who created the dashboard",
    )

    is_shared: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        doc="Whether dashboard is visible to all users",
    )

    # Widget Configuration (JSONB for PostgreSQL)
    widgets: Mapped[list] = mapped_column(
        JSON,
        default=list,
        nullable=False,
        doc=(
            "JSON array of widget configurations. Each widget: "
            "{ id, type, x, y, w, h, config: { sensorId, actuatorId, ... } }"
        ),
    )

    # Scope
    scope: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        doc="Dashboard scope: 'zone', 'cross-zone', or 'sensor-detail'",
    )

    zone_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        doc="Associated zone ID (for zone-scoped dashboards)",
    )

    auto_generated: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        doc="Whether dashboard was auto-generated from zone devices",
    )

    sensor_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        doc="Associated sensor ID (for sensor-detail dashboards)",
    )

    # Target configuration (where/how to display the dashboard)
    target: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        doc=(
            "Display target config: "
            "{ view: 'monitor'|'hardware', placement: 'page'|'inline'|'side-panel'|'bottom-panel', "
            "anchor?: string, panelPosition?: 'left'|'right', panelWidth?: number, order?: number }"
        ),
    )

    # Indices
    __table_args__ = (
        Index("idx_dashboard_owner", "owner_id"),
        Index("idx_dashboard_shared", "is_shared"),
        Index("idx_dashboard_scope_zone", "scope", "zone_id"),
    )

    def __repr__(self) -> str:
        return f"<Dashboard(name='{self.name}', owner_id={self.owner_id}, shared={self.is_shared})>"
