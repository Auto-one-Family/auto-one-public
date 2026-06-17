"""
AI Model: AIPredictions
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Index, JSON, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, _utc_now


class AIPredictions(Base):
    """
    AI Predictions Model (God Layer Integration).

    Stores predictions from the God layer AI/ML models for anomaly detection,
    resource optimization, and failure prediction.

    Attributes:
        id: Primary key (UUID)
        prediction_type: Type (anomaly_detection, resource_optimization, failure_prediction)
        target_esp_id: Foreign key to ESP device (optional, zone-level predictions have None)
        target_zone_id: Zone ID for zone-level predictions
        input_data: JSON snapshot of sensor data used for prediction
        prediction_result: JSON prediction output (anomalies, recommendations, etc.)
        confidence_score: Confidence score (0.0-1.0)
        model_version: AI model version used for prediction
        timestamp: Prediction timestamp
        metadata: Additional prediction metadata
    """

    __tablename__ = "ai_predictions"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Primary key (UUID)",
    )

    # Prediction Type
    prediction_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        doc="Prediction type (anomaly_detection, resource_optimization, failure_prediction)",
    )

    # Target Information (SET NULL — preserve predictions after device deletion, T02-Fix1)
    target_esp_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("esp_devices.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        doc="Foreign key to ESP device (None for zone-level predictions)",
    )

    target_zone_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        index=True,
        doc="Zone ID for zone-level predictions",
    )

    # Prediction Data (CRITICAL!)
    input_data: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        doc="Snapshot of sensor data used for prediction",
    )

    prediction_result: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        doc=(
            "Prediction output. "
            "Example (anomaly): {'anomalies': [{'sensor': 'temp_34', 'severity': 'high', 'value': 35.2}]}. "
            "Example (optimization): {'recommendations': [{'action': 'reduce_pump_speed', 'gpio': 18, 'value': 0.5}]}"
        ),
    )

    # Confidence & Model Info
    confidence_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        doc="Confidence score (0.0-1.0)",
    )

    model_version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        doc="AI model version used for prediction",
    )

    # Timestamp (CRITICAL for Time-Series!)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        default=_utc_now,
        doc="Prediction timestamp",
    )

    # Metadata
    prediction_metadata: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        doc="Additional prediction metadata (processing_time_ms, etc.)",
    )

    # Time-Series Optimized Indices
    __table_args__ = (
        Index("idx_prediction_type_timestamp", "prediction_type", "timestamp"),
        Index("idx_esp_timestamp_ai", "target_esp_id", "timestamp"),
        Index("idx_zone_timestamp_ai", "target_zone_id", "timestamp"),
        Index("idx_timestamp_desc_ai", "timestamp", postgresql_ops={"timestamp": "DESC"}),
    )

    def __repr__(self) -> str:
        return (
            f"<AIPredictions(type='{self.prediction_type}', "
            f"confidence={self.confidence_score:.2f}, "
            f"timestamp='{self.timestamp.isoformat()}')>"
        )
