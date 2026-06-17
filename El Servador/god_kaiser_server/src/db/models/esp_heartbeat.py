"""
ESP Heartbeat Log Model: Time-Series Heartbeat Data

Records historical heartbeat data from ESP32 devices for:
- Device health trending (RAM, WiFi over time)
- Performance monitoring
- Diagnostic analysis
- Industrial-grade device monitoring (Siemens/Rockwell-pattern)

Phase: ESP-Heartbeat-Persistierung
Priority: HIGH
Status: IMPLEMENTED
"""

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from ..types import JSONBCompat


class ESPHeartbeatLog(Base):
    """
    ESP Heartbeat History Log (Time-Series).

    Stores historical heartbeat data for device health trending.
    Designed for high-volume inserts with optimized time-based queries.

    Performance Indexes:
    - idx_heartbeat_esp_timestamp: Fast lookup by ESP and time
    - idx_heartbeat_device_timestamp: Fast lookup by device_id and time
    - idx_heartbeat_timestamp_desc: Fast time-ordered queries
    - idx_heartbeat_data_source_timestamp: Fast filtering by data source

    Retention:
    - Default: 7 days (configurable via HEARTBEAT_LOG_RETENTION_DAYS)
    - Cleanup via HeartbeatLogCleanup maintenance job

    Attributes:
        id: Primary key (UUID)
        esp_id: Foreign key to esp_devices.id (for JOIN queries)
        device_id: Denormalized device identifier (e.g. "ESP_12AB34CD")
        timestamp: Heartbeat timestamp (indexed for time-series queries)
        heap_free: Free heap memory in bytes
        wifi_rssi: WiFi signal strength in dBm
        uptime: Device uptime in seconds
        sensor_count: Number of active sensors
        actuator_count: Number of active actuators
        gpio_reserved_count: Number of reserved GPIO pins
        data_source: Source type (production, mock, test)
        health_status: Calculated health (healthy, degraded, critical)
    """

    __tablename__ = "esp_heartbeat_logs"

    # Time-Series Optimized Indices
    __table_args__ = (
        Index("idx_heartbeat_esp_timestamp", "esp_id", "timestamp"),
        Index("idx_heartbeat_device_timestamp", "device_id", "timestamp"),
        Index("idx_heartbeat_timestamp_desc", "timestamp", postgresql_using="btree"),
        Index("idx_heartbeat_data_source_timestamp", "data_source", "timestamp"),
        Index("idx_heartbeat_health_status", "health_status", "timestamp"),
    )

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Primary key (UUID)",
    )

    # Foreign Key to ESP Device (SET NULL — preserve heartbeat history after device deletion, T02-Fix1)
    esp_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("esp_devices.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        doc="FK to esp_devices.id (nullable for data preservation after device deletion)",
    )

    # Denormalized Device ID (for fast queries without JOIN)
    device_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        doc="Device identifier (e.g. ESP_12AB34CD)",
    )

    # Timestamp (CRITICAL for Time-Series)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        doc="Heartbeat timestamp (timezone-aware)",
    )

    # Health Metrics
    heap_free: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="Free heap memory in bytes",
    )

    wifi_rssi: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="WiFi signal strength in dBm",
    )

    uptime: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="Device uptime in seconds",
    )

    # Device Counts
    sensor_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        doc="Number of active sensors",
    )

    actuator_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        doc="Number of active actuators",
    )

    # GPIO Status
    gpio_reserved_count: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        default=0,
        doc="Number of reserved GPIO pins",
    )

    # Data Source (for mock/test/production distinction)
    data_source: Mapped[str] = mapped_column(
        String(20),
        default="production",
        nullable=False,
        index=True,
        doc="Data source: production, mock, test",
    )

    # Health Assessment (calculated on insert)
    health_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="healthy",
        doc="Calculated: healthy, degraded, critical",
    )

    # Firmware extension fields (persistence/network/runtime flags, drop counters) — see migration comment.
    runtime_telemetry: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONBCompat,
        nullable=True,
        doc="JSONB snapshot of firmware heartbeat telemetry beyond core metrics",
    )

    def __repr__(self) -> str:
        return (
            f"<ESPHeartbeatLog(device_id='{self.device_id}', "
            f"timestamp='{self.timestamp}', "
            f"health='{self.health_status}')>"
        )

    @property
    def heap_free_kb(self) -> float:
        """Get free heap in KB."""
        return self.heap_free / 1024.0

    @property
    def uptime_hours(self) -> float:
        """Get uptime in hours."""
        return self.uptime / 3600.0

    @property
    def is_healthy(self) -> bool:
        """Check if device was healthy at this heartbeat."""
        return self.health_status == "healthy"

    @property
    def is_critical(self) -> bool:
        """Check if device was in critical state."""
        return self.health_status == "critical"


# Health Status Constants
class HeartbeatHealthStatus:
    """Heartbeat health status constants."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"


def determine_health_status(
    wifi_rssi: int,
    heap_free: int,
    *,
    runtime_telemetry: Optional[dict[str, Any]] = None,
) -> str:
    """
    Determine health status based on metrics.

    Industrial-Standard: Traffic Light System (Green/Yellow/Red)

    Args:
        wifi_rssi: WiFi signal strength in dBm
        heap_free: Free heap memory in bytes
        runtime_telemetry: Optional firmware flags (persistence/network/runtime degradation).

    Returns:
        Health status: "healthy", "degraded", or "critical"
    """
    # Critical: WiFi very weak OR RAM very low
    if wifi_rssi < -80 or heap_free < 10240:  # < 10KB RAM
        base = HeartbeatHealthStatus.CRITICAL
    # Degraded: WiFi weak OR RAM low
    elif wifi_rssi < -70 or heap_free < 20480:  # < 20KB RAM
        base = HeartbeatHealthStatus.DEGRADED
    else:
        base = HeartbeatHealthStatus.HEALTHY

    if not runtime_telemetry:
        return base

    order = {
        HeartbeatHealthStatus.HEALTHY: 0,
        HeartbeatHealthStatus.DEGRADED: 1,
        HeartbeatHealthStatus.CRITICAL: 2,
    }
    rt = runtime_telemetry
    telemetry_floor = HeartbeatHealthStatus.HEALTHY
    if rt.get("network_degraded") is True or rt.get("mqtt_circuit_breaker_open") is True:
        telemetry_floor = HeartbeatHealthStatus.DEGRADED
    if rt.get("wifi_circuit_breaker_open") is True:
        telemetry_floor = HeartbeatHealthStatus.DEGRADED
    if rt.get("persistence_degraded") is True or rt.get("runtime_state_degraded") is True:
        telemetry_floor = HeartbeatHealthStatus.DEGRADED

    # Never downgrade critical RAM/WiFi to degraded-only; only upgrade toward worse if needed.
    if order[base] >= order[HeartbeatHealthStatus.CRITICAL]:
        return base
    if order[telemetry_floor] > order[base]:
        return telemetry_floor
    return base
