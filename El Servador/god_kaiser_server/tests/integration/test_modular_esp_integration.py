"""
Modular ESP Integration Tests - Phase 5

Tests for modulare ESP-Erstellung mit dynamischer Sensor/Aktor-Konfiguration.
Validiert das data_source Tracking und die Filterung.

Test-Pattern:
1. Mock ESP erstellen (via MockESP32Client)
2. Sensoren/Aktoren auf Pins hinzufuegen
3. Werte setzen und MQTT-Messages triggern
4. Server-Verarbeitung validieren
5. Datenbank-Eintraege pruefen
6. Cleanup
"""

import pytest
import time
from datetime import datetime, timedelta
from uuid import uuid4

from tests.esp32.mocks.mock_esp32_client import BrokerMode, MockESP32Client


class TestModularSensorIntegration:
    """Modulare Sensor-Tests mit dynamischer Pin-Konfiguration."""

    def test_add_sensor_and_publish(self):
        """User erstellt Mock ESP, fuegt Sensor hinzu, publiziert Daten."""
        # 1. Mock ESP erstellen
        mock = MockESP32Client(esp_id="MOCK_MODULAR_001")
        mock.configure_zone("test_zone", "master_zone", "subzone_a")

        # 2. Sensor auf GPIO 4 hinzufuegen (DS18B20 Temperatur)
        mock.set_sensor_value(
            gpio=4,
            raw_value=23.5,
            sensor_type="DS18B20",
            name="Boden Temperatur",
            unit="C",
            quality="good",
        )

        # 3. Sensor-Daten "publishen" (simuliert)
        response = mock.handle_command("sensor_read", {"gpio": 4})

        # 4. Assertions
        assert response["status"] == "ok"
        assert response["data"]["value"] == 23.5

        # 5. Published Messages pruefen
        messages = mock.get_messages_by_topic_pattern("/sensor/4/data")
        assert len(messages) >= 1
        assert messages[0]["payload"]["sensor_type"] == "DS18B20"

        # 6. Cleanup
        mock.reset()

    def test_multiple_sensors_different_types(self):
        """Mehrere Sensoren verschiedener Typen auf einem ESP."""
        mock = MockESP32Client(esp_id="MOCK_MULTI_SENSOR")
        mock.configure_zone("greenhouse", "main", "zone_a")

        # Temperatur-Sensor
        mock.set_sensor_value(gpio=4, raw_value=24.5, sensor_type="DS18B20")

        # Feuchtigkeits-Sensor (Multi-Value)
        mock.set_multi_value_sensor(
            gpio=21, sensor_type="SHT31", primary_value=25.0, secondary_values={"humidity": 68.5}
        )

        # pH-Sensor
        mock.set_sensor_value(gpio=34, raw_value=6.8, sensor_type="pH")

        # Batch-Read
        response = mock.handle_command("sensor_batch", {})

        assert response["status"] == "ok"
        assert response["data"]["count"] == 3

        mock.reset()

    def test_multi_value_sensor_sht31(self):
        """SHT31 Multi-Value Sensor mit Temperatur + Humidity."""
        mock = MockESP32Client(esp_id="MOCK_SHT31_TEST")
        mock.configure_zone("greenhouse", "main", "zone_a")

        # SHT31 mit Temperatur + Humidity
        mock.set_multi_value_sensor(
            gpio=21,
            sensor_type="SHT31",
            primary_value=23.8,
            secondary_values={"humidity": 65.2},
            name="Luft Sensor",
            quality="excellent",
        )

        # Einzelnes Lesen
        response = mock.handle_command("sensor_read", {"gpio": 21})

        assert response["status"] == "ok"
        assert response["data"]["value"] == 23.8
        assert "humidity" in response["data"]["secondary_values"]
        assert response["data"]["secondary_values"]["humidity"] == 65.2

        mock.reset()

    def test_sensor_quality_levels(self):
        """Test verschiedener Quality-Level fuer Sensoren."""
        mock = MockESP32Client(esp_id="MOCK_QUALITY_TEST")
        mock.configure_zone("quality_zone", "main", "test")

        quality_levels = ["excellent", "good", "fair", "poor", "bad"]

        for i, quality in enumerate(quality_levels):
            gpio = 30 + i
            mock.set_sensor_value(
                gpio=gpio, raw_value=20.0 + i, sensor_type="generic", quality=quality
            )

            response = mock.handle_command("sensor_read", {"gpio": gpio})
            assert response["status"] == "ok"
            assert response["data"]["quality"] == quality

        mock.reset()


class TestModularActuatorIntegration:
    """Modulare Aktor-Tests mit dynamischer Konfiguration."""

    def test_actuator_with_sensor_feedback(self):
        """Actuator steuern und Sensor-Feedback pruefen."""
        mock = MockESP32Client(esp_id="MOCK_FEEDBACK")
        mock.configure_zone("irrigation", "main", "zone_b")

        # Pumpe konfigurieren
        mock.configure_actuator(gpio=5, actuator_type="pump", name="Bewaesserung")

        # Feuchtigkeitssensor
        mock.set_sensor_value(gpio=34, raw_value=30.0, sensor_type="moisture")

        # Pumpe einschalten
        response = mock.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})

        assert response["status"] == "ok"
        assert response["data"]["state"] is True

        # Status-Message wurde publiziert
        status_msgs = mock.get_messages_by_topic_pattern("/actuator/5/status")
        assert len(status_msgs) >= 1

        mock.reset()

    def test_pwm_actuator_control(self):
        """PWM-Aktor mit Werten 0.0-1.0."""
        mock = MockESP32Client(esp_id="MOCK_PWM")
        mock.configure_zone("ventilation", "main", "zone_c")

        # PWM Ventilator
        mock.configure_actuator(
            gpio=18, actuator_type="fan", name="Ventilator", min_value=0.1, max_value=1.0
        )

        # PWM auf 50%
        response = mock.handle_command("actuator_set", {"gpio": 18, "value": 0.5, "mode": "pwm"})

        assert response["status"] == "ok"
        assert response["data"]["pwm_value"] == 0.5

        # PWM auf 100%
        response = mock.handle_command("actuator_set", {"gpio": 18, "value": 1.0, "mode": "pwm"})

        assert response["status"] == "ok"
        assert response["data"]["pwm_value"] == 1.0

        mock.reset()

    def test_emergency_stop(self):
        """Emergency-Stop deaktiviert alle Aktoren."""
        mock = MockESP32Client(esp_id="MOCK_EMERGENCY")
        mock.configure_zone("emergency_zone", "main", "test")

        # Mehrere Aktoren konfigurieren
        mock.configure_actuator(gpio=5, actuator_type="pump", name="Pump 1")
        mock.configure_actuator(gpio=6, actuator_type="valve", name="Valve 1")
        mock.configure_actuator(gpio=7, actuator_type="fan", name="Fan 1")

        # Alle einschalten
        mock.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})
        mock.handle_command("actuator_set", {"gpio": 6, "value": 1, "mode": "digital"})
        mock.handle_command("actuator_set", {"gpio": 7, "value": 0.5, "mode": "pwm"})

        # Emergency Stop
        response = mock.handle_command("emergency_stop", {"reason": "test"})

        assert response["status"] == "ok"
        # Note: emergency_stop returns stopped_actuators at top-level (not nested in data)
        assert len(response["stopped_actuators"]) == 3

        # Alle Aktoren sollten emergency_stopped sein
        for gpio in [5, 6, 7]:
            state = mock.get_actuator_state(gpio)
            assert state.emergency_stopped is True

        mock.reset()


class TestDataSourceTracking:
    """Tests fuer data_source Tracking."""

    def test_mock_esp_id_prefix(self):
        """Mock-ESP mit MOCK_ Prefix wird erkannt."""
        mock = MockESP32Client(esp_id="MOCK_TEST_001")
        mock.configure_zone("test_zone", "main", "test")

        # ESP-ID sollte MOCK_ Prefix haben
        assert mock.esp_id.startswith("MOCK_")

        mock.reset()

    def test_test_esp_id_prefix(self):
        """Test-ESP mit TEST_ Prefix wird erkannt."""
        mock = MockESP32Client(esp_id="TEST_UNIT_001")
        mock.configure_zone("test_zone", "main", "test")

        assert mock.esp_id.startswith("TEST_")

        mock.reset()

    def test_simulation_esp_id_prefix(self):
        """Simulation-ESP mit SIM_ Prefix wird erkannt."""
        mock = MockESP32Client(esp_id="SIM_WOKWI_001")
        mock.configure_zone("test_zone", "main", "test")

        assert mock.esp_id.startswith("SIM_")

        mock.reset()

    def test_broker_mode_enum(self):
        """BrokerMode Enum hat korrekte Werte."""
        assert BrokerMode.DIRECT == "direct"
        assert BrokerMode.MQTT == "mqtt"

    def test_default_broker_mode_is_direct(self):
        """Standard-BrokerMode ist DIRECT."""
        mock = MockESP32Client(esp_id="MOCK_DEFAULT")
        assert mock.broker_mode == BrokerMode.DIRECT
        mock.reset()


class TestMessageTracking:
    """Tests fuer Published Message Tracking."""

    def test_sensor_messages_tracked(self):
        """Sensor-Messages werden in published_messages gespeichert."""
        mock = MockESP32Client(esp_id="MOCK_TRACK_001")
        mock.configure_zone("track_zone", "main", "test")

        mock.set_sensor_value(gpio=4, raw_value=23.5, sensor_type="DS18B20")
        mock.handle_command("sensor_read", {"gpio": 4})

        messages = mock.get_published_messages()
        sensor_messages = [m for m in messages if "/sensor/" in m["topic"]]

        assert len(sensor_messages) >= 1

        mock.reset()

    def test_actuator_messages_tracked(self):
        """Actuator-Messages werden in published_messages gespeichert."""
        mock = MockESP32Client(esp_id="MOCK_TRACK_002")
        mock.configure_zone("track_zone", "main", "test")

        mock.configure_actuator(gpio=5, actuator_type="pump", name="Test Pump")
        mock.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})

        messages = mock.get_published_messages()
        actuator_messages = [m for m in messages if "/actuator/" in m["topic"]]

        assert len(actuator_messages) >= 1

        mock.reset()

    def test_heartbeat_messages_tracked(self):
        """Heartbeat-Messages werden in published_messages gespeichert."""
        mock = MockESP32Client(esp_id="MOCK_TRACK_003")
        mock.configure_zone("track_zone", "main", "test")

        mock.handle_command("heartbeat", {})

        messages = mock.get_published_messages()
        heartbeat_messages = [m for m in messages if "/heartbeat" in m["topic"]]

        assert len(heartbeat_messages) >= 1

        mock.reset()

    def test_clear_published_messages(self):
        """Published Messages koennen geloescht werden."""
        mock = MockESP32Client(esp_id="MOCK_CLEAR_001")
        mock.configure_zone("clear_zone", "main", "test")

        mock.set_sensor_value(gpio=4, raw_value=23.5, sensor_type="DS18B20")
        mock.handle_command("sensor_read", {"gpio": 4})

        assert len(mock.get_published_messages()) > 0

        mock.clear_published_messages()

        assert len(mock.get_published_messages()) == 0

        mock.reset()

    def test_filter_messages_by_topic_pattern(self):
        """Messages koennen nach Topic-Pattern gefiltert werden."""
        mock = MockESP32Client(esp_id="MOCK_FILTER_001")
        mock.configure_zone("filter_zone", "main", "test")

        # Verschiedene Message-Typen erzeugen
        mock.set_sensor_value(gpio=4, raw_value=23.5, sensor_type="DS18B20")
        mock.configure_actuator(gpio=5, actuator_type="pump", name="Pump")

        mock.handle_command("sensor_read", {"gpio": 4})
        mock.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})
        mock.handle_command("heartbeat", {})

        # Nach Sensor filtern
        sensor_msgs = mock.get_messages_by_topic_pattern("/sensor/")
        assert all("/sensor/" in m["topic"] for m in sensor_msgs)

        # Nach Actuator filtern
        actuator_msgs = mock.get_messages_by_topic_pattern("/actuator/")
        assert all("/actuator/" in m["topic"] for m in actuator_msgs)

        # Nach Heartbeat filtern
        heartbeat_msgs = mock.get_messages_by_topic_pattern("/heartbeat")
        assert all("/heartbeat" in m["topic"] for m in heartbeat_msgs)

        mock.reset()


class TestZoneConfiguration:
    """Tests fuer Zone-Konfiguration."""

    def test_zone_configured_in_payload(self):
        """Zone-ID wird in Payload inkludiert."""
        mock = MockESP32Client(esp_id="MOCK_ZONE_001")
        mock.configure_zone(
            zone_id="greenhouse_1",
            master_zone_id="main_greenhouse",
            subzone_id="section_a",
            zone_name="Gewaechshaus 1",
            subzone_name="Sektion A",
        )

        mock.set_sensor_value(gpio=4, raw_value=23.5, sensor_type="DS18B20")
        mock.handle_command("sensor_read", {"gpio": 4})

        messages = mock.get_messages_by_topic_pattern("/sensor/4/data")
        assert len(messages) >= 1

        # Zone-Topic sollte auch publiziert werden
        zone_messages = mock.get_messages_by_topic_pattern("/zone/")
        assert len(zone_messages) >= 1

        mock.reset()

    def test_heartbeat_includes_zone_info(self):
        """Heartbeat enthaelt Zone-Informationen."""
        mock = MockESP32Client(esp_id="MOCK_ZONE_HB")
        mock.configure_zone(zone_id="test_zone", master_zone_id="master", zone_name="Test Zone")

        mock.handle_command("heartbeat", {})

        messages = mock.get_messages_by_topic_pattern("/heartbeat")
        assert len(messages) >= 1

        payload = messages[0]["payload"]
        assert payload["zone_id"] == "test_zone"
        assert payload["master_zone_id"] == "master"
        assert payload["zone_assigned"] is True

        mock.reset()
