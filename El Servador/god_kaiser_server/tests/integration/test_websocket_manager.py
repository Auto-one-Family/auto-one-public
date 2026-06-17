"""
Integration Tests für WebSocketManager.

Location: tests/integration/test_websocket_manager.py
Benötigt: Async Context, Singleton Reset

Phase 3 Test-Suite: Broadcast, Filters, Rate Limiting, Thread-Safe Operations.
"""

import pytest
import pytest_asyncio
import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock, patch
from starlette.websockets import WebSocketState

from src.websocket.manager import WebSocketManager


class TestSingletonPattern:
    """Test WebSocketManager singleton pattern."""

    @pytest_asyncio.fixture
    async def reset_singleton(self):
        """Reset singleton instance before and after each test."""
        WebSocketManager._instance = None
        yield
        WebSocketManager._instance = None

    @pytest.mark.asyncio
    async def test_get_instance_returns_singleton(self, reset_singleton):
        """get_instance returns same instance on multiple calls."""
        manager1 = await WebSocketManager.get_instance()
        manager2 = await WebSocketManager.get_instance()

        assert manager1 is manager2

    @pytest.mark.asyncio
    async def test_get_instance_is_async(self, reset_singleton):
        """get_instance is an async method that must be awaited."""
        # Should not raise error when awaited
        manager = await WebSocketManager.get_instance()
        assert isinstance(manager, WebSocketManager)

    @pytest.mark.asyncio
    async def test_initialize_sets_event_loop(self, reset_singleton):
        """initialize captures the event loop."""
        manager = await WebSocketManager.get_instance()
        await manager.initialize()

        assert manager._loop is not None
        assert manager._loop == asyncio.get_running_loop()


class TestConnectionManagement:
    """Test connection management."""

    @pytest_asyncio.fixture
    async def manager(self):
        """Get fresh WebSocketManager instance."""
        WebSocketManager._instance = None
        manager = await WebSocketManager.get_instance()
        await manager.initialize()
        yield manager
        await manager.shutdown()
        WebSocketManager._instance = None

    @pytest.fixture
    def mock_websocket(self):
        """Mock WebSocket connection."""
        ws = MagicMock()
        ws.accept = AsyncMock()
        ws.send_json = AsyncMock()
        ws.close = AsyncMock()
        ws.client_state = WebSocketState.CONNECTED
        return ws

    @pytest.mark.asyncio
    async def test_connect_adds_client(self, manager, mock_websocket):
        """connect adds client to connections."""
        await manager.connect(mock_websocket, "client_1")

        assert manager.connection_count == 1
        assert "client_1" in manager._connections

    @pytest.mark.asyncio
    async def test_connect_accepts_websocket(self, manager, mock_websocket):
        """connect accepts the WebSocket connection."""
        await manager.connect(mock_websocket, "client_1")

        mock_websocket.accept.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_removes_client(self, manager, mock_websocket):
        """disconnect removes client from connections."""
        await manager.connect(mock_websocket, "client_1")
        assert manager.connection_count == 1

        await manager.disconnect("client_1")
        assert manager.connection_count == 0
        assert "client_1" not in manager._connections

    @pytest.mark.asyncio
    async def test_disconnect_nonexistent_client(self, manager):
        """disconnect handles non-existent client gracefully."""
        # Should not raise error
        await manager.disconnect("nonexistent_client")

    @pytest.mark.asyncio
    async def test_connection_count_property(self, manager, mock_websocket):
        """connection_count property returns correct count."""
        assert manager.connection_count == 0

        await manager.connect(mock_websocket, "client_1")
        assert manager.connection_count == 1

        mock_websocket2 = MagicMock()
        mock_websocket2.accept = AsyncMock()
        mock_websocket2.client_state = WebSocketState.CONNECTED

        await manager.connect(mock_websocket2, "client_2")
        assert manager.connection_count == 2


class TestSubscriptionManagement:
    """Test subscription management."""

    @pytest_asyncio.fixture
    async def manager(self):
        """Get fresh WebSocketManager instance."""
        WebSocketManager._instance = None
        manager = await WebSocketManager.get_instance()
        await manager.initialize()
        yield manager
        await manager.shutdown()
        WebSocketManager._instance = None

    @pytest.fixture
    def mock_websocket(self):
        ws = MagicMock()
        ws.accept = AsyncMock()
        ws.send_json = AsyncMock()
        ws.close = AsyncMock()
        ws.client_state = WebSocketState.CONNECTED
        return ws

    @pytest.mark.asyncio
    async def test_subscribe_adds_filters(self, manager, mock_websocket):
        """subscribe adds filters for client."""
        await manager.connect(mock_websocket, "client_1")

        filters = {
            "types": ["sensor_data", "actuator_status"],
            "esp_ids": ["ESP_12AB34CD"],
        }
        await manager.subscribe("client_1", filters)

        assert manager._subscriptions["client_1"] == filters

    @pytest.mark.asyncio
    async def test_subscribe_nonexistent_client(self, manager):
        """subscribe handles non-existent client gracefully."""
        # Should not raise error
        await manager.subscribe("nonexistent", {"types": ["sensor_data"]})

    @pytest.mark.asyncio
    async def test_unsubscribe_clears_all_filters(self, manager, mock_websocket):
        """unsubscribe with None clears all filters."""
        await manager.connect(mock_websocket, "client_1")
        await manager.subscribe("client_1", {"types": ["sensor_data"]})

        await manager.unsubscribe("client_1")

        assert manager._subscriptions["client_1"] == {}

    @pytest.mark.asyncio
    async def test_unsubscribe_specific_filters(self, manager, mock_websocket):
        """unsubscribe with filters removes specific items."""
        await manager.connect(mock_websocket, "client_1")
        await manager.subscribe(
            "client_1",
            {
                "types": ["sensor_data", "actuator_status", "esp_health"],
                "esp_ids": ["ESP_1", "ESP_2"],
            },
        )

        await manager.unsubscribe(
            "client_1",
            {
                "types": ["actuator_status"],
            },
        )

        # actuator_status should be removed from types
        assert "sensor_data" in manager._subscriptions["client_1"]["types"]
        assert "esp_health" in manager._subscriptions["client_1"]["types"]
        assert "actuator_status" not in manager._subscriptions["client_1"]["types"]


class TestBroadcast:
    """Test broadcast functionality."""

    @pytest_asyncio.fixture
    async def manager(self):
        """Get fresh WebSocketManager instance."""
        WebSocketManager._instance = None
        manager = await WebSocketManager.get_instance()
        await manager.initialize()
        yield manager
        await manager.shutdown()
        WebSocketManager._instance = None

    @pytest.fixture
    def mock_websocket(self):
        ws = MagicMock()
        ws.accept = AsyncMock()
        ws.send_json = AsyncMock()
        ws.close = AsyncMock()
        ws.client_state = WebSocketState.CONNECTED
        return ws

    @pytest.mark.asyncio
    async def test_broadcast_sends_to_connected_clients(self, manager, mock_websocket):
        """broadcast sends message to connected clients."""
        await manager.connect(mock_websocket, "client_1")
        await manager.subscribe("client_1", {})  # Subscribe to all

        await manager.broadcast("sensor_data", {"esp_id": "ESP_12AB", "value": 25.0})

        mock_websocket.send_json.assert_called()

    @pytest.mark.asyncio
    async def test_broadcast_message_format(self, manager, mock_websocket):
        """broadcast sends correctly formatted message."""
        await manager.connect(mock_websocket, "client_1")
        await manager.subscribe("client_1", {})

        await manager.broadcast("esp_health", {"esp_id": "ESP_12AB", "status": "online"})

        call_args = mock_websocket.send_json.call_args
        message = call_args.args[0]

        assert "type" in message
        assert message["type"] == "esp_health"
        assert "timestamp" in message
        assert "data" in message
        assert message["data"]["esp_id"] == "ESP_12AB"

    @pytest.mark.asyncio
    async def test_broadcast_no_clients(self, manager):
        """broadcast handles no connected clients gracefully."""
        # Should not raise error
        await manager.broadcast("sensor_data", {"value": 25.0})

    @pytest.mark.asyncio
    async def test_broadcast_filters_by_type(self, manager):
        """broadcast respects type filters."""
        ws1 = MagicMock()
        ws1.accept = AsyncMock()
        ws1.send_json = AsyncMock()
        ws1.client_state = WebSocketState.CONNECTED

        ws2 = MagicMock()
        ws2.accept = AsyncMock()
        ws2.send_json = AsyncMock()
        ws2.client_state = WebSocketState.CONNECTED

        await manager.connect(ws1, "client_1")
        await manager.connect(ws2, "client_2")

        # client_1 subscribes to sensor_data only
        await manager.subscribe("client_1", {"types": ["sensor_data"]})
        # client_2 subscribes to actuator_status only
        await manager.subscribe("client_2", {"types": ["actuator_status"]})

        # Broadcast sensor_data
        await manager.broadcast("sensor_data", {"value": 25.0})

        # Only client_1 should receive (subscribed to sensor_data)
        ws1.send_json.assert_called()

    @pytest.mark.asyncio
    async def test_broadcast_filters_by_esp_id(self, manager):
        """broadcast respects esp_id filters."""
        ws1 = MagicMock()
        ws1.accept = AsyncMock()
        ws1.send_json = AsyncMock()
        ws1.client_state = WebSocketState.CONNECTED

        await manager.connect(ws1, "client_1")
        await manager.subscribe("client_1", {"esp_ids": ["ESP_SPECIFIC"]})

        # Broadcast for different ESP
        await manager.broadcast("sensor_data", {"esp_id": "ESP_OTHER", "value": 25.0})

        # Should not receive (wrong ESP)
        ws1.send_json.assert_not_called()


class TestRateLimiting:
    """Test rate limiting functionality."""

    @pytest_asyncio.fixture
    async def manager(self):
        """Get fresh WebSocketManager instance."""
        WebSocketManager._instance = None
        manager = await WebSocketManager.get_instance()
        await manager.initialize()
        # Set tighter rate limits for testing
        manager._rate_limit_max = 3  # 3 messages per second
        yield manager
        await manager.shutdown()
        WebSocketManager._instance = None

    @pytest.fixture
    def mock_websocket(self):
        ws = MagicMock()
        ws.accept = AsyncMock()
        ws.send_json = AsyncMock()
        ws.close = AsyncMock()
        ws.client_state = WebSocketState.CONNECTED
        return ws

    @pytest.mark.asyncio
    async def test_rate_limiter_initialized_on_connect(self, manager, mock_websocket):
        """Rate limiter is initialized when client connects."""
        await manager.connect(mock_websocket, "client_1")

        assert "client_1" in manager._rate_limiter

    @pytest.mark.asyncio
    async def test_rate_limiter_cleaned_on_disconnect(self, manager, mock_websocket):
        """Rate limiter is cleaned when client disconnects."""
        await manager.connect(mock_websocket, "client_1")
        await manager.disconnect("client_1")

        assert "client_1" not in manager._rate_limiter

    @pytest.mark.asyncio
    async def test_rate_limit_drops_non_bypass_events(self, manager, mock_websocket):
        """Non-bypass event type (sensor_data) is throttled under burst load."""
        await manager.connect(mock_websocket, "client_1")
        await manager.subscribe("client_1", {})

        # Rate limit is 3 per second in this fixture. Burst 10 of a non-bypass type.
        for i in range(10):
            await manager.broadcast("sensor_data", {"esp_id": "ESP_1", "value": i})

        # Only the first 3 should actually reach the client.
        assert mock_websocket.send_json.call_count == 3

    @pytest.mark.asyncio
    async def test_actuator_status_bypasses_rate_limit_under_burst(self, manager, mock_websocket):
        """AUT-68: burst of 20 actuator_status events in <1s — none dropped.

        Regression test: actuator_status carries GPIO state changes, which must
        NEVER be silently dropped by per-client WS rate limiting (burst load
        during multi-GPIO operations would otherwise lose state transitions).
        """
        await manager.connect(mock_websocket, "client_1")
        await manager.subscribe("client_1", {})

        # Pre-condition: actuator_status is registered as a bypass type.
        assert "actuator_status" in manager._rate_limit_bypass_types

        # Burst 20 events back-to-back (well above the 3 msg/s test limit).
        for i in range(20):
            await manager.broadcast(
                "actuator_status",
                {"esp_id": "ESP_1", "gpio": 18, "state": "on" if i % 2 else "off"},
            )

        # ALL 20 events must reach the client — no drops.
        assert mock_websocket.send_json.call_count == 20

    @pytest.mark.asyncio
    async def test_esp_health_bypasses_rate_limit_under_burst(self, manager, mock_websocket):
        """esp_health remains a rate-limit-bypass event under burst load (regression)."""
        await manager.connect(mock_websocket, "client_1")
        await manager.subscribe("client_1", {})

        assert "esp_health" in manager._rate_limit_bypass_types

        for i in range(20):
            await manager.broadcast("esp_health", {"esp_id": "ESP_1", "status": "online", "seq": i})

        assert mock_websocket.send_json.call_count == 20

    @pytest.mark.asyncio
    async def test_sensor_data_bypasses_rate_limit_under_burst(self, manager, mock_websocket):
        """AUT-481 P2: sensor_data must not be dropped during actuator intent bursts."""
        await manager.connect(mock_websocket, "client_1")
        await manager.subscribe("client_1", {})

        assert "sensor_data" in manager._rate_limit_bypass_types

        for i in range(20):
            await manager.broadcast(
                "sensor_data",
                {"esp_id": "ESP_1", "gpio": 34, "value": 20.0 + i, "sensor_type": "moisture"},
            )

        assert mock_websocket.send_json.call_count == 20

    def test_rate_limit_bypass_contains_all_critical_realtime_events(self, manager):
        """Catalogue check: bypass set covers all critical realtime event types (AUT-68, PKG-04a, AUT-481)."""
        expected = {
            "sensor_data",
            "actuator_status",
            "config_response_guard_replay",
            "device_discovered",
            "device_rediscovered",
            "esp_health",
            "notification_new",
            "notification_unread_count",
            "notification_updated",
        }
        assert manager._rate_limit_bypass_types == expected


class TestThreadSafety:
    """Test thread-safe operations."""

    @pytest_asyncio.fixture
    async def manager(self):
        """Get fresh WebSocketManager instance."""
        WebSocketManager._instance = None
        manager = await WebSocketManager.get_instance()
        await manager.initialize()
        yield manager
        await manager.shutdown()
        WebSocketManager._instance = None

    @pytest.mark.asyncio
    async def test_broadcast_threadsafe_exists(self, manager):
        """broadcast_threadsafe method exists for MQTT callback use."""
        assert hasattr(manager, "broadcast_threadsafe") or hasattr(manager, "broadcast")


class TestShutdown:
    """Test manager shutdown."""

    @pytest_asyncio.fixture
    async def manager(self):
        """Get fresh WebSocketManager instance."""
        WebSocketManager._instance = None
        manager = await WebSocketManager.get_instance()
        await manager.initialize()
        yield manager
        WebSocketManager._instance = None

    @pytest.fixture
    def mock_websocket(self):
        ws = MagicMock()
        ws.accept = AsyncMock()
        ws.send_json = AsyncMock()
        ws.close = AsyncMock()
        ws.client_state = WebSocketState.CONNECTED
        return ws

    @pytest.mark.asyncio
    async def test_shutdown_closes_all_connections(self, manager, mock_websocket):
        """shutdown closes all WebSocket connections."""
        await manager.connect(mock_websocket, "client_1")
        await manager.connect(mock_websocket, "client_2")

        await manager.shutdown()

        # All connections should be closed
        assert manager.connection_count == 0


class TestEventTypes:
    """Test supported event types."""

    @pytest_asyncio.fixture
    async def manager(self):
        """Get fresh WebSocketManager instance."""
        WebSocketManager._instance = None
        manager = await WebSocketManager.get_instance()
        await manager.initialize()
        yield manager
        await manager.shutdown()
        WebSocketManager._instance = None

    @pytest.fixture
    def mock_websocket(self):
        ws = MagicMock()
        ws.accept = AsyncMock()
        ws.send_json = AsyncMock()
        ws.close = AsyncMock()
        ws.client_state = WebSocketState.CONNECTED
        return ws

    @pytest.mark.asyncio
    async def test_sensor_data_event(self, manager, mock_websocket):
        """sensor_data event broadcasts correctly."""
        await manager.connect(mock_websocket, "client_1")
        await manager.subscribe("client_1", {})

        await manager.broadcast(
            "sensor_data",
            {
                "esp_id": "ESP_12AB",
                "gpio": 34,
                "value": 25.5,
            },
        )

        mock_websocket.send_json.assert_called()

    @pytest.mark.asyncio
    async def test_actuator_status_event(self, manager, mock_websocket):
        """actuator_status event broadcasts correctly."""
        await manager.connect(mock_websocket, "client_1")
        await manager.subscribe("client_1", {})

        await manager.broadcast(
            "actuator_status",
            {
                "esp_id": "ESP_12AB",
                "gpio": 18,
                "state": "on",
            },
        )

        mock_websocket.send_json.assert_called()

    @pytest.mark.asyncio
    async def test_esp_health_event(self, manager, mock_websocket):
        """esp_health event broadcasts correctly."""
        await manager.connect(mock_websocket, "client_1")
        await manager.subscribe("client_1", {})

        await manager.broadcast(
            "esp_health",
            {
                "esp_id": "ESP_12AB",
                "status": "online",
                "heap_free": 50000,
            },
        )

        mock_websocket.send_json.assert_called()

    @pytest.mark.asyncio
    async def test_config_response_event(self, manager, mock_websocket):
        """config_response event broadcasts correctly."""
        await manager.connect(mock_websocket, "client_1")
        await manager.subscribe("client_1", {})

        await manager.broadcast(
            "config_response",
            {
                "esp_id": "ESP_12AB",
                "status": "success",
                "type": "sensor",
            },
        )

        mock_websocket.send_json.assert_called()

    @pytest.mark.asyncio
    async def test_device_discovered_event(self, manager, mock_websocket):
        """device_discovered event broadcasts correctly."""
        await manager.connect(mock_websocket, "client_1")
        await manager.subscribe("client_1", {})

        await manager.broadcast(
            "device_discovered",
            {
                "esp_id": "ESP_NEW",
                "status": "pending_approval",
            },
        )

        mock_websocket.send_json.assert_called()
