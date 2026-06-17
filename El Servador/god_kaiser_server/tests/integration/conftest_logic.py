"""
Logic Engine Integration Test Fixtures.

Provides pre-configured setups for Logic Engine testing with
hardware-realistic sensor and actuator configurations.

Usage:
    # Import in test file
    from tests.integration.conftest_logic import *

    # Or import specific fixtures
    from tests.integration.conftest_logic import mock_esp32_ph, logic_test_setup
"""

import pytest
import pytest_asyncio
from typing import Dict, Any, Optional
from unittest.mock import AsyncMock

# MockESP32Client imports
import sys
from pathlib import Path

# Ensure project root is in path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from tests.esp32.mocks.mock_esp32_client import (  # noqa: F401, E402
    MockESP32Client,
    BrokerMode,
    SystemState,
    ActuatorState,
    SensorState,
)

# Logic Engine imports
from src.services.actuator_service import ActuatorSendCommandResult  # noqa: E402
from src.services.logic_engine import LogicEngine  # noqa: E402
from src.services.logic_service import LogicService  # noqa: E402
from src.db.repositories.logic_repo import LogicRepository  # noqa: E402

_MOCK_ACTUATOR_SEND_OK = ActuatorSendCommandResult(
    success=True,
    correlation_id="00000000-0000-4000-8000-000000000001",
    command_sent=True,
    safety_warnings=[],
)


# =============================================================================
# Pytest Markers for Logic Engine Tests
# =============================================================================
def pytest_configure(config):
    """Register custom markers for Logic Engine tests."""
    config.addinivalue_line("markers", "logic: Logic Engine tests")
    config.addinivalue_line("markers", "ph_sensor: pH sensor tests")
    config.addinivalue_line("markers", "ds18b20: DS18B20 temperature sensor tests")
    config.addinivalue_line("markers", "sht31: SHT31 humidity/temperature tests")
    config.addinivalue_line("markers", "relay: Relay interlock tests")
    config.addinivalue_line("markers", "pwm: PWM proportional control tests")
    config.addinivalue_line("markers", "cross_esp: Cross-ESP communication tests")
    config.addinivalue_line("markers", "safety: Safety validation tests")
    config.addinivalue_line("markers", "hysteresis: Hysteresis condition tests")
    config.addinivalue_line("markers", "sequence: Sequence action tests")
    config.addinivalue_line("markers", "e2e: End-to-end tests (requires server)")
    config.addinivalue_line("markers", "requires_server: Tests requiring running server")


# =============================================================================
# Logic Engine Core Fixtures
# =============================================================================
@pytest.fixture
async def mock_actuator_service():
    """Create a mock ActuatorService for testing."""
    service = AsyncMock()
    service.send_command = AsyncMock(return_value=_MOCK_ACTUATOR_SEND_OK)
    service.get_state = AsyncMock(return_value={"state": False, "pwm_value": 0.0})
    service.emergency_stop = AsyncMock(return_value=True)
    return service


@pytest.fixture
async def mock_logic_repo():
    """Create a mock LogicRepository for testing."""
    repo = AsyncMock()
    repo.get_enabled_rules = AsyncMock(return_value=[])
    repo.get_rules_by_trigger_sensor = AsyncMock(return_value=[])
    repo.get_last_execution = AsyncMock(return_value=None)
    repo.log_execution = AsyncMock()
    repo.get_execution_history = AsyncMock(return_value=[])
    repo.get_execution_count = AsyncMock(return_value=0)
    return repo


@pytest.fixture
async def mock_websocket_manager():
    """Create a mock WebSocketManager for testing."""
    manager = AsyncMock()
    manager.broadcast = AsyncMock()
    return manager


@pytest.fixture
async def logic_engine(mock_logic_repo, mock_actuator_service, mock_websocket_manager):
    """Create LogicEngine instance with mocked dependencies."""
    engine = LogicEngine(
        logic_repo=mock_logic_repo,
        actuator_service=mock_actuator_service,
        websocket_manager=mock_websocket_manager,
    )
    return engine


@pytest_asyncio.fixture
async def logic_test_setup(db_session, mock_actuator_service, mock_websocket_manager):
    """
    Complete Logic Engine test setup with real DB session.

    Returns dict with:
        - engine: LogicEngine instance
        - service: LogicService for CRUD
        - repo: LogicRepository for direct DB access
        - actuator_service: Mocked ActuatorService
        - websocket_manager: Mocked WebSocketManager
        - session: DB session
    """
    logic_repo = LogicRepository(db_session)

    logic_engine = LogicEngine(
        logic_repo=logic_repo,
        actuator_service=mock_actuator_service,
        websocket_manager=mock_websocket_manager,
    )

    logic_service = LogicService(logic_repo)

    return {
        "engine": logic_engine,
        "service": logic_service,
        "repo": logic_repo,
        "actuator_service": mock_actuator_service,
        "websocket_manager": mock_websocket_manager,
        "session": db_session,
    }


# =============================================================================
# pH Sensor Fixtures
# =============================================================================
@pytest.fixture
def mock_esp32_ph():
    """
    ESP with pH sensor on GPIO34 (ADC1).

    Hardware Context:
    - Haoshi H-101 Industrial pH Electrode
    - PH-4502C Interface Board
    - GPIO34 (ADC1_CH6) - safe with WiFi
    - 2-point calibration (pH 4.0, pH 7.0)

    Actuators:
    - GPIO16: Base Dosing Pump (relay)
    - GPIO17: Acid Dosing Pump (relay)
    """
    mock = MockESP32Client(esp_id="ESP_PH_SENSOR", kaiser_id="god")
    mock.configure_zone("hydroponics", "main-greenhouse", "nutrient-tank")
    mock.add_ph_sensor(gpio=34, initial_ph=7.0, calibrated=True)
    mock.configure_actuator(gpio=16, actuator_type="pump", name="Base Dosing Pump")
    mock.configure_actuator(gpio=17, actuator_type="pump", name="Acid Dosing Pump")
    mock.clear_published_messages()
    yield mock
    mock.reset()


@pytest.fixture
def mock_esp32_ph_uncalibrated():
    """ESP with uncalibrated pH sensor for calibration tests."""
    mock = MockESP32Client(esp_id="ESP_PH_UNCAL", kaiser_id="god")
    mock.configure_zone("hydroponics", "main-greenhouse", "tank-2")
    mock.add_ph_sensor(gpio=34, initial_ph=7.0, calibrated=False, drift_rate=0.02)
    mock.clear_published_messages()
    yield mock
    mock.reset()


# =============================================================================
# DS18B20 Temperature Sensor Fixtures
# =============================================================================
@pytest.fixture
def mock_esp32_ds18b20_multi():
    """
    ESP with 3 DS18B20 sensors on OneWire bus (GPIO4).

    Hardware Context:
    - OneWire bus with 4.7kΩ pull-up
    - 3 sensors with unique ROM addresses
    - 12-bit resolution (750ms conversion time)

    Actuator:
    - GPIO25: Ventilation Fan (PWM)
    """
    mock = MockESP32Client(esp_id="ESP_TEMP_ARRAY", kaiser_id="god")
    mock.configure_zone("greenhouse", "main-greenhouse", "zone-a")
    mock.add_ds18b20_multi(
        gpio=4,
        count=3,
        initial_temps=[22.5, 23.0, 22.8],
        rom_addresses=["28-000000000001", "28-000000000002", "28-000000000003"],
    )
    mock.configure_actuator(gpio=25, actuator_type="fan", name="Ventilation Fan")
    mock.clear_published_messages()
    yield mock
    mock.reset()


@pytest.fixture
def mock_esp32_ds18b20_dual_bus():
    """
    ESP with DS18B20 sensors on two separate OneWire buses.

    Hardware Context:
    - GPIO4: Indoor temperature sensors (3 sensors)
    - GPIO16: Outdoor temperature sensor (1 sensor)
    """
    mock = MockESP32Client(esp_id="ESP_DUAL_BUS", kaiser_id="god")
    mock.configure_zone("greenhouse", "main-greenhouse", "monitoring")
    mock.add_ds18b20_multi(
        gpio=4,
        count=3,
        initial_temps=[22.5, 23.0, 22.8],
        rom_addresses=["28-000000000001", "28-000000000002", "28-000000000003"],
    )
    mock.add_ds18b20_multi(
        gpio=16, count=1, initial_temps=[18.0], rom_addresses=["28-OUTDOOR00001"]
    )
    mock.clear_published_messages()
    yield mock
    mock.reset()


# =============================================================================
# SHT31 Humidity/Temperature Sensor Fixtures
# =============================================================================
@pytest.fixture
def mock_esp32_sht31():
    """
    ESP with SHT31 I2C sensor (temp + humidity).

    Hardware Context:
    - I2C address 0x44 (ADR=LOW)
    - GPIO21 (SDA), GPIO22 (SCL)
    - Built-in heater for condensation
    """
    mock = MockESP32Client(esp_id="ESP_SHT31", kaiser_id="god")
    mock.configure_zone("greenhouse", "main-greenhouse", "zone-a")
    mock.set_multi_value_sensor(
        gpio=21,
        sensor_type="SHT31",
        primary_value=23.5,
        secondary_values={"humidity": 65.0},
        name="SHT31_0x44",
        quality="good",
    )
    # Add second SHT31 at address 0x45
    mock.set_multi_value_sensor(
        gpio=22,  # Different GPIO for tracking (actually same I2C bus)
        sensor_type="SHT31",
        primary_value=24.0,
        secondary_values={"humidity": 60.0},
        name="SHT31_0x45",
        quality="good",
    )
    mock.configure_actuator(gpio=26, actuator_type="fan", name="Zone Ventilation")
    mock.clear_published_messages()
    yield mock
    mock.reset()


@pytest.fixture
def mock_esp32_sht31_high_humidity():
    """ESP with SHT31 showing high humidity (>95%) for heater tests."""
    mock = MockESP32Client(esp_id="ESP_SHT31_WET", kaiser_id="god")
    mock.configure_zone("greenhouse", "main-greenhouse", "humid-zone")
    mock.set_multi_value_sensor(
        gpio=21,
        sensor_type="SHT31",
        primary_value=25.0,
        secondary_values={"humidity": 98.5},  # >95% triggers heater
        name="SHT31_Humid",
        quality="good",
    )
    mock.clear_published_messages()
    yield mock
    mock.reset()


# =============================================================================
# Relay Interlock Fixtures
# =============================================================================
@pytest.fixture
def mock_esp32_relay_interlock():
    """
    ESP with Pump/Valve relay interlock on safe pins.

    Hardware Context:
    - GPIO16: Main Pump (relay, active-low)
    - GPIO17: Main Valve (relay, active-low)
    - Interlock: Valve must open before pump starts
    - Safety timeout: 5 minutes (300000ms)
    """
    mock = MockESP32Client(esp_id="ESP_IRRIGATION", kaiser_id="god")
    mock.configure_zone("irrigation", "main-greenhouse", "zone-a")
    mock.configure_actuator(
        gpio=16, actuator_type="pump", name="Main Pump", safety_timeout_ms=300000
    )
    mock.configure_actuator(gpio=17, actuator_type="valve", name="Main Valve")
    # Set both as active-low relays
    mock.set_relay_state(gpio=16, state=False, trigger_type="active_low")
    mock.set_relay_state(gpio=17, state=False, trigger_type="active_low")
    mock.clear_published_messages()
    yield mock
    mock.reset()


@pytest.fixture
def mock_esp32_relay_strapping():
    """
    ESP with relays on strapping pins (for boot glitch testing).

    WARNING: This is intentionally BAD configuration for testing.
    Relays on strapping pins (GPIO0, 2, 12, 15) may glitch during boot.
    """
    mock = MockESP32Client(esp_id="ESP_BAD_RELAY", kaiser_id="god")
    mock.configure_zone("test", "test-zone", "test-subzone")
    # Intentionally configure on strapping pins
    mock.configure_actuator(gpio=2, actuator_type="relay", name="Bad Relay 1")
    mock.configure_actuator(gpio=15, actuator_type="relay", name="Bad Relay 2")
    # Also configure safe pins for comparison
    mock.configure_actuator(gpio=16, actuator_type="relay", name="Safe Relay")
    mock.clear_published_messages()
    yield mock
    mock.reset()


# =============================================================================
# PWM Actuator Fixtures
# =============================================================================
@pytest.fixture
def mock_esp32_pwm_fan():
    """
    ESP with PWM-controlled ventilation fan.

    Hardware Context:
    - GPIO25: PWM Fan (25kHz, 8-bit)
    - Temperature sensor for proportional control
    """
    mock = MockESP32Client(esp_id="ESP_FAN_CTRL", kaiser_id="god")
    mock.configure_zone("greenhouse", "main-greenhouse", "ventilation")
    mock.set_sensor_value(
        gpio=4, raw_value=22.0, sensor_type="DS18B20", name="Control Temp", unit="°C"
    )
    mock.configure_actuator(
        gpio=25,
        actuator_type="pwm_motor",
        name="Ventilation Fan",
        min_value=0.2,  # Minimum 20% to prevent stall
        max_value=1.0,
    )
    mock.set_pwm_duty(gpio=25, duty_cycle=0, frequency=25000)
    mock.clear_published_messages()
    yield mock
    mock.reset()


@pytest.fixture
def mock_esp32_servo_valve():
    """
    ESP with servo-controlled proportional valve.

    Hardware Context:
    - GPIO26: Servo (50Hz, 1-2ms pulse)
    - Position: 0° (closed) to 180° (fully open)
    """
    mock = MockESP32Client(esp_id="ESP_SERVO_VALVE", kaiser_id="god")
    mock.configure_zone("irrigation", "main-greenhouse", "zone-a")
    mock.configure_actuator(
        gpio=26, actuator_type="servo", name="Proportional Valve", min_value=0.0, max_value=1.0
    )
    mock.set_pwm_duty(gpio=26, duty_cycle=0, frequency=50)  # Servo at 50Hz
    mock.clear_published_messages()
    yield mock
    mock.reset()


# =============================================================================
# Cross-ESP Fixtures
# =============================================================================
@pytest.fixture
def cross_esp_logic_setup():
    """
    Two ESPs for cross-ESP Logic testing.

    ESP_SENSORS (Monitoring):
    - GPIO4: DS18B20 Temperature
    - GPIO21: SHT31 Temp+Humidity
    - GPIO34: pH Sensor

    ESP_ACTUATORS (Control):
    - GPIO5: Irrigation Pump
    - GPIO6: Irrigation Valve
    - GPIO25: Ventilation Fan (PWM)
    """
    sensor_esp = MockESP32Client(esp_id="ESP_SENSORS", kaiser_id="god")
    sensor_esp.configure_zone("sensors", "main-greenhouse", "monitoring")
    sensor_esp.set_sensor_value(gpio=4, raw_value=22.0, sensor_type="DS18B20", name="Air Temp")
    sensor_esp.set_multi_value_sensor(
        gpio=21,
        sensor_type="SHT31",
        primary_value=23.5,
        secondary_values={"humidity": 65.0},
        name="Temp/Humidity",
    )
    sensor_esp.add_ph_sensor(gpio=34, initial_ph=6.5, calibrated=True)

    actuator_esp = MockESP32Client(esp_id="ESP_ACTUATORS", kaiser_id="god")
    actuator_esp.configure_zone("actuators", "main-greenhouse", "control")
    actuator_esp.configure_actuator(gpio=5, actuator_type="pump", name="Irrigation Pump")
    actuator_esp.configure_actuator(gpio=6, actuator_type="valve", name="Irrigation Valve")
    actuator_esp.configure_actuator(
        gpio=25, actuator_type="pwm_motor", name="Ventilation", min_value=0.0, max_value=1.0
    )

    sensor_esp.clear_published_messages()
    actuator_esp.clear_published_messages()

    return {"sensor_esp": sensor_esp, "actuator_esp": actuator_esp}


@pytest.fixture
def multi_zone_esp_setup():
    """
    Four ESPs across two zones for multi-zone testing.

    Zone A:
    - ESP_ZA_SENS: Sensors (temp, humidity)
    - ESP_ZA_ACT: Actuators (pump, valve)

    Zone B:
    - ESP_ZB_SENS: Sensors (temp, humidity)
    - ESP_ZB_ACT: Actuators (pump, valve)
    """
    # Zone A - Sensors
    za_sens = MockESP32Client(esp_id="ESP_ZA_SENS", kaiser_id="god")
    za_sens.configure_zone("zone-a", "greenhouse-complex", "sensors-a")
    za_sens.set_sensor_value(gpio=4, raw_value=24.0, sensor_type="DS18B20", name="Zone A Temp")
    za_sens.set_multi_value_sensor(
        gpio=21,
        sensor_type="SHT31",
        primary_value=24.0,
        secondary_values={"humidity": 70.0},
        name="Zone A Humidity",
    )

    # Zone A - Actuators
    za_act = MockESP32Client(esp_id="ESP_ZA_ACT", kaiser_id="god")
    za_act.configure_zone("zone-a", "greenhouse-complex", "actuators-a")
    za_act.configure_actuator(gpio=5, actuator_type="pump", name="Zone A Pump")
    za_act.configure_actuator(gpio=6, actuator_type="valve", name="Zone A Valve")

    # Zone B - Sensors
    zb_sens = MockESP32Client(esp_id="ESP_ZB_SENS", kaiser_id="god")
    zb_sens.configure_zone("zone-b", "greenhouse-complex", "sensors-b")
    zb_sens.set_sensor_value(gpio=4, raw_value=22.0, sensor_type="DS18B20", name="Zone B Temp")
    zb_sens.set_multi_value_sensor(
        gpio=21,
        sensor_type="SHT31",
        primary_value=22.0,
        secondary_values={"humidity": 55.0},
        name="Zone B Humidity",
    )

    # Zone B - Actuators
    zb_act = MockESP32Client(esp_id="ESP_ZB_ACT", kaiser_id="god")
    zb_act.configure_zone("zone-b", "greenhouse-complex", "actuators-b")
    zb_act.configure_actuator(gpio=5, actuator_type="pump", name="Zone B Pump")
    zb_act.configure_actuator(gpio=6, actuator_type="valve", name="Zone B Valve")

    for mock in [za_sens, za_act, zb_sens, zb_act]:
        mock.clear_published_messages()

    return {
        "zone_a_sensors": za_sens,
        "zone_a_actuators": za_act,
        "zone_b_sensors": zb_sens,
        "zone_b_actuators": zb_act,
    }


# =============================================================================
# Complete Greenhouse Setup Fixture
# =============================================================================
@pytest.fixture
def mock_esp32_complete_greenhouse():
    """
    Complete greenhouse ESP with all sensor/actuator types.

    Sensors:
    - GPIO4: DS18B20 Temperature (soil)
    - GPIO21: SHT31 Temp+Humidity (air)
    - GPIO34: pH Sensor (nutrient tank)
    - GPIO35: Soil Moisture (analog)

    Actuators:
    - GPIO5: Irrigation Pump
    - GPIO6: Irrigation Valve
    - GPIO16: Dosing Pump (base)
    - GPIO17: Dosing Pump (acid)
    - GPIO25: Ventilation Fan (PWM)
    - GPIO26: Servo Valve (PWM)
    """
    mock = MockESP32Client(esp_id="ESP_GREENHOUSE", kaiser_id="god")
    mock.configure_zone("greenhouse", "main-facility", "zone-1")

    # Temperature sensors
    mock.add_ds18b20_multi(
        gpio=4,
        count=2,
        initial_temps=[22.0, 21.5],
        rom_addresses=["28-SOIL00000001", "28-SOIL00000002"],
    )

    # Air temperature + humidity
    mock.set_multi_value_sensor(
        gpio=21,
        sensor_type="SHT31",
        primary_value=23.0,
        secondary_values={"humidity": 65.0},
        name="Air Conditions",
    )

    # pH sensor
    mock.add_ph_sensor(gpio=34, initial_ph=6.5, calibrated=True)

    # Soil moisture (analog)
    mock.set_sensor_value(
        gpio=35, raw_value=2048.0, sensor_type="analog", name="Soil Moisture", unit="raw"
    )

    # Irrigation
    mock.configure_actuator(
        gpio=5, actuator_type="pump", name="Irrigation Pump", safety_timeout_ms=300000
    )
    mock.configure_actuator(gpio=6, actuator_type="valve", name="Irrigation Valve")

    # pH dosing
    mock.configure_actuator(gpio=16, actuator_type="pump", name="Base Dosing")
    mock.configure_actuator(gpio=17, actuator_type="pump", name="Acid Dosing")

    # PWM controlled
    mock.configure_actuator(
        gpio=25, actuator_type="pwm_motor", name="Ventilation Fan", min_value=0.2, max_value=1.0
    )
    mock.configure_actuator(gpio=26, actuator_type="servo", name="Flow Control Valve")

    mock.clear_published_messages()
    yield mock
    mock.reset()


# =============================================================================
# Helper Functions for Test Data Generation
# =============================================================================
def create_sensor_condition(
    esp_id: str, gpio: int, operator: str, value: float, sensor_type: str = "DS18B20"
) -> Dict[str, Any]:
    """Create a sensor condition dict for Logic Rules."""
    return {
        "type": "sensor",
        "esp_id": esp_id,
        "gpio": gpio,
        "sensor_type": sensor_type,
        "operator": operator,
        "value": value,
    }


def create_actuator_action(
    esp_id: str, gpio: int, command: str = "ON", value: float = 1.0, duration: int = 0
) -> Dict[str, Any]:
    """Create an actuator action dict for Logic Rules."""
    return {
        "type": "actuator_command",
        "esp_id": esp_id,
        "gpio": gpio,
        "command": command,
        "value": value,
        "duration_seconds": duration,
    }


def create_hysteresis_condition(
    esp_id: str,
    gpio: int,
    activate_above: Optional[float] = None,
    deactivate_below: Optional[float] = None,
    activate_below: Optional[float] = None,
    deactivate_above: Optional[float] = None,
    sensor_type: str = "DS18B20",
) -> Dict[str, Any]:
    """
    Create a hysteresis condition dict for Logic Rules.

    Cooling mode: activate_above + deactivate_below
    Heating mode: activate_below + deactivate_above
    """
    condition = {
        "type": "hysteresis",
        "esp_id": esp_id,
        "gpio": gpio,
        "sensor_type": sensor_type,
    }
    if activate_above is not None:
        condition["activate_above"] = activate_above
    if deactivate_below is not None:
        condition["deactivate_below"] = deactivate_below
    if activate_below is not None:
        condition["activate_below"] = activate_below
    if deactivate_above is not None:
        condition["deactivate_above"] = deactivate_above
    return condition


def create_sequence_action(
    steps: list, abort_on_failure: bool = True, description: str = ""
) -> Dict[str, Any]:
    """Create a sequence action dict for Logic Rules."""
    return {
        "type": "sequence",
        "description": description,
        "abort_on_failure": abort_on_failure,
        "steps": steps,
    }


def create_notification_action(channel: str, target: str, message_template: str) -> Dict[str, Any]:
    """Create a notification action dict for Logic Rules."""
    return {
        "type": "notification",
        "channel": channel,
        "target": target,
        "message_template": message_template,
    }
