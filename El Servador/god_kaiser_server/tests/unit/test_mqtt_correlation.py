"""
Unit tests for MQTT handler ContextVar (correlation ID) propagation.

Tests that the Subscriber._run_handler_with_cid() wrapper correctly
sets and clears the ContextVar in the event loop context.
"""

import asyncio

import pytest

from src.core.request_context import (
    get_request_id,
    set_request_id,
    clear_request_id,
)
from src.mqtt.subscriber import Subscriber


@pytest.fixture(autouse=True)
def _cleanup_request_id():
    """Ensure ContextVar is clean before and after each test."""
    clear_request_id()
    yield
    clear_request_id()


@pytest.mark.asyncio
async def test_mqtt_handler_has_correlation_id():
    """CID is available inside the handler via get_request_id()."""
    captured_cid = None

    async def mock_handler(topic: str, payload: dict):
        nonlocal captured_cid
        captured_cid = get_request_id()

    cid = "ESP_001:data:42:1708704000000"
    await Subscriber._run_handler_with_cid(
        mock_handler, "kaiser/god/esp/ESP_001/sensor/temp/data", {}, cid
    )

    assert captured_cid == cid


@pytest.mark.asyncio
async def test_mqtt_handler_cid_cleared_after_handler():
    """CID is cleared after handler completes."""

    async def mock_handler(topic: str, payload: dict):
        pass

    cid = "ESP_002:heartbeat:10:1708704001000"
    await Subscriber._run_handler_with_cid(mock_handler, "test/topic", {}, cid)

    # After handler, CID should be cleared
    assert get_request_id() is None


@pytest.mark.asyncio
async def test_mqtt_handler_cid_cleared_on_exception():
    """CID is cleared even when handler raises an exception."""

    async def failing_handler(topic: str, payload: dict):
        raise ValueError("handler error")

    cid = "ESP_003:error:5:1708704002000"

    with pytest.raises(ValueError, match="handler error"):
        await Subscriber._run_handler_with_cid(failing_handler, "test/topic", {}, cid)

    # Must be cleaned up despite exception
    assert get_request_id() is None


@pytest.mark.asyncio
async def test_parallel_mqtt_messages_isolated():
    """Two concurrent MQTT messages have isolated CIDs."""
    captured_cids = {}

    async def mock_handler(topic: str, payload: dict):
        # Simulate async work to allow interleaving
        await asyncio.sleep(0.01)
        captured_cids[topic] = get_request_id()

    cid_a = "ESP_A:data:1:1000"
    cid_b = "ESP_B:data:2:2000"

    await asyncio.gather(
        Subscriber._run_handler_with_cid(mock_handler, "topic/a", {}, cid_a),
        Subscriber._run_handler_with_cid(mock_handler, "topic/b", {}, cid_b),
    )

    assert captured_cids["topic/a"] == cid_a
    assert captured_cids["topic/b"] == cid_b


@pytest.mark.asyncio
async def test_mqtt_handler_preserves_outer_context():
    """Wrapper restores outer ContextVar state after handler completes."""
    # Set an outer context value
    outer_token = set_request_id("outer-request-id")

    captured_inner = None

    async def mock_handler(topic: str, payload: dict):
        nonlocal captured_inner
        captured_inner = get_request_id()

    cid = "ESP_X:data:99:9999"
    await Subscriber._run_handler_with_cid(mock_handler, "test/topic", {}, cid)

    # Inner handler should have seen the MQTT CID
    assert captured_inner == cid

    # After wrapper, outer context should be restored
    assert get_request_id() == "outer-request-id"

    # Cleanup
    clear_request_id(outer_token)
