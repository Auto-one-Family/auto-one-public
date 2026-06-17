"""
MQTT Handler: ESP32 Heartbeat Metrics (AUT-121 Part 2)

Pure ingest handler for extended runtime metrics published on
``kaiser/{kaiser_id}/esp/{esp_id}/system/heartbeat_metrics``.

Scope:
- Parse the topic via TopicBuilder.
- Buffer latest metrics per esp_id in a TTLCache (no unbounded dict).
- Emit a structured log line for observability.

Explicitly NOT in scope:
- No database writes.
- No WebSocket broadcasts.
- No direct state changes.

The HeartbeatHandler merges the buffered metrics into the next heartbeat
for that ESP (idempotent, freshness-tagged).
"""

import time
from typing import Any, Dict, Optional

from cachetools import TTLCache

from ...core.error_codes import ValidationErrorCode
from ...core.logging_config import get_logger
from ..topics import TopicBuilder

logger = get_logger(__name__)

METRICS_TTL_SECONDS = 120
METRICS_CACHE_MAXSIZE = 10_000


class HeartbeatMetricsHandler:
    """
    Buffers latest heartbeat_metrics payload per ESP.

    Flow:
    1. Parse topic -> extract esp_id.
    2. Validate minimal payload structure.
    3. Store (payload, receive_ts) in TTLCache keyed by esp_id.
    4. Log for observability.
    """

    def __init__(self) -> None:
        self._latest: TTLCache[str, Dict[str, Any]] = TTLCache(
            maxsize=METRICS_CACHE_MAXSIZE, ttl=METRICS_TTL_SECONDS
        )

    def get_latest(self, esp_id: str) -> Optional[Dict[str, Any]]:
        """Return cached metrics entry for *esp_id*, or None if expired/absent."""
        return self._latest.get(esp_id)

    async def handle_heartbeat_metrics(self, topic: str, payload: dict) -> bool:
        """
        Ingest a heartbeat_metrics message.

        Returns True on success, False on topic parse failure.
        """
        try:
            parsed = TopicBuilder.parse_heartbeat_metrics_topic(topic)
            if not parsed:
                logger.error(
                    "[%s] Failed to parse heartbeat_metrics topic: %s",
                    ValidationErrorCode.MISSING_REQUIRED_FIELD,
                    topic,
                )
                return False

            esp_id = parsed["esp_id"]
            safe_payload = payload if isinstance(payload, dict) else {}

            receive_ts = time.time()
            self._latest[esp_id] = {
                "payload": safe_payload,
                "receive_ts": receive_ts,
                "esp_ts": safe_payload.get("ts", 0),
            }

            logger.debug(
                "Heartbeat metrics buffered: esp_id=%s keys=%s",
                esp_id,
                list(safe_payload.keys())[:10],
            )
            return True

        except Exception as e:
            logger.error("Error handling heartbeat_metrics: %s", e, exc_info=True)
            return False


_handler_instance: Optional[HeartbeatMetricsHandler] = None


def get_heartbeat_metrics_handler() -> HeartbeatMetricsHandler:
    """Get singleton heartbeat-metrics handler instance."""
    global _handler_instance
    if _handler_instance is None:
        _handler_instance = HeartbeatMetricsHandler()
    return _handler_instance


async def handle_heartbeat_metrics(topic: str, payload: dict) -> bool:
    """Handle heartbeat_metrics message (convenience function)."""
    handler = get_heartbeat_metrics_handler()
    return await handler.handle_heartbeat_metrics(topic, payload)
