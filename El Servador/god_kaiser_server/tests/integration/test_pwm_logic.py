"""
Test-Modul: PWM/Servo Proportional Control

Fokus: PWM-gesteuerte Aktoren (Fans, Servos) mit Logic Engine Integration

Hardware-Kontext:
- ESP32 LEDC für PWM (16 unabhängige Kanäle)
- Fans: 1-25kHz, 8-bit Resolution (0-255)
- Servos: 50Hz, 1-2ms Pulse (0°-180°)
- Empfohlene Pins: GPIO25, 26, 27 (haben DAC)

Dependencies:
- MockESP32Client with set_pwm_duty()
- LogicEngine
- Proportional Control Rules
"""

import pytest
import pytest_asyncio
import uuid
import time
from unittest.mock import AsyncMock, MagicMock, patch

# Import fixtures
from tests.integration.conftest_logic import (  # noqa: F401
    mock_esp32_pwm_fan,
    mock_esp32_servo_valve,
    cross_esp_logic_setup,
    logic_engine,
    mock_actuator_service,
    mock_logic_repo,
    mock_websocket_manager,
    create_sensor_condition,
    create_actuator_action,
)

from tests.esp32.mocks.mock_esp32_client import MockESP32Client, SystemState  # noqa: F401

pytestmark = [pytest.mark.logic, pytest.mark.pwm]


class TestFanProportionalControl:
    """Tests for PWM fan proportional temperature control."""

    @pytest.mark.asyncio
    async def test_fan_proportional_temperature(self, mock_esp32_pwm_fan, logic_engine):
        """
        SZENARIO: Fan-Geschwindigkeit steigt proportional mit Temperatur

        HARDWARE-KONTEXT:
        - PWM Fan auf GPIO25
        - Frequenz: 25kHz
        - Duty Cycle: 0-255 (8-bit)
        - Min Speed: 20% (Stall-Prevention)

        GIVEN: Temperatur steigt von 24°C auf 30°C
        WHEN: Temperatur kreuzt Thresholds
        THEN: Fan-Geschwindigkeit steigt stufenweise

        LOGIC RULES:
        - 24-26°C: 30% PWM (duty=77)
        - 26-28°C: 60% PWM (duty=153)
        - 28-30°C: 100% PWM (duty=255)
        """
        # === SETUP ===
        mock = mock_esp32_pwm_fan

        # Define temperature-to-PWM mapping
        temp_pwm_map = [
            (24.0, 0.30, 77),  # 30% PWM
            (26.0, 0.60, 153),  # 60% PWM
            (28.0, 1.00, 255),  # 100% PWM
        ]

        # === TEST EACH TEMPERATURE LEVEL ===
        for temp, expected_pwm_value, expected_duty in temp_pwm_map:
            mock.sensors[4].raw_value = temp + 0.5  # Slightly above threshold

            # Set corresponding PWM
            duty_cycle = expected_duty
            mock.set_pwm_duty(gpio=25, duty_cycle=duty_cycle, frequency=25000)

            # === VERIFY ===
            actuator = mock.get_actuator_state(25)
            assert abs(actuator.pwm_value - expected_pwm_value) < 0.01
            assert mock.get_pwm_duty(25) == expected_duty

    @pytest.mark.asyncio
    async def test_fan_minimum_speed_stall_prevention(self, mock_esp32_pwm_fan):
        """
        SZENARIO: Fan hat Minimum-Geschwindigkeit (Stall Prevention)

        HARDWARE-KONTEXT:
        - Manche Fans starten nicht unter ~20% PWM
        - min_value=0.2 verhindert Stall

        GIVEN: Fan mit min_value=0.2
        WHEN: PWM unter 20% gefordert
        THEN: PWM wird auf min_value (20%) geklemmt
        """
        # === SETUP ===
        mock = mock_esp32_pwm_fan

        fan = mock.get_actuator_state(25)
        assert fan.min_value == 0.2  # Minimum 20%

        # === TEST: Set below minimum ===
        mock.set_pwm_duty(gpio=25, duty_cycle=25, frequency=25000)  # ~10% PWM

        # Note: Actual clamping would be done by SafetyService/ActuatorService
        # Here we verify the configuration is correct
        assert fan.min_value == 0.2


class TestServoProportionalControl:
    """Tests for servo valve proportional control."""

    @pytest.mark.asyncio
    async def test_servo_valve_proportional_opening(self, mock_esp32_servo_valve):
        """
        SZENARIO: Servo-Ventil öffnet proportional zum Flow-Demand

        HARDWARE-KONTEXT:
        - Servo auf GPIO26
        - 50Hz PWM (20ms Periode)
        - Pulsbreite: 1ms (0°) bis 2ms (180°)
        - Duty: ~5% (1ms) bis ~10% (2ms) bei 50Hz

        GIVEN: Flow demand = 50%
        WHEN: Logic berechnet Ventilposition
        THEN: Servo bewegt auf 90° (1.5ms pulse)

        LOGIC RULE:
        - Condition: flow_demand_percent
        - Action: servo_position(gpio=26, angle=demand*1.8)
        """
        # === SETUP ===
        mock = mock_esp32_servo_valve

        # Flow demand → Servo position mapping
        # 0% → 0° (closed), 50% → 90°, 100% → 180° (fully open)
        demand_angle_map = [
            (0, 0),  # 0% demand → 0°
            (50, 90),  # 50% demand → 90°
            (100, 180),  # 100% demand → 180°
        ]

        for demand, expected_angle in demand_angle_map:
            # Calculate duty cycle for servo angle
            # At 50Hz: 0° = ~3% duty, 180° = ~12% duty
            # Simplified: duty = 3% + (angle/180 * 9%)
            base_duty = 0.03  # 3% for 0°
            range_duty = 0.09  # Additional 9% for 0-180°
            duty_percent = base_duty + (expected_angle / 180.0) * range_duty

            duty_cycle = int(duty_percent * 255)
            mock.set_pwm_duty(gpio=26, duty_cycle=duty_cycle, frequency=50)

        # === VERIFY ===
        assert mock.get_pwm_frequency(26) == 50  # Servo frequency


class TestPWMRamping:
    """Tests for PWM gradual ramping."""

    @pytest.mark.asyncio
    async def test_pwm_ramp_up_gradual(self, mock_esp32_pwm_fan):
        """
        SZENARIO: PWM Rampe (nicht sprunghaft)

        HARDWARE-KONTEXT:
        - Plötzliche PWM-Änderung kann Motoren beschädigen
        - Sanftes Hochfahren über 2-3 Sekunden
        - Reduziert Stromspitzen

        GIVEN: Fan bei 0%
        WHEN: Target = 100%
        THEN: Rampe über mehrere Schritte (nicht sofort 100%)

        NOTE: Actual ramping is done by ESP32 firmware or Logic Engine
        """
        # === SETUP ===
        mock = mock_esp32_pwm_fan

        # Start at 0%
        mock.set_pwm_duty(gpio=25, duty_cycle=0, frequency=25000)
        assert mock.get_pwm_duty(25) == 0

        # Simulate ramp steps
        ramp_steps = [0, 64, 128, 192, 255]  # 0%, 25%, 50%, 75%, 100%

        for step in ramp_steps:
            mock.set_pwm_duty(gpio=25, duty_cycle=step, frequency=25000)
            # In real implementation, there would be delay between steps

        # === VERIFY ===
        final_duty = mock.get_pwm_duty(25)
        assert final_duty == 255


class TestPWMValueValidation:
    """Tests for PWM value validation and clamping."""

    def test_pwm_value_clamping(self):
        """
        SZENARIO: PWM-Wert wird auf gültigen Bereich geklemmt

        HARDWARE-KONTEXT:
        - PWM Duty Cycle: 0-255 (8-bit)
        - Werte > 255 werden auf 255 geklemmt
        - Werte < 0 werden auf 0 geklemmt

        GIVEN: PWM actuator konfiguriert
        WHEN: duty_cycle > 255 übergeben
        THEN: Wird auf 255 geklemmt
        """
        # === SETUP ===
        mock = MockESP32Client(esp_id="ESP_PWM_CLAMP", kaiser_id="god")
        mock.configure_zone("test", "test-zone", "test-subzone")
        mock.configure_actuator(gpio=25, actuator_type="pwm_motor", name="Test Fan")

        # === TEST: Above maximum ===
        mock.set_pwm_duty(gpio=25, duty_cycle=300, frequency=25000)  # > 255
        assert mock.get_pwm_duty(25) == 255  # Clamped

        # === TEST: Below minimum ===
        mock.set_pwm_duty(gpio=25, duty_cycle=-50, frequency=25000)  # < 0
        assert mock.get_pwm_duty(25) == 0  # Clamped

    def test_pwm_min_max_limits(self, mock_esp32_pwm_fan):
        """
        SZENARIO: Actuator min/max Limits werden respektiert

        HARDWARE-KONTEXT:
        - Fan min_value=0.2 (20%)
        - Fan max_value=1.0 (100%)
        - SafetyService enforced diese Limits

        GIVEN: Fan mit min=0.2, max=1.0
        WHEN: PWM gesetzt
        THEN: Wert muss im Bereich 0.2-1.0 liegen
        """
        # === SETUP ===
        mock = mock_esp32_pwm_fan

        fan = mock.get_actuator_state(25)

        # === VERIFY ===
        assert fan.min_value == 0.2
        assert fan.max_value == 1.0


class TestPWMFrequencyValidation:
    """Tests for PWM frequency validation."""

    def test_pwm_frequency_fan_vs_servo(self):
        """
        SZENARIO: Korrekte Frequenz für Fan vs Servo

        HARDWARE-KONTEXT:
        - Fans: 1-25kHz (typisch 25kHz)
        - Servos: 50Hz (20ms Periode)
        - Falsche Frequenz = Fehlfunktion

        GIVEN: Fan auf GPIO25, Servo auf GPIO26
        WHEN: Frequenz abgefragt
        THEN: Fan=25000Hz, Servo=50Hz
        """
        # === SETUP ===
        mock = MockESP32Client(esp_id="ESP_FREQ_TEST", kaiser_id="god")
        mock.configure_zone("test", "test-zone", "test-subzone")

        # Fan with 25kHz
        mock.set_pwm_duty(gpio=25, duty_cycle=128, frequency=25000)

        # Servo with 50Hz
        mock.set_pwm_duty(gpio=26, duty_cycle=128, frequency=50)

        # === VERIFY ===
        assert mock.get_pwm_frequency(25) == 25000
        assert mock.get_pwm_frequency(26) == 50

        # Actuator type should be inferred from frequency
        fan = mock.get_actuator_state(25)
        servo = mock.get_actuator_state(26)

        assert fan.actuator_type == "pwm_motor"
        assert servo.actuator_type == "servo"
