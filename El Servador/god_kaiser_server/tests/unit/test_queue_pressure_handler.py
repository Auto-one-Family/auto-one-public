"""Unit tests for QueuePressureHandler (AUT-345: Loki visibility at LOG_LEVEL=WARNING)."""

import logging
from unittest.mock import patch

import pytest

from src.mqtt.handlers.queue_pressure_handler import QueuePressureHandler


@pytest.mark.asyncio
async def test_entered_pressure_logs_at_warning(caplog):
    handler = QueuePressureHandler()
    topic = "kaiser/god/esp/ESP_TEST/system/queue_pressure"
    payload = {
        "event": "entered_pressure",
        "fill_level": 7,
        "high_watermark": 8,
        "shed_count": 1,
        "drop_count": 0,
    }

    with caplog.at_level(logging.WARNING):
        with patch(
            "src.mqtt.handlers.queue_pressure_handler.increment_queue_pressure_event"
        ) as mock_inc, patch.object(
            handler, "_persist_transition"
        ) as mock_persist, patch.object(
            handler, "_broadcast_transition"
        ) as mock_broadcast:
            ok = await handler.handle_queue_pressure(topic, payload)

    assert ok is True
    mock_inc.assert_called_once_with("ESP_TEST", "entered_pressure")
    mock_persist.assert_called_once()
    mock_broadcast.assert_called_once()
    assert any(r.levelno == logging.WARNING for r in caplog.records)
    assert "Queue pressure event" in caplog.text
    assert "entered_pressure" in caplog.text


@pytest.mark.asyncio
async def test_recovered_logs_at_info(caplog):
    handler = QueuePressureHandler()
    topic = "kaiser/god/esp/ESP_TEST/system/queue_pressure"
    payload = {
        "event": "recovered",
        "fill_level": 0,
        "high_watermark": 8,
        "shed_count": 0,
        "drop_count": 0,
    }

    with caplog.at_level(logging.INFO):
        with patch(
            "src.mqtt.handlers.queue_pressure_handler.increment_queue_pressure_event"
        ), patch.object(
            handler, "_persist_transition"
        ), patch.object(
            handler, "_broadcast_transition"
        ):
            ok = await handler.handle_queue_pressure(topic, payload)

    assert ok is True
    assert any(r.levelno == logging.INFO for r in caplog.records)
    assert "recovered" in caplog.text


@pytest.mark.asyncio
async def test_parse_failure_returns_false(caplog):
    handler = QueuePressureHandler()
    with caplog.at_level(logging.ERROR):
        ok = await handler.handle_queue_pressure("invalid/topic", {})

    assert ok is False
    assert "Failed to parse queue_pressure topic" in caplog.text


def test_normalize_recovered_to_exited_pressure():
    assert QueuePressureHandler._normalize_event("recovered") == "exited_pressure"
    assert QueuePressureHandler._normalize_event("entered_pressure") == "entered_pressure"
