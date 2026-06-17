"""AUT-121 unit tests for heartbeat_metrics_handler."""

import time

import pytest

from src.mqtt.handlers.heartbeat_metrics_handler import (
    HeartbeatMetricsHandler,
    METRICS_TTL_SECONDS,
)


@pytest.fixture
def handler() -> HeartbeatMetricsHandler:
    return HeartbeatMetricsHandler()


# ── Topic parsing ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_happy_path_buffers_metrics(handler: HeartbeatMetricsHandler) -> None:
    topic = "kaiser/god/esp/ESP_AABB1122/system/heartbeat_metrics"
    payload = {"heap_min_free": 30000, "loop_time_avg_us": 4200, "ts": 1700000000}

    result = await handler.handle_heartbeat_metrics(topic, payload)

    assert result is True
    entry = handler.get_latest("ESP_AABB1122")
    assert entry is not None
    assert entry["payload"]["heap_min_free"] == 30000
    assert entry["esp_ts"] == 1700000000
    assert entry["receive_ts"] > 0


@pytest.mark.asyncio
async def test_invalid_topic_returns_false(handler: HeartbeatMetricsHandler) -> None:
    result = await handler.handle_heartbeat_metrics(
        "kaiser/god/esp/ESP_AABB1122/system/heartbeat", {"ts": 1}
    )
    assert result is False


@pytest.mark.asyncio
async def test_malformed_topic_returns_false(handler: HeartbeatMetricsHandler) -> None:
    result = await handler.handle_heartbeat_metrics("bogus/topic", {"ts": 1})
    assert result is False


# ── Cache behaviour ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_latest_overwrite(handler: HeartbeatMetricsHandler) -> None:
    topic = "kaiser/god/esp/ESP_001/system/heartbeat_metrics"

    await handler.handle_heartbeat_metrics(topic, {"version": 1, "ts": 100})
    await handler.handle_heartbeat_metrics(topic, {"version": 2, "ts": 200})

    entry = handler.get_latest("ESP_001")
    assert entry is not None
    assert entry["payload"]["version"] == 2


@pytest.mark.asyncio
async def test_get_latest_returns_none_for_unknown_esp(
    handler: HeartbeatMetricsHandler,
) -> None:
    assert handler.get_latest("ESP_NONEXISTENT") is None


# ── Non-dict payload safety ────────────────────────────────────────


@pytest.mark.asyncio
async def test_non_dict_payload_treated_as_empty(
    handler: HeartbeatMetricsHandler,
) -> None:
    topic = "kaiser/god/esp/ESP_002/system/heartbeat_metrics"
    result = await handler.handle_heartbeat_metrics(topic, "not-a-dict")  # type: ignore[arg-type]
    assert result is True
    entry = handler.get_latest("ESP_002")
    assert entry is not None
    assert entry["payload"] == {}
