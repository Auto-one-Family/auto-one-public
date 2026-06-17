"""AUT-347: rate-limited ``tracing_degraded`` logs + Prometheus counter for intent trace gaps."""

from __future__ import annotations

import threading
import time
from typing import Any

from ...core.logging_config import get_logger
from ...core.metrics import increment_intent_tracing_degraded

logger = get_logger(__name__)

_lock = threading.Lock()
_last_log_mono: dict[tuple[str, str], float] = {}
_LOG_INTERVAL_SEC = 60.0


def emit_tracing_degraded(esp_id: str, reason: str, log_message: str, *args: Any) -> None:
    """Always increment metrics; emit at most one structured log per (esp_id, reason) per minute."""
    increment_intent_tracing_degraded(reason, esp_id)
    key = (str(esp_id)[:128], str(reason)[:64])
    now = time.monotonic()
    with _lock:
        last = _last_log_mono.get(key, 0.0)
        if now - last < _LOG_INTERVAL_SEC:
            return
        _last_log_mono[key] = now
    logger.info(log_message, *args)
