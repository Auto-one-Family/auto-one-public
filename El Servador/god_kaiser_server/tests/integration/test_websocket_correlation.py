"""
Integration tests for WebSocket correlation ID propagation.

Verifies that correlation IDs from MQTT message processing
appear in WebSocket broadcast messages sent to the frontend.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.core.request_context import (
    clear_request_id,
    set_request_id,
)
from src.websocket.manager import WebSocketManager


@pytest.fixture
def ws_manager():
    """Create a fresh WebSocketManager for testing."""
    # Reset singleton
    WebSocketManager._instance = None
    manager = WebSocketManager()
    manager._loop = asyncio.get_event_loop()
    return manager


@pytest.fixture
def mock_websocket():
    """Create a mock WebSocket connection."""
    ws = AsyncMock()
    ws.client_state = 1  # WebSocketState.CONNECTED
    ws.send_json = AsyncMock()
    return ws


@pytest.fixture
async def connected_manager(ws_manager, mock_websocket):
    """WebSocketManager with one connected client."""
    await ws_manager.connect(mock_websocket, "test-client")
    await ws_manager.subscribe("test-client", {"types": ["sensor_data"]})
    return ws_manager


@pytest.mark.asyncio
async def test_sensor_broadcast_contains_cid(connected_manager, mock_websocket):
    """WebSocket broadcast includes correlation_id from MQTT context."""
    set_request_id("ESP_001:data:42:1708704000000")
    try:
        await connected_manager.broadcast("sensor_data", {"esp_id": "ESP_001", "value": 23.5})

        mock_websocket.send_json.assert_called_once()
        message = mock_websocket.send_json.call_args[0][0]
        assert message["correlation_id"] == "ESP_001:data:42:1708704000000"
        assert message["type"] == "sensor_data"
        assert message["data"]["value"] == 23.5
    finally:
        clear_request_id()


@pytest.mark.asyncio
async def test_broadcast_without_cid_omits_field(connected_manager, mock_websocket):
    """When no correlation_id is set, the field is omitted from broadcast."""
    clear_request_id()
    await connected_manager.broadcast("sensor_data", {"esp_id": "ESP_001"})

    mock_websocket.send_json.assert_called_once()
    message = mock_websocket.send_json.call_args[0][0]
    assert "correlation_id" not in message


@pytest.mark.asyncio
async def test_explicit_cid_overrides_context(connected_manager, mock_websocket):
    """Explicit correlation_id parameter takes precedence over ContextVar."""
    set_request_id("context-cid")
    try:
        await connected_manager.broadcast(
            "sensor_data",
            {"esp_id": "ESP_001"},
            correlation_id="explicit-cid",
        )

        message = mock_websocket.send_json.call_args[0][0]
        assert message["correlation_id"] == "explicit-cid"
    finally:
        clear_request_id()


@pytest.mark.asyncio
async def test_broadcast_threadsafe_passes_cid(ws_manager, mock_websocket):
    """broadcast_threadsafe passes correlation_id to async broadcast."""
    await ws_manager.connect(mock_websocket, "test-client")
    await ws_manager.subscribe("test-client", {"types": ["actuator_status"]})

    ws_manager._loop = asyncio.get_running_loop()

    with patch.object(ws_manager, "broadcast", new_callable=AsyncMock) as mock_broadcast:
        ws_manager.broadcast_threadsafe(
            "actuator_status",
            {"gpio": 12, "state": True},
            correlation_id="ESP_001:status:99:123456",
        )
        # Allow the coroutine to execute
        await asyncio.sleep(0.1)

        mock_broadcast.assert_called_once_with(
            "actuator_status",
            {"gpio": 12, "state": True},
            None,
            correlation_id="ESP_001:status:99:123456",
        )


@pytest.mark.asyncio
async def test_envelope_data_divergence_emits_contract_metrics(connected_manager, mock_websocket):
    """Divergence between envelope and data correlation emits mismatch metrics."""
    with (
        patch("src.websocket.manager.increment_ws_envelope_data_divergence") as div_metric,
        patch("src.websocket.manager.increment_ws_contract_mismatch") as mismatch_metric,
        patch("src.websocket.manager.increment_ws_missing_correlation") as missing_metric,
    ):
        await connected_manager.broadcast(
            "sensor_data",
            {"esp_id": "ESP_001", "value": 23.5, "correlation_id": "domain-cid"},
            correlation_id="envelope-cid",
        )

        message = mock_websocket.send_json.call_args[0][0]
        assert message["correlation_id"] == "envelope-cid"
        assert message["data"]["correlation_id"] == "domain-cid"
        div_metric.assert_called_once()
        mismatch_metric.assert_called_once()
        missing_metric.assert_not_called()


@pytest.mark.asyncio
async def test_missing_correlation_increments_metric(connected_manager, mock_websocket):
    """Missing envelope and data correlation increments dedicated metric."""
    with (
        patch("src.websocket.manager.increment_ws_envelope_data_divergence") as div_metric,
        patch("src.websocket.manager.increment_ws_contract_mismatch") as mismatch_metric,
        patch("src.websocket.manager.increment_ws_missing_correlation") as missing_metric,
    ):
        await connected_manager.broadcast("sensor_data", {"esp_id": "ESP_001", "value": 21.0})

        message = mock_websocket.send_json.call_args[0][0]
        assert "correlation_id" not in message
        missing_metric.assert_called_once()
        div_metric.assert_not_called()
        mismatch_metric.assert_not_called()
