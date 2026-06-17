"""
Production-Ready System Test Suite

Diese Tests können in Production verwendet werden um:
- Weitere virtuelle ESPs zu simulieren
- Last-Tests durchzuführen
- Cross-ESP-Logik zu validieren
- Sensor-Processing zu testen

Test-Szenarien:
1. ESP32 Registrierung und Verwaltung
2. SHT31/DS18B20 Sensor hinzufügen und auslesen
3. Raw Values → Processing → Echte Werte
4. Sensor Speichern und Löschen
5. Cross-ESP Kommunikation
6. Emergency Stop (Broadcast)
7. Greenhouse Automation (Full Workflow)

Author: Production-Ready Test Suite
Date: December 2025
"""

import pytest
import time
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from tests.esp32.mocks.mock_esp32_client import MockESP32Client
from src.sensors.sensor_libraries.active.temperature import DS18B20Processor, SHT31TemperatureProcessor
from src.sensors.sensor_libraries.active.humidity import SHT31HumidityProcessor


# =============================================================================
# Szenario 1: ESP32 Registrierung im System
# =============================================================================
class TestESPRegistration:
    """ESP32 Anmeldung und Verwaltung."""
    
    def test_esp_registration_and_ping(self):
        """Neue ESP32 meldet sich an via Ping."""
        mock = MockESP32Client(esp_id="greenhouse-esp-001", kaiser_id="god-kaiser-main")
        response = mock.handle_command("ping", {})
        
        assert response["status"] == "ok"
        assert response["esp_id"] == "greenhouse-esp-001"
        assert "uptime" in response
        assert response["command"] == "pong"
    
    def test_esp_config_retrieval(self):
        """ESP32 ruft seine Config ab."""
        mock = MockESP32Client(esp_id="config-test-001")
        config = mock.handle_command("config_get", {})
        
        assert config["status"] == "ok"
        assert "wifi" in config["data"]["config"]
        assert "zone" in config["data"]["config"]  # zone key exists (can be None)
        assert "system" in config["data"]["config"]
        assert config["data"]["config"]["system"]["version"] == "1.0.0-mock"
    
    def test_esp_reset_clears_state(self):
        """Reset löscht alle Sensoren und Actuators."""
        mock = MockESP32Client(esp_id="reset-test-001")
        
        # Configure zone (required for actuator control)
        mock.configure_zone("reset-zone", "main-zone", "test-subzone")
        
        # Sensoren/Actuators hinzufügen
        mock.set_sensor_value(gpio=34, raw_value=100.0, sensor_type="analog")
        mock.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})
        
        assert len(mock.sensors) == 1
        assert len(mock.actuators) == 1
        
        # Reset
        response = mock.handle_command("reset", {})
        assert response["status"] == "ok"
        
        assert len(mock.sensors) == 0
        assert len(mock.actuators) == 0
    
    def test_esp_multiple_registration(self):
        """Mehrere ESPs können sich unabhängig registrieren."""
        esps = [
            MockESP32Client(esp_id=f"esp-{i:03d}") 
            for i in range(1, 6)
        ]
        
        for i, esp in enumerate(esps, 1):
            response = esp.handle_command("ping", {})
            assert response["status"] == "ok"
            assert response["esp_id"] == f"esp-{i:03d}"


# =============================================================================
# Szenario 2: SHT31 Hinzufügen und Auslesen
# =============================================================================
class TestSHT31SensorDataFlow:
    """SHT31 Sensor hinzufügen, auslesen, MQTT validieren."""
    
    def test_add_sht31_temperature_sensor(self):
        """SHT31 Temperatur Sensor hinzufügen und auslesen."""
        mock = MockESP32Client(esp_id="sht31-test")
        
        # Temperature (23.5°C) - I2C SDA GPIO 21
        mock.set_sensor_value(gpio=21, raw_value=23.5, sensor_type="SHT31_temp")
        
        response = mock.handle_command("sensor_read", {"gpio": 21})
        
        assert response["status"] == "ok"
        assert response["data"]["gpio"] == 21
        assert response["data"]["type"] == "SHT31_temp"
        assert response["data"]["raw_value"] == 23.5
        assert "timestamp" in response["data"]
    
    def test_add_sht31_humidity_sensor(self):
        """SHT31 Humidity Sensor hinzufügen und auslesen."""
        mock = MockESP32Client(esp_id="sht31-humidity-test")
        
        # Humidity (65.2%)
        mock.set_sensor_value(gpio=22, raw_value=65.2, sensor_type="SHT31_humidity")
        
        response = mock.handle_command("sensor_read", {"gpio": 22})
        
        assert response["status"] == "ok"
        assert response["data"]["raw_value"] == 65.2
        assert response["data"]["type"] == "SHT31_humidity"
    
    def test_sht31_mqtt_message_validation(self):
        """MQTT Topics folgen dem korrekten Schema."""
        mock = MockESP32Client(esp_id="mqtt-test-001")
        mock.set_sensor_value(gpio=21, raw_value=23.5, sensor_type="SHT31")
        mock.handle_command("sensor_read", {"gpio": 21})
        
        messages = mock.get_published_messages()
        
        # Topic: kaiser/god/esp/mqtt-test-001/sensor/21/data
        # (Only 1 message because no zone configured = no zone topic)
        assert len(messages) >= 1
        sensor_msgs = [m for m in messages if "/sensor/" in m["topic"]]
        assert len(sensor_msgs) >= 1
        assert sensor_msgs[0]["topic"] == "kaiser/god/esp/mqtt-test-001/sensor/21/data"
        assert sensor_msgs[0]["payload"]["gpio"] == 21
        # MQTT payload uses "raw" (not "raw_value") per Mqtt_Protocoll.md
        assert sensor_msgs[0]["payload"]["raw"] == 23.5


# =============================================================================
# Szenario 3: Raw Values → Processing → Echte Werte
# =============================================================================
class TestSensorProcessing:
    """Raw Values → Processing → Echte Werte (Pi-Enhanced Flow)."""
    
    def test_ds18b20_raw_to_celsius(self):
        """DS18B20: Raw Value wird korrekt zu °C."""
        processor = DS18B20Processor()
        result = processor.process(raw_value=23.5)
        
        assert result.value == 23.5
        assert result.unit == "°C"
        assert result.quality == "good"
    
    def test_ds18b20_with_calibration(self):
        """DS18B20: Calibration Offset wird angewendet."""
        processor = DS18B20Processor()
        result = processor.process(raw_value=23.5, calibration={"offset": 0.5})
        
        assert result.value == 24.0
        assert result.metadata["calibrated"] is True
    
    def test_ds18b20_fahrenheit_conversion(self):
        """DS18B20: Konvertierung zu Fahrenheit."""
        processor = DS18B20Processor()
        result = processor.process(raw_value=0.0, params={"unit": "fahrenheit"})
        
        assert result.value == 32.0
        assert result.unit == "°F"
    
    def test_ds18b20_kelvin_conversion(self):
        """DS18B20: Konvertierung zu Kelvin."""
        processor = DS18B20Processor()
        result = processor.process(raw_value=0.0, params={"unit": "kelvin"})
        
        assert result.value == 273.15
        assert result.unit == "K"
    
    def test_ds18b20_quality_assessment(self):
        """DS18B20: Quality Assessment für verschiedene Temperaturen."""
        processor = DS18B20Processor()
        
        # Normal temperature (good quality)
        result_good = processor.process(raw_value=25.0)
        assert result_good.quality == "good"
        
        # Extreme cold (fair quality)
        result_cold = processor.process(raw_value=-50.0)
        assert result_cold.quality == "fair"
        
        # Extreme hot (fair quality)
        result_hot = processor.process(raw_value=100.0)
        assert result_hot.quality == "fair"
    
    def test_sht31_temperature_processing(self):
        """SHT31: Temperature Processing."""
        processor = SHT31TemperatureProcessor()
        result = processor.process(raw_value=22.3)
        
        assert result.value == 22.3
        assert result.unit == "°C"
        assert result.quality == "good"
    
    def test_sht31_humidity_processing(self):
        """SHT31: Humidity Processing mit Quality."""
        processor = SHT31HumidityProcessor()
        
        # Normal humidity
        result = processor.process(raw_value=65.0)
        assert result.quality == "good"
        assert result.unit == "%RH"
    
    def test_sht31_humidity_condensation_warning(self):
        """SHT31: High humidity (condensation) Warning."""
        processor = SHT31HumidityProcessor()
        
        # High humidity (condensation)
        result_high = processor.process(raw_value=96.5)
        assert result_high.quality == "poor"
        
        # Check for condensation warning in metadata
        warnings = result_high.metadata.get("warnings", [])
        has_condensation_warning = any(
            "condensation" in str(w).lower() or "high humidity" in str(w).lower()
            for w in warnings
        )
        assert has_condensation_warning, f"Expected condensation warning, got: {warnings}"
    
    def test_sht31_humidity_with_calibration(self):
        """SHT31: Humidity with calibration offset."""
        processor = SHT31HumidityProcessor()
        result = processor.process(raw_value=65.5, calibration={"offset": -2.0})
        
        assert result.value == 63.5
        assert result.metadata["calibrated"] is True


# =============================================================================
# Szenario 4: Sensor Speichern und Löschen
# =============================================================================
class TestSensorPersistence:
    """Sensor Hinzufügen, Mehrere Sensoren, Löschen."""
    
    def test_add_multiple_sensors(self):
        """Mehrere Sensoren hinzufügen."""
        mock = MockESP32Client(esp_id="multi-sensor-test")
        
        mock.set_sensor_value(gpio=34, raw_value=2048.0, sensor_type="DS18B20")
        mock.set_sensor_value(gpio=35, raw_value=65.2, sensor_type="SHT31")
        mock.set_sensor_value(gpio=36, raw_value=1500.0, sensor_type="moisture")
        
        assert len(mock.sensors) == 3
    
    def test_read_multiple_sensors(self):
        """Mehrere Sensoren auslesen."""
        mock = MockESP32Client(esp_id="multi-read-test")
        
        mock.set_sensor_value(gpio=34, raw_value=23.5, sensor_type="DS18B20")
        mock.set_sensor_value(gpio=35, raw_value=65.2, sensor_type="SHT31")
        
        response_34 = mock.handle_command("sensor_read", {"gpio": 34})
        response_35 = mock.handle_command("sensor_read", {"gpio": 35})
        
        assert response_34["status"] == "ok"
        assert response_35["status"] == "ok"
        assert response_34["data"]["raw_value"] == 23.5
        assert response_35["data"]["raw_value"] == 65.2
    
    def test_reset_deletes_all_sensors(self):
        """Reset löscht alle Sensoren."""
        mock = MockESP32Client(esp_id="delete-test")
        
        mock.set_sensor_value(gpio=34, raw_value=2048.0, sensor_type="DS18B20")
        mock.set_sensor_value(gpio=35, raw_value=65.2, sensor_type="SHT31")
        
        assert len(mock.sensors) == 2
        
        mock.handle_command("reset", {})
        
        assert len(mock.sensors) == 0
    
    def test_update_sensor_value(self):
        """Sensor Wert aktualisieren."""
        mock = MockESP32Client(esp_id="update-test")
        
        mock.set_sensor_value(gpio=34, raw_value=20.0, sensor_type="DS18B20")
        response1 = mock.handle_command("sensor_read", {"gpio": 34})
        assert response1["data"]["raw_value"] == 20.0
        
        # Update value
        mock.set_sensor_value(gpio=34, raw_value=25.0, sensor_type="DS18B20")
        response2 = mock.handle_command("sensor_read", {"gpio": 34})
        assert response2["data"]["raw_value"] == 25.0


# =============================================================================
# Szenario 5: Cross-ESP Kommunikation
# =============================================================================
class TestCrossESPCommunication:
    """Multi-ESP Szenarien - Sensor auf ESP-A steuert Actuator auf ESP-B."""
    
    def test_sensor_on_esp_a_controls_actuator_on_esp_b(self):
        """Sensor auf ESP-A steuert Actuator auf ESP-B."""
        esp_sensors = MockESP32Client(esp_id="sensors-zone-a")
        esp_actuators = MockESP32Client(esp_id="actuators-zone-a")
        
        # Configure zones (required for actuator control)
        esp_sensors.configure_zone("zone-a", "main-zone", "sensors")
        esp_actuators.configure_zone("zone-a", "main-zone", "actuators")
        
        # Moisture Sensor
        esp_sensors.set_sensor_value(gpio=34, raw_value=1500.0, sensor_type="moisture")
        esp_sensors.clear_published_messages()
        moisture = esp_sensors.handle_command("sensor_read", {"gpio": 34})
        
        # Decision: Zu trocken → Pumpe an
        if moisture["data"]["raw_value"] < 2000:
            esp_actuators.clear_published_messages()
            pump = esp_actuators.handle_command("actuator_set", {
                "gpio": 5, "value": 1, "mode": "digital"
            })
            assert pump["state"] is True
        
        # MQTT Topics sind getrennt
        sensor_msgs = esp_sensors.get_published_messages()
        actuator_msgs = [m for m in esp_actuators.get_published_messages() if "/actuator/" in m["topic"]]
        
        assert all("sensors-zone-a" in m["topic"] for m in sensor_msgs if "/sensor/" in m["topic"])
        assert all("actuators-zone-a" in m["topic"] for m in actuator_msgs)
    
    def test_greenhouse_sensor_to_actuator_flow(self):
        """Greenhouse-Szenario: Feuchtigkeitssensor steuert Pumpe."""
        esps = {
            "esp1": MockESP32Client(esp_id="pump-controller"),
            "esp2": MockESP32Client(esp_id="sensor-station"),
            "esp3": MockESP32Client(esp_id="backup-controller")
        }
        
        # Configure zones (required for actuator control)
        esps["esp1"].configure_zone("greenhouse", "main-gh", "pumps")
        esps["esp2"].configure_zone("greenhouse", "main-gh", "sensors")
        esps["esp3"].configure_zone("greenhouse", "main-gh", "backup")
        
        # Sensor auslesen (ESP-002)
        esps["esp2"].set_sensor_value(gpio=34, raw_value=1800.0, sensor_type="moisture")
        esps["esp2"].clear_published_messages()
        moisture = esps["esp2"].handle_command("sensor_read", {"gpio": 34})
        moisture_value = moisture["data"]["raw_value"]
        
        # Entscheidungslogik (Server-Side)
        if moisture_value < 2000:  # Zu trocken
            esps["esp1"].clear_published_messages()
            # Pumpe aktivieren auf ESP-001
            pump = esps["esp1"].handle_command("actuator_set", {
                "gpio": 5, "value": 1, "mode": "digital"
            })
            assert pump["state"] is True
            
            # Validiere MQTT-Topics sind korrekt getrennt
            esp1_msgs = esps["esp1"].get_published_messages()
            esp2_msgs = esps["esp2"].get_published_messages()
            
            # ESP-001 hat Actuator-Status publiziert (filter for actuator topics)
            actuator_msgs = [m for m in esp1_msgs if "/actuator/" in m["topic"]]
            assert len(actuator_msgs) > 0
            assert "pump-controller" in actuator_msgs[-1]["topic"]
            # ESP-002 hat Sensor-Data publiziert
            sensor_msgs = [m for m in esp2_msgs if "/sensor/" in m["topic"]]
            assert len(sensor_msgs) > 0
            assert "sensor-station" in sensor_msgs[-1]["topic"]
    
    def test_multiple_sensors_single_actuator(self):
        """Mehrere Sensoren steuern einen Actuator."""
        esp_sensors1 = MockESP32Client(esp_id="zone-a-sensors")
        esp_sensors2 = MockESP32Client(esp_id="zone-b-sensors")
        esp_actuators = MockESP32Client(esp_id="main-actuator")
        
        # Configure zones (required for actuator control)
        esp_sensors1.configure_zone("zone-a", "main-zone", "sensors-a")
        esp_sensors2.configure_zone("zone-b", "main-zone", "sensors-b")
        esp_actuators.configure_zone("main", "main-zone", "actuators")
        
        # Read temperatures from both zones
        esp_sensors1.set_sensor_value(gpio=34, raw_value=28.0, sensor_type="DS18B20")
        esp_sensors2.set_sensor_value(gpio=34, raw_value=30.0, sensor_type="DS18B20")
        
        temp1 = esp_sensors1.handle_command("sensor_read", {"gpio": 34})
        temp2 = esp_sensors2.handle_command("sensor_read", {"gpio": 34})
        
        avg_temp = (temp1["data"]["raw_value"] + temp2["data"]["raw_value"]) / 2
        
        # Control fan based on average temperature
        if avg_temp > 25:
            fan = esp_actuators.handle_command("actuator_set", {
                "gpio": 7, "value": 0.8, "mode": "pwm"
            })
            assert fan["pwm_value"] == 0.8


# =============================================================================
# Szenario 6: Emergency Stop (Broadcast)
# =============================================================================
class TestEmergencyStop:
    """Emergency Stop Tests - Broadcast über alle ESPs."""
    
    def test_emergency_stop_single_esp(self):
        """Emergency Stop stoppt alle Actuators auf einem ESP."""
        mock = MockESP32Client(esp_id="emergency-test")
        
        # Configure zone (required for actuator control)
        mock.configure_zone("emergency-zone", "main-zone", "test-subzone")
        
        # Alle Pumpen aktivieren
        mock.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})
        mock.handle_command("actuator_set", {"gpio": 6, "value": 1, "mode": "digital"})
        mock.handle_command("actuator_set", {"gpio": 7, "value": 0.75, "mode": "pwm"})
        
        # Verify all ON
        assert mock.get_actuator_state(5).state is True
        assert mock.get_actuator_state(6).state is True
        assert mock.get_actuator_state(7).state is True
        
        # Emergency Stop
        response = mock.handle_command("emergency_stop", {})
        assert response["status"] == "ok"
        
        # Verify all OFF
        assert mock.get_actuator_state(5).state is False
        assert mock.get_actuator_state(6).state is False
        assert mock.get_actuator_state(7).state is False
    
    def test_emergency_stop_all_esps(self):
        """Emergency Stop stoppt ALLE ESPs."""
        esps = {
            "esp1": MockESP32Client(esp_id="zone-a"),
            "esp2": MockESP32Client(esp_id="zone-b"),
            "esp3": MockESP32Client(esp_id="zone-c")
        }
        
        # Configure zones (required for actuator control)
        esps["esp1"].configure_zone("zone-a", "main-zone", "subzone-a")
        esps["esp2"].configure_zone("zone-b", "main-zone", "subzone-b")
        esps["esp3"].configure_zone("zone-c", "main-zone", "subzone-c")
        
        # Alle Pumpen AN
        for esp in esps.values():
            esp.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})
            assert esp.get_actuator_state(5).state is True
        
        # Emergency Stop (Broadcast simuliert)
        for esp in esps.values():
            response = esp.handle_command("emergency_stop", {})
            assert response["status"] == "ok"
        
        # Alle AUS
        for esp in esps.values():
            assert esp.get_actuator_state(5).state is False
    
    def test_emergency_stop_broadcast_topic(self):
        """Validiere Broadcast-Topic bei Emergency Stop."""
        mock = MockESP32Client(esp_id="broadcast-test")
        
        # Configure zone (required for actuator control)
        mock.configure_zone("broadcast-zone", "main-zone", "test-subzone")
        
        mock.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})
        mock.clear_published_messages()
        
        mock.handle_command("emergency_stop", {})
        
        messages = mock.get_published_messages()
        broadcast_msgs = [m for m in messages if m["topic"] == "kaiser/broadcast/emergency"]
        
        assert len(broadcast_msgs) == 1
        assert broadcast_msgs[0]["payload"]["esp_id"] == "broadcast-test"
        assert "stopped_actuators" in broadcast_msgs[0]["payload"]
    
    def test_recovery_after_emergency_stop(self):
        """System kann nach Emergency Stop neu starten (requires clear_emergency)."""
        mock = MockESP32Client(esp_id="recovery-test")
        
        # Configure zone (required for actuator control)
        mock.configure_zone("recovery-zone", "main-zone", "test-subzone")
        
        mock.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})
        mock.handle_command("emergency_stop", {})
        
        assert mock.get_actuator_state(5).state is False
        assert mock.get_actuator_state(5).emergency_stopped is True
        
        # Recovery requires clear_emergency first
        clear_response = mock.handle_command("clear_emergency", {})
        assert clear_response["status"] == "ok"
        assert 5 in clear_response["cleared_actuators"]
        
        # Now actuator can be controlled again
        response = mock.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})
        assert response["status"] == "ok"
        assert mock.get_actuator_state(5).state is True


# =============================================================================
# Szenario 7: Greenhouse Automation (Full Workflow)
# =============================================================================
class TestGreenhouseAutomation:
    """Kompletter Automatisierungs-Workflow."""
    
    def test_full_greenhouse_cycle(self):
        """Kompletter Sensor → Logic → Actuator Zyklus."""
        esp_sensors = MockESP32Client(esp_id="gh-sensors")
        esp_actuators = MockESP32Client(esp_id="gh-actuators")
        
        # Configure zones (required for actuator control)
        esp_sensors.configure_zone("greenhouse", "main-gh", "sensors")
        esp_actuators.configure_zone("greenhouse", "main-gh", "actuators")
        
        # Sensoren Setup
        esp_sensors.set_sensor_value(gpio=34, raw_value=1500.0, sensor_type="moisture")
        esp_sensors.set_sensor_value(gpio=35, raw_value=28.5, sensor_type="DS18B20")
        esp_sensors.set_sensor_value(gpio=36, raw_value=72.0, sensor_type="SHT31")
        
        # Auslesen
        moisture = esp_sensors.handle_command("sensor_read", {"gpio": 34})
        temp = esp_sensors.handle_command("sensor_read", {"gpio": 35})
        humidity = esp_sensors.handle_command("sensor_read", {"gpio": 36})
        
        assert moisture["status"] == "ok"
        assert temp["status"] == "ok"
        assert humidity["status"] == "ok"
        
        # Logic
        m = moisture["data"]["raw_value"]
        t = temp["data"]["raw_value"]
        _h = humidity["data"]["raw_value"]
        
        # Bewässerung
        if m < 2000:
            esp_actuators.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})
        
        # Ventilator (PWM basierend auf Temperatur)
        fan_speed = min(1.0, max(0.0, (t - 20) / 20))
        esp_actuators.handle_command("actuator_set", {"gpio": 7, "value": fan_speed, "mode": "pwm"})
        
        # Validierung
        pump = esp_actuators.get_actuator_state(5)
        fan = esp_actuators.get_actuator_state(7)
        
        assert pump.state is True  # Pumpe sollte AN sein (1500 < 2000)
        assert 0.0 <= fan.pwm_value <= 1.0
    
    def test_greenhouse_with_sensor_processing(self):
        """Greenhouse Workflow mit Sensor Processing Libraries."""
        esp_sensors = MockESP32Client(esp_id="greenhouse-sensors")
        esp_actuators = MockESP32Client(esp_id="greenhouse-actuators")
        
        # Configure zones (required for actuator control)
        esp_sensors.configure_zone("greenhouse", "main-gh", "sensors")
        esp_actuators.configure_zone("greenhouse", "main-gh", "actuators")
        
        # Initialize processors
        ds18b20_proc = DS18B20Processor()
        sht31_humidity_proc = SHT31HumidityProcessor()
        
        # Sensoren Setup
        esp_sensors.set_sensor_value(gpio=34, raw_value=1500.0, sensor_type="moisture")
        esp_sensors.set_sensor_value(gpio=35, raw_value=28.5, sensor_type="DS18B20")
        esp_sensors.set_sensor_value(gpio=21, raw_value=72.0, sensor_type="SHT31")
        
        # Clear messages from setup
        esp_sensors.clear_published_messages()
        esp_actuators.clear_published_messages()
        
        # 1. Sensor-Daten auslesen
        moisture = esp_sensors.handle_command("sensor_read", {"gpio": 34})
        temperature = esp_sensors.handle_command("sensor_read", {"gpio": 35})
        humidity = esp_sensors.handle_command("sensor_read", {"gpio": 21})
        
        # 2. Process raw values through libraries
        temp_result = ds18b20_proc.process(temperature["data"]["raw_value"])
        humidity_result = sht31_humidity_proc.process(humidity["data"]["raw_value"])
        
        assert temp_result.quality == "good"
        assert humidity_result.quality == "good"
        
        # 3. Server-Side Logic (Decision Engine)
        if moisture["data"]["raw_value"] < 2000:
            # Bewässerung aktivieren
            esp_actuators.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})
        
        if temp_result.value > 25.0:
            # Ventilator auf 75%
            esp_actuators.handle_command("actuator_set", {"gpio": 7, "value": 0.75, "mode": "pwm"})
        
        if humidity_result.value > 90.0:
            # Entfeuchter aktivieren
            esp_actuators.handle_command("actuator_set", {"gpio": 6, "value": 1, "mode": "digital"})
        
        # 4. State validieren
        assert esp_actuators.get_actuator_state(5).state is True  # Pumpe AN
        assert esp_actuators.get_actuator_state(7).pwm_value == 0.75  # Ventilator 75%
        
        # 5. MQTT-Messages validieren
        sensor_msgs = esp_sensors.get_published_messages()
        actuator_msgs = esp_actuators.get_published_messages()
        
        # Filter for sensor-specific topics
        sensor_data_msgs = [m for m in sensor_msgs if "/sensor/" in m["topic"]]
        
        # Alle Sensor-Topics korrekt
        for msg in sensor_data_msgs:
            assert "greenhouse-sensors" in msg["topic"]
            assert "/sensor/" in msg["topic"]
        
        # Alle Actuator-Topics korrekt (filter for actuator topics)
        actuator_data_msgs = [m for m in actuator_msgs if "/actuator/" in m["topic"]]
        for msg in actuator_data_msgs:
            assert "greenhouse-actuators" in msg["topic"]
            assert "/actuator/" in msg["topic"]
    
    def test_multi_zone_irrigation(self):
        """Multi-Zone Irrigation System."""
        zones = {
            "zone-a": {
                "sensors": MockESP32Client(esp_id="zone-a-sensors"),
                "actuators": MockESP32Client(esp_id="zone-a-actuators"),
            },
            "zone-b": {
                "sensors": MockESP32Client(esp_id="zone-b-sensors"),
                "actuators": MockESP32Client(esp_id="zone-b-actuators"),
            },
        }
        
        # Configure zones (required for actuator control)
        zones["zone-a"]["sensors"].configure_zone("zone-a", "irrigation", "sensors-a")
        zones["zone-a"]["actuators"].configure_zone("zone-a", "irrigation", "actuators-a")
        zones["zone-b"]["sensors"].configure_zone("zone-b", "irrigation", "sensors-b")
        zones["zone-b"]["actuators"].configure_zone("zone-b", "irrigation", "actuators-b")
        
        # Setup sensors for each zone
        zones["zone-a"]["sensors"].set_sensor_value(gpio=34, raw_value=1500.0, sensor_type="moisture")
        zones["zone-b"]["sensors"].set_sensor_value(gpio=34, raw_value=2500.0, sensor_type="moisture")
        
        # Control irrigation per zone based on individual moisture
        for zone_name, zone in zones.items():
            moisture = zone["sensors"].handle_command("sensor_read", {"gpio": 34})
            
            if moisture["data"]["raw_value"] < 2000:
                zone["actuators"].handle_command("actuator_set", {
                    "gpio": 5, "value": 1, "mode": "digital"
                })
        
        # Verify: Zone-A should be ON (dry), Zone-B should stay OFF (wet)
        assert zones["zone-a"]["actuators"].get_actuator_state(5).state is True
        assert zones["zone-b"]["actuators"].get_actuator_state(5) is None  # Not created = OFF


# =============================================================================
# Szenario 8: MQTT Topic Validation
# =============================================================================
class TestMQTTTopicValidation:
    """Validate MQTT Topic Structure."""
    
    def test_sensor_topic_structure(self):
        """Sensor Topic: kaiser/god/esp/{esp_id}/sensor/{gpio}/data"""
        mock = MockESP32Client(esp_id="topic-test-001")
        mock.set_sensor_value(gpio=34, raw_value=2048.0, sensor_type="analog")
        mock.handle_command("sensor_read", {"gpio": 34})
        
        messages = mock.get_published_messages()
        # Without zone, only 1 sensor message
        sensor_msgs = [m for m in messages if "/sensor/" in m["topic"]]
        assert len(sensor_msgs) >= 1
        
        expected_topic = "kaiser/god/esp/topic-test-001/sensor/34/data"
        assert sensor_msgs[0]["topic"] == expected_topic
    
    def test_actuator_topic_structure(self):
        """Actuator Topic: kaiser/god/esp/{esp_id}/actuator/{gpio}/status AND /response"""
        mock = MockESP32Client(esp_id="topic-test-002")
        
        # Configure zone (required for actuator control)
        mock.configure_zone("topic-zone", "main-zone", "test-subzone")
        mock.clear_published_messages()
        
        mock.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})
        
        messages = mock.get_published_messages()
        
        # Now publishes 2 messages: status + response
        status_msgs = [m for m in messages if "/status" in m["topic"]]
        response_msgs = [m for m in messages if "/response" in m["topic"]]
        
        assert len(status_msgs) == 1
        assert len(response_msgs) == 1
        
        expected_status_topic = "kaiser/god/esp/topic-test-002/actuator/5/status"
        expected_response_topic = "kaiser/god/esp/topic-test-002/actuator/5/response"
        assert status_msgs[0]["topic"] == expected_status_topic
        assert response_msgs[0]["topic"] == expected_response_topic
    
    def test_emergency_topic_structure(self):
        """Emergency Topics: Device-specific + Broadcast."""
        mock = MockESP32Client(esp_id="emergency-topic-test")
        
        # Configure zone (required for actuator control)
        mock.configure_zone("emergency-zone", "main-zone", "test-subzone")
        
        mock.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})
        mock.clear_published_messages()
        
        mock.handle_command("emergency_stop", {})
        
        messages = mock.get_published_messages()
        
        # Should have: actuator status + device emergency + broadcast
        device_emergency = [m for m in messages if "actuator/emergency" in m["topic"]]
        broadcast_emergency = [m for m in messages if m["topic"] == "kaiser/broadcast/emergency"]
        
        assert len(device_emergency) == 1
        assert len(broadcast_emergency) == 1


# =============================================================================
# Szenario 9: Performance Tests
# =============================================================================
@pytest.mark.performance
class TestPerformance:
    """Performance Tests für Multi-ESP Orchestration."""
    
    def test_rapid_sensor_reads(self):
        """Test rapid sensor reading performance."""
        mock = MockESP32Client(esp_id="perf-test-001")
        
        # Setup sensors
        for gpio in range(30, 40):
            mock.set_sensor_value(gpio=gpio, raw_value=float(gpio * 100), sensor_type="analog")
        
        start = time.time()
        
        # 100 rapid reads
        for _ in range(10):
            for gpio in range(30, 40):
                response = mock.handle_command("sensor_read", {"gpio": gpio})
                assert response["status"] == "ok"
        
        elapsed = time.time() - start
        assert elapsed < 1.0, f"100 reads too slow: {elapsed:.3f}s"
    
    def test_many_esps_coordination(self):
        """Test coordination with many ESPs."""
        num_esps = 10
        esps = [MockESP32Client(esp_id=f"esp-{i:03d}") for i in range(num_esps)]
        
        # Configure zones for all ESPs (required for actuator control)
        for i, esp in enumerate(esps):
            esp.configure_zone(f"zone-{i}", "main-zone", f"subzone-{i}")
        
        start = time.time()
        
        # Each ESP does: ping + sensor read + actuator set
        for esp in esps:
            esp.set_sensor_value(gpio=34, raw_value=2048.0, sensor_type="analog")
            
            ping = esp.handle_command("ping", {})
            assert ping["status"] == "ok"
            
            sensor = esp.handle_command("sensor_read", {"gpio": 34})
            assert sensor["status"] == "ok"
            
            actuator = esp.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})
            assert actuator["status"] == "ok"
        
        elapsed = time.time() - start
        assert elapsed < 2.0, f"10 ESP coordination too slow: {elapsed:.3f}s"


# =============================================================================
# Szenario 10: Error Handling
# =============================================================================
class TestErrorHandling:
    """Error Handling und Recovery Tests."""
    
    def test_invalid_command(self):
        """Invalid Command returns error."""
        mock = MockESP32Client(esp_id="error-test-001")
        response = mock.handle_command("invalid_command", {})
        
        assert response["status"] == "error"
        assert "Unknown command" in response["error"]
    
    def test_missing_parameter(self):
        """Missing parameter returns error."""
        mock = MockESP32Client(esp_id="error-test-002")
        
        # Configure zone (required for actuator control)
        mock.configure_zone("error-zone", "main-zone", "test-subzone")
        
        response = mock.handle_command("actuator_set", {"gpio": 5})  # Missing value
        
        assert response["status"] == "error"
        assert "Missing" in response["error"]
    
    def test_actuator_without_zone_returns_error(self):
        """Actuator command without zone configuration returns error."""
        mock = MockESP32Client(esp_id="no-zone-test")
        
        # No zone configured
        response = mock.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})
        
        assert response["status"] == "error"
        assert "Zone not configured" in response["error"]
    
    def test_recovery_after_error(self):
        """System recovers after error."""
        mock = MockESP32Client(esp_id="recovery-error-test")
        
        # Cause error
        error_response = mock.handle_command("invalid_command", {})
        assert error_response["status"] == "error"
        
        # System should still work
        ok_response = mock.handle_command("ping", {})
        assert ok_response["status"] == "ok"
    
    def test_read_nonexistent_sensor(self):
        """Reading non-existent sensor creates default sensor."""
        mock = MockESP32Client(esp_id="nonexistent-test")
        
        # Read sensor that doesn't exist
        response = mock.handle_command("sensor_read", {"gpio": 99})
        
        # Should create default sensor
        assert response["status"] == "ok"
        assert response["data"]["raw_value"] == 0.0
    
    def test_temperature_out_of_range(self):
        """Temperature processor handles out-of-range values."""
        processor = DS18B20Processor()
        
        # Way below minimum (-55°C)
        result = processor.process(raw_value=-100.0)
        assert result.quality == "error"
        
        # Way above maximum (125°C)
        result = processor.process(raw_value=200.0)
        assert result.quality == "error"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--no-cov"])

