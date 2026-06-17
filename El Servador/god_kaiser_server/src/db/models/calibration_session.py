"""
Calibration Session Model (Phase: S-P2)

Tracks multi-point calibration sessions from start to terminal state.
Enables the server to correlate measurement trigger → data arrival → persist → apply.

Session lifecycle:
    PENDING → COLLECTING → FINALIZING → APPLIED | REJECTED | EXPIRED
"""

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin
from ..types import JSONBCompat


class CalibrationStatus(str, enum.Enum):
    """Calibration session lifecycle states."""

    PENDING = "pending"  # Session created, no points yet
    COLLECTING = "collecting"  # Points being captured
    FINALIZING = "finalizing"  # All points captured, computing result
    APPLIED = "applied"  # Calibration applied to sensor config
    REJECTED = "rejected"  # User rejected the calibration
    EXPIRED = "expired"  # Session timed out (24h default)
    FAILED = "failed"  # Calibration computation failed


class CalibrationSession(Base, TimestampMixin):
    """
    Persistent calibration session with multi-point tracking.

    Each session tracks:
    - Which sensor is being calibrated (esp_id + gpio + sensor_type)
    - Calibration points collected so far (in calibration_points JSONB)
    - Terminal result (slope, offset, etc. in calibration_result JSONB)
    - Intent correlation for MQTT command tracking
    """

    __tablename__ = "calibration_sessions"

    __table_args__ = (
        Index("idx_cal_sessions_sensor", "esp_id", "gpio", "sensor_type"),
        Index("idx_cal_sessions_status", "status"),
        Index("idx_cal_sessions_created", "created_at"),
        Index(
            "idx_cal_sessions_active",
            "esp_id",
            "gpio",
            "status",
            unique=False,
        ),
    )

    # ── Primary Key ────────────────────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # ── Sensor Reference (denormalized for fast queries) ───────────────────
    esp_id: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        doc="ESP device identifier",
    )
    gpio: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="GPIO pin number of the sensor",
    )
    sensor_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        doc="Normalized sensor type (e.g. 'moisture', 'ph', 'ec')",
    )

    # ── Optional FK to sensor_configs (SET NULL if sensor deleted) ─────────
    sensor_config_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sensor_configs.id", ondelete="SET NULL"),
        nullable=True,
        doc="FK to sensor_configs for data integrity (nullable for history)",
    )

    # ── Session State ──────────────────────────────────────────────────────
    status: Mapped[CalibrationStatus] = mapped_column(
        Enum(CalibrationStatus, name="calibration_status", native_enum=False),
        nullable=False,
        default=CalibrationStatus.PENDING,
        doc="Current session lifecycle state",
    )

    method: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="linear_2point",
        doc="Calibration method (linear_2point, linear, moisture_2point, offset, ph_2point, ec_1point, ec_2point)",
    )

    expected_points: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=2,
        doc="Number of calibration points expected",
    )

    # ── Calibration Data (JSONB) ───────────────────────────────────────────
    calibration_points: Mapped[Optional[dict]] = mapped_column(
        JSONBCompat,
        nullable=True,
        default=None,
        doc=(
            "Array of {raw, reference, quality, timestamp, intent_id, point_role} objects. "
            "point_role: moisture(dry|wet), pH(buffer_high|buffer_low), EC(reference|air), linear(dry|wet), offset(dry|wet)"
        ),
    )

    calibration_result: Mapped[Optional[dict]] = mapped_column(
        JSONBCompat,
        nullable=True,
        default=None,
        doc="Computed calibration: {slope, offset, type, ...} or null if not finalized",
    )

    # ── Intent Correlation ─────────────────────────────────────────────────
    correlation_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        doc="Cross-system correlation ID for MQTT intent tracking",
    )

    # ── User Tracking ──────────────────────────────────────────────────────
    initiated_by: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        doc="Username of operator who started the session",
    )

    # ── Session Metadata (AUT-299) ─────────────────────────────────────────
    session_metadata: Mapped[Optional[dict]] = mapped_column(
        JSONBCompat,
        nullable=True,
        default=None,
        doc="Session-level metadata: calibration_temperature (°C for EC ATC), etc.",
    )

    # ── Terminal Metadata ──────────────────────────────────────────────────
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="When session reached terminal state (applied/rejected/expired/failed)",
    )

    failure_reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Human-readable reason if status is failed/rejected",
    )

    def __repr__(self) -> str:
        return (
            f"<CalibrationSession id={self.id} "
            f"esp={self.esp_id} gpio={self.gpio} "
            f"type={self.sensor_type} status={self.status}>"
        )

    @property
    def is_terminal(self) -> bool:
        """Whether the session has reached a terminal state."""
        return self.status in (
            CalibrationStatus.APPLIED,
            CalibrationStatus.REJECTED,
            CalibrationStatus.EXPIRED,
            CalibrationStatus.FAILED,
        )

    @property
    def points_collected(self) -> int:
        """Number of calibration points collected so far."""
        if not self.calibration_points:
            return 0
        points = self.calibration_points.get("points", [])
        return len(points) if isinstance(points, list) else 0

    @property
    def is_ready_to_finalize(self) -> bool:
        """Whether enough points have been collected."""
        return self.points_collected >= self.expected_points
