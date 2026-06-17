"""
Sensor Type Defaults Model

Stores default operating mode configuration per sensor type.
Users can override these defaults for individual sensor instances.

Phase: 2A - Sensor Operating Modes

Example:
    - sensor_type "ph" → default mode "on_demand", no timeout
    - sensor_type "temperature" → default mode "continuous", 180s timeout

Configuration Hierarchy (Priority):
    1. SensorConfig (per-instance override) - highest priority
    2. SensorTypeDefaults (per-type defaults from this table)
    3. Sensor Library (RECOMMENDED_MODE in processor class)
    4. System Default (continuous, 180s timeout) - lowest priority
"""

import uuid
from typing import Optional

from sqlalchemy import Boolean, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class SensorTypeDefaults(Base, TimestampMixin):
    """
    Default operating mode configuration per sensor type.

    This table allows users to configure default behavior for each sensor type.
    Individual sensor instances (SensorConfig) can override these defaults.

    Attributes:
        id: Primary key (UUID)
        sensor_type: Unique sensor type identifier (e.g., "ph", "temperature")
        operating_mode: Default operating mode (continuous, on_demand, scheduled, paused)
        measurement_interval_seconds: Default interval for continuous mode
        timeout_seconds: Timeout for stale detection (0 = no timeout)
        timeout_warning_enabled: Whether to show warnings on timeout
        supports_on_demand: Whether this sensor type supports manual triggering
        description: User-facing description of this sensor type's behavior
        schedule_config: Default schedule configuration for scheduled mode
        created_at: Record creation timestamp (from TimestampMixin)
        updated_at: Record last update timestamp (from TimestampMixin)
    """

    __tablename__ = "sensor_type_defaults"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Primary key (UUID)",
    )

    # Sensor Type (unique identifier)
    sensor_type: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
        doc="Sensor type identifier (e.g., 'ph', 'temperature', 'humidity')",
    )

    # Operating Mode Configuration
    operating_mode: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="continuous",
        doc="Default operating mode: continuous, on_demand, scheduled, paused",
    )

    measurement_interval_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=30,
        doc="Default measurement interval in seconds (for continuous mode)",
    )

    timeout_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=180,
        doc="Timeout in seconds for stale detection (0 = no timeout)",
    )

    timeout_warning_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        doc="Whether to show warnings when timeout is exceeded",
    )

    # Capabilities
    supports_on_demand: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        doc="Whether this sensor type supports manual/on-demand measurements",
    )

    # Documentation
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="User-facing description of recommended usage for this sensor type",
    )

    # Schedule Configuration (for scheduled mode)
    schedule_config: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        doc="Default schedule configuration (cron expression or time list)",
    )

    # Sensor-Lifecycle: Freshness & Calibration
    measurement_freshness_hours: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        doc="Hours after which an on-demand/scheduled measurement is considered stale (NULL = no limit)",
    )

    calibration_interval_days: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        doc="Days between recommended recalibrations (NULL = no reminder)",
    )

    def __repr__(self) -> str:
        return (
            f"<SensorTypeDefaults(sensor_type='{self.sensor_type}', "
            f"mode='{self.operating_mode}', timeout={self.timeout_seconds}s)>"
        )
