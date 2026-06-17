"""Unit tests: AUT-347 tracing_degraded emit helper."""

from __future__ import annotations

from unittest.mock import patch

from src.mqtt.handlers.tracing_degraded_emit import emit_tracing_degraded


def test_emit_always_increments_metric_rate_limits_logs() -> None:
    with (
        patch(
            "src.mqtt.handlers.tracing_degraded_emit.increment_intent_tracing_degraded"
        ) as inc,
        patch("src.mqtt.handlers.tracing_degraded_emit.logger") as log,
    ):
        emit_tracing_degraded("ESP_A", "reason_x", "msg %s", "a")
        emit_tracing_degraded("ESP_A", "reason_x", "msg %s", "b")
    assert inc.call_count == 2
    assert log.info.call_count == 1
