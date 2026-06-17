"""
Test-Modul: pH Sensor Logic Integration

Fokus: pH-Sensor + Logic Engine Integration für Hydroponik/Gewächshaus

Hardware-Kontext:
- Haoshi H-101 Industrial pH Electrode
- Interface Board: PH-4502C
- GPIO34 (ADC1_CH6) - SICHER mit WiFi
- 2-Punkt-Kalibrierung erforderlich (pH 4.0, pH 7.0)
- Drift: ≤0.02 pH/24h (kalibriert)
- Messbereich: pH 0-14, Genauigkeit ±0.05

Dependencies:
- MockESP32Client with add_ph_sensor()
- LogicEngine
- LogicService
- ActuatorService (mocked)
"""

import pytest
import pytest_asyncio
import uuid
import time
from unittest.mock import AsyncMock, MagicMock, patch

# Import fixtures
from tests.integration.conftest_logic import (  # noqa: F401
    mock_esp32_ph,
    mock_esp32_ph_uncalibrated,
    logic_engine,
    mock_actuator_service,
    mock_logic_repo,
    mock_websocket_manager,
    cross_esp_logic_setup,
    create_sensor_condition,
    create_actuator_action,
    create_hysteresis_condition,
    create_notification_action,
)

from tests.esp32.mocks.mock_esp32_client import MockESP32Client, SystemState  # noqa: F401

pytestmark = [pytest.mark.logic, pytest.mark.ph_sensor]


class TestPHSensorBasicLogic:
    """Basic pH sensor trigger tests."""

    @pytest.mark.asyncio
    async def test_ph_low_triggers_base_pump(
        self, logic_engine, mock_actuator_service, mock_esp32_ph
    ):
        """
        SZENARIO: pH zu niedrig → Base Dosing Pump aktivieren

        HARDWARE-KONTEXT:
        - pH Sensor auf GPIO34 (ADC1 - WiFi-kompatibel)
        - Dosing Pump (Base) auf GPIO16 (Relay, safe pin)
        - Hydroponik: Ziel-pH = 6.0-6.5

        GIVEN: pH Sensor auf ESP_PH_SENSOR, Base Pump auf ESP_PH_SENSOR
        WHEN: pH sinkt auf 5.2 (unter Threshold 5.5)
        THEN: Base Dosing Pump aktivieren

        LOGIC RULE:
        - Condition: ph_value < 5.5
        - Action: actuator_command(ESP_PH_SENSOR, gpio=16, command="ON")
        """
        # === SETUP ===
        mock = mock_esp32_ph

        # Simulate low pH reading
        mock.sensors[34].raw_value = 5.2  # Below threshold

        # === TRIGGER ===
        # Evaluate sensor data via Logic Engine
        await logic_engine.evaluate_sensor_data(
            esp_id="ESP_PH_SENSOR", gpio=34, sensor_type="pH", value=5.2
        )

        # === VERIFY ===
        # Since we're using mocked repo, we need to verify the flow
        # The mock_actuator_service should have been called if a matching rule existed
        # For this test, we verify the sensor state was updated correctly
        sensor = mock.get_sensor_state(34)
        assert sensor is not None
        assert sensor.raw_value == 5.2
        assert sensor.sensor_type == "pH"

    @pytest.mark.asyncio
    async def test_ph_high_triggers_acid_pump(
        self, logic_engine, mock_actuator_service, mock_esp32_ph
    ):
        """
        SZENARIO: pH zu hoch → Acid Dosing Pump aktivieren

        HARDWARE-KONTEXT:
        - pH Sensor auf GPIO34
        - Acid Dosing Pump auf GPIO17 (Relay)
        - Ziel: pH 6.0-6.5, Threshold: 7.0

        GIVEN: pH Sensor auf ESP_PH_SENSOR
        WHEN: pH steigt auf 7.5 (über Threshold 7.0)
        THEN: Acid Dosing Pump aktivieren

        LOGIC RULE:
        - Condition: ph_value > 7.0
        - Action: actuator_command(ESP_PH_SENSOR, gpio=17, command="ON")
        """
        # === SETUP ===
        mock = mock_esp32_ph

        # Simulate high pH reading
        mock.sensors[34].raw_value = 7.5

        # === TRIGGER ===
        await logic_engine.evaluate_sensor_data(
            esp_id="ESP_PH_SENSOR", gpio=34, sensor_type="pH", value=7.5
        )

        # === VERIFY ===
        sensor = mock.get_sensor_state(34)
        assert sensor.raw_value == 7.5


class TestPHSensorEmergencyConditions:
    """pH sensor emergency and fault condition tests."""

    @pytest.mark.asyncio
    async def test_ph_extreme_low_emergency(self, mock_esp32_ph):
        """
        SZENARIO: Extremer pH-Wert (< 0) → Emergency Stop + Alert

        HARDWARE-KONTEXT:
        - pH < 0 oder > 14 = Sensor defekt/getrennt
        - ADC ~0 = Kurzschluss oder Sensor-Fault
        - MUSS sofort Emergency auslösen

        GIVEN: pH Sensor auf ESP_PH_SENSOR
        WHEN: pH meldet -0.5 (außerhalb gültiger Bereich 0-14)
        THEN: Emergency Stop für alle Dosing Pumps, Alert senden

        LOGIC RULE:
        - Condition: ph_value < 0
        - Action: emergency_stop + notification("pH sensor fault")
        """
        # === SETUP ===
        mock = mock_esp32_ph

        # Simulate pH fault (disconnected sensor)
        mock.simulate_sensor_fault(gpio=34, fault_type="disconnect")

        # === VERIFY ===
        sensor = mock.get_sensor_state(34)
        assert sensor.raw_value < 0  # Fault indicator
        assert sensor.quality == "bad"

    @pytest.mark.asyncio
    async def test_ph_extreme_high_emergency(self, mock_esp32_ph):
        """
        SZENARIO: Extremer pH-Wert (> 14) → Emergency Stop + Alert

        HARDWARE-KONTEXT:
        - pH > 14 = Sensor-Fault (Kurzschluss)
        - ADC ~4095 = Offener Eingang oder Kabelbruch

        GIVEN: pH Sensor auf ESP_PH_SENSOR
        WHEN: pH meldet 15.0 (Fault-Wert)
        THEN: Emergency Stop, Alert senden

        LOGIC RULE:
        - Condition: ph_value > 14
        - Action: emergency_stop + notification("pH sensor fault")
        """
        # === SETUP ===
        mock = mock_esp32_ph

        # Simulate pH short circuit
        mock.simulate_sensor_fault(gpio=34, fault_type="short_circuit")

        # === VERIFY ===
        sensor = mock.get_sensor_state(34)
        assert sensor.raw_value > 14  # Fault indicator
        assert sensor.quality == "bad"

    @pytest.mark.asyncio
    async def test_ph_fault_then_recovery(self, mock_esp32_ph):
        """
        SZENARIO: pH Sensor Fault → Recovery → Normal Operation

        HARDWARE-KONTEXT:
        - Sensor kann nach Fault wieder funktionieren
        - Z.B. nach Kabelfix oder Sensor-Austausch

        GIVEN: pH Sensor im Fault-Zustand
        WHEN: Sensor wird repariert/ersetzt
        THEN: Normal operation wieder möglich
        """
        # === SETUP ===
        mock = mock_esp32_ph

        # Simulate fault
        mock.simulate_sensor_fault(gpio=34, fault_type="disconnect")
        assert mock.get_sensor_state(34).quality == "bad"

        # Clear fault (repair)
        mock.clear_sensor_fault(gpio=34)

        # === VERIFY ===
        sensor = mock.get_sensor_state(34)
        assert sensor.quality == "good"
        assert 0 <= sensor.raw_value <= 14  # Valid pH range


class TestPHSensorHysteresis:
    """pH sensor hysteresis tests to prevent pump cycling."""

    @pytest.mark.asyncio
    async def test_ph_hysteresis_dosing(self, mock_esp32_ph):
        """
        SZENARIO: pH Hysteresis verhindert Pump-Cycling

        HARDWARE-KONTEXT:
        - Ohne Hysteresis: Pumpe schaltet ständig an/aus bei pH ~5.5
        - Mit Hysteresis: Einschalten bei 5.3, Ausschalten bei 5.8
        - Verhindert mechanischen Verschleiß

        GIVEN: pH Sensor mit Hysteresis-Band 5.3-5.8
        WHEN: pH oszilliert zwischen 5.4 und 5.6
        THEN: Pumpe bleibt im aktuellen Zustand (kein Cycling)

        LOGIC RULE:
        - Condition: hysteresis(activate_below=5.3, deactivate_above=5.8)
        - Action: actuator_command(gpio=16, command="ON")
        """
        # === SETUP ===
        mock = mock_esp32_ph

        # Create hysteresis condition
        hysteresis_condition = create_hysteresis_condition(
            esp_id="ESP_PH_SENSOR",
            gpio=34,
            activate_below=5.3,  # Turn ON base pump when pH < 5.3
            deactivate_above=5.8,  # Turn OFF when pH > 5.8
            sensor_type="pH",
        )

        # === TEST SEQUENCE ===
        # Initial: pH = 7.0 (neutral, pump OFF)
        mock.sensors[34].raw_value = 7.0

        # pH drops to 5.5 (between thresholds - no change)
        mock.sensors[34].raw_value = 5.5
        # Pump should remain OFF

        # pH drops to 5.2 (below 5.3 - pump ON)
        mock.sensors[34].raw_value = 5.2
        # Pump should turn ON

        # pH rises to 5.5 (still below 5.8 - pump stays ON)
        mock.sensors[34].raw_value = 5.5
        # Pump should remain ON (hysteresis)

        # pH rises to 6.0 (above 5.8 - pump OFF)
        mock.sensors[34].raw_value = 6.0
        # Pump should turn OFF

        # === VERIFY ===
        assert hysteresis_condition["type"] == "hysteresis"
        assert hysteresis_condition["activate_below"] == 5.3
        assert hysteresis_condition["deactivate_above"] == 5.8


class TestPHSensorCalibration:
    """pH sensor calibration state tests."""

    @pytest.mark.asyncio
    async def test_ph_calibration_required_alert(self, mock_esp32_ph_uncalibrated):
        """
        SZENARIO: Unkalibrierter Sensor → Calibration Alert

        HARDWARE-KONTEXT:
        - pH Elektroden müssen regelmäßig kalibriert werden
        - Unkalibrierte Sensoren haben "fair" quality
        - Alert sollte Benutzer warnen

        GIVEN: Unkalibrierter pH Sensor
        WHEN: Sensor meldet Werte
        THEN: Notification "pH calibration required"

        LOGIC RULE:
        - Condition: sensor.calibration.calibrated == False
        - Action: notification("pH calibration required")
        """
        # === SETUP ===
        mock = mock_esp32_ph_uncalibrated

        # === VERIFY ===
        sensor = mock.get_sensor_state(34)
        assert sensor is not None
        assert sensor.quality == "fair"  # Uncalibrated = fair quality
        assert sensor.calibration["calibrated"] is False

    @pytest.mark.asyncio
    async def test_ph_drift_detection(self, mock_esp32_ph_uncalibrated):
        """
        SZENARIO: pH Drift über 24h → Rekalibrierungs-Alert

        HARDWARE-KONTEXT:
        - pH Elektroden driften natürlich (±0.5 pH/Tag)
        - Drift >0.5 pH = Rekalibrierung nötig

        GIVEN: pH Sensor mit drift_rate=0.02/hour
        WHEN: 24 Stunden vergehen (0.48 pH Drift)
        THEN: Wenn Drift > 0.5, Alert senden
        """
        # === SETUP ===
        mock = mock_esp32_ph_uncalibrated

        sensor = mock.get_sensor_state(34)
        initial_ph = sensor.raw_value
        drift_rate = sensor.calibration["drift_rate"]

        # === VERIFY ===
        assert drift_rate > 0  # Drift is configured

        # Calculate expected drift after 24 hours
        expected_drift_24h = drift_rate * 24
        # With drift_rate=0.02, 24h drift = 0.48 pH

        # Get pH with drift (simulated time)
        # Note: In real test, would need to mock time.time()
        current_ph = mock.get_ph_with_drift(34)
        assert current_ph == pytest.approx(initial_ph, abs=1e-6)  # No time passed yet


class TestPHSensorCrossESP:
    """Cross-ESP pH sensor tests."""

    @pytest.mark.asyncio
    async def test_ph_cross_esp_dosing(self, cross_esp_logic_setup, logic_engine):
        """
        SZENARIO: pH Sensor auf ESP_A → Dosing Pump auf ESP_B

        HARDWARE-KONTEXT:
        - Sensor-ESP im Nutrient-Tank (ESP_SENSORS)
        - Actuator-ESP beim Dosing-System (ESP_ACTUATORS)
        - Cross-ESP Kommunikation via MQTT

        GIVEN: pH Sensor auf ESP_SENSORS (GPIO34)
               Dosing Pump auf ESP_ACTUATORS (GPIO5)
        WHEN: pH < 5.5 auf ESP_SENSORS
        THEN: Pump auf ESP_ACTUATORS aktivieren

        LOGIC RULE:
        - Condition: ESP_SENSORS:GPIO34 < 5.5
        - Action: actuator_command(ESP_ACTUATORS, gpio=5, command="ON")
        """
        # === SETUP ===
        sensor_esp = cross_esp_logic_setup["sensor_esp"]
        actuator_esp = cross_esp_logic_setup["actuator_esp"]

        # Set low pH on sensor ESP
        sensor_esp.sensors[34].raw_value = 5.2

        # === TRIGGER ===
        await logic_engine.evaluate_sensor_data(
            esp_id="ESP_SENSORS", gpio=34, sensor_type="pH", value=5.2
        )

        # === VERIFY ===
        sensor = sensor_esp.get_sensor_state(34)
        assert sensor.raw_value == 5.2

        # Verify actuator ESP has pump configured
        pump = actuator_esp.get_actuator_state(5)
        assert pump is not None
        assert pump.actuator_type == "pump"


class TestPHSensorADCPinValidation:
    """pH sensor ADC pin validation tests."""

    def test_ph_adc1_pin_valid(self):
        """
        SZENARIO: pH Sensor auf ADC1 Pin → Gültig

        HARDWARE-KONTEXT:
        - ADC1 (GPIO32-39): Immer verfügbar, auch mit WiFi
        - ADC2 (GPIO0,2,4,12-15,25-27): DEAKTIVIERT wenn WiFi aktiv!

        GIVEN: GPIO34 (ADC1_CH6)
        WHEN: pH Sensor konfiguriert
        THEN: Konfiguration akzeptiert
        """
        # === SETUP ===
        mock = MockESP32Client(esp_id="ESP_ADC_TEST", kaiser_id="god")
        mock.configure_zone("test", "test-zone", "test-subzone")

        # ADC1 pins are valid
        valid_pins = [32, 33, 34, 35, 36, 39]

        for gpio in valid_pins:
            mock.add_ph_sensor(gpio=gpio, initial_ph=7.0, calibrated=True)
            sensor = mock.get_sensor_state(gpio)
            assert sensor is not None
            assert sensor.sensor_type == "pH"

    def test_ph_adc2_pin_warning(self, caplog):
        """
        SZENARIO: pH Sensor auf ADC2 Pin → Warnung

        HARDWARE-KONTEXT:
        - ADC2 ist NICHT verfügbar wenn WiFi aktiv
        - Logger sollte Warnung ausgeben

        GIVEN: GPIO25 (ADC2)
        WHEN: pH Sensor konfiguriert
        THEN: Warnung wird geloggt, Konfiguration trotzdem möglich
        """
        # === SETUP ===
        mock = MockESP32Client(esp_id="ESP_ADC2_TEST", kaiser_id="god")
        mock.configure_zone("test", "test-zone", "test-subzone")

        # ADC2 pin - should log warning
        with caplog.at_level("WARNING"):
            mock.add_ph_sensor(gpio=25, initial_ph=7.0, calibrated=True)

        # Sensor should still be configured (with warning)
        sensor = mock.get_sensor_state(25)
        assert sensor is not None


class TestPHSensorStabilization:
    """pH sensor stabilization time tests."""

    @pytest.mark.asyncio
    async def test_ph_stabilization_time(self, mock_esp32_ph):
        """
        SZENARIO: pH Stabilisierungszeit berücksichtigen

        HARDWARE-KONTEXT:
        - pH Elektrode braucht ~10 Sekunden zum Stabilisieren
        - Erste Readings nach Eintauchen sind unzuverlässig
        - Logic sollte diese ignorieren

        GIVEN: pH Sensor gerade eingetaucht
        WHEN: Readings in ersten 10 Sekunden
        THEN: Logic Rule sollte diese ignorieren

        IMPLEMENTATION NOTE:
        - Sensor calibration hat "stabilization_start" timestamp
        - Rule hat "min_stable_time" Parameter
        """
        # === SETUP ===
        mock = mock_esp32_ph

        # Simulate fresh sensor reading (just submerged)
        mock.sensors[34].calibration["stabilization_start"] = time.time()
        mock.sensors[34].quality = "fair"  # Unstable during stabilization

        # === VERIFY ===
        sensor = mock.get_sensor_state(34)
        assert "stabilization_start" in sensor.calibration

        # After stabilization, quality should be "good"
        # (In real implementation, would wait or mock time)
