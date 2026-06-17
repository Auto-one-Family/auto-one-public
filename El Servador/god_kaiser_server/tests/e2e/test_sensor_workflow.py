"""
E2E Tests: Complete SHT31 Sensor Workflow

Tests the full sensor data pipeline:
    MQTT Publish → sensor_handler → Database → REST API Query
    MQTT Publish → sensor_handler → WebSocket Broadcast → Client Receive

WICHTIG: Diese Tests benoetigen einen LAUFENDEN Server!
    .venv/Scripts/pytest.exe tests/e2e/test_sensor_workflow.py --e2e -v

Dependencies:
- Running Server (uvicorn)
- MQTT Broker (Mosquitto)
- PostgreSQL Database
"""

import asyncio
import json
import os
import time

import pytest

from conftest import (
    E2EAPIClient,
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


async def publish_sht31_data(
    mqtt_client: E2EMQTTClient,
    esp_id: str,
    gpio: int,
    value: float,
    unit: str = "°C",
    sensor_type: str = "SHT31",
    sensor_name: str = None,
    quality: str = "good",
):
    """
    Publish SHT31 data with SimulationScheduler-conformant payload.

    Uses raw_value (float), ts in milliseconds, no 'raw' field.
    Matches the format from scheduler.py and real ESP32 firmware.
    """
    topic = f"kaiser/god/esp/{esp_id}/sensor/{gpio}/data"
    payload = {
        "ts": int(time.time() * 1000),
        "esp_id": esp_id,
        "gpio": gpio,
        "sensor_type": sensor_type,
        "raw_value": value,
        "value": value,
        "unit": unit,
        "quality": quality,
        "raw_mode": True,
        "sensor_name": sensor_name or f"{sensor_type}_{gpio}",
    }
    await mqtt_client._client.publish(topic, json.dumps(payload), qos=1)
    await asyncio.sleep(0.1)


class TestSHT31SingleValuePersist:
    """
    Test: Single SHT31 temperature value persisted in database.

    Flow: MQTT Publish → sensor_handler → Database → REST API Query
    """

    async def test_sht31_temperature_persisted_in_db(
        self,
        api_client: E2EAPIClient,
        mqtt_client: E2EMQTTClient,
        cleanup_test_devices,
    ):
        """
        MQTT sensor data → Database persistence → REST query returns correct values

        GEGEBEN: Ein registrierter ESP32
        WENN: SHT31 Temperatur-Daten via MQTT gesendet werden
        DANN: Sollten die Daten ueber die REST API abrufbar sein
        UND: raw_value, unit und quality sollten korrekt sein
        """
        esp_id = generate_unique_mock_id("SHT31S")
        cleanup_test_devices(esp_id)

        try:
            # 1. Register ESP
            await api_client.register_esp(
                ESPDeviceTestData(device_id=esp_id, name="SHT31 Single Test")
            )
            await mqtt_client.publish_heartbeat(esp_id)
            await asyncio.sleep(1.0)

            # 2. Publish SHT31 temperature
            await publish_sht31_data(mqtt_client, esp_id, gpio=21, value=28.5, unit="°C")
            await asyncio.sleep(2.0)

            # 3. Verify in DB via REST API
            readings = await api_client.get_sensor_data(esp_id, gpio=21, limit=1)
            assert len(readings) > 0, f"No sensor data found for {esp_id} GPIO 21"

            r = readings[0]
            assert r["raw_value"] == pytest.approx(28.5, abs=0.1)
            assert r["unit"] == "°C"
            assert r["quality"] == "good"

            print(f"✓ SHT31 temperature persisted: {r['raw_value']}°C for {esp_id}")

        finally:
            pass


class TestSHT31MultiValue:
    """
    Test: SHT31 temperature AND humidity persisted as separate readings.

    Flow: 2x MQTT Publish (temp + humidity) → sensor_handler → Database → REST query
    """

    async def test_sht31_temp_and_humidity_persisted(
        self,
        api_client: E2EAPIClient,
        mqtt_client: E2EMQTTClient,
        cleanup_test_devices,
    ):
        """
        Two MQTT messages (temp + humidity) → Both readings in database

        GEGEBEN: Ein registrierter ESP32
        WENN: SHT31 Temperatur UND Humidity via MQTT gesendet werden
        DANN: Sollten beide Werte in der Datenbank sein
        UND: Temperatur-Reading hat unit=°C, Humidity hat unit=%RH
        """
        esp_id = generate_unique_mock_id("SHT31M")
        cleanup_test_devices(esp_id)

        try:
            await api_client.register_esp(
                ESPDeviceTestData(device_id=esp_id, name="SHT31 Multi Test")
            )
            await mqtt_client.publish_heartbeat(esp_id)
            await asyncio.sleep(1.0)

            # Publish temperature
            await publish_sht31_data(
                mqtt_client,
                esp_id,
                gpio=21,
                value=28.5,
                unit="°C",
                sensor_type="SHT31",
                sensor_name="SHT31_temp",
            )
            await asyncio.sleep(0.5)

            # Publish humidity (same GPIO, different sensor_type)
            await publish_sht31_data(
                mqtt_client,
                esp_id,
                gpio=21,
                value=72.3,
                unit="%RH",
                sensor_type="SHT31_humidity",
                sensor_name="SHT31_humidity",
            )
            await asyncio.sleep(2.0)

            # Verify: both values in DB
            all_readings = await api_client.get_sensor_data(esp_id, gpio=21, limit=10)
            assert len(all_readings) >= 2, f"Expected >= 2 readings, got {len(all_readings)}"

            # Temperature check
            temp_readings = [r for r in all_readings if r.get("unit") == "°C"]
            assert len(temp_readings) >= 1, "No temperature reading found"
            assert temp_readings[0]["raw_value"] == pytest.approx(28.5, abs=0.1)

            # Humidity check
            humid_readings = [r for r in all_readings if r.get("unit") == "%RH"]
            assert len(humid_readings) >= 1, "No humidity reading found"
            assert humid_readings[0]["raw_value"] == pytest.approx(72.3, abs=0.1)

            print(
                f"✓ SHT31 multi-value persisted: "
                f"temp={temp_readings[0]['raw_value']}°C, "
                f"humidity={humid_readings[0]['raw_value']}%RH for {esp_id}"
            )

        finally:
            pass


class TestSHT31WebSocketBroadcast:
    """
    Test: SHT31 sensor data triggers WebSocket broadcast.

    Flow: MQTT Publish → sensor_handler → WebSocket Broadcast → Client Receive
    """

    async def test_sht31_data_triggers_ws_event(
        self,
        api_client: E2EAPIClient,
        mqtt_client: E2EMQTTClient,
        ws_client: E2EWebSocketClient,
        cleanup_test_devices,
    ):
        """
        MQTT sensor data → WebSocket sensor_data event with correct fields

        GEGEBEN: Ein registrierter ESP32 und ein verbundener WebSocket Client
        WENN: SHT31 Temperatur-Daten via MQTT gesendet werden
        DANN: Sollte ein sensor_data WebSocket Event empfangen werden
        UND: Event enthält esp_id, gpio, sensor_type, value, quality
        """
        esp_id = generate_unique_mock_id("SHT31W")
        cleanup_test_devices(esp_id)

        try:
            await api_client.register_esp(ESPDeviceTestData(device_id=esp_id, name="SHT31 WS Test"))
            await mqtt_client.publish_heartbeat(esp_id)
            await asyncio.sleep(1.0)

            # Subscribe to sensor_data events for this ESP
            await ws_client.subscribe({"types": ["sensor_data"], "esp_ids": [esp_id]})
            await asyncio.sleep(0.5)
            ws_client.clear_messages()

            # Publish SHT31 temperature
            await publish_sht31_data(mqtt_client, esp_id, gpio=21, value=28.5, unit="°C")

            # Verify WebSocket event
            event = await ws_client.wait_for_event(
                event_type="sensor_data",
                timeout=10.0,
                match_fn=lambda e: e.get("data", {}).get("esp_id") == esp_id,
            )

            assert event is not None, "sensor_data WS event should be received"
            assert event["type"] == "sensor_data"

            data = event["data"]
            assert data["esp_id"] == esp_id
            assert data["gpio"] == 21
            assert data["sensor_type"] == "SHT31"
            assert data["quality"] == "good"
            assert "value" in data

            print(f"✓ SHT31 WebSocket broadcast received for {esp_id}")

        finally:
            pass
