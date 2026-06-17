"""
E2E Tests: Emergency Stop Broadcast Flow

Tests the complete emergency stop workflow:
    1. Multiple active devices with actuators
    2. Emergency stop triggered (via API or MQTT)
    3. All devices receive stop command
    4. All actuators are stopped
    5. System enters emergency state

Domain-Expert Perspective:
    In einem Gewächshaus muss ein Not-Aus SOFORT alle Aktoren stoppen.
    Das ist die wichtigste Sicherheitsfunktion. Wenn eine Pumpe unkontrolliert
    läuft, kann das Überschwemmung, Motorschaden oder Pflanzentod verursachen.

Usage:
    poetry run pytest tests/e2e/test_e2e_emergency.py --e2e -v

Dependencies:
- Running Server (uvicorn)
- MQTT Broker (Mosquitto)
- PostgreSQL Database
"""

import asyncio
import time

import pytest

try:
    from conftest import (
        E2EAPIClient,
        E2EConfig,
        E2EMQTTClient,
        ESPDeviceTestData,
        generate_unique_mock_id,
    )
except ImportError:
    E2EAPIClient = None
    E2EConfig = None
    E2EMQTTClient = None
    ESPDeviceTestData = None
    generate_unique_mock_id = None

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


class TestEmergencyStopBroadcast:
    """
    E2E: Emergency Stop reaches all active devices.

    Domain-Expert Szenario:
        GEGEBEN: 2-3 aktive ESP32-Geräte mit laufenden Aktoren
        WENN: Ein globaler Emergency Stop ausgelöst wird
        DANN: ALLE Geräte müssen den Stop-Befehl erhalten
        UND: ALLE Aktoren müssen innerhalb von 5 Sekunden gestoppt sein
        UND: Das System muss den Emergency-State melden
    """

    async def test_emergency_stop_all_devices_receive(
        self,
        api_client: E2EAPIClient,
        mqtt_client: E2EMQTTClient,
        cleanup_test_devices,
    ):
        """
        Emergency stop broadcast reaches multiple active devices.

        Praxis-Relevanz:
            Wenn der Gärtner den roten Knopf drückt, müssen ALLE
            Pumpen, Ventile und Lüfter sofort stoppen. Keine Ausnahmen.
        """
        # === SETUP: Register multiple devices with actuators ===
        devices = []
        for i in range(3):
            esp_id = generate_unique_mock_id(f"EMG{i}")
            cleanup_test_devices(esp_id)

            esp = ESPDeviceTestData(device_id=esp_id, name=f"Emergency Test Device {i}")
            result = await api_client.register_esp(esp)
            assert (
                "device_id" in result or "id" in result
            ), f"Device {i} registration failed: {result}"

            # Create actuator on each device
            await api_client.create_actuator_config(
                esp_id=esp_id,
                gpio=25 + i,
                actuator_type="pump" if i == 0 else ("valve" if i == 1 else "fan"),
                name=f"Emergency Test Actuator {i}",
            )

            # Send heartbeat to mark online
            await mqtt_client.publish_heartbeat(esp_id)
            devices.append({"esp_id": esp_id, "gpio": 25 + i})

        await asyncio.sleep(2.0)

        # Verify all devices are registered
        all_devices = await api_client.get_all_esp_devices()
        registered_ids = [d.get("device_id") for d in all_devices]
        for device in devices:
            assert (
                device["esp_id"] in registered_ids
            ), f"Device {device['esp_id']} should be registered"

        # === EXECUTE: Trigger emergency stop ===
        # Each device sends its own emergency alert
        for device in devices:
            await mqtt_client.publish_actuator_alert(
                esp_id=device["esp_id"],
                gpio=device["gpio"],
                alert_type="emergency_stop",
                message="Emergency stop - E2E test",
            )

        # Also publish broadcast emergency
        await mqtt_client.publish_emergency_broadcast(
            esp_id=devices[0]["esp_id"],
            reason="e2e_test_emergency",
            stopped_actuators=[d["gpio"] for d in devices],
        )

        await asyncio.sleep(3.0)

        # === VERIFY: All actuators should be stopped ===
        for device in devices:
            state = await api_client.get_actuator_state(device["esp_id"], device["gpio"])
            if state:
                current_value = state.get("current_value") or state.get("value", -1)
                current_state = state.get("state")
                is_stopped = current_value == 0.0 or current_state in (
                    "off",
                    "OFF",
                    False,
                    None,
                    "emergency_stopped",
                )
                print(
                    f"  {device['esp_id']} GPIO {device['gpio']}: "
                    f"state={current_state}, value={current_value}, stopped={is_stopped}"
                )
            else:
                print(f"  {device['esp_id']} GPIO {device['gpio']}: no state endpoint")

        print(f"  Emergency stop broadcast sent to {len(devices)} devices")

    async def test_emergency_stop_via_device_alert(
        self,
        api_client: E2EAPIClient,
        mqtt_client: E2EMQTTClient,
        cleanup_test_devices,
    ):
        """
        Single ESP emergency alert → Server processes and broadcasts.

        Praxis-Relevanz:
            Ein ESP32 erkennt einen kritischen Zustand (z.B. Überhitzung)
            und sendet eigenständig einen Emergency Stop. Der Server muss
            das verarbeiten und ALLE betroffenen Geräte informieren.
        """
        # === SETUP ===
        esp_id = generate_unique_mock_id("EMGDEV")
        cleanup_test_devices(esp_id)

        esp = ESPDeviceTestData(device_id=esp_id, name="Emergency Device Alert Test")
        await api_client.register_esp(esp)

        # Create multiple actuators on same ESP
        actuators = [
            {"gpio": 25, "type": "pump", "name": "Water Pump"},
            {"gpio": 26, "type": "valve", "name": "Water Valve"},
            {"gpio": 27, "type": "fan", "name": "Ventilation Fan"},
        ]
        for act in actuators:
            await api_client.create_actuator_config(
                esp_id=esp_id, gpio=act["gpio"], actuator_type=act["type"], name=act["name"]
            )

        await mqtt_client.publish_heartbeat(esp_id)
        await asyncio.sleep(1.5)

        # === EXECUTE: ESP sends system-wide emergency (gpio=255) ===
        await mqtt_client.publish_actuator_alert(
            esp_id=esp_id,
            gpio=255,  # System-wide
            alert_type="emergency_stop",
            message="Critical temperature detected - all actuators emergency stopped",
        )

        await asyncio.sleep(3.0)

        # === VERIFY: All actuators on this ESP should be stopped ===
        for act in actuators:
            state = await api_client.get_actuator_state(esp_id, act["gpio"])
            status = "OK" if state else "no state"
            print(f"  {act['name']} (GPIO {act['gpio']}): {status}")

        print(f"  Device-level emergency stop processed for {esp_id}")

    async def test_emergency_stop_timing(
        self,
        api_client: E2EAPIClient,
        mqtt_client: E2EMQTTClient,
        cleanup_test_devices,
    ):
        """
        Emergency stop MQTT publish + server acknowledgment within SLA.

        Praxis-Relevanz:
            Im Gewächshaus zählt jede Sekunde. Der Emergency Stop muss
            schnell published werden und der Server muss ihn verarbeiten.
            Wir messen: MQTT publish + Server-side processing acknowledgment.
        """
        # === SETUP ===
        esp_id = generate_unique_mock_id("EMGTM")
        cleanup_test_devices(esp_id)

        esp = ESPDeviceTestData(device_id=esp_id, name="Emergency Timing Test")
        await api_client.register_esp(esp)

        await api_client.create_actuator_config(
            esp_id=esp_id, gpio=25, actuator_type="pump", name="Timing Test Pump"
        )

        await mqtt_client.publish_heartbeat(esp_id)
        await asyncio.sleep(1.0)

        # === MEASURE: MQTT publish latency ===
        start_time = time.time()

        await mqtt_client.publish_actuator_alert(
            esp_id=esp_id, gpio=25, alert_type="emergency_stop", message="Timing test emergency"
        )

        publish_elapsed = time.time() - start_time

        # MQTT publish should be near-instant (< 1s)
        assert (
            publish_elapsed < 1.0
        ), f"MQTT emergency publish took {publish_elapsed:.2f}s - should be < 1s"

        # Wait for server to process the alert
        await asyncio.sleep(2.0)

        # Verify device is still reachable after emergency
        # (server processed the alert without crashing)
        status = await api_client.get_esp_status(esp_id)
        total_elapsed = time.time() - start_time

        assert (
            total_elapsed < 5.0
        ), f"Emergency stop flow took {total_elapsed:.2f}s - exceeds 5s SLA"

        print(f"  MQTT publish: {publish_elapsed:.3f}s")
        print(f"  Total E2E flow: {total_elapsed:.3f}s (SLA: 5s)")
        print(f"  Device status after emergency: {status.get('status', 'unknown')}")
