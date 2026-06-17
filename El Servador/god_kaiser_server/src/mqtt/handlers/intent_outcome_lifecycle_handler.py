"""
MQTT Handler: Intent outcome CONFIG_PENDING lifecycle (firmware subtopic).

Topic: kaiser/{kaiser_id}/esp/{esp_id}/system/intent_outcome/lifecycle
QoS: 1

Separate from canonical intent_outcome JSON: schema-tagged transition events only.
See El Trabajante docs/runtime-readiness-policy.md.
"""

from __future__ import annotations

from typing import Optional

from ...core.logging_config import get_logger
from ...core.metrics import increment_intent_outcome_lifecycle
from ...db.models.audit_log import AuditSeverity
from ...db.repositories.audit_log_repo import AuditLogRepository
from ...db.session import resilient_session
from ..topics import TopicBuilder
from .tracing_degraded_emit import emit_tracing_degraded

logger = get_logger(__name__)


class IntentOutcomeLifecycleHandler:
    async def handle_lifecycle(self, topic: str, payload: dict) -> bool:
        try:
            parsed = TopicBuilder.parse_intent_outcome_lifecycle_topic(topic)
            if not parsed:
                logger.error("Failed to parse intent_outcome/lifecycle topic: %s", topic)
                return False

            esp_id = parsed["esp_id"]
            payload = dict(payload)
            err = self._validate_payload(payload)
            if err:
                # Treat malformed lifecycle events as non-fatal noise: they should
                # not bubble up as handler failures that pollute transport health logs.
                emit_tracing_degraded(
                    esp_id,
                    "malformed_lifecycle_payload",
                    (
                        "tracing_degraded esp_id=%s reason=malformed_intent_outcome_lifecycle "
                        "validation=%s (AUT-347)"
                    ),
                    esp_id,
                    err,
                )
                return True

            event_type = str(payload.get("event_type") or "").strip()
            schema = str(payload.get("schema") or "").strip()
            boot_sequence_id = payload.get("boot_sequence_id")
            reason_code = payload.get("reason_code")
            correlation_id = str(payload.get("correlation_id") or "").strip() or None
            intent_id = str(payload.get("intent_id") or "").strip() or None
            if correlation_id is None and intent_id is not None:
                correlation_id = intent_id

            logger.info(
                "Intent outcome lifecycle: esp_id=%s event_type=%s schema=%s boot_sequence_id=%s",
                esp_id,
                event_type,
                schema,
                boot_sequence_id,
            )
            increment_intent_outcome_lifecycle(event_type, schema)

            async with resilient_session() as session:
                audit_repo = AuditLogRepository(session)
                await audit_repo.log_device_event(
                    esp_id=esp_id,
                    event_type="intent_outcome_lifecycle",
                    status=event_type[:50],  # truncate to match VARCHAR(50) column limit
                    message=f"CONFIG_PENDING lifecycle: {event_type}",
                    details={
                        "schema": schema,
                        "event_type": event_type,
                        "reason_code": reason_code,
                        "boot_sequence_id": boot_sequence_id,
                        "trigger_source": payload.get("trigger_source"),
                        "state_before": payload.get("state_before"),
                        "state_after": payload.get("state_after"),
                        "sensor_count": payload.get("sensor_count"),
                        "actuator_count": payload.get("actuator_count"),
                        "offline_rule_count": payload.get("offline_rule_count"),
                        "readiness_decision": payload.get("readiness_decision"),
                        "runtime_profile": payload.get("runtime_profile"),
                        "config_pending_enter_count": payload.get("config_pending_enter_count"),
                        "config_pending_exit_count": payload.get("config_pending_exit_count"),
                        "config_pending_exit_blocked_count": payload.get(
                            "config_pending_exit_blocked_count"
                        ),
                        "intent_id": intent_id,
                        "correlation_id": correlation_id,
                        "seq": payload.get("seq"),
                        "ts": payload.get("ts"),
                    },
                    severity=AuditSeverity.INFO,
                    correlation_id=correlation_id,
                )
                await session.commit()

            try:
                from ...websocket.manager import WebSocketManager

                ws = await WebSocketManager.get_instance()
                await ws.broadcast(
                    "intent_outcome_lifecycle",
                    {
                        "esp_id": esp_id,
                        "schema": schema,
                        "event_type": event_type,
                        "reason_code": reason_code,
                        "boot_sequence_id": boot_sequence_id,
                        "ts": payload.get("ts"),
                    },
                )
            except Exception as ws_err:
                logger.warning("intent_outcome_lifecycle WebSocket broadcast failed: %s", ws_err)

            return True
        except Exception as exc:
            logger.error("Error handling intent_outcome/lifecycle: %s", exc, exc_info=True)
            return False

    @staticmethod
    def _validate_payload(payload: dict) -> Optional[str]:
        if not str(payload.get("event_type") or "").strip():
            return "Missing event_type"
        if not str(payload.get("schema") or "").strip():
            return "Missing schema"
        ts = payload.get("ts")
        if ts is not None:
            try:
                int(ts)
            except (TypeError, ValueError):
                return "Invalid ts"
        return None


_handler: Optional[IntentOutcomeLifecycleHandler] = None


def get_intent_outcome_lifecycle_handler() -> IntentOutcomeLifecycleHandler:
    global _handler
    if _handler is None:
        _handler = IntentOutcomeLifecycleHandler()
    return _handler


async def handle_intent_outcome_lifecycle(topic: str, payload: dict) -> bool:
    return await get_intent_outcome_lifecycle_handler().handle_lifecycle(topic, payload)
