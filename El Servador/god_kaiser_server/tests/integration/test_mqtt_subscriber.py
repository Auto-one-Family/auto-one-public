"""
Integration Tests für MQTT Subscriber.

Location: tests/integration/test_mqtt_subscriber.py
Benötigt: Event-Loop, Thread-Pool

Phase 3 Test-Suite: Handler Registration, Message Routing, Error Isolation, Event Loop Binding.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from src.mqtt.subscriber import Subscriber
from src.mqtt.topics import TopicBuilder


class TestHandlerRegistration:
    """Test handler registration."""

    def test_register_handler_adds_to_registry(self):
        """Handler is added to internal registry."""
        with patch("src.mqtt.subscriber.MQTTClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.get_instance.return_value = mock_client

            subscriber = Subscriber(max_workers=2)
            try:

                async def handler(topic, payload):
                    return True

                subscriber.register_handler("kaiser/god/esp/+/sensor/+/data", handler)

                assert "kaiser/god/esp/+/sensor/+/data" in subscriber.handlers
                assert subscriber.handlers["kaiser/god/esp/+/sensor/+/data"] == handler
            finally:
                subscriber.shutdown(wait=False)

    def test_register_multiple_handlers(self):
        """Multiple handlers can be registered."""
        with patch("src.mqtt.subscriber.MQTTClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.get_instance.return_value = mock_client

            subscriber = Subscriber(max_workers=2)
            try:

                async def handler1(topic, payload):
                    return True

                async def handler2(topic, payload):
                    return True

                subscriber.register_handler("pattern/1", handler1)
                subscriber.register_handler("pattern/2", handler2)

                assert len(subscriber.handlers) == 2
                assert "pattern/1" in subscriber.handlers
                assert "pattern/2" in subscriber.handlers
            finally:
                subscriber.shutdown(wait=False)

    def test_unregister_handler(self):
        """Handler can be unregistered."""
        with patch("src.mqtt.subscriber.MQTTClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.get_instance.return_value = mock_client

            subscriber = Subscriber(max_workers=2)
            try:

                async def handler(topic, payload):
                    return True

                subscriber.register_handler("pattern/1", handler)
                assert "pattern/1" in subscriber.handlers

                result = subscriber.unregister_handler("pattern/1")
                assert result is True
                assert "pattern/1" not in subscriber.handlers
            finally:
                subscriber.shutdown(wait=False)

    def test_unregister_nonexistent_handler(self):
        """Unregistering non-existent handler returns False."""
        with patch("src.mqtt.subscriber.MQTTClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.get_instance.return_value = mock_client

            subscriber = Subscriber(max_workers=2)
            try:
                result = subscriber.unregister_handler("nonexistent/pattern")
                assert result is False
            finally:
                subscriber.shutdown(wait=False)

    def test_get_registered_patterns(self):
        """Get list of registered patterns."""
        with patch("src.mqtt.subscriber.MQTTClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.get_instance.return_value = mock_client

            subscriber = Subscriber(max_workers=2)
            try:

                async def handler1(topic, payload):
                    return True

                async def handler2(topic, payload):
                    return True

                subscriber.register_handler("pattern/1", handler1)
                subscriber.register_handler("pattern/2", handler2)

                patterns = subscriber.get_registered_patterns()
                assert "pattern/1" in patterns
                assert "pattern/2" in patterns
                assert len(patterns) == 2
            finally:
                subscriber.shutdown(wait=False)


class TestMessageRouting:
    """Test message routing to handlers."""

    def test_find_handler_matches_pattern(self):
        """_find_handler matches correct pattern."""
        with patch("src.mqtt.subscriber.MQTTClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.get_instance.return_value = mock_client

            subscriber = Subscriber(max_workers=2)
            try:

                async def sensor_handler(topic, payload):
                    return True

                subscriber.register_handler("kaiser/god/esp/+/sensor/+/data", sensor_handler)

                found = subscriber._find_handler("kaiser/god/esp/ESP_12AB/sensor/34/data")
                assert found == sensor_handler
            finally:
                subscriber.shutdown(wait=False)

    def test_find_handler_returns_none_for_no_match(self):
        """_find_handler returns None when no pattern matches."""
        with patch("src.mqtt.subscriber.MQTTClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.get_instance.return_value = mock_client

            subscriber = Subscriber(max_workers=2)
            try:

                async def handler(topic, payload):
                    return True

                subscriber.register_handler("pattern/specific", handler)

                found = subscriber._find_handler("different/topic")
                assert found is None
            finally:
                subscriber.shutdown(wait=False)

    def test_find_handler_wildcard_matching(self):
        """_find_handler supports MQTT wildcards."""
        with patch("src.mqtt.subscriber.MQTTClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.get_instance.return_value = mock_client

            subscriber = Subscriber(max_workers=2)
            try:

                async def heartbeat_handler(topic, payload):
                    return True

                subscriber.register_handler("kaiser/god/esp/+/system/heartbeat", heartbeat_handler)

                # Different ESP IDs should match
                found1 = subscriber._find_handler("kaiser/god/esp/ESP_12AB34CD/system/heartbeat")
                found2 = subscriber._find_handler("kaiser/god/esp/ESP_OTHER/system/heartbeat")
                found3 = subscriber._find_handler("kaiser/god/esp/MOCK_TEST/system/heartbeat")

                assert found1 == heartbeat_handler
                assert found2 == heartbeat_handler
                assert found3 == heartbeat_handler
            finally:
                subscriber.shutdown(wait=False)

    def test_critical_topic_detection(self):
        """Critical inbound classes are detected for durable inbox."""
        assert Subscriber._is_critical_topic("kaiser/god/esp/ESP_1/system/error") is True
        assert Subscriber._is_critical_topic("kaiser/god/esp/ESP_1/config_response") is True
        assert Subscriber._is_critical_topic("kaiser/god/esp/ESP_1/system/intent_outcome") is True
        assert (
            Subscriber._is_critical_topic("kaiser/god/esp/ESP_1/system/intent_outcome/lifecycle")
            is True
        )
        assert Subscriber._is_critical_topic("kaiser/god/esp/ESP_1/sensor/34/data") is True
        assert Subscriber._is_critical_topic("kaiser/god/esp/ESP_1/system/will") is True
        assert Subscriber._is_critical_topic("kaiser/god/esp/ESP_1/system/heartbeat") is False

    def test_route_message_prefers_payload_correlation_id_for_handler_context(self):
        """If payload has correlation_id, it is forwarded to handler execution."""
        with patch("src.mqtt.subscriber.MQTTClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.get_instance.return_value = mock_client

            subscriber = Subscriber(max_workers=2)
            try:
                submit_mock = MagicMock()
                subscriber.executor.submit = submit_mock

                async def handler(topic, payload):
                    return True

                subscriber.register_handler("kaiser/god/esp/+/actuator/+/status", handler)
                subscriber._route_message(
                    "kaiser/god/esp/ESP_TEST/actuator/25/status",
                    '{"esp_id":"ESP_TEST","seq":42,"correlation_id":"cid-from-payload"}',
                )

                submit_mock.assert_called_once()
                assert submit_mock.call_args.args[4] == "cid-from-payload"
            finally:
                subscriber.shutdown(wait=False)


class TestErrorIsolation:
    """Test error isolation in handler execution."""

    def test_invalid_json_increments_failed_counter(self):
        """Invalid JSON payload increments messages_failed."""
        with patch("src.mqtt.subscriber.MQTTClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.get_instance.return_value = mock_client

            subscriber = Subscriber(max_workers=2)
            try:
                initial_failed = subscriber.messages_failed

                subscriber._route_message("some/topic", "invalid json {{{")

                assert subscriber.messages_failed == initial_failed + 1
            finally:
                subscriber.shutdown(wait=False)

    def test_handler_not_found_logs_warning(self, caplog):
        """Handler not found logs warning but doesn't fail."""
        import logging

        caplog.set_level(logging.WARNING)

        with patch("src.mqtt.subscriber.MQTTClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.get_instance.return_value = mock_client

            subscriber = Subscriber(max_workers=2)
            try:
                subscriber._route_message("unknown/topic", '{"key": "value"}')

                assert "No handler" in caplog.text or "handler" in caplog.text.lower()
            finally:
                subscriber.shutdown(wait=False)

    def test_empty_json_still_parsed(self):
        """Empty JSON object is still valid."""
        with patch("src.mqtt.subscriber.MQTTClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.get_instance.return_value = mock_client

            subscriber = Subscriber(max_workers=2)
            try:
                initial_failed = subscriber.messages_failed

                # Empty JSON is valid, just no handler will be found
                subscriber._route_message("some/topic", "{}")

                # Should NOT increment failed counter (JSON is valid)
                assert subscriber.messages_failed == initial_failed
            finally:
                subscriber.shutdown(wait=False)


class TestShutdownRoutingGuard:
    """Regression: _route_message must not submit after executor shutdown."""

    def test_route_message_drops_during_shutdown_without_error_noise(self):
        with patch("src.mqtt.subscriber.MQTTClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.get_instance.return_value = mock_client

            subscriber = Subscriber(max_workers=2)
            try:

                async def handler(topic, payload):
                    return True

                subscriber.register_handler("kaiser/god/esp/+/system/heartbeat", handler)
                subscriber._is_shutting_down = True
                subscriber.executor.submit = MagicMock(
                    side_effect=RuntimeError("cannot schedule new futures after shutdown")
                )

                failed_before = subscriber.messages_failed
                processed_before = subscriber.messages_processed
                subscriber._route_message(
                    "kaiser/god/esp/ESP_1/system/heartbeat",
                    '{"esp_id":"ESP_1","seq":1}',
                )

                subscriber.executor.submit.assert_not_called()
                assert subscriber.messages_failed == failed_before
                assert subscriber.messages_processed == processed_before
            finally:
                subscriber.shutdown(wait=False)

    def test_route_message_handles_submit_runtimeerror_as_shutdown_drop(self):
        with patch("src.mqtt.subscriber.MQTTClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.get_instance.return_value = mock_client

            subscriber = Subscriber(max_workers=2)
            try:

                async def handler(topic, payload):
                    return True

                subscriber.register_handler("kaiser/god/esp/+/system/heartbeat", handler)
                subscriber._is_shutting_down = False
                subscriber.executor.submit = MagicMock(
                    side_effect=RuntimeError("cannot schedule new futures after shutdown")
                )

                failed_before = subscriber.messages_failed
                processed_before = subscriber.messages_processed
                subscriber._route_message(
                    "kaiser/god/esp/ESP_1/system/heartbeat",
                    '{"esp_id":"ESP_1","seq":1}',
                )

                subscriber.executor.submit.assert_called_once()
                assert subscriber.messages_failed == failed_before
                assert subscriber.messages_processed == processed_before
            finally:
                subscriber.shutdown(wait=False)


class TestEventLoopBinding:
    """Test event loop binding (Bug O fix)."""

    def test_set_main_loop_updates_internal_loop(self):
        """set_main_loop updates _main_loop."""
        with patch("src.mqtt.subscriber.MQTTClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.get_instance.return_value = mock_client

            subscriber = Subscriber(max_workers=2)
            try:
                loop = asyncio.new_event_loop()
                subscriber.set_main_loop(loop)

                assert subscriber._main_loop == loop
                loop.close()
            finally:
                subscriber.shutdown(wait=False)

    def test_get_valid_main_loop_raises_when_closed(self):
        """_get_valid_main_loop raises when loop is closed."""
        with patch("src.mqtt.subscriber.MQTTClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.get_instance.return_value = mock_client

            subscriber = Subscriber(max_workers=2)
            try:
                loop = asyncio.new_event_loop()
                subscriber.set_main_loop(loop)
                loop.close()  # Close the loop

                with pytest.raises(RuntimeError):
                    subscriber._get_valid_main_loop()
            finally:
                subscriber.shutdown(wait=False)

    def test_get_valid_main_loop_returns_loop_when_valid(self):
        """_get_valid_main_loop returns loop when it's valid."""
        with patch("src.mqtt.subscriber.MQTTClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.get_instance.return_value = mock_client

            subscriber = Subscriber(max_workers=2)
            try:
                loop = asyncio.new_event_loop()
                subscriber.set_main_loop(loop)

                result = subscriber._get_valid_main_loop()
                assert result == loop

                loop.close()
            finally:
                subscriber.shutdown(wait=False)


class TestSubscription:
    """Test subscription functionality."""

    def test_subscribe_calls_client(self):
        """subscribe calls underlying MQTT client."""
        with patch("src.mqtt.subscriber.MQTTClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.subscribe.return_value = True
            mock_client_class.get_instance.return_value = mock_client

            subscriber = Subscriber(max_workers=2)
            try:
                result = subscriber.subscribe("test/topic", qos=1)

                assert result is True
                mock_client.subscribe.assert_called_once_with("test/topic", 1)
            finally:
                subscriber.shutdown(wait=False)

    def test_subscribe_all_subscribes_to_registered_patterns(self):
        """subscribe_all subscribes to all registered handler patterns."""
        with patch("src.mqtt.subscriber.MQTTClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.subscribe.return_value = True
            mock_client_class.get_instance.return_value = mock_client

            subscriber = Subscriber(max_workers=2)
            try:

                async def handler1(topic, payload):
                    return True

                async def handler2(topic, payload):
                    return True

                subscriber.register_handler("pattern/1", handler1)
                subscriber.register_handler("pattern/2", handler2)

                result = subscriber.subscribe_all()

                assert result is True
                assert mock_client.subscribe.call_count == 2
            finally:
                subscriber.shutdown(wait=False)

    def test_subscribe_all_uses_correct_qos(self):
        """subscribe_all uses correct QoS levels based on topic type."""
        with patch("src.mqtt.subscriber.MQTTClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.subscribe.return_value = True
            mock_client_class.get_instance.return_value = mock_client

            subscriber = Subscriber(max_workers=2)
            try:

                async def handler(topic, payload):
                    return True

                # Register handlers for different topic types
                subscriber.register_handler("kaiser/god/esp/+/sensor/+/data", handler)
                subscriber.register_handler("kaiser/god/esp/+/system/heartbeat", handler)
                subscriber.register_handler("kaiser/god/esp/+/config_response", handler)

                subscriber.subscribe_all()

                # Verify QoS levels
                calls = mock_client.subscribe.call_args_list
                qos_map = {call.args[0]: call.args[1] for call in calls}

                # Sensor data: QoS 1
                assert qos_map["kaiser/god/esp/+/sensor/+/data"] == 1
                # Heartbeat: QoS 0
                assert qos_map["kaiser/god/esp/+/system/heartbeat"] == 0
                # Config response: QoS 2
                assert qos_map["kaiser/god/esp/+/config_response"] == 2
            finally:
                subscriber.shutdown(wait=False)


class TestShutdown:
    """Test subscriber shutdown."""

    def test_shutdown_returns_stats(self, caplog):
        """Shutdown logs performance stats."""
        import logging

        caplog.set_level(logging.INFO)

        with patch("src.mqtt.subscriber.MQTTClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.get_instance.return_value = mock_client

            subscriber = Subscriber(max_workers=2)
            subscriber.messages_processed = 100
            subscriber.messages_failed = 3

            subscriber.shutdown(wait=True, timeout=5)

            # Stats should be logged
            assert "stats" in caplog.text.lower() or "Subscriber" in caplog.text


class TestStatistics:
    """Test subscriber statistics."""

    def test_get_stats_returns_correct_structure(self):
        """get_stats returns proper statistics structure."""
        with patch("src.mqtt.subscriber.MQTTClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.get_instance.return_value = mock_client

            subscriber = Subscriber(max_workers=2)
            try:
                subscriber.messages_processed = 100
                subscriber.messages_failed = 5

                stats = subscriber.get_stats()

                assert "messages_processed" in stats
                assert "messages_failed" in stats
                assert "success_rate" in stats
                assert stats["messages_processed"] == 100
                assert stats["messages_failed"] == 5
                # Success rate: 100 / (100 + 5) * 100 = 95.24%
                assert 95 <= stats["success_rate"] <= 96
            finally:
                subscriber.shutdown(wait=False)

    def test_get_stats_zero_messages(self):
        """get_stats handles zero messages."""
        with patch("src.mqtt.subscriber.MQTTClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.get_instance.return_value = mock_client

            subscriber = Subscriber(max_workers=2)
            try:
                stats = subscriber.get_stats()

                assert stats["messages_processed"] == 0
                assert stats["messages_failed"] == 0
                assert stats["success_rate"] == 0.0
            finally:
                subscriber.shutdown(wait=False)


class TestInitialization:
    """Test subscriber initialization."""

    def test_init_with_custom_max_workers(self):
        """Subscriber initializes with custom max_workers."""
        with patch("src.mqtt.subscriber.MQTTClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.get_instance.return_value = mock_client

            subscriber = Subscriber(max_workers=5)
            try:
                assert subscriber.executor._max_workers == 5
            finally:
                subscriber.shutdown(wait=False)

    def test_init_sets_message_callback(self):
        """Subscriber sets message callback on MQTT client."""
        with patch("src.mqtt.subscriber.MQTTClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.get_instance.return_value = mock_client

            subscriber = Subscriber(max_workers=2)
            try:
                mock_client.set_on_message_callback.assert_called_once_with(
                    subscriber._route_message
                )
            finally:
                subscriber.shutdown(wait=False)

    def test_init_initializes_counters(self):
        """Subscriber initializes counters to zero."""
        with patch("src.mqtt.subscriber.MQTTClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.get_instance.return_value = mock_client

            subscriber = Subscriber(max_workers=2)
            try:
                assert subscriber.messages_processed == 0
                assert subscriber.messages_failed == 0
            finally:
                subscriber.shutdown(wait=False)
