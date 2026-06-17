"""
Pytest fixtures for ESP32 orchestrated tests.

Provides:
- mock_esp32: MockESP32Client for hardware-independent tests
- mock_esp32_with_actuators: Pre-configured with actuators
- mock_esp32_with_sensors: Pre-configured with sensors
- mock_esp32_with_zones: Pre-configured with zone management
- mock_esp32_with_sht31: Pre-configured with multi-value SHT31
- mock_esp32_greenhouse: Complete greenhouse setup
- multiple_mock_esp32: Multiple ESPs for cross-ESP testing
- real_esp32: Connection to real ESP32 device (optional)
"""

import os
from typing import Optional

import pytest

import socket
import time

from .mocks.in_memory_mqtt_client import InMemoryMQTTTestClient
from .mocks.mock_esp32_client import BrokerMode, MockESP32Client


@pytest.fixture
def mock_esp32():
    """
    Provide a MockESP32Client for hardware-independent tests.

    Usage:
        def test_actuator_control(mock_esp32):
            response = mock_esp32.handle_command("actuator_set", {"gpio": 5, "value": 1})
            assert response["status"] == "ok"
    """
    mock = MockESP32Client(esp_id="test-esp-001", kaiser_id="god")

    # Configure zone (required for actuator control)
    mock.configure_zone("test-zone", "test-master", "test-subzone")

    yield mock

    # Cleanup
    mock.reset()


@pytest.fixture
def mock_esp32_unconfigured():
    """
    Provide a MockESP32Client without zone provisioning.

    Useful to validate pre-provisioning safety behavior (actuators should reject).
    """
    mock = MockESP32Client(esp_id="ESP_UNPROVISIONED", kaiser_id="god")
    yield mock
    mock.reset()


@pytest.fixture
def mock_esp32_with_actuators():
    """
    Provide a MockESP32Client with pre-configured actuators.

    Pre-configured actuators:
    - GPIO 5: Pump (digital)
    - GPIO 6: Valve (digital)
    - GPIO 7: PWM Motor (pwm)
    """
    mock = MockESP32Client(esp_id="test-esp-002", kaiser_id="god")

    # Configure zone (required for actuator control)
    mock.configure_zone("actuator-zone", "main-zone", "actuator-subzone")

    # Pre-configure actuators using configure_actuator
    mock.configure_actuator(gpio=5, actuator_type="pump", name="Main Pump")
    mock.configure_actuator(gpio=6, actuator_type="valve", name="Main Valve")
    mock.configure_actuator(gpio=7, actuator_type="pwm_motor", name="Ventilation Fan")

    # Clear published messages from setup
    mock.clear_published_messages()

    yield mock

    mock.reset()


@pytest.fixture
def mock_esp32_with_sensors():
    """
    Provide a MockESP32Client with pre-configured sensors.

    Pre-configured sensors:
    - GPIO 34: Analog sensor (moisture)
    - GPIO 35: Analog sensor (temperature)
    - GPIO 36: Digital sensor (flow)
    """
    mock = MockESP32Client(esp_id="test-esp-003", kaiser_id="god")

    # Configure zone (required for actuator control)
    mock.configure_zone("sensor-zone", "main-zone", "sensor-subzone")

    # Pre-configure sensors with mock values using full params
    mock.set_sensor_value(
        gpio=34,
        raw_value=2048.0,
        sensor_type="analog",
        name="Soil Moisture",
        unit="raw",
        quality="good",
    )
    mock.set_sensor_value(
        gpio=35,
        raw_value=1500.0,
        sensor_type="analog",
        name="Temperature Raw",
        unit="raw",
        quality="good",
    )
    mock.set_sensor_value(
        gpio=36,
        raw_value=1.0,
        sensor_type="digital",
        name="Flow Sensor",
        unit="bool",
        quality="good",
    )

    # Clear published messages from setup
    mock.clear_published_messages()

    yield mock

    mock.reset()


@pytest.fixture
def mock_esp32_with_zones():
    """
    Provide a MockESP32Client with zone configuration.

    Zone configuration:
    - zone_id: greenhouse
    - master_zone_id: main-greenhouse
    - subzone_id: zone-a
    """
    mock = MockESP32Client(esp_id="ESP_ZONE001", kaiser_id="god")

    # Configure zone
    mock.configure_zone(
        zone_id="greenhouse",
        master_zone_id="main-greenhouse",
        subzone_id="zone-a",
        zone_name="Greenhouse Section",
        subzone_name="Zone A - Tomatoes",
    )

    # Add some sensors and actuators
    mock.set_sensor_value(
        gpio=4,
        raw_value=23.5,
        sensor_type="DS18B20",
        name="Soil Temperature",
        unit="°C",
        subzone_id="zone-a",
        library_name="dallas_temp",
    )

    mock.configure_actuator(gpio=5, actuator_type="pump", name="Irrigation Pump")

    mock.clear_published_messages()

    yield mock

    mock.reset()


@pytest.fixture
def mock_esp32_with_sht31():
    """
    Provide a MockESP32Client with multi-value SHT31 sensor.

    SHT31 provides:
    - Primary: Temperature (°C)
    - Secondary: Humidity (%RH)
    """
    mock = MockESP32Client(esp_id="ESP_SHT31001", kaiser_id="god")

    # Configure SHT31 as multi-value sensor
    mock.set_multi_value_sensor(
        gpio=21,
        sensor_type="SHT31",
        primary_value=23.5,  # Temperature
        secondary_values={"humidity": 65.2},
        name="SHT31 Temp/Humidity",
        quality="good",
    )

    # Also add a DS18B20 for comparison
    mock.set_sensor_value(
        gpio=4,
        raw_value=24.0,
        sensor_type="DS18B20",
        name="Backup Temperature",
        unit="°C",
        library_name="dallas_temp",
    )

    mock.clear_published_messages()

    yield mock

    mock.reset()


@pytest.fixture
def mock_esp32_greenhouse():
    """
    Provide a complete greenhouse setup for full workflow tests.

    Configuration:
    - Zone: greenhouse / main-greenhouse / zone-a
    - Sensors:
      - GPIO 4: DS18B20 Temperature
      - GPIO 21: SHT31 Temp+Humidity (multi-value)
      - GPIO 34: Soil Moisture (analog)
    - Actuators:
      - GPIO 5: Irrigation Pump
      - GPIO 6: Ventilation Valve
      - GPIO 7: Fan (PWM)
    - Libraries:
      - dallas_temp
      - sht31_combined
    """
    mock = MockESP32Client(esp_id="ESP_GH001", kaiser_id="god")

    # Configure zone
    mock.configure_zone(
        zone_id="greenhouse",
        master_zone_id="main-greenhouse",
        subzone_id="zone-a",
        zone_name="Main Greenhouse",
        subzone_name="Tomato Section A",
    )

    # Install libraries
    mock.handle_command(
        "library_install", {"name": "dallas_temp", "version": "1.2.0", "sensor_type": "DS18B20"}
    )
    mock.handle_command(
        "library_install", {"name": "sht31_combined", "version": "2.0.0", "sensor_type": "SHT31"}
    )

    # Configure sensors
    mock.set_sensor_value(
        gpio=4,
        raw_value=24.5,
        sensor_type="DS18B20",
        name="Soil Temperature",
        unit="°C",
        quality="good",
        library_name="dallas_temp",
        subzone_id="zone-a",
        calibration={"offset": 0.0, "multiplier": 1.0},
    )

    mock.set_multi_value_sensor(
        gpio=21,
        sensor_type="SHT31",
        primary_value=25.0,
        secondary_values={"humidity": 68.5},
        name="Air Temp/Humidity",
        quality="good",
    )

    mock.set_sensor_value(
        gpio=34,
        raw_value=1800.0,
        sensor_type="moisture",
        name="Soil Moisture",
        unit="raw",
        quality="good",
        subzone_id="zone-a",
    )

    # Configure actuators
    mock.configure_actuator(
        gpio=5,
        actuator_type="pump",
        name="Irrigation Pump",
        safety_timeout_ms=300000,  # 5 minutes max
    )

    mock.configure_actuator(gpio=6, actuator_type="valve", name="Ventilation Valve")

    mock.configure_actuator(
        gpio=7,
        actuator_type="fan",
        name="Ventilation Fan",
        min_value=0.2,  # Minimum 20% speed
        max_value=1.0,
    )

    mock.clear_published_messages()

    yield mock

    mock.reset()


@pytest.fixture
def multiple_mock_esp32():
    """
    Provide 3 MockESP32Clients for cross-ESP testing.

    Uses REAL MQTT topic structure for authentic routing validation.

    Pre-configured ESPs:
    - esp-001: Actuator controller (pump, valve) on GPIO 5, 6
    - esp-002: Sensor station (moisture, temp, flow) on GPIO 34, 35, 36
    - esp-003: Mixed (1 actuator, 2 sensors) on GPIO 5, 34, 35

    All use zone configuration for complete testing.

    Usage:
        def test_cross_esp(multiple_mock_esp32):
            esps = multiple_mock_esp32
            # Read sensor on ESP-002
            sensor_data = esps["esp2"].handle_command("sensor_read", {"gpio": 34})
            # Control actuator on ESP-001
            esps["esp1"].handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})
    """
    esp1 = MockESP32Client(esp_id="test-esp-001", kaiser_id="god")
    esp2 = MockESP32Client(esp_id="test-esp-002", kaiser_id="god")
    esp3 = MockESP32Client(esp_id="test-esp-003", kaiser_id="god")

    # Configure zones for all ESPs
    esp1.configure_zone("irrigation", "main-zone", "pumps")
    esp2.configure_zone("irrigation", "main-zone", "sensors")
    esp3.configure_zone("irrigation", "main-zone", "mixed")

    # Pre-configure ESP-001 with actuators
    esp1.configure_actuator(gpio=5, actuator_type="pump", name="Main Pump")
    esp1.configure_actuator(gpio=6, actuator_type="valve", name="Main Valve")

    # Pre-configure ESP-002 with sensors
    esp2.set_sensor_value(gpio=34, raw_value=2048.0, sensor_type="moisture", name="Soil Moisture")
    esp2.set_sensor_value(gpio=35, raw_value=1500.0, sensor_type="analog", name="Temperature Raw")
    esp2.set_sensor_value(gpio=36, raw_value=1.0, sensor_type="digital", name="Flow Sensor")

    # Pre-configure ESP-003 with mixed (actuator + sensors)
    esp3.configure_actuator(gpio=5, actuator_type="pump", name="Backup Pump")
    esp3.set_sensor_value(gpio=34, raw_value=3000.0, sensor_type="moisture", name="Backup Moisture")
    esp3.set_sensor_value(gpio=35, raw_value=1800.0, sensor_type="analog", name="Backup Temp")

    # Clear setup messages
    esp1.clear_published_messages()
    esp2.clear_published_messages()
    esp3.clear_published_messages()

    yield {"esp1": esp1, "esp2": esp2, "esp3": esp3}

    # Cleanup
    esp1.reset()
    esp2.reset()
    esp3.reset()


@pytest.fixture
def multiple_mock_esp32_with_zones():
    """
    Provide multiple ESPs with complete zone configuration for zone-based testing.

    Zone structure:
    - Master Zone: greenhouse-complex
    - Subzones:
      - zone-a: ESP-A (sensors) + ESP-B (actuators)
      - zone-b: ESP-C (sensors) + ESP-D (actuators)
    """
    esps = {}

    # Zone A - Sensors
    esp_a_sensors = MockESP32Client(esp_id="ESP_ZA_SENS", kaiser_id="god")
    esp_a_sensors.configure_zone("greenhouse-a", "greenhouse-complex", "zone-a-sensors")
    esp_a_sensors.set_sensor_value(
        gpio=4, raw_value=24.0, sensor_type="DS18B20", name="Zone A Temp"
    )
    esp_a_sensors.set_multi_value_sensor(
        gpio=21,
        sensor_type="SHT31",
        primary_value=25.0,
        secondary_values={"humidity": 70.0},
        name="Zone A SHT31",
    )
    esps["zone_a_sensors"] = esp_a_sensors

    # Zone A - Actuators
    esp_a_actuators = MockESP32Client(esp_id="ESP_ZA_ACT", kaiser_id="god")
    esp_a_actuators.configure_zone("greenhouse-a", "greenhouse-complex", "zone-a-actuators")
    esp_a_actuators.configure_actuator(gpio=5, actuator_type="pump", name="Zone A Pump")
    esp_a_actuators.configure_actuator(gpio=6, actuator_type="fan", name="Zone A Fan")
    esps["zone_a_actuators"] = esp_a_actuators

    # Zone B - Sensors
    esp_b_sensors = MockESP32Client(esp_id="ESP_ZB_SENS", kaiser_id="god")
    esp_b_sensors.configure_zone("greenhouse-b", "greenhouse-complex", "zone-b-sensors")
    esp_b_sensors.set_sensor_value(
        gpio=4, raw_value=26.0, sensor_type="DS18B20", name="Zone B Temp"
    )
    esp_b_sensors.set_multi_value_sensor(
        gpio=21,
        sensor_type="SHT31",
        primary_value=27.0,
        secondary_values={"humidity": 65.0},
        name="Zone B SHT31",
    )
    esps["zone_b_sensors"] = esp_b_sensors

    # Zone B - Actuators
    esp_b_actuators = MockESP32Client(esp_id="ESP_ZB_ACT", kaiser_id="god")
    esp_b_actuators.configure_zone("greenhouse-b", "greenhouse-complex", "zone-b-actuators")
    esp_b_actuators.configure_actuator(gpio=5, actuator_type="pump", name="Zone B Pump")
    esp_b_actuators.configure_actuator(gpio=6, actuator_type="fan", name="Zone B Fan")
    esps["zone_b_actuators"] = esp_b_actuators

    # Clear setup messages
    for esp in esps.values():
        esp.clear_published_messages()

    yield esps

    # Cleanup
    for esp in esps.values():
        esp.reset()


@pytest.fixture
def mock_esp32_safe_mode():
    """
    Provide a MockESP32Client that can be put into SAFE_MODE for testing.
    """
    mock = MockESP32Client(esp_id="ESP_SAFE001", kaiser_id="god")

    # Configure zone (required for actuator control)
    mock.configure_zone("safe-mode-zone", "main-zone", "safe-subzone")

    # Configure some actuators
    mock.configure_actuator(gpio=5, actuator_type="pump", name="Test Pump")
    mock.configure_actuator(gpio=6, actuator_type="valve", name="Test Valve")

    mock.clear_published_messages()

    yield mock

    mock.reset()


@pytest.fixture
def real_esp32():
    """
    Provide connection to a real ESP32 device via MQTT.

    Uses REAL MQTT topics - identical to MockESP32Client API.
    Enable via environment variables:
    - ESP32_TEST_DEVICE_ID: ESP32 device ID
    - MQTT_BROKER_HOST: Broker address
    - MQTT_BROKER_PORT: Broker port (default: 1883)
    - MQTT_USERNAME: Optional auth
    - MQTT_PASSWORD: Optional auth

    Usage:
        def test_real_actuator(real_esp32):
            response = real_esp32.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})
            assert response["status"] == "ok"

    Marks tests with @pytest.mark.hardware for selective running:
        pytest -m hardware  # Run only hardware tests
        pytest -m "not hardware"  # Skip hardware tests (default in CI)
    """
    esp_id = os.getenv("ESP32_TEST_DEVICE_ID")
    if not esp_id:
        pytest.skip("ESP32_TEST_DEVICE_ID not set - skipping real hardware tests")

    broker_host = os.getenv("MQTT_BROKER_HOST")
    if not broker_host:
        pytest.skip("MQTT_BROKER_HOST not set - skipping real hardware tests")

    broker_port = int(os.getenv("MQTT_BROKER_PORT", "1883"))
    username = os.getenv("MQTT_USERNAME")
    password = os.getenv("MQTT_PASSWORD")

    try:
        from .mocks.real_esp32_client import RealESP32Client

        client = RealESP32Client(
            esp_id=esp_id,
            broker_host=broker_host,
            broker_port=broker_port,
            username=username,
            password=password,
        )

        yield client

        client.disconnect()

    except ImportError as e:
        pytest.skip(f"RealESP32Client not available: {e}")
    except ConnectionError as e:
        pytest.skip(f"Could not connect to MQTT broker: {e}")


@pytest.fixture(scope="session")
def mqtt_test_config():
    """
    Provide MQTT configuration for tests.

    Returns:
        dict: MQTT configuration (broker, port, credentials)
    """
    return {
        "broker_host": os.getenv("MQTT_BROKER_HOST", "localhost"),
        "broker_port": int(os.getenv("MQTT_BROKER_PORT", "1883")),
        "username": os.getenv("MQTT_USERNAME", "test"),
        "password": os.getenv("MQTT_PASSWORD", "test"),
        "client_id": "pytest-esp32-test-client",
    }


@pytest.fixture
def mqtt_test_client(mqtt_test_config):
    """
    Provide an in-memory MQTT test client for offline publish/subscribe tests.

    This avoids broker dependencies while keeping the API surface compatible
    with a real MQTT client.
    """
    return InMemoryMQTTTestClient()


# =============================================================================
# MQTT Broker Mode Fixtures (Phase 3)
# =============================================================================


def is_mqtt_broker_available(host: str = "localhost", port: int = 1883) -> bool:
    """
    Check if MQTT broker is available at given host:port.

    Args:
        host: MQTT broker hostname
        port: MQTT broker port

    Returns:
        True if broker is reachable
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


@pytest.fixture
def mock_esp32_with_broker(mqtt_test_config):
    """
    Provide a MockESP32Client with real MQTT broker connection.

    Automatically skips if MQTT broker is not available.
    Useful for end-to-end integration tests.

    Usage:
        def test_mqtt_publish(mock_esp32_with_broker):
            mock = mock_esp32_with_broker
            mock.set_sensor_value(gpio=4, raw_value=23.5, sensor_type="DS18B20")
            # Message is published to real broker
            assert mock.is_broker_connected()
    """
    host = mqtt_test_config.get("broker_host", "localhost")
    port = mqtt_test_config.get("broker_port", 1883)

    if not is_mqtt_broker_available(host, port):
        pytest.skip(f"MQTT Broker nicht erreichbar auf {host}:{port}")

    # Generate unique ESP ID to avoid conflicts
    esp_id = f"MOCK_BROKER_{int(time.time() * 1000) % 100000:05d}"

    mock = MockESP32Client(
        esp_id=esp_id,
        kaiser_id="god",
        broker_mode=BrokerMode.MQTT,
        mqtt_config={
            "host": host,
            "port": port,
            "username": mqtt_test_config.get("username"),
            "password": mqtt_test_config.get("password"),
        },
    )

    # Configure zone for full functionality
    mock.configure_zone("broker_test_zone", "broker_master", "broker_subzone")

    yield mock

    # Cleanup: Disconnect from broker
    mock.disconnect_mqtt()
    mock.reset()


@pytest.fixture
def mock_esp32_broker_fallback(mqtt_test_config):
    """
    Provide a MockESP32Client that tries broker mode but falls back to direct.

    Always succeeds - uses broker if available, otherwise direct mode.
    Useful for tests that work in both modes.

    Usage:
        def test_sensor_publish(mock_esp32_broker_fallback):
            mock = mock_esp32_broker_fallback
            mock.set_sensor_value(gpio=4, raw_value=23.5, sensor_type="DS18B20")
            # Works regardless of broker availability
    """
    host = mqtt_test_config.get("broker_host", "localhost")
    port = mqtt_test_config.get("broker_port", 1883)

    broker_available = is_mqtt_broker_available(host, port)
    esp_id = f"MOCK_FALLBACK_{int(time.time() * 1000) % 100000:05d}"

    if broker_available:
        mock = MockESP32Client(
            esp_id=esp_id,
            kaiser_id="god",
            broker_mode=BrokerMode.MQTT,
            mqtt_config={
                "host": host,
                "port": port,
                "username": mqtt_test_config.get("username"),
                "password": mqtt_test_config.get("password"),
            },
        )
    else:
        # Fallback to direct mode
        mock = MockESP32Client(esp_id=esp_id, kaiser_id="god", broker_mode=BrokerMode.DIRECT)

    mock.configure_zone("fallback_zone", "fallback_master", "fallback_subzone")

    yield mock

    if broker_available:
        mock.disconnect_mqtt()
    mock.reset()


# =============================================================================
# Subzone Management Fixtures
# =============================================================================


@pytest.fixture
def mock_esp32_with_zone_for_subzones():
    """
    Provide a MockESP32Client with zone configured for subzone testing.

    Zone configuration:
    - zone_id: greenhouse_zone_1
    - master_zone_id: greenhouse_master

    No actuators/sensors pre-configured - allows subzone tests to assign GPIOs.
    """
    from .test_subzone_management import MockESP32WithSubzones

    esp = MockESP32WithSubzones(esp_id="ESP_SUBZONE001", kaiser_id="god")
    esp.configure_zone(
        zone_id="greenhouse_zone_1",
        master_zone_id="greenhouse_master",
        zone_name="Greenhouse Zone 1",
    )

    yield esp

    esp.reset()


@pytest.fixture
def mock_esp32_no_zone_for_subzones():
    """
    Provide a MockESP32WithSubzones without zone configured.

    Useful for testing validation (subzone assignment should fail).
    """
    from .test_subzone_management import MockESP32WithSubzones

    esp = MockESP32WithSubzones(esp_id="ESP_NO_ZONE", kaiser_id="god")

    yield esp

    esp.reset()


@pytest.fixture
def mock_esp32_with_actuators_for_subzones():
    """
    Provide a MockESP32WithSubzones with pre-configured actuators.

    Pre-configured actuators:
    - GPIO 5: Pump (digital)
    - GPIO 6: Valve (digital)
    - GPIO 18: Fan (PWM)

    Zone configured for subzone assignment.
    """
    from .test_subzone_management import MockESP32WithSubzones

    esp = MockESP32WithSubzones(esp_id="ESP_ACTUATOR_SUBZONE", kaiser_id="god")
    esp.configure_zone(
        zone_id="greenhouse_zone_1",
        master_zone_id="greenhouse_master",
    )

    # Pre-configure actuators
    esp.configure_actuator(gpio=5, actuator_type="pump", name="Water Pump")
    esp.configure_actuator(gpio=6, actuator_type="valve", name="Water Valve")
    esp.configure_actuator(gpio=18, actuator_type="fan", name="Fan Control")

    esp.clear_published_messages()

    yield esp

    esp.reset()


@pytest.fixture
def multiple_mock_esp32_for_subzones():
    """
    Provide multiple MockESP32WithSubzones for cross-ESP subzone testing.

    Structure:
    - zone_a_sensors: ESP with sensors in greenhouse_zone_a
    - zone_a_actuators: ESP with actuators in greenhouse_zone_a
    - zone_b: ESP in greenhouse_zone_b (isolated)
    """
    from .test_subzone_management import MockESP32WithSubzones

    esps = {}

    # ESP-A: Sensors station in zone A
    esp_a = MockESP32WithSubzones(esp_id="ESP_ZONE_A_SENSORS", kaiser_id="god")
    esp_a.configure_zone(
        zone_id="greenhouse_zone_a",
        master_zone_id="greenhouse_master",
    )
    esp_a.set_sensor_value(gpio=4, raw_value=23.5, sensor_type="DS18B20")
    esp_a.set_sensor_value(gpio=21, raw_value=65.2, sensor_type="SHT31")
    esps["zone_a_sensors"] = esp_a

    # ESP-B: Actuators station in zone A
    esp_b = MockESP32WithSubzones(esp_id="ESP_ZONE_A_ACTUATORS", kaiser_id="god")
    esp_b.configure_zone(
        zone_id="greenhouse_zone_a",
        master_zone_id="greenhouse_master",
    )
    esp_b.configure_actuator(gpio=5, actuator_type="pump")
    esp_b.configure_actuator(gpio=6, actuator_type="fan")
    esps["zone_a_actuators"] = esp_b

    # ESP-C: Different zone
    esp_c = MockESP32WithSubzones(esp_id="ESP_ZONE_B", kaiser_id="god")
    esp_c.configure_zone(
        zone_id="greenhouse_zone_b",
        master_zone_id="greenhouse_master",
    )
    esps["zone_b"] = esp_c

    # Clear setup messages
    for esp in esps.values():
        esp.clear_published_messages()

    yield esps

    # Cleanup
    for esp in esps.values():
        esp.reset()
