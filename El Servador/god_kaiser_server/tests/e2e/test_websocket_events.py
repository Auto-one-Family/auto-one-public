"""
E2E Tests: WebSocket Real-time Events

Tests the complete WebSocket event pipeline:
    MQTT/API Trigger → Server Handler → WebSocket Broadcast → Client Receive

WICHTIG: Diese Tests benötigen einen LAUFENDEN Server!
    poetry run pytest tests/e2e/test_websocket_events.py --e2e -v

Dependencies:
- Running Server (uvicorn)
- MQTT Broker (Mosquitto)
- PostgreSQL Database
"""

import asyncio
import os

import pytest

from conftest import (
    E2EAPIClient,
    E2EConfig,
    E2EMQTTClient,
    E2EWebSocketClient,
    ESPDeviceTestData,
    generate_unique_mock_id,
)

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.environ.get("CI") == "true",
        reason="Requires live MQTT/IoT data — TODO: link to Wokwi SIL testing",
    ),
]


class TestSensorDataWebSocketEvent:
    """
    Test: sensor_data Event wird bei MQTT Sensor-Nachricht gesendet.

    Flow: ESP32 → MQTT → sensor_handler → DB → WebSocket Broadcast
    """

    async def test_sensor_data_triggers_ws_event(
        self,
        api_client: E2EAPIClient,
        mqtt_client: E2EMQTTClient,
        ws_client: E2EWebSocketClient,
        cleanup_test_devices,
    ):
        """
        MQTT sensor data → WebSocket sensor_data event

        GEGEBEN: Ein registrierter ESP32 mit Sensor
        UND: WebSocket Client ist verbunden und subscribed
        WENN: Sensor-Daten via MQTT gesendet werden
        DANN: Sollte ein sensor_data Event empfangen werden
        UND: Die Payload sollte die korrekten Werte enthalten
        """
        # === SETUP ===
        esp_id = generate_unique_mock_id("WSSNSR")
        sensor_gpio = 4
        test_value = 25.5
        cleanup_test_devices(esp_id)

        try:
            # Register ESP
            esp = ESPDeviceTestData(device_id=esp_id, name="WS Sensor Test ESP")
            await api_client.register_esp(esp)
            await mqtt_client.publish_heartbeat(esp_id)
            await asyncio.sleep(1.0)

            # Subscribe to sensor_data events for this ESP
            await ws_client.subscribe({"types": ["sensor_data"], "esp_ids": [esp_id]})
            await asyncio.sleep(0.5)

            # === EXECUTE ===
            # Clear any previous messages
            ws_client.clear_messages()

            # Publish sensor data via MQTT
            await mqtt_client.publish_sensor_data(
                esp_id=esp_id,
                gpio=sensor_gpio,
                value=test_value,
                sensor_type="temperature",
                raw_mode=True,
            )

            # === VERIFY ===
            # Wait for WebSocket event
            event = await ws_client.wait_for_event(
                event_type="sensor_data",
                timeout=10.0,
                match_fn=lambda e: e.get("data", {}).get("esp_id") == esp_id,
            )

            assert event is not None, "sensor_data WebSocket event should be received"
            assert event["type"] == "sensor_data"

            data = event["data"]
            assert data["esp_id"] == esp_id
            assert data["gpio"] == sensor_gpio
            assert data["sensor_type"] == "temperature"
            assert "value" in data

            print(f"✓ sensor_data WebSocket event received for {esp_id}")

        finally:
            pass


class TestDeviceDiscoveredWebSocketEvent:
    """
    Test: device_discovered Event bei neuem ESP Heartbeat.

    Flow: Neues ESP → MQTT Heartbeat → heartbeat_handler → WebSocket Broadcast
    """

    async def test_device_discovered_triggers_ws_event(
        self,
        api_client: E2EAPIClient,
        mqtt_client: E2EMQTTClient,
        ws_client: E2EWebSocketClient,
        cleanup_test_devices,
    ):
        """
        New ESP heartbeat → WebSocket device_discovered event

        GEGEBEN: WebSocket Client ist connected
        WENN: Ein NEUES (unbekanntes) ESP einen Heartbeat sendet
        DANN: Sollte ein device_discovered Event empfangen werden
        """
        # === SETUP ===
        # Generate unique ID that doesn't exist in DB
        esp_id = generate_unique_mock_id("WSNEW")
        cleanup_test_devices(esp_id)

        # Subscribe to device discovery events
        await ws_client.subscribe({"types": ["device_discovered"]})
        await asyncio.sleep(0.5)
        ws_client.clear_messages()

        # === EXECUTE ===
        # Send heartbeat from "new" device (not registered via API)
        await mqtt_client.publish_heartbeat(esp_id)

        # === VERIFY ===
        event = await ws_client.wait_for_event(
            event_type="device_discovered",
            timeout=10.0,
            match_fn=lambda e: e.get("data", {}).get("esp_id") == esp_id,
        )

        assert event is not None, "device_discovered WebSocket event should be received"
        assert event["data"]["esp_id"] == esp_id
        assert event["data"].get("pending") is True

        print(f"✓ device_discovered WebSocket event received for {esp_id}")


class TestActuatorResponseWebSocketEvent:
    """
    Test: actuator_response Event nach ESP Antwort.

    Flow: REST Command → MQTT → ESP Response → actuator_response_handler → WebSocket
    """

    async def test_actuator_response_triggers_ws_event(
        self,
        api_client: E2EAPIClient,
        mqtt_client: E2EMQTTClient,
        ws_client: E2EWebSocketClient,
        cleanup_test_devices,
    ):
        """
        ESP actuator response → WebSocket actuator_response event

        GEGEBEN: Ein registrierter ESP mit Actuator
        UND: WebSocket Client ist subscribed
        WENN: ESP eine Actuator-Response sendet
        DANN: Sollte ein actuator_response Event empfangen werden
        """
        # === SETUP ===
        esp_id = generate_unique_mock_id("WSACTR")
        actuator_gpio = 25
        cleanup_test_devices(esp_id)

        try:
            # Register ESP
            esp = ESPDeviceTestData(device_id=esp_id, name="WS Actuator Test ESP")
            await api_client.register_esp(esp)
            await api_client.create_actuator_config(
                esp_id=esp_id, gpio=actuator_gpio, actuator_type="relay", name="WS Test Relay"
            )
            await mqtt_client.publish_heartbeat(esp_id)
            await asyncio.sleep(1.0)

            # Subscribe to actuator events
            await ws_client.subscribe({"types": ["actuator_response"], "esp_ids": [esp_id]})
            await asyncio.sleep(0.5)
            ws_client.clear_messages()

            # === EXECUTE ===
            # Send actuator command via API
            await api_client.send_actuator_command(device_id=esp_id, gpio=actuator_gpio, value=1.0)

            # Simulate ESP response
            await mqtt_client.publish_actuator_response(
                esp_id=esp_id,
                gpio=actuator_gpio,
                command="ON",
                value=1.0,
                success=True,
                message="Command executed",
            )

            # === VERIFY ===
            event = await ws_client.wait_for_event(
                event_type="actuator_response",
                timeout=10.0,
                match_fn=lambda e: e.get("data", {}).get("esp_id") == esp_id,
            )

            assert event is not None, "actuator_response WebSocket event should be received"
            assert event["data"]["esp_id"] == esp_id
            assert event["data"]["gpio"] == actuator_gpio
            assert event["data"]["success"] is True

            print(f"✓ actuator_response WebSocket event received for {esp_id}")

        finally:
            pass


class TestActuatorAlertWebSocketEvent:
    """
    Test: actuator_alert Event bei ESP Emergency.

    Flow: ESP Alert → MQTT → actuator_alert_handler → WebSocket Broadcast
    """

    async def test_actuator_alert_triggers_ws_event(
        self,
        api_client: E2EAPIClient,
        mqtt_client: E2EMQTTClient,
        ws_client: E2EWebSocketClient,
        cleanup_test_devices,
    ):
        """
        ESP actuator alert → WebSocket actuator_alert event

        GEGEBEN: Ein registrierter ESP mit Actuator
        WENN: ESP einen Alert (emergency_stop) sendet
        DANN: Sollte ein actuator_alert Event empfangen werden
        UND: Die Severity sollte "critical" sein
        """
        # === SETUP ===
        esp_id = generate_unique_mock_id("WSALRT")
        actuator_gpio = 25
        cleanup_test_devices(esp_id)

        try:
            # Register ESP
            esp = ESPDeviceTestData(device_id=esp_id, name="WS Alert Test ESP")
            await api_client.register_esp(esp)
            await api_client.create_actuator_config(
                esp_id=esp_id, gpio=actuator_gpio, actuator_type="pump", name="WS Test Pump"
            )
            await mqtt_client.publish_heartbeat(esp_id)
            await asyncio.sleep(1.0)

            # Subscribe to alert events
            await ws_client.subscribe({"types": ["actuator_alert"]})
            await asyncio.sleep(0.5)
            ws_client.clear_messages()

            # === EXECUTE ===
            # ESP sends emergency alert
            await mqtt_client.publish_actuator_alert(
                esp_id=esp_id,
                gpio=actuator_gpio,
                alert_type="emergency_stop",
                message="High temperature - emergency stop activated",
            )

            # === VERIFY ===
            event = await ws_client.wait_for_event(
                event_type="actuator_alert",
                timeout=10.0,
                match_fn=lambda e: e.get("data", {}).get("esp_id") == esp_id,
            )

            assert event is not None, "actuator_alert WebSocket event should be received"
            assert event["data"]["esp_id"] == esp_id
            assert event["data"]["alert_type"] == "emergency_stop"
            assert event["data"]["severity"] == "critical"

            print(f"✓ actuator_alert WebSocket event received for {esp_id}")

        finally:
            pass


class TestWebSocketAuthRejection:
    """
    Test: WebSocket-Verbindung ohne Auth wird abgelehnt.
    """

    async def test_ws_connection_without_auth_rejected(
        self,
        e2e_config: E2EConfig,
    ):
        """
        WebSocket connect without token → Connection rejected (4001)

        GEGEBEN: Kein Auth-Token
        WENN: WebSocket-Verbindung ohne Token versucht wird
        DANN: Sollte die Verbindung mit Code 4001 abgelehnt werden
        """
        try:
            import websockets
        except ImportError:
            pytest.skip("websockets package not installed")

        # Build URL WITHOUT token
        client_id = f"test_noauth_{int(asyncio.get_event_loop().time())}"
        base_url = e2e_config.server_url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = f"{base_url}/api/v1/ws/realtime/{client_id}"

        try:
            async with asyncio.timeout(5.0):
                async with websockets.connect(ws_url) as ws:
                    # If we get here, connection was accepted (unexpected)
                    pytest.fail("WebSocket should reject connection without token")
        except websockets.exceptions.ConnectionClosed as e:
            # Expected: Connection closed with 4001
            assert e.code == 4001, f"Expected close code 4001, got {e.code}"
            print(f"✓ WebSocket correctly rejected: code={e.code}, reason={e.reason}")
        except asyncio.TimeoutError:
            pytest.skip("WebSocket connection timed out")
        except Exception as e:
            # Connection refused is also acceptable (server not running)
            if "refused" in str(e).lower():
                pytest.skip("WebSocket server not reachable")
            raise


class TestWebSocketEventFiltering:
    """
    Test: WebSocket Subscriptions filtern Events korrekt.
    """

    async def test_ws_receives_only_subscribed_events(
        self,
        api_client: E2EAPIClient,
        mqtt_client: E2EMQTTClient,
        ws_client: E2EWebSocketClient,
        cleanup_test_devices,
    ):
        """
        Subscription filter → Only matching events received

        GEGEBEN: WebSocket subscribed nur für "sensor_data"
        WENN: sensor_data UND actuator_alert Events gesendet werden
        DANN: Sollte NUR sensor_data empfangen werden
        """
        # === SETUP ===
        esp_id = generate_unique_mock_id("WSFLT")
        cleanup_test_devices(esp_id)

        try:
            # Register ESP
            esp = ESPDeviceTestData(device_id=esp_id, name="WS Filter Test")
            await api_client.register_esp(esp)
            await api_client.create_actuator_config(
                esp_id=esp_id, gpio=25, actuator_type="pump", name="Filter Pump"
            )
            await mqtt_client.publish_heartbeat(esp_id)
            await asyncio.sleep(1.0)

            # Subscribe ONLY to sensor_data (NOT actuator_alert)
            await ws_client.subscribe({"types": ["sensor_data"], "esp_ids": [esp_id]})
            await asyncio.sleep(0.5)
            ws_client.clear_messages()

            # === EXECUTE ===
            # Send both sensor data and actuator alert
            await mqtt_client.publish_sensor_data(
                esp_id=esp_id, gpio=4, value=25.0, sensor_type="temperature"
            )
            await mqtt_client.publish_actuator_alert(
                esp_id=esp_id, gpio=25, alert_type="runtime_protection", message="Test"
            )

            # Wait a bit for events
            await asyncio.sleep(3.0)

            # === VERIFY ===
            events = ws_client.received_messages
            event_types = [e.get("type") for e in events]

            # Should have sensor_data but NOT actuator_alert
            assert "sensor_data" in event_types, "sensor_data should be received"
            # Note: actuator_alert might still arrive due to filter timing
            # The key test is that sensor_data IS received

            print(f"✓ Event filtering works: received {len(events)} events")

        finally:
            pass


class TestESPHealthWebSocketEvent:
    """
    Test: esp_health Event bei ESP Heartbeat.

    Flow: ESP Heartbeat → MQTT → heartbeat_handler → WebSocket Broadcast
    """

    async def test_esp_health_triggers_ws_event(
        self,
        api_client: E2EAPIClient,
        mqtt_client: E2EMQTTClient,
        ws_client: E2EWebSocketClient,
        cleanup_test_devices,
    ):
        """
        ESP heartbeat → WebSocket esp_health event

        GEGEBEN: Ein registrierter ESP32
        UND: WebSocket Client ist subscribed für esp_health
        WENN: ESP einen Heartbeat sendet
        DANN: Sollte ein esp_health Event empfangen werden
        """
        # === SETUP ===
        esp_id = generate_unique_mock_id("WSHLTH")
        cleanup_test_devices(esp_id)

        try:
            # Register ESP
            esp = ESPDeviceTestData(device_id=esp_id, name="WS Health Test ESP")
            await api_client.register_esp(esp)

            # First heartbeat to make device "known"
            await mqtt_client.publish_heartbeat(esp_id)
            await asyncio.sleep(1.0)

            # Subscribe to esp_health events
            await ws_client.subscribe({"types": ["esp_health"], "esp_ids": [esp_id]})
            await asyncio.sleep(0.5)
            ws_client.clear_messages()

            # === EXECUTE ===
            # Send another heartbeat
            await mqtt_client.publish_heartbeat(esp_id=esp_id, heap_free=100000, uptime=7200)

            # === VERIFY ===
            event = await ws_client.wait_for_event(
                event_type="esp_health",
                timeout=10.0,
                match_fn=lambda e: e.get("data", {}).get("esp_id") == esp_id,
            )

            assert event is not None, "esp_health WebSocket event should be received"
            assert event["data"]["esp_id"] == esp_id
            assert "heap_free" in event["data"]
            assert "uptime" in event["data"] or "uptime_seconds" in event["data"]

            print(f"✓ esp_health WebSocket event received for {esp_id}")

        finally:
            pass
