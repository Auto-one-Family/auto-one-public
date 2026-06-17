"""
Unit Tests: DiagnosticsHandler (MQTT System Diagnostics)

Tests the DiagnosticsHandler which processes ESP32 health snapshots
published to kaiser/{kaiser_id}/esp/{esp_id}/system/diagnostics.

The handler:
1. Parses topic via TopicBuilder.parse_system_diagnostics_topic()
2. Validates payload (requires heap_free:int, wifi_rssi:int)
3. Looks up ESP device via ESPRepository.get_by_device_id()
4. Updates device_metadata["diagnostics"] and commits
5. Broadcasts via WebSocketManager

Mock Strategy:
- resilient_session: async context manager yielding mock session
- ESPRepository: constructor takes session, async get_by_device_id()
- WebSocketManager: class with async get_instance() + async broadcast()
"""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.error_codes import ConfigErrorCode, ValidationErrorCode
from src.mqtt.handlers.diagnostics_handler import (
    DiagnosticsHandler,
    get_diagnostics_handler,
)
from src.mqtt.topics import TopicBuilder

# =============================================================================
# Test Data Constants
# =============================================================================

VALID_TOPIC = "kaiser/god/esp/ESP_TEST_001/system/diagnostics"
INVALID_TOPIC = "kaiser/god/esp/ESP_TEST_001/sensor/34/data"

FULL_PAYLOAD = {
    "ts": 1735818000,
    "esp_id": "ESP_TEST_001",
    "heap_free": 150000,
    "heap_min_free": 120000,
    "heap_fragmentation": 15,
    "uptime_seconds": 3600,
    "error_count": 3,
    "wifi_connected": True,
    "wifi_rssi": -65,
    "mqtt_connected": True,
    "sensor_count": 4,
    "actuator_count": 2,
    "system_state": "OPERATIONAL",
}

MINIMAL_PAYLOAD = {
    "heap_free": 150000,
    "wifi_rssi": -65,
}


# =============================================================================
# Helper: Mock resilient_session context manager
# =============================================================================


def create_mock_session_and_repo(esp_device=None):
    """
    Create mock session, repository, and WebSocket manager for handler tests.

    Args:
        esp_device: The ESPDevice mock to return from get_by_device_id().
                    None simulates device not found.

    Returns:
        Tuple of (mock_session, mock_esp_repo, mock_ws_manager, session_patcher, ws_patcher, repo_patcher)
    """
    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()

    mock_esp_repo = MagicMock()
    mock_esp_repo.get_by_device_id = AsyncMock(return_value=esp_device)

    mock_ws_instance = AsyncMock()
    mock_ws_instance.broadcast = AsyncMock()

    mock_ws_manager = MagicMock()
    mock_ws_manager.get_instance = AsyncMock(return_value=mock_ws_instance)

    @asynccontextmanager
    async def mock_resilient_session():
        yield mock_session

    session_patcher = patch(
        "src.mqtt.handlers.diagnostics_handler.resilient_session",
        mock_resilient_session,
    )
    repo_patcher = patch(
        "src.mqtt.handlers.diagnostics_handler.ESPRepository",
        return_value=mock_esp_repo,
    )
    # WebSocketManager is imported inline (lazy import inside handle_diagnostics),
    # so we patch it at its source module where the inline import resolves it.
    ws_patcher = patch(
        "src.websocket.manager.WebSocketManager",
        mock_ws_manager,
    )

    return (
        mock_session,
        mock_esp_repo,
        mock_ws_instance,
        session_patcher,
        repo_patcher,
        ws_patcher,
    )


def create_mock_esp_device(device_id: str = "ESP_TEST_001") -> MagicMock:
    """
    Create a mock ESPDevice with device_metadata.

    Args:
        device_id: The device ID for the mock device.

    Returns:
        MagicMock simulating an ESPDevice instance.
    """
    device = MagicMock()
    device.device_id = device_id
    device.device_metadata = {}
    return device


# =============================================================================
# Tests
# =============================================================================


class TestDiagnosticsHandler:
    """Unit tests for DiagnosticsHandler."""

    @pytest.mark.asyncio
    async def test_handle_diagnostics_valid_payload(self):
        """Happy path: full payload processes successfully and returns True."""
        mock_device = create_mock_esp_device()
        (
            mock_session,
            mock_esp_repo,
            mock_ws_instance,
            session_patcher,
            repo_patcher,
            ws_patcher,
        ) = create_mock_session_and_repo(esp_device=mock_device)

        handler = DiagnosticsHandler()

        with session_patcher, repo_patcher, ws_patcher:
            result = await handler.handle_diagnostics(VALID_TOPIC, FULL_PAYLOAD.copy())

        assert result is True
        mock_esp_repo.get_by_device_id.assert_awaited_once_with("ESP_TEST_001")
        mock_session.commit.assert_awaited_once()
        mock_ws_instance.broadcast.assert_awaited_once()

        # Verify broadcast event type and esp_id
        broadcast_args = mock_ws_instance.broadcast.call_args
        assert broadcast_args[0][0] == "esp_diagnostics"
        assert broadcast_args[0][1]["esp_id"] == "ESP_TEST_001"

    @pytest.mark.asyncio
    async def test_handle_diagnostics_minimal_payload(self):
        """Minimal payload with only required fields processes successfully."""
        mock_device = create_mock_esp_device()
        (
            mock_session,
            mock_esp_repo,
            mock_ws_instance,
            session_patcher,
            repo_patcher,
            ws_patcher,
        ) = create_mock_session_and_repo(esp_device=mock_device)

        handler = DiagnosticsHandler()

        with session_patcher, repo_patcher, ws_patcher:
            result = await handler.handle_diagnostics(VALID_TOPIC, MINIMAL_PAYLOAD.copy())

        assert result is True
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_handle_diagnostics_missing_heap_free(self):
        """Payload without heap_free fails validation and returns False."""
        handler = DiagnosticsHandler()

        payload = {"wifi_rssi": -65, "uptime_seconds": 3600}

        # No need to mock DB/WS - validation fails before DB access
        result = await handler.handle_diagnostics(VALID_TOPIC, payload)

        assert result is False

    @pytest.mark.asyncio
    async def test_handle_diagnostics_missing_wifi_rssi(self):
        """Payload without wifi_rssi fails validation and returns False."""
        handler = DiagnosticsHandler()

        payload = {"heap_free": 150000, "uptime_seconds": 3600}

        result = await handler.handle_diagnostics(VALID_TOPIC, payload)

        assert result is False

    @pytest.mark.asyncio
    async def test_handle_diagnostics_wrong_type_heap_free(self):
        """heap_free as string fails type validation and returns False."""
        handler = DiagnosticsHandler()

        payload = {"heap_free": "150000", "wifi_rssi": -65}

        result = await handler.handle_diagnostics(VALID_TOPIC, payload)

        assert result is False

    @pytest.mark.asyncio
    async def test_handle_diagnostics_unknown_device(self):
        """Unknown ESP device (not in DB) returns False."""
        (
            mock_session,
            mock_esp_repo,
            mock_ws_instance,
            session_patcher,
            repo_patcher,
            ws_patcher,
        ) = create_mock_session_and_repo(esp_device=None)

        handler = DiagnosticsHandler()

        with session_patcher, repo_patcher, ws_patcher:
            result = await handler.handle_diagnostics(VALID_TOPIC, FULL_PAYLOAD.copy())

        assert result is False
        mock_esp_repo.get_by_device_id.assert_awaited_once_with("ESP_TEST_001")
        mock_session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_handle_diagnostics_invalid_topic(self):
        """Invalid topic format returns False without DB access."""
        handler = DiagnosticsHandler()

        result = await handler.handle_diagnostics(INVALID_TOPIC, FULL_PAYLOAD.copy())

        assert result is False

    @pytest.mark.asyncio
    async def test_handle_diagnostics_db_metadata_updated(self):
        """Verify device_metadata['diagnostics'] contains correct fields after processing."""
        mock_device = create_mock_esp_device()
        (
            mock_session,
            mock_esp_repo,
            mock_ws_instance,
            session_patcher,
            repo_patcher,
            ws_patcher,
        ) = create_mock_session_and_repo(esp_device=mock_device)

        handler = DiagnosticsHandler()

        with session_patcher, repo_patcher, ws_patcher:
            result = await handler.handle_diagnostics(VALID_TOPIC, FULL_PAYLOAD.copy())

        assert result is True

        # Verify diagnostics metadata was written to device
        diagnostics = mock_device.device_metadata.get("diagnostics")
        assert diagnostics is not None, "device_metadata['diagnostics'] must be set"

        # Verify all expected fields from the full payload
        assert diagnostics["heap_free"] == 150000
        assert diagnostics["heap_min_free"] == 120000
        assert diagnostics["heap_fragmentation"] == 15
        assert diagnostics["uptime_seconds"] == 3600
        assert diagnostics["error_count"] == 3
        assert diagnostics["wifi_connected"] is True
        assert diagnostics["wifi_rssi"] == -65
        assert diagnostics["mqtt_connected"] is True
        assert diagnostics["sensor_count"] == 4
        assert diagnostics["actuator_count"] == 2
        assert diagnostics["system_state"] == "OPERATIONAL"
        assert "received_at" in diagnostics, "received_at timestamp must be set"


class TestDiagnosticsHandlerSingleton:
    """Test the module-level convenience function and singleton pattern."""

    def test_get_diagnostics_handler_returns_instance(self):
        """get_diagnostics_handler() returns a DiagnosticsHandler instance."""
        # Reset singleton to avoid state leakage from other tests
        import src.mqtt.handlers.diagnostics_handler as module

        module._handler_instance = None

        handler = get_diagnostics_handler()
        assert isinstance(handler, DiagnosticsHandler)

    def test_get_diagnostics_handler_is_singleton(self):
        """Calling get_diagnostics_handler() twice returns the same instance."""
        import src.mqtt.handlers.diagnostics_handler as module

        module._handler_instance = None

        handler1 = get_diagnostics_handler()
        handler2 = get_diagnostics_handler()
        assert handler1 is handler2

        # Cleanup
        module._handler_instance = None
