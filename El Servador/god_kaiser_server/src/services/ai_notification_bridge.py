"""
AI Notification Bridge — Route KI-Anomalien in die Phase-4A-Notification-Pipeline (Phase K4 L2.2)

Anomalie → AIPredictions persist → AlertSuppression prüfen → NotificationRouter.route()
Vorbedingung: NOTIFICATION_SOURCES += "ai_anomaly_service", NOTIFICATION_CATEGORIES += "ai_anomaly" (bereits ergänzt).
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logging_config import get_logger
from ..db.models.ai import AIPredictions
from ..db.repositories import SensorRepository
from ..schemas.notification import NotificationCreate
from .alert_suppression_service import AlertSuppressionService
from .notification_router import NotificationRouter

logger = get_logger(__name__)


@dataclass
class AnomalyResult:
    """Result from anomaly detection (Z-Score or Isolation Forest)."""

    sensor_config_id: uuid.UUID
    sensor_name: str
    severity: str  # critical | warning | info
    explanation: str
    value: Optional[float] = None
    expected_range: Optional[tuple[float, float]] = None
    z_score: Optional[float] = None


class AINotificationBridge:
    """
    Connects KI anomaly results to Phase 4A notification pipeline.

    - Persists to ai_predictions
    - Checks AlertSuppressionService (is_sensor_suppressed)
    - Creates notification and routes via NotificationRouter
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.sensor_repo = SensorRepository(session)
        self.suppression_service = AlertSuppressionService(session)
        self.notification_router = NotificationRouter(session)

    async def route_anomaly(self, anomaly: AnomalyResult) -> Optional[uuid.UUID]:
        """
        Persist prediction, check suppression, then route notification.

        Returns prediction ID if persisted, None if suppressed or error.
        """
        # 1. Persist to ai_predictions
        prediction_id = uuid.uuid4()
        esp_id: Optional[uuid.UUID] = None
        try:
            sensor_config = await self.sensor_repo.get_by_id(anomaly.sensor_config_id)
            if sensor_config:
                esp_id = sensor_config.esp_id
        except Exception as e:
            logger.warning("AI bridge: could not load sensor_config for suppression check: %s", e)

        prediction = AIPredictions(
            id=prediction_id,
            prediction_type="anomaly_detection",
            target_esp_id=esp_id,
            target_zone_id=None,
            input_data={
                "sensor_config_id": str(anomaly.sensor_config_id),
                "value": anomaly.value,
                "expected_range": list(anomaly.expected_range) if anomaly.expected_range else None,
                "z_score": anomaly.z_score,
            },
            prediction_result={
                "sensor_name": anomaly.sensor_name,
                "severity": anomaly.severity,
                "explanation": anomaly.explanation,
            },
            confidence_score=min(1.0, (anomaly.z_score or 0) / 5.0) if anomaly.z_score else 0.8,
            model_version="z_score_v1",
            prediction_metadata={"source": "ai_notification_bridge"},
        )
        self.session.add(prediction)
        await self.session.commit()

        # 2. Check suppression (expects SensorConfig model)
        sensor_config = await self.sensor_repo.get_by_id(anomaly.sensor_config_id)
        if sensor_config:
            is_suppressed, reason = await self.suppression_service.is_sensor_suppressed(
                sensor_config
            )
            if is_suppressed:
                logger.debug("AI anomaly suppressed for sensor %s: %s", anomaly.sensor_name, reason)
                return prediction_id
        else:
            logger.warning(
                "AI bridge: sensor_config %s not found for suppression check",
                anomaly.sensor_config_id,
            )

        # Enrich explanation with AI analysis if not already set
        from .ai_service import ai_service as _ai_svc  # lazy — avoids circular import

        if _ai_svc.is_available() and not anomaly.explanation:
            asyncio.create_task(_enrich_anomaly_explanation(anomaly))

        # 3. Route notification
        notification = NotificationCreate(
            channel="websocket",
            category="ai_anomaly",
            severity=anomaly.severity,
            title=f"Anomalie: {anomaly.sensor_name}",
            body=anomaly.explanation,
            source="ai_anomaly_service",
            correlation_id=str(prediction_id),
        )
        try:
            await self.notification_router.route(notification)
        except Exception as e:
            logger.exception("AI bridge: notification route failed: %s", e)
        return prediction_id


async def _enrich_anomaly_explanation(result: AnomalyResult) -> None:
    """
    Fire-and-forget AI enrichment for anomaly results without an explanation.

    Non-critical: exceptions are swallowed to never affect the main bridge flow.
    """
    try:
        from .ai_service import ErrorAnalysisRequest, ai_service  # lazy — avoids circular import

        finding = await ai_service.analyze_error(
            ErrorAnalysisRequest(
                error_code=0,
                context={
                    "sensor_config_id": str(result.sensor_config_id),
                    "value": result.value,
                },
                recent_errors=[],
                system_state={"anomaly_severity": result.severity},
            )
        )
        result.explanation = finding.root_cause
    except Exception:
        logger.debug("AI anomaly enrichment failed", exc_info=True)
