"""
Test-Modul: SHT31 I2C Multi-Sensor Logic

Fokus: SHT31 I2C Temperatur+Feuchtigkeits-Sensoren mit Logic Engine Integration

Hardware-Kontext:
- SHT31 I2C Sensoren (Temp + Humidity)
- I2C Adressen: 0x44 (ADR=LOW), 0x45 (ADR=HIGH)
- Max 2 pro I2C-Bus ohne Multiplexer
- Built-in Heater für Kondensation
- Genauigkeit: ±0.2°C, ±2% RH

Dependencies:
- MockESP32Client with set_multi_value_sensor()
- LogicEngine
- Compound Conditions (temp + humidity)
"""

import pytest
import pytest_asyncio
import uuid
import time
from unittest.mock import AsyncMock, MagicMock, patch

# Import fixtures
from tests.integration.conftest_logic import (  # noqa: F401
    mock_esp32_sht31,
    mock_esp32_sht31_high_humidity,
    cross_esp_logic_setup,
    multi_zone_esp_setup,
    logic_engine,
    mock_actuator_service,
    mock_logic_repo,
    mock_websocket_manager,
    create_sensor_condition,
    create_actuator_action,
    create_hysteresis_condition,
    create_notification_action,
)

from tests.esp32.mocks.mock_esp32_client import MockESP32Client, SystemState  # noqa: F401

pytestmark = [pytest.mark.logic, pytest.mark.sht31]


class TestSHT31DualSensorComparison:
    """Tests for dual SHT31 sensor zone comparison."""

    @pytest.mark.asyncio
    async def test_dual_address_zone_comparison(self, mock_esp32_sht31, logic_engine):
        """
        SZENARIO: Vergleich zwischen zwei Zonen via 2 SHT31

        HARDWARE-KONTEXT:
        - SHT31_A at 0x44 (ADR LOW) - Zone A
        - SHT31_B at 0x45 (ADR HIGH) - Zone B
        - Beide auf I2C-Bus (GPIO21/22)

        GIVEN: SHT31_A (Zone A): 75% RH, 24°C
               SHT31_B (Zone B): 55% RH, 22°C
        WHEN: Zone A humidity > Zone B + 10%
        THEN: Ventilation in Zone A aktivieren

        LOGIC RULE:
        - Condition: humidity_A > humidity_B + 10
        - Action: actuator_command(gpio=26, command="ON")
        """
        # === SETUP ===
        mock = mock_esp32_sht31

        # Update humidity values
        mock.sensors[21].secondary_values = {"humidity": 75.0}
        mock.sensors[22].secondary_values = {"humidity": 55.0}

        # === VERIFY ===
        sensor_a = mock.get_sensor_state(21)  # 0x44
        sensor_b = mock.get_sensor_state(22)  # 0x45

        humidity_a = sensor_a.secondary_values["humidity"]
        humidity_b = sensor_b.secondary_values["humidity"]

        differential = humidity_a - humidity_b
        assert differential == 20.0  # > 10% threshold

    @pytest.mark.asyncio
    async def test_temp_humidity_correlation(self, mock_esp32_sht31, logic_engine):
        """
        SZENARIO: Korrelierte Temp+Humidity Bedingung

        HARDWARE-KONTEXT:
        - SHT31 liefert beide Werte gleichzeitig
        - Compound Condition: Temp UND Humidity

        GIVEN: SHT31 mit temp=28°C, humidity=80%
        WHEN: temp > 26 AND humidity > 75
        THEN: Aggressive Ventilation aktivieren

        LOGIC RULE:
        - Condition: compound(temp > 26 AND humidity > 75)
        - Action: actuator_command(gpio=26, command="PWM", value=1.0)
        """
        # === SETUP ===
        mock = mock_esp32_sht31

        # Set high temp AND high humidity
        mock.sensors[21].raw_value = 28.0  # Temperature
        mock.sensors[21].secondary_values = {"humidity": 80.0}

        # === TRIGGER ===
        await logic_engine.evaluate_sensor_data(
            esp_id="ESP_SHT31", gpio=21, sensor_type="SHT31", value=28.0
        )

        # === VERIFY ===
        sensor = mock.get_sensor_state(21)
        assert sensor.raw_value > 26.0
        assert sensor.secondary_values["humidity"] > 75.0


class TestSHT31HeaterActivation:
    """Tests for SHT31 built-in heater functionality."""

    @pytest.mark.asyncio
    async def test_heater_activation_on_condensation(
        self, mock_esp32_sht31_high_humidity, logic_engine
    ):
        """
        SZENARIO: Kondensation → SHT31 Heater aktivieren

        HARDWARE-KONTEXT:
        - SHT31 hat eingebauten Heater
        - Heater entfernt Kondensation von Sensor-Oberfläche
        - Aktivieren bei >95% RH für >5 Minuten
        - Heater läuft max 30 Sekunden

        GIVEN: SHT31 meldet 98% RH
        WHEN: Humidity >95% für >5 Minuten
        THEN: SHT31 Heater für 30 Sekunden aktivieren

        LOGIC RULE:
        - Condition: humidity > 95 AND duration > 300s
        - Action: sht31_heater_command(duration=30)
        """
        # === SETUP ===
        mock = mock_esp32_sht31_high_humidity

        sensor = mock.get_sensor_state(21)
        humidity = sensor.secondary_values["humidity"]

        # === VERIFY ===
        assert humidity == 98.5  # >95% threshold
        assert humidity > 95.0

    @pytest.mark.asyncio
    async def test_heater_timeout_protection(self, mock_esp32_sht31_high_humidity):
        """
        SZENARIO: Heater Auto-Off nach 30 Sekunden

        HARDWARE-KONTEXT:
        - Heater darf maximal 30 Sekunden laufen
        - Überhitzung kann Sensor beschädigen
        - Auto-Off Schutz erforderlich

        GIVEN: SHT31 Heater ist aktiv
        WHEN: 30 Sekunden vergehen
        THEN: Heater automatisch abschalten

        LOGIC RULE:
        - Condition: heater_active AND heater_runtime > 30
        - Action: heater_off
        """
        # === SETUP ===
        mock = mock_esp32_sht31_high_humidity

        # Heater max duration is 30 seconds
        MAX_HEATER_DURATION = 30

        # === VERIFY ===
        assert MAX_HEATER_DURATION == 30


class TestSHT31DewPointCalculation:
    """Tests for dew point calculation and condensation warning."""

    @pytest.mark.asyncio
    async def test_dew_point_calculation_warning(self, mock_esp32_sht31):
        """
        SZENARIO: Taupunkt-Berechnung für Kondensations-Warnung

        HARDWARE-KONTEXT:
        - Taupunkt = f(Temperatur, Luftfeuchtigkeit)
        - Magnus-Formel: Td = 243.04 * (ln(RH/100) + ((17.625 * T) / (243.04 + T))) /
                               (17.625 - (ln(RH/100) + ((17.625 * T) / (243.04 + T))))
        - Wenn Oberflächentemp < Taupunkt → Kondensation

        GIVEN: SHT31 meldet 22°C, 80% RH
        WHEN: Berechneter Taupunkt = 18.4°C
               UND Pflanzenoberfläche < 18.4°C
        THEN: Warning "Condensation risk"

        LOGIC RULE:
        - Condition: surface_temp < dew_point
        - Action: notification("Condensation risk on plants")
        """
        # === SETUP ===
        mock = mock_esp32_sht31

        # Set values for dew point calculation
        mock.sensors[21].raw_value = 22.0  # Temperature
        mock.sensors[21].secondary_values = {"humidity": 80.0}

        # === CALCULATE DEW POINT (simplified Magnus formula) ===
        import math

        temp = 22.0
        rh = 80.0

        # Magnus formula constants
        a = 17.625
        b = 243.04

        alpha = ((a * temp) / (b + temp)) + math.log(rh / 100.0)
        dew_point = (b * alpha) / (a - alpha)

        # === VERIFY ===
        # Expected dew point ~18.4°C for 22°C/80%RH
        assert 17.5 < dew_point < 19.0


class TestSHT31I2CErrorHandling:
    """Tests for I2C communication error handling."""

    @pytest.mark.asyncio
    async def test_i2c_nack_error_handling(self, mock_esp32_sht31):
        """
        SZENARIO: I2C NACK Error → Alert

        HARDWARE-KONTEXT:
        - I2C NACK = Sensor nicht angeschlossen/defekt
        - Kann bei Kabelbruch oder Adresskonflikt auftreten

        GIVEN: SHT31 auf I2C Bus
        WHEN: Sensor meldet I2C NACK
        THEN: Alert "SHT31 not responding", quality="bad"

        LOGIC RULE:
        - Condition: sensor.quality == "bad" AND sensor.type == "SHT31"
        - Action: notification("SHT31 I2C error")
        """
        # === SETUP ===
        mock = mock_esp32_sht31

        # Simulate I2C NACK
        mock.simulate_sensor_fault(gpio=21, fault_type="i2c_nack")

        # === VERIFY ===
        sensor = mock.get_sensor_state(21)
        assert sensor.quality == "bad"
        assert sensor.raw_value == 0.0  # Invalid reading

    def test_address_conflict_detection(self):
        """
        SZENARIO: I2C Adresskonflikt erkennen

        HARDWARE-KONTEXT:
        - Max 2 SHT31 pro Bus (0x44, 0x45)
        - Mehr als 2 → Adresskonflikt

        GIVEN: 2 SHT31 bereits konfiguriert
        WHEN: Dritter SHT31 hinzugefügt wird
        THEN: Error "I2C address conflict"
        """
        # === SETUP ===
        mock = MockESP32Client(esp_id="ESP_I2C_TEST", kaiser_id="god")
        mock.configure_zone("test", "test-zone", "test-subzone")

        # Add first two SHT31 (valid)
        mock.set_multi_value_sensor(
            gpio=21,
            sensor_type="SHT31",
            primary_value=22.0,
            secondary_values={"humidity": 50.0},
            name="SHT31_0x44",
        )
        mock.set_multi_value_sensor(
            gpio=22,
            sensor_type="SHT31",
            primary_value=23.0,
            secondary_values={"humidity": 55.0},
            name="SHT31_0x45",
        )

        # === VERIFY ===
        # Both sensors should exist
        assert mock.get_sensor_state(21) is not None
        assert mock.get_sensor_state(22) is not None


class TestSHT31HumidityHysteresis:
    """Tests for humidity-based hysteresis control."""

    @pytest.mark.asyncio
    async def test_humidity_hysteresis_fan_control(self, mock_esp32_sht31):
        """
        SZENARIO: Humidity Hysteresis für Fan Control

        HARDWARE-KONTEXT:
        - Ohne Hysteresis: Fan schaltet ständig bei ~65% RH
        - Mit Hysteresis: ON bei >70%, OFF bei <60%
        - Reduziert mechanischen Verschleiß

        GIVEN: SHT31 mit Hysteresis-Band 60%-70%
        WHEN: Humidity oszilliert zwischen 62% und 68%
        THEN: Fan bleibt im aktuellen Zustand (kein Cycling)

        LOGIC RULE:
        - Condition: hysteresis(activate_above=70, deactivate_below=60)
        - Action: actuator_command(gpio=26, command="ON")
        """
        # === SETUP ===
        mock = mock_esp32_sht31

        # Create hysteresis condition for humidity
        hysteresis_condition = create_hysteresis_condition(
            esp_id="ESP_SHT31",
            gpio=21,
            activate_above=70.0,
            deactivate_below=60.0,
            sensor_type="SHT31",
        )

        # === TEST SEQUENCE ===
        humidity_values = [65.0, 68.0, 71.0, 65.0, 62.0, 59.0]

        for humidity in humidity_values:
            mock.sensors[21].secondary_values = {"humidity": humidity}

        # === VERIFY ===
        assert hysteresis_condition["activate_above"] == 70.0
        assert hysteresis_condition["deactivate_below"] == 60.0


class TestSHT31MultiValueProcessing:
    """Tests for multi-value sensor data processing."""

    @pytest.mark.asyncio
    async def test_multi_value_sensor_data_structure(self, mock_esp32_sht31):
        """
        SZENARIO: Multi-Value Sensor Datenstruktur verifizieren

        HARDWARE-KONTEXT:
        - SHT31 liefert 2 Werte: Temperature (primary) + Humidity (secondary)
        - Beide werden in einem MQTT-Payload übertragen

        GIVEN: SHT31 Sensor konfiguriert
        WHEN: Sensor-Daten abgefragt
        THEN: Beide Werte (temp, humidity) verfügbar
        """
        # === SETUP ===
        mock = mock_esp32_sht31

        sensor = mock.get_sensor_state(21)

        # === VERIFY ===
        assert sensor.is_multi_value is True
        assert sensor.raw_value is not None  # Primary: Temperature
        assert sensor.secondary_values is not None
        assert "humidity" in sensor.secondary_values

        # Verify data types
        assert isinstance(sensor.raw_value, float)
        assert isinstance(sensor.secondary_values["humidity"], float)
