"""Unit tests: intent_outcome/lifecycle handler (AUT-347 malformed path)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.mqtt.handlers.intent_outcome_lifecycle_handler import (
    IntentOutcomeLifecycleHandler,
)


@pytest.mark.asyncio
async def test_malformed_lifecycle_returns_true_and_emits_tracing_degraded() -> None:
    handler = IntentOutcomeLifecycleHandler()
    topic = "kaiser/god/esp/ESP_UNIT/system/intent_outcome/lifecycle"
    payload = {"schema": "intent_chain_stage_v1", "ts": 1}  # missing event_type

    with patch(
        "src.mqtt.handlers.intent_outcome_lifecycle_handler.emit_tracing_degraded"
    ) as emit:
        ok = await handler.handle_lifecycle(topic, payload)
    assert ok is True
    emit.assert_called_once()
    assert emit.call_args[0][0] == "ESP_UNIT"
    assert emit.call_args[0][1] == "malformed_lifecycle_payload"
