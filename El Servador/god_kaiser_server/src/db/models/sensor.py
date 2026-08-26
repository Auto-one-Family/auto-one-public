"""
Sensor Models: SensorConfig, SensorData

Phase 2A: Added operating mode fields for per-sensor override of type defaults.
"""

import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin, _utc_now
from .enums import DataSource


class SensorConfig(Base, TimestampMixin):
    """
    Sensor Configuration Model.

    Stores configuration for sensors attached to ESP32 devices.
    Each sensor is uniquely identified by (esp_id, gpio) combination.

    Attributes:
        id: Primary key (UUID)
        esp_id: Foreign key to ESP device
        gpio: GPIO pin number
        sensor_type: Type of sensor (temperature, humidity, ph, etc.)
        sensor_name: Human-readable sensor name
        enabled: Whether sensor is active
        pi_enhanced: Whether to use Pi-Enhanced processing
        sample_interval_ms: Sampling interval in milliseconds
        calibration_data: JSON calibration parameters
        thresholds: JSON alert thresholds
    """

    __tablename__ = "sensor_configs"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Primary key (UUID)",
    )

    # Foreign Keys
    esp_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("esp_devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Foreign key to ESP device",
    )

    # Hardware Configuration
    gpio: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        doc="GPIO pin number (nullable for I2C/OneWire bus devices)",
    )

    # Sensor Information
    sensor_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        doc="Type of sensor (temperature, humidity, ph, ec, moisture, etc.)",
    )

    sensor_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        doc="Human-readable sensor name",
    )

    # =========================================================================
    # MULTI-VALUE SENSOR SUPPORT (I2C/OneWire)
    # =========================================================================
    # Interface type identifies how the sensor communicates with ESP32

    interface_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="ANALOG",
        doc="Interface type: I2C, ONEWIRE, ANALOG, DIGITAL, VIRTUAL",
    )

    i2c_address: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        index=True,  # Indexed for fast I2C address conflict checks
        doc="I2C address (required for I2C sensors, e.g., 68 for 0x44)",
    )

    onewire_address: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
        doc="OneWire device address (required for OneWire sensors, e.g. 28FF82F110C78897 or SIM_xxxx)",
    )

    # =========================================================================
    # EXTERNAL ADC SOURCE (ADS1115) — per-sensor acquisition source
    # =========================================================================
    # pH/EC can OPTIONALLY be acquired via an external 16-bit I2C ADC (ADS1115)
    # instead of the internal ESP32 ADC. Only the acquisition source changes —
    # the RAW value still flows through the identical conversion/calibration path.
    # The internal ADC remains the default ('internal').

    adc_source: Mapped[str] = mapped_column(
        String(20),
        default="internal",
        server_default="internal",
        nullable=False,
        doc="ADC acquisition source: 'internal' (ESP32 12-bit, default) or 'ads1115' (external 16-bit I2C ADC)",
    )

    adc_channel: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        doc="ADS1115 single-ended channel 0-3 (only for adc_source='ads1115'; NULL for internal ADC)",
    )

    pga_gain: Mapped[Optional[str]] = mapped_column(
        String(16),
        nullable=True,
        doc="ADS1115 PGA full-scale range in volts as string, e.g. '4.096' (only for adc_source='ads1115'; NULL for internal ADC)",
    )

    # =========================================================================
    # DIGITAL SENSOR POLARITY (liquid_level)
    # =========================================================================
    # Signal polarity for digital switch sensors. 'active_low' (NPN, e.g.
    # XKC-Y25-NPN) is the default and reproduces the pre-existing behavior.
    # 'active_high' (PNP, e.g. XKC-Y26S-PNP) inverts the firmware's interpretation.

    polarity: Mapped[str] = mapped_column(
        String(16),
        default="active_low",
        server_default="active_low",
        nullable=False,
        doc="Signal polarity for digital sensors: 'active_low' (NPN, default) or 'active_high' (PNP)",
    )

    provides_values: Mapped[Optional[list]] = mapped_column(
        JSON,
        nullable=True,
        doc="List of value types this sensor provides (for multi-value sensors, e.g., ['sht31_temp', 'sht31_humidity'])",
    )

    enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        doc="Whether sensor is active",
    )

    # Processing Mode (CRITICAL!)
    pi_enhanced: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        doc="Whether to use Pi-Enhanced processing",
    )

    # Sampling Configuration
    sample_interval_ms: Mapped[int] = mapped_column(
        Integer,
        default=1000,
        nullable=False,
        doc="Sampling interval in milliseconds",
    )

    # Calibration & Thresholds
    calibration_data: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        doc="Calibration parameters (offset, scale, etc.)",
    )

    thresholds: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        doc="Alert thresholds (min, max, warning, critical)",
    )

    # Metadata
    sensor_metadata: Mapped[dict] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
        doc="Additional sensor metadata",
    )

    # Alert Configuration (Phase 4A.7 — Per-Sensor Alert Suppression)
    alert_config: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        doc="Per-sensor alert config: alerts_enabled, suppression_reason/note/until, custom_thresholds, severity_override",
    )

    # Runtime Statistics (Phase 4A.8 — Runtime & Maintenance)
    runtime_stats: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        doc="Runtime stats: uptime_hours, last_restart, expected_lifetime_hours, maintenance_log[]",
    )

    # =========================================================================
    # OPERATING MODE CONFIGURATION (Phase 2A)
    # =========================================================================
    # These fields allow per-sensor override of type defaults.
    # NULL values mean "use type default" from sensor_type_defaults table.

    operating_mode: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,  # NULL = use type default
        doc="Operating mode override: continuous, on_demand, scheduled, paused (NULL = use type default)",
    )

    timeout_seconds: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,  # NULL = use type default
        doc="Timeout override in seconds (NULL = use type default, 0 = no timeout)",
    )

    timeout_warning_enabled: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        nullable=True,  # NULL = use type default
        doc="Timeout warning override (NULL = use type default)",
    )

    schedule_config: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        doc="Schedule configuration for scheduled mode (cron expression or time list)",
    )

    last_manual_request: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Timestamp of last manual measurement request (for on_demand mode)",
    )

    # Sensor-Lifecycle: Freshness & Calibration (instance overrides)
    measurement_freshness_hours: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        doc="Hours after which measurement is stale (NULL = use type default)",
    )

    calibration_interval_days: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        doc="Days between recalibrations (NULL = use type default)",
    )

    # =========================================================================
    # MULTI-ZONE DEVICE SCOPE (T13-R2)
    # =========================================================================
    # Allows sensors to serve multiple zones (shared equipment, mobile devices).

    device_scope: Mapped[str] = mapped_column(
        String(20),
        default="zone_local",
        server_default="zone_local",
        nullable=False,
        doc="Device scope: 'zone_local' (default), 'multi_zone', 'mobile'",
    )

    assigned_zones: Mapped[Optional[list]] = mapped_column(
        JSON,
        default=list,
        nullable=True,
        doc="JSON list of zone_ids this sensor can serve (for multi_zone/mobile)",
    )

    assigned_subzones: Mapped[Optional[list]] = mapped_column(
        JSON,
        default=list,
        nullable=True,
        doc=(
            "DEPRECATED (AUT-227): legacy field, not consumed by business logic. "
            "Subzone assignment is owned by subzone_configs.assigned_gpios. "
            "Candidate for DROP COLUMN after evidence period."
        ),
    )

    # =========================================================================
    # MOUNT GEOMETRY (AUT-1555) — server-only, not pushed to firmware
    # =========================================================================
    # First-class columns on the existing config row (same pattern as device_scope).
    # Not stored in sensor_metadata. NULL = unset; old rows stay valid.

    mount_height_cm: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        doc="AUT-1555: Mount height in cm. NULL = unset. Server-side only.",
    )

    mount_medium: Mapped[Optional[str]] = mapped_column(
        String(16),
        nullable=True,
        doc="AUT-1555: Mount medium — air | canopy | substrate | solution. NULL = unset.",
    )

    mount_angle_deg: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        doc="AUT-1555: Mount angle in degrees. NULL = unset. Server-side only.",
    )

    # =========================================================================
    # CONFIG STATUS (Phase 4 - Detailed Config Feedback)
    # =========================================================================
    # Tracks the configuration status from ESP32 config_response.

    config_status: Mapped[Optional[str]] = mapped_column(
        String(20),
        default="pending",
        doc="Config status: pending, applied, failed",
    )

    config_error: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        doc="Error code if config_status=failed (e.g., GPIO_CONFLICT)",
    )

    config_error_detail: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True,
        doc="Detailed error message if config_status=failed",
    )

    sensor_kind: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="continuous",
        server_default="continuous",
        doc="Sensor kind: continuous (MQTT stream) or snapshot (manual, e.g. MultispeQ)",
    )

    # AUT-299: Optional linked temperature sensor for ATC
    temp_sensor_config_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sensor_configs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        doc="Optional FK to a temperature SensorConfig for automatic temperature compensation (ATC). NULL = use same-ESP auto-discovery.",
    )

    # Relationships
    esp: Mapped["ESPDevice"] = relationship(
        "ESPDevice",
        back_populates="sensors",
        doc="ESP device this sensor belongs to",
    )

    # AUT-299: Self-referential relationships for temp sensor ATC link
    temp_sensor: Mapped[Optional["SensorConfig"]] = relationship(
        "SensorConfig",
        foreign_keys="[SensorConfig.temp_sensor_config_id]",
        primaryjoin="SensorConfig.temp_sensor_config_id == SensorConfig.id",
        remote_side="SensorConfig.id",
        back_populates="compensated_sensors",
        lazy="select",
        doc="Linked temperature SensorConfig for ATC (AUT-299). None = same-ESP auto-discovery.",
    )
    compensated_sensors: Mapped[List["SensorConfig"]] = relationship(
        "SensorConfig",
        foreign_keys="[SensorConfig.temp_sensor_config_id]",
        primaryjoin="SensorConfig.id == SensorConfig.temp_sensor_config_id",
        back_populates="temp_sensor",
        lazy="select",
        doc="pH/EC SensorConfigs that use this sensor as their ATC temperature source (AUT-299).",
    )

    # Table Constraints
    # MULTI-VALUE SUPPORT: Erlaubt mehrere sensor_types pro GPIO
    # z.B. SHT31 auf GPIO 21: sht31_temp + sht31_humidity
    # ONEWIRE SUPPORT: Erlaubt mehrere DS18B20 auf demselben GPIO (Bus-Sharing)
    # I2C SUPPORT: Erlaubt mehrere I2C-Sensoren auf verschiedenen Adressen
    #
    # UNIQUENESS: Enforced by expression index unique_esp_gpio_sensor_interface_v3
    # using COALESCE(onewire_address, ''), COALESCE(i2c_address::text, ''),
    # COALESCE(adc_channel::text, '') to handle NULLs correctly. The adc_channel
    # term lets two pH/EC sensors share one ADS1115 (same i2c_address, gpio=0,
    # same sensor_type) on different channels. Created via Alembic migration
    # add_adc_source_channel_pga.py (supersedes _v2 from
    # fix_sensor_unique_constraint_null_coalesce.py, V19-F02+F13).
    # No SQLAlchemy UniqueConstraint here — expression indexes cannot be
    # declared in ORM __table_args__.
    __table_args__ = (
        Index("idx_sensor_type_enabled", "sensor_type", "enabled"),
        # AUT-227: enforce valid device_scope values at the DB layer.
        CheckConstraint(
            "device_scope IN ('zone_local', 'multi_zone', 'mobile')",
            name="ck_sensor_configs_device_scope",
        ),
        # AUT-1555: mount_medium catalog. NULL stays valid (no backfill).
        CheckConstraint(
            "mount_medium IS NULL OR mount_medium IN "
            "('air', 'canopy', 'substrate', 'solution')",
            name="ck_sensor_configs_mount_medium",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<SensorConfig(sensor_name='{self.sensor_name}', "
            f"type='{self.sensor_type}', gpio={self.gpio})>"
        )


class SensorData(Base):
    """
    Sensor Data Model (Time-Series).

    Stores time-series sensor readings. Designed for high-volume inserts
    with optimized indices for time-based queries.

    Attributes:
        id: Primary key (UUID)
        esp_id: Foreign key to ESP device
        gpio: GPIO pin number
        sensor_type: Type of sensor
        raw_value: Raw ADC/digital reading
        processed_value: Processed value (after Pi-Enhanced processing)
        unit: Measurement unit
        processing_mode: Processing mode used
        quality: Data quality indicator
        timestamp: Reading timestamp
        metadata: Additional data metadata
    """

    __tablename__ = "sensor_data"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Primary key (UUID)",
    )

    # Foreign Keys (SET NULL — preserve sensor_data after device deletion, T02-Fix1)
    esp_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("esp_devices.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        doc="Foreign key to ESP device (nullable for data preservation after device deletion)",
    )

    # Sensor Information
    gpio: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="GPIO pin number",
    )

    sensor_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        doc="Type of sensor",
    )

    # Values
    raw_value: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        doc="Raw ADC/digital reading from sensor",
    )

    processed_value: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        doc="Processed value (after Pi-Enhanced processing or calibration)",
    )

    unit: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        doc="Measurement unit (°C, %, pH, etc.)",
    )

    # Processing Information
    processing_mode: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        doc="Processing mode (pi_enhanced, local, raw)",
    )

    quality: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        doc="Data quality indicator (good, fair, poor, error)",
    )

    # Timestamp (CRITICAL for Time-Series!)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        default=_utc_now,
        doc="Reading timestamp",
    )

    # Metadata
    sensor_metadata: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        doc="Additional reading metadata (warnings, errors, etc.)",
    )

    # Data Source Tracking (for mock/test/production distinction)
    data_source: Mapped[str] = mapped_column(
        String(20),
        default=DataSource.PRODUCTION.value,
        nullable=False,
        index=True,
        doc="Data source: production, mock, test, simulation",
    )

    # Zone/Subzone zum Messzeitpunkt (Phase 0.1 — Logic Engine Subzone-Matching)
    zone_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        index=True,
        doc="Zone ID at measurement time (from esp_devices.zone_id)",
    )
    subzone_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        index=True,
        doc="Subzone ID at measurement time (from subzone_configs.assigned_gpios)",
    )

    # Device context snapshot (T02-Fix1 — data remains identifiable after device soft-delete)
    device_name: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
        doc="Device name at measurement time (from esp_devices.name)",
    )

    # Plant association (MultispeQ snapshot data — AUT-222)
    plant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plants.plant_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        doc="Plant FK (nullable — only set for MultispeQ snapshot sensor_data rows)",
    )

    # Time-Series Optimized Indices
    # NOTE: uq_sensor_data_esp_gpio_type_timestamp does not cover orphaned rows
    # with esp_id=NULL after device soft-delete (NULL != NULL in UNIQUE constraints).
    # For live MQTT data esp_id is always set, so this is acceptable.
    __table_args__ = (
        UniqueConstraint(
            "esp_id",
            "gpio",
            "sensor_type",
            "timestamp",
            name="uq_sensor_data_esp_gpio_type_timestamp",
        ),
        Index("idx_esp_gpio_timestamp", "esp_id", "gpio", "timestamp"),
        Index("idx_sensor_type_timestamp", "sensor_type", "timestamp"),
        Index("idx_timestamp_desc", "timestamp", postgresql_ops={"timestamp": "DESC"}),
        Index("idx_data_source_timestamp", "data_source", "timestamp"),
    )

    def __repr__(self) -> str:
        return (
            f"<SensorData(gpio={self.gpio}, "
            f"value={self.processed_value or self.raw_value}, "
            f"timestamp='{self.timestamp.isoformat()}')>"
        )
