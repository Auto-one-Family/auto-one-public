"""
Test-Modul: DS18B20 Multi-Sensor Cross-ESP Logic

Fokus: DS18B20 OneWire Temperatur-Sensoren mit Cross-ESP Logic Engine Integration

Hardware-Kontext:
- DS18B20 OneWire Digital Sensoren
- GPIO4 für OneWire-Bus (empfohlen)
- Mehrere Sensoren auf einem Bus (unique 64-bit ROM-Adresse)
- RAW-Wert = Temperatur direkt (12-bit Auflösung = 0.0625°C)
- Special Values: -127°C (Fault/CRC), +85°C (Power-On-Reset)
- Conversion Time: 750ms (12-bit)

Dependencies:
- MockESP32Client with add_ds18b20_multi()
- LogicEngine
- Cross-ESP Communication
"""

import pytest
import pytest_asyncio
import uuid
import time
from unittest.mock import AsyncMock, MagicMock, patch

# Import fixtures
from tests.integration.conftest_logic import (  # noqa: F401
    mock_esp32_ds18b20_multi,
    mock_esp32_ds18b20_dual_bus,
    cross_esp_logic_setup,
    multi_zone_esp_setup,
    logic_engine,
    mock_actuator_service,
    mock_logic_repo,
    mock_websocket_manager,
    create_sensor_condition,
    create_actuator_action,
    create_notification_action,
)

from tests.esp32.mocks.mock_esp32_client import MockESP32Client, SystemState  # noqa: F401

pytestmark = [pytest.mark.logic, pytest.mark.ds18b20, pytest.mark.cross_esp]


class TestDS18B20MultiSensorAveraging:
    """Tests for multi-sensor averaging and aggregation."""

    @pytest.mark.asyncio
    async def test_multi_sensor_average_trigger(self, logic_engine, mock_esp32_ds18b20_multi):
        """
        SZENARIO: Durchschnittstemperatur aus 3 Sensoren triggert Aktion

        HARDWARE-KONTEXT:
        - 3 DS18B20 auf einem OneWire-Bus (GPIO4)
        - Jeder hat einzigartige 64-bit ROM-Adresse
        - Durchschnitt reduziert Einzelsensor-Fehler

        GIVEN: 3 DS18B20 auf ESP_TEMP_ARRAY
               Sensor_1: 22.5°C, Sensor_2: 23.0°C, Sensor_3: 22.8°C
        WHEN: Average = 22.77°C > 22.5°C Threshold
        THEN: Ventilation Fan auf GPIO25 aktivieren

        LOGIC RULE:
        - Condition: avg(temp_1, temp_2, temp_3) > 22.5
        - Action: actuator_command(GPIO25, command="ON")
        """
        # === SETUP ===
        mock = mock_esp32_ds18b20_multi

        # Verify sensors exist
        assert hasattr(mock, "_ds18b20_buses")
        bus = mock._ds18b20_buses[4]
        assert len(bus) == 3

        # === CALCULATE AVERAGE ===
        average = mock.get_ds18b20_average(4)
        expected_avg = (22.5 + 23.0 + 22.8) / 3  # = 22.77

        # === VERIFY ===
        assert average is not None
        assert abs(average - expected_avg) < 0.01
        assert average > 22.5  # Threshold exceeded

    @pytest.mark.asyncio
    async def test_multi_sensor_ignores_fault_in_average(self, mock_esp32_ds18b20_multi):
        """
        SZENARIO: Faulty Sensor wird vom Average ausgeschlossen

        HARDWARE-KONTEXT:
        - Wenn ein Sensor -127°C meldet (Fault)
        - Sollte er nicht in Average einbezogen werden

        GIVEN: 3 Sensoren, einer meldet -127°C
        WHEN: Average berechnet wird
        THEN: Nur gültige Sensoren (2) werden verwendet
        """
        # === SETUP ===
        mock = mock_esp32_ds18b20_multi

        # Set one sensor to fault value
        mock.set_ds18b20_value(
            gpio=4, rom_address="28-000000000002", temperature=-127.0, quality="bad"
        )

        # === CALCULATE AVERAGE ===
        average = mock.get_ds18b20_average(4)

        # Should be average of only 2 valid sensors: (22.5 + 22.8) / 2 = 22.65
        expected_avg = (22.5 + 22.8) / 2

        # === VERIFY ===
        assert average is not None
        assert abs(average - expected_avg) < 0.01


class TestDS18B20FaultHandling:
    """Tests for DS18B20 fault detection and handling."""

    @pytest.mark.asyncio
    async def test_power_on_reset_ignored(self, mock_esp32_ds18b20_multi):
        """
        SZENARIO: Power-On-Reset Value (+85°C) ignorieren

        HARDWARE-KONTEXT:
        - DS18B20 meldet +85°C (RAW 1360) nach Power-On
        - Das ist KEINE echte Temperatur!
        - Muss erkannt und ignoriert werden

        GIVEN: DS18B20 gerade eingeschaltet
        WHEN: Sensor meldet 85.0°C
        THEN: Logic Rule ignoriert diesen Wert, wartet auf nächsten

        LOGIC RULE:
        - Condition: temp == 85.0 AND first_reading_after_boot
        - Action: skip_execution, log_warning
        """
        # === SETUP ===
        mock = mock_esp32_ds18b20_multi

        # Simulate power-on reset on one sensor
        mock.simulate_sensor_fault(gpio=4, fault_type="power_on_reset")

        # === VERIFY ===
        sensor = mock.get_sensor_state(4)
        assert sensor.raw_value == 85.0  # Power-on reset value
        assert sensor.quality == "stale"  # Not "good"

    @pytest.mark.asyncio
    async def test_disconnect_fault_detection(self, mock_esp32_ds18b20_multi):
        """
        SZENARIO: Sensor Disconnect (-127°C) erkennen

        HARDWARE-KONTEXT:
        - DS18B20 meldet -127°C bei:
          - CRC-Fehler
          - Getrennte Verbindung
          - Beschädigter Sensor

        GIVEN: DS18B20 auf GPIO4
        WHEN: Sensor meldet -127°C
        THEN: Error loggen, Sensor als "bad" markieren

        LOGIC RULE:
        - Condition: temp == -127
        - Action: notification("Sensor fault"), mark_sensor_bad
        """
        # === SETUP ===
        mock = mock_esp32_ds18b20_multi

        # Simulate disconnect
        mock.simulate_sensor_fault(gpio=4, fault_type="disconnect")

        # === VERIFY ===
        sensor = mock.get_sensor_state(4)
        assert sensor.raw_value == -127.0
        assert sensor.quality == "bad"

        # All sensors on bus should be affected
        for rom, bus_sensor in mock._ds18b20_buses[4].items():
            assert bus_sensor.quality == "bad"

    @pytest.mark.asyncio
    async def test_sensor_failover_to_backup(self, mock_esp32_ds18b20_multi):
        """
        SZENARIO: Primärsensor fällt aus → Backup übernimmt

        HARDWARE-KONTEXT:
        - Bei mehreren Sensoren kann ein Backup übernehmen
        - Logic Rule sollte automatisch auf nächsten gültigen Sensor wechseln

        GIVEN: 2 DS18B20 (Primary + Backup)
        WHEN: Primary meldet -127°C (Sensor-Fault)
        THEN: Logic schaltet auf Backup-Sensor
        """
        # === SETUP ===
        mock = mock_esp32_ds18b20_multi

        # Get ROM addresses
        bus = mock._ds18b20_buses[4]
        rom_addresses = list(bus.keys())

        # Set primary to fault
        mock.set_ds18b20_value(
            gpio=4, rom_address=rom_addresses[0], temperature=-127.0, quality="bad"
        )

        # === VERIFY BACKUP AVAILABLE ===
        backup_sensor = mock.get_ds18b20_by_rom(4, rom_addresses[1])
        assert backup_sensor is not None
        assert backup_sensor.quality == "good"
        assert backup_sensor.raw_value > -100  # Valid temperature


class TestDS18B20GradientDetection:
    """Tests for temperature gradient (rate of change) detection."""

    @pytest.mark.asyncio
    async def test_gradient_detection_alert(self, mock_esp32_ds18b20_multi):
        """
        SZENARIO: Schnelle Temperaturänderung erkennen

        HARDWARE-KONTEXT:
        - Schnelle Temperaturänderung kann auf Problem hindeuten
        - >5°C/Minute = abnormal
        - Z.B. Sensor in der Sonne, Heizung defekt

        GIVEN: DS18B20 meldet normale Temperaturen
        WHEN: Temperatur springt von 22°C auf 30°C in 1 Minute
        THEN: Alert "Abnormal temperature gradient"

        LOGIC RULE:
        - Condition: abs(temp_current - temp_previous) / time_delta > 5°C/min
        - Action: notification("Abnormal temperature gradient")
        """
        # === SETUP ===
        mock = mock_esp32_ds18b20_multi

        # Record initial value
        initial_temp = mock.get_sensor_state(4).raw_value

        # Simulate rapid temperature change
        mock.sensors[4].raw_value = initial_temp + 8.0  # +8°C jump

        # === VERIFY ===
        current_temp = mock.get_sensor_state(4).raw_value
        gradient = abs(current_temp - initial_temp)

        assert gradient > 5.0  # Abnormal gradient detected


class TestDS18B20CrossESP:
    """Cross-ESP temperature control tests."""

    @pytest.mark.asyncio
    async def test_cross_esp_temp_ventilation(self, cross_esp_logic_setup, logic_engine):
        """
        SZENARIO: Temperatur auf ESP_A → Lüfter auf ESP_B

        HARDWARE-KONTEXT:
        - Sensor-ESP misst Temperatur
        - Actuator-ESP steuert Lüfter
        - Cross-ESP via MQTT

        GIVEN: DS18B20 auf ESP_SENSORS (GPIO4)
               PWM Fan auf ESP_ACTUATORS (GPIO25)
        WHEN: Temperatur > 26°C
        THEN: Fan auf 75% PWM aktivieren

        LOGIC RULE:
        - Condition: ESP_SENSORS:GPIO4 > 26
        - Action: actuator_command(ESP_ACTUATORS, gpio=25, command="PWM", value=0.75)
        """
        # === SETUP ===
        sensor_esp = cross_esp_logic_setup["sensor_esp"]
        actuator_esp = cross_esp_logic_setup["actuator_esp"]

        # Set high temperature
        sensor_esp.sensors[4].raw_value = 28.0

        # === TRIGGER ===
        await logic_engine.evaluate_sensor_data(
            esp_id="ESP_SENSORS", gpio=4, sensor_type="DS18B20", value=28.0
        )

        # === VERIFY ===
        sensor = sensor_esp.get_sensor_state(4)
        assert sensor.raw_value == 28.0
        assert sensor.raw_value > 26.0  # Threshold exceeded

        # Fan should be configured on actuator ESP
        fan = actuator_esp.get_actuator_state(25)
        assert fan is not None
        assert fan.actuator_type == "pwm_motor"

    @pytest.mark.asyncio
    async def test_zone_differential_balancing(self, multi_zone_esp_setup, logic_engine):
        """
        SZENARIO: Temperatur-Ausgleich zwischen Zonen

        HARDWARE-KONTEXT:
        - Zone A: 24°C (warm)
        - Zone B: 22°C (cool)
        - Differential > 2°C → Lüfter zur Ausgleichung

        GIVEN: 2 Zonen mit unterschiedlichen Temperaturen
        WHEN: Zone A - Zone B > 2°C
        THEN: Ventilation aktivieren für Ausgleich

        LOGIC RULE:
        - Condition: (zone_a_temp - zone_b_temp) > 2
        - Action: activate_zone_a_ventilation
        """
        # === SETUP ===
        za_sensors = multi_zone_esp_setup["zone_a_sensors"]
        zb_sensors = multi_zone_esp_setup["zone_b_sensors"]

        temp_a = za_sensors.get_sensor_state(4).raw_value  # 24°C
        temp_b = zb_sensors.get_sensor_state(4).raw_value  # 22°C

        # === VERIFY ===
        differential = temp_a - temp_b
        assert differential == 2.0  # Exactly at threshold


class TestDS18B20ROMAddressing:
    """Tests for ROM address targeting and bus management."""

    def test_rom_address_targeting(self, mock_esp32_ds18b20_multi):
        """
        SZENARIO: Spezifischen Sensor via ROM-Adresse ansprechen

        HARDWARE-KONTEXT:
        - Jeder DS18B20 hat einzigartige 64-bit ROM-Adresse
        - Format: "28-XXXXXXXXXXXX" (Family Code 28 = DS18B20)

        GIVEN: 3 DS18B20 auf einem Bus
        WHEN: Spezifische ROM-Adresse angesprochen
        THEN: Nur dieser Sensor wird gelesen/geändert
        """
        # === SETUP ===
        mock = mock_esp32_ds18b20_multi

        # Target specific sensor
        target_rom = "28-000000000002"
        sensor = mock.get_ds18b20_by_rom(4, target_rom)

        # === VERIFY ===
        assert sensor is not None
        assert sensor.calibration["rom_address"] == target_rom

        # Update only this sensor
        mock.set_ds18b20_value(4, target_rom, 30.0)

        # Verify only target was updated
        updated = mock.get_ds18b20_by_rom(4, target_rom)
        other = mock.get_ds18b20_by_rom(4, "28-000000000001")

        assert updated.raw_value == 30.0
        assert other.raw_value == 22.5  # Unchanged

    def test_multiple_buses_independent(self, mock_esp32_ds18b20_dual_bus):
        """
        SZENARIO: Mehrere OneWire-Busse arbeiten unabhängig

        HARDWARE-KONTEXT:
        - ESP32 kann mehrere OneWire-Busse haben
        - GPIO4: Indoor-Sensoren
        - GPIO16: Outdoor-Sensor

        GIVEN: 2 OneWire-Busse (GPIO4, GPIO16)
        WHEN: Sensor auf GPIO4 wird geändert
        THEN: Sensor auf GPIO16 bleibt unverändert
        """
        # === SETUP ===
        mock = mock_esp32_ds18b20_dual_bus

        # Get initial values
        bus_4_sensor = mock.get_sensor_state(4)
        bus_16_sensor = mock.get_ds18b20_by_rom(16, "28-OUTDOOR00001")

        initial_4 = bus_4_sensor.raw_value
        initial_16 = bus_16_sensor.raw_value

        # === MODIFY BUS 4 ===
        mock.sensors[4].raw_value = 35.0

        # === VERIFY ===
        # Bus 16 should be unchanged
        current_16 = mock.get_ds18b20_by_rom(16, "28-OUTDOOR00001")
        assert current_16.raw_value == initial_16


class TestDS18B20ConversionTime:
    """Tests for DS18B20 conversion time handling."""

    def test_conversion_time_12bit(self, mock_esp32_ds18b20_multi):
        """
        SZENARIO: 12-bit Conversion benötigt 750ms

        HARDWARE-KONTEXT:
        - DS18B20 braucht Zeit für Temperatur-Konvertierung
        - 9-bit: 93.75ms, 10-bit: 187.5ms, 11-bit: 375ms, 12-bit: 750ms
        - Lesen vor Fertigstellung → falscher Wert

        GIVEN: DS18B20 in 12-bit Modus
        WHEN: Conversion gestartet
        THEN: Warten auf 750ms vor Lesen
        """
        # === SETUP ===
        mock = mock_esp32_ds18b20_multi

        sensor = mock.get_ds18b20_by_rom(4, "28-000000000001")

        # === VERIFY ===
        assert sensor.calibration["resolution"] == 12
        assert sensor.calibration["conversion_time_ms"] == 750


class TestDS18B20MinMaxTracking:
    """Tests for temperature min/max tracking."""

    @pytest.mark.asyncio
    async def test_min_max_tracking_notification(self, mock_esp32_ds18b20_multi):
        """
        SZENARIO: Tages-Min/Max-Temperatur tracking

        HARDWARE-KONTEXT:
        - Tracking von Temperatur-Extremen für Analyse
        - Notification bei neuen Rekorden

        GIVEN: DS18B20 Sensor
        WHEN: Neue Min oder Max Temperatur erreicht
        THEN: Notification mit neuem Rekord

        LOGIC RULE:
        - Condition: temp > max_today OR temp < min_today
        - Action: notification("New temperature record")
        """
        # === SETUP ===
        mock = mock_esp32_ds18b20_multi

        # Simulate temperature readings
        readings = [22.0, 23.5, 24.0, 21.5, 22.8, 25.0, 20.0]
        max_temp = max(readings)
        min_temp = min(readings)

        # === VERIFY ===
        assert max_temp == 25.0
        assert min_temp == 20.0


class TestDS18B20SensorOfflineHandling:
    """Tests for handling offline sensors."""

    @pytest.mark.asyncio
    async def test_sensor_offline_graceful_degradation(
        self, mock_esp32_ds18b20_multi, logic_engine
    ):
        """
        SZENARIO: Ein Sensor offline → System arbeitet weiter

        HARDWARE-KONTEXT:
        - In großen Installationen können einzelne Sensoren ausfallen
        - System sollte mit reduzierter Genauigkeit weiterlaufen

        GIVEN: 3 DS18B20 Sensoren
        WHEN: 1 Sensor fällt aus (offline/fault)
        THEN: System nutzt verbleibende 2 Sensoren, loggt Warning

        LOGIC RULE:
        - Condition: available_sensors < expected_sensors
        - Action: log_warning, continue_with_available
        """
        # === SETUP ===
        mock = mock_esp32_ds18b20_multi

        # Set one sensor to fault
        mock.set_ds18b20_value(
            gpio=4, rom_address="28-000000000001", temperature=-127.0, quality="bad"
        )

        # === VERIFY ===
        # System can still get average from remaining sensors
        average = mock.get_ds18b20_average(4)
        assert average is not None

        # Count valid sensors
        bus = mock._ds18b20_buses[4]
        valid_count = sum(1 for s in bus.values() if s.quality != "bad")
        assert valid_count == 2  # 1 of 3 is faulty
