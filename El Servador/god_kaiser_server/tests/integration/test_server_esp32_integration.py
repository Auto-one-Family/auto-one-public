"""
Integration Tests: Server verarbeitet ESP32-Nachrichten

Diese Tests simulieren echte ESP32-Nachrichten und prüfen
ob der Server-Code korrekt reagiert.

WICHTIG: Diese Tests rufen den ECHTEN Server-Code auf, nicht nur den Mock!
- SensorDataHandler.handle_sensor_data()
- ActuatorStatusHandler.handle_actuator_status()
- TopicBuilder.parse_*()

Reference: El Trabajante/docs/Mqtt_Protocoll.md
"""

import pytest
import pytest_asyncio
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Server imports
from src.db.base import Base
from src.db.models import esp, sensor, actuator  # noqa: F401
from src.db.models.esp import ESPDevice
from src.db.models.sensor import SensorConfig, SensorData
from src.db.models.actuator import ActuatorConfig, ActuatorState
from src.db.repositories.esp_repo import ESPRepository
from src.db.repositories.sensor_repo import SensorRepository
from src.db.repositories.actuator_repo import ActuatorRepository
from src.mqtt.handlers.sensor_handler import SensorDataHandler, handle_sensor_data
from src.mqtt.handlers.actuator_handler import ActuatorStatusHandler, handle_actuator_status
from src.mqtt.topics import TopicBuilder

# =============================================================================
# Test Database Fixtures
# =============================================================================

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="function")
async def test_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Create test database engine with all tables."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        future=True,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def test_session(test_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Create test database session."""
    async_session_maker = sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with async_session_maker() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def sample_esp_device(test_session: AsyncSession) -> ESPDevice:
    """
    Create a sample ESP device matching Mqtt_Protocoll.md format.

    ESP ID format: ESP_{8 hex chars}
    """
    device = ESPDevice(
        device_id="ESP_12AB34CD",  # Matches protocol spec
        name="Test ESP32 Greenhouse",
        ip_address="192.168.1.100",
        mac_address="AA:BB:CC:DD:EE:FF",
        firmware_version="1.0.0",
        hardware_type="ESP32_WROOM",
        status="online",
        capabilities={"max_sensors": 20, "max_actuators": 12},
    )
    test_session.add(device)
    await test_session.flush()
    await test_session.refresh(device)
    return device


@pytest_asyncio.fixture
async def sample_sensor_config(
    test_session: AsyncSession, sample_esp_device: ESPDevice
) -> SensorConfig:
    """Create a sample sensor config with Pi-Enhanced enabled."""
    config = SensorConfig(
        esp_id=sample_esp_device.id,
        gpio=34,
        sensor_name="pH Sensor Pool",
        sensor_type="ph",
        enabled=True,
        pi_enhanced=True,  # Server should process raw data
        sample_interval_ms=30000,
        calibration_data={"offset": 0.0, "multiplier": 1.0},
        sensor_metadata={"processing_params": {"reference_voltage": 3.3}},
    )
    test_session.add(config)
    await test_session.flush()
    await test_session.refresh(config)
    return config


@pytest_asyncio.fixture
async def sample_actuator_config(
    test_session: AsyncSession, sample_esp_device: ESPDevice
) -> ActuatorConfig:
    """Create a sample actuator config."""
    config = ActuatorConfig(
        esp_id=sample_esp_device.id,
        gpio=18,
        actuator_name="Irrigation Pump",
        actuator_type="pump",
        enabled=True,
        min_value=0.0,
        max_value=1.0,
        timeout_seconds=300,
        actuator_metadata={"zone": "greenhouse-a"},
    )
    test_session.add(config)
    await test_session.flush()
    await test_session.refresh(config)
    return config


# =============================================================================
# Topic Parsing Tests
# =============================================================================


class TestTopicParsing:
    """Test that Server correctly parses ESP32 MQTT topics."""

    def test_parse_sensor_data_topic_valid(self):
        """Parse valid sensor data topic."""
        topic = "kaiser/god/esp/ESP_12AB34CD/sensor/34/data"

        result = TopicBuilder.parse_sensor_data_topic(topic)

        assert result is not None
        assert result["esp_id"] == "ESP_12AB34CD"
        assert result["gpio"] == 34
        assert result["type"] == "sensor_data"

    def test_parse_sensor_data_topic_different_gpio(self):
        """Parse sensor topic with different GPIO values."""
        for gpio in [0, 4, 21, 34, 35, 36]:
            topic = f"kaiser/god/esp/ESP_AABBCCDD/sensor/{gpio}/data"
            result = TopicBuilder.parse_sensor_data_topic(topic)

            assert result is not None, f"Failed for GPIO {gpio}"
            assert result["gpio"] == gpio

    def test_parse_sensor_data_topic_invalid(self):
        """Invalid topics return None."""
        invalid_topics = [
            "kaiser/god/esp/ESP_12AB34CD/sensor/34/config",  # wrong suffix
            "kaiser/esp/ESP_12AB34CD/sensor/34/data",  # missing god
            "kaiser/god/esp/invalid/sensor/34/data",  # invalid esp_id format
            "completely/wrong/topic",
        ]

        for topic in invalid_topics:
            result = TopicBuilder.parse_sensor_data_topic(topic)
            assert result is None, f"Should have failed for: {topic}"

    def test_parse_actuator_status_topic_valid(self):
        """Parse valid actuator status topic."""
        topic = "kaiser/god/esp/ESP_12AB34CD/actuator/18/status"

        result = TopicBuilder.parse_actuator_status_topic(topic)

        assert result is not None
        assert result["esp_id"] == "ESP_12AB34CD"
        assert result["gpio"] == 18
        assert result["type"] == "actuator_status"

    def test_parse_heartbeat_topic_valid(self):
        """Parse valid heartbeat topic."""
        topic = "kaiser/god/esp/ESP_12AB34CD/heartbeat"

        result = TopicBuilder.parse_heartbeat_topic(topic)

        assert result is not None
        assert result["esp_id"] == "ESP_12AB34CD"
        assert result["type"] == "heartbeat"

    def test_validate_esp_id_format(self):
        """Validate ESP ID format matches spec (6-8 hex characters)."""
        # Valid formats - 8 hex
        assert TopicBuilder.validate_esp_id("ESP_12AB34CD") is True
        assert TopicBuilder.validate_esp_id("ESP_AABBCCDD") is True
        assert TopicBuilder.validate_esp_id("ESP_00000000") is True
        # Valid formats - 6 hex (real ESP from MAC)
        assert TopicBuilder.validate_esp_id("ESP_D0B19C") is True
        assert TopicBuilder.validate_esp_id("ESP_AABBCC") is True
        # Valid formats - 7 hex
        assert TopicBuilder.validate_esp_id("ESP_12AB34C") is True

        # Invalid formats
        assert TopicBuilder.validate_esp_id("ESP_12AB3") is False  # 5 hex - too short
        assert TopicBuilder.validate_esp_id("ESP_12AB34CDE") is False  # 9 hex - too long
        assert TopicBuilder.validate_esp_id("esp_12AB34CD") is False  # lowercase prefix
        assert TopicBuilder.validate_esp_id("ESP_12ab34cd") is False  # lowercase hex
        assert TopicBuilder.validate_esp_id("12AB34CD") is False  # no prefix
        assert TopicBuilder.validate_esp_id("ESP_GHIJKLMN") is False  # non-hex chars


# =============================================================================
# Sensor Handler Tests - Payload Validation
# =============================================================================


class TestSensorHandlerValidation:
    """Test SensorDataHandler payload validation."""

    @pytest.fixture
    def sensor_handler(self):
        """Create SensorDataHandler with mocked publisher."""
        handler = SensorDataHandler()
        handler.publisher = MagicMock()
        handler.publisher.publish_pi_enhanced_response = MagicMock()
        return handler

    @pytest.fixture
    def valid_sensor_payload(self):
        """
        Payload exactly matching ACTUAL ESP32 implementation.

        Reference: El Trabajante/src/services/sensor/sensor_manager.cpp
        Function: buildMQTTPayload() lines 705-755
        """
        return {
            "esp_id": "ESP_12AB34CD",
            "zone_id": "greenhouse",
            "subzone_id": "zone_a",
            "gpio": 34,
            "sensor_type": "ph",
            "raw": 2150,
            "value": 0.0,  # ESP32 sends 0 when raw_mode=True
            "unit": "",
            "quality": "good",
            "ts": int(time.time()),
            "raw_mode": True,  # ESP32 always sends raw_mode: true
        }

    def test_validate_complete_payload(self, sensor_handler, valid_sensor_payload):
        """Complete payload passes validation."""
        result = sensor_handler._validate_payload(valid_sensor_payload)

        assert result["valid"] is True
        assert result["error"] == ""

    def test_validate_missing_required_fields(self, sensor_handler):
        """Payload with missing required fields fails."""
        required_fields = ["ts", "esp_id", "gpio", "sensor_type", "raw"]

        for field in required_fields:
            payload = {
                "ts": int(time.time()),
                "esp_id": "ESP_12AB34CD",
                "gpio": 34,
                "sensor_type": "ph",
                "raw": 2150,
                "raw_mode": True,
            }
            del payload[field]

            result = sensor_handler._validate_payload(payload)

            assert result["valid"] is False, f"Should fail for missing {field}"
            assert field in result["error"]

    def test_validate_raw_mode_defaults_to_true(self, sensor_handler):
        """Payload without raw_mode should default to True."""
        payload = {
            "ts": int(time.time()),
            "esp_id": "ESP_12AB34CD",
            "gpio": 34,
            "sensor_type": "ph",
            "raw": 2150,
        }

        result = sensor_handler._validate_payload(payload)

        assert result["valid"] is True
        assert payload["raw_mode"] is True

    def test_validate_wrong_types(self, sensor_handler):
        """Payload with wrong types fails."""
        # ts must be int
        result = sensor_handler._validate_payload(
            {
                "ts": "not_an_int",
                "esp_id": "ESP_12AB34CD",
                "gpio": 34,
                "sensor_type": "ph",
                "raw": 2150,
                "raw_mode": True,
            }
        )
        assert result["valid"] is False
        assert "ts" in result["error"]

        # gpio must be int
        result = sensor_handler._validate_payload(
            {
                "ts": int(time.time()),
                "esp_id": "ESP_12AB34CD",
                "gpio": "34",  # string instead of int
                "sensor_type": "ph",
                "raw": 2150,
                "raw_mode": True,
            }
        )
        assert result["valid"] is False
        assert "gpio" in result["error"]

        # raw_mode must be bool
        result = sensor_handler._validate_payload(
            {
                "ts": int(time.time()),
                "esp_id": "ESP_12AB34CD",
                "gpio": 34,
                "sensor_type": "ph",
                "raw": 2150,
                "raw_mode": "true",  # string instead of bool
            }
        )
        assert result["valid"] is False
        assert "raw_mode" in result["error"]

    def test_validate_raw_value_numeric(self, sensor_handler):
        """raw field can be int or float."""
        for raw_value in [2150, 2150.5, 0, -100.5]:
            result = sensor_handler._validate_payload(
                {
                    "ts": int(time.time()),
                    "esp_id": "ESP_12AB34CD",
                    "gpio": 34,
                    "sensor_type": "ph",
                    "raw": raw_value,
                    "raw_mode": True,
                }
            )
            assert result["valid"] is True, f"Should accept raw={raw_value}"


# =============================================================================
# Sensor Handler Tests - Full Processing Flow
# =============================================================================


class TestSensorHandlerProcessing:
    """Test SensorDataHandler processing with real database."""

    @pytest.mark.asyncio
    async def test_handle_sensor_data_success(
        self,
        test_session: AsyncSession,
        sample_esp_device: ESPDevice,
        sample_sensor_config: SensorConfig,
    ):
        """Successfully process sensor data and save to database."""
        # Setup handler with mocked dependencies
        handler = SensorDataHandler()
        handler.publisher = MagicMock()
        handler.publisher.publish_pi_enhanced_response = MagicMock()

        topic = "kaiser/god/esp/ESP_12AB34CD/sensor/34/data"
        payload = {
            "ts": int(time.time()),
            "esp_id": "ESP_12AB34CD",
            "gpio": 34,
            "sensor_type": "ph",
            "raw": 2150,
            "value": 0.0,
            "unit": "",
            "quality": "good",
            "raw_mode": False,  # Local processing (no Pi-Enhanced)
        }

        # Mock resilient_session to return our test session
        @asynccontextmanager
        async def mock_resilient_session():
            yield test_session

        with patch("src.mqtt.handlers.sensor_handler.resilient_session", mock_resilient_session):
            result = await handler.handle_sensor_data(topic, payload)

        assert result is True

        # Verify data was saved
        sensor_repo = SensorRepository(test_session)
        saved_data = await sensor_repo.get_latest_data(sample_esp_device.id, 34)

        assert len(saved_data) == 1
        assert saved_data[0].raw_value == 2150
        assert saved_data[0].processing_mode == "local"

    @pytest.mark.asyncio
    async def test_handle_sensor_data_unknown_esp(self, test_session: AsyncSession):
        """Handle sensor data from unknown ESP device."""
        handler = SensorDataHandler()
        handler.publisher = MagicMock()

        topic = "kaiser/god/esp/ESP_UNKNOWN1/sensor/34/data"
        payload = {
            "ts": int(time.time()),
            "esp_id": "ESP_UNKNOWN1",
            "gpio": 34,
            "sensor_type": "ph",
            "raw": 2150,
            "value": 0.0,
            "unit": "",
            "quality": "good",
            "raw_mode": False,
        }

        @asynccontextmanager
        async def mock_resilient_session():
            yield test_session

        with patch("src.mqtt.handlers.sensor_handler.resilient_session", mock_resilient_session):
            result = await handler.handle_sensor_data(topic, payload)

        # Should fail - ESP not in database
        assert result is False

    @pytest.mark.asyncio
    async def test_handle_sensor_data_invalid_topic(self):
        """Handle sensor data with invalid topic format."""
        handler = SensorDataHandler()
        handler.publisher = MagicMock()

        topic = "invalid/topic/format"
        payload = {
            "ts": int(time.time()),
            "esp_id": "ESP_12AB34CD",
            "gpio": 34,
            "sensor_type": "ph",
            "raw": 2150,
            "value": 0.0,
            "unit": "",
            "quality": "good",
            "raw_mode": False,
        }

        result = await handler.handle_sensor_data(topic, payload)

        assert result is False


# =============================================================================
# Actuator Handler Tests
# =============================================================================


class TestActuatorHandlerValidation:
    """Test ActuatorStatusHandler payload validation."""

    @pytest.fixture
    def actuator_handler(self):
        """Create ActuatorStatusHandler."""
        return ActuatorStatusHandler()

    @pytest.fixture
    def valid_actuator_payload(self):
        """
        Actuator status payload matching Mqtt_Protocoll.md specification.
        """
        return {
            "ts": int(time.time()),
            "esp_id": "ESP_12AB34CD",
            "gpio": 18,
            "actuator_type": "pump",
            "state": "on",
            "value": 255,
            "last_command": "on",
            "uptime": 3600,
            "error": None,
        }

    def test_validate_complete_payload(self, actuator_handler, valid_actuator_payload):
        """Complete actuator payload passes validation."""
        result = actuator_handler._validate_payload(valid_actuator_payload)

        assert result["valid"] is True
        assert result["error"] == ""

    def test_validate_missing_required_fields(self, actuator_handler):
        """Actuator payload with missing required fields fails."""
        required_fields = ["ts", "esp_id", "gpio", "actuator_type", "state", "value"]

        for field in required_fields:
            payload = {
                "ts": int(time.time()),
                "esp_id": "ESP_12AB34CD",
                "gpio": 18,
                "actuator_type": "pump",
                "state": "on",
                "value": 255,
            }
            del payload[field]

            result = actuator_handler._validate_payload(payload)

            assert result["valid"] is False, f"Should fail for missing {field}"

    def test_validate_state_values(self, actuator_handler):
        """Actuator state must be valid value."""
        valid_states = ["on", "off", "pwm", "error", "unknown"]

        for state in valid_states:
            payload = {
                "ts": int(time.time()),
                "esp_id": "ESP_12AB34CD",
                "gpio": 18,
                "actuator_type": "pump",
                "state": state,
                "value": 255,
            }
            result = actuator_handler._validate_payload(payload)
            assert result["valid"] is True, f"Should accept state={state}"

        # Invalid state
        payload = {
            "ts": int(time.time()),
            "esp_id": "ESP_12AB34CD",
            "gpio": 18,
            "actuator_type": "pump",
            "state": "invalid_state",
            "value": 255,
        }
        result = actuator_handler._validate_payload(payload)
        assert result["valid"] is False


class TestActuatorHandlerProcessing:
    """Test ActuatorStatusHandler processing with real database."""

    @pytest.mark.asyncio
    async def test_handle_actuator_status_success(
        self,
        test_session: AsyncSession,
        sample_esp_device: ESPDevice,
        sample_actuator_config: ActuatorConfig,
    ):
        """Successfully process actuator status and save to database."""
        handler = ActuatorStatusHandler()

        topic = "kaiser/god/esp/ESP_12AB34CD/actuator/18/status"
        payload = {
            "ts": int(time.time()),
            "esp_id": "ESP_12AB34CD",
            "gpio": 18,
            "actuator_type": "pump",
            "state": "on",
            "value": 255,
            "last_command": "on",
            "uptime": 3600,
            "error": None,
        }

        @asynccontextmanager
        async def mock_resilient_session():
            yield test_session

        with patch("src.mqtt.handlers.actuator_handler.resilient_session", mock_resilient_session):
            result = await handler.handle_actuator_status(topic, payload)

        assert result is True

        # Verify state was updated
        actuator_repo = ActuatorRepository(test_session)
        state = await actuator_repo.get_state(sample_esp_device.id, 18)
        assert state is not None
        assert state.current_value == 255
        assert state.state == "on"

    @pytest.mark.asyncio
    async def test_handle_actuator_status_with_error(
        self,
        test_session: AsyncSession,
        sample_esp_device: ESPDevice,
        sample_actuator_config: ActuatorConfig,
    ):
        """Handle actuator status with error reported."""
        handler = ActuatorStatusHandler()

        topic = "kaiser/god/esp/ESP_12AB34CD/actuator/18/status"
        payload = {
            "ts": int(time.time()),
            "esp_id": "ESP_12AB34CD",
            "gpio": 18,
            "actuator_type": "pump",
            "state": "error",
            "value": 0,
            "last_command": "on",
            "uptime": 3600,
            "error": "Motor stalled - overcurrent detected",
        }

        @asynccontextmanager
        async def mock_resilient_session():
            yield test_session

        with patch("src.mqtt.handlers.actuator_handler.resilient_session", mock_resilient_session):
            result = await handler.handle_actuator_status(topic, payload)

        assert result is True  # Should still process, but log error


# =============================================================================
# Full Message Flow Tests (ESP32 → Server → Database)
# =============================================================================


class TestFullMessageFlow:
    """
    End-to-end tests: ESP32 message → Server handler → Database.

    These tests simulate the complete flow as if a real ESP32 sent a message.
    """

    @pytest.mark.asyncio
    async def test_sensor_batch_flow(
        self,
        test_session: AsyncSession,
        sample_esp_device: ESPDevice,
    ):
        """
        Test processing multiple sensor readings.

        Simulates: ESP32 sends batch of sensor data → Server processes each → DB saves
        """
        # Create sensor configs for batch
        sensors = [
            SensorConfig(
                esp_id=sample_esp_device.id,
                gpio=4,
                sensor_name="Soil Temperature",
                sensor_type="DS18B20",
                enabled=True,
                pi_enhanced=False,
            ),
            SensorConfig(
                esp_id=sample_esp_device.id,
                gpio=34,
                sensor_name="pH Sensor",
                sensor_type="ph",
                enabled=True,
                pi_enhanced=True,
            ),
            SensorConfig(
                esp_id=sample_esp_device.id,
                gpio=35,
                sensor_name="Moisture",
                sensor_type="moisture",
                enabled=True,
                pi_enhanced=False,
            ),
        ]
        for s in sensors:
            test_session.add(s)
        await test_session.flush()

        handler = SensorDataHandler()
        handler.publisher = MagicMock()

        # Simulate batch of sensor readings
        sensor_readings = [
            {
                "gpio": 4,
                "sensor_type": "DS18B20",
                "raw": 2150,
                "value": 21.5,
                "unit": "°C",
                "quality": "good",
                "raw_mode": False,
            },
            {
                "gpio": 34,
                "sensor_type": "ph",
                "raw": 2800,
                "value": 0.0,
                "unit": "",
                "quality": "good",
                "raw_mode": False,  # For now, test without Pi-Enhanced
            },
            {
                "gpio": 35,
                "sensor_type": "moisture",
                "raw": 1800,
                "value": 1800,
                "unit": "raw",
                "quality": "good",
                "raw_mode": False,
            },
        ]

        @asynccontextmanager
        async def mock_resilient_session():
            yield test_session

        with patch("src.mqtt.handlers.sensor_handler.resilient_session", mock_resilient_session):
            for reading in sensor_readings:
                topic = f"kaiser/god/esp/ESP_12AB34CD/sensor/{reading['gpio']}/data"
                payload = {
                    "ts": int(time.time()),
                    "esp_id": "ESP_12AB34CD",
                    "raw_mode": reading["raw_mode"],
                    **reading,
                }

                result = await handler.handle_sensor_data(topic, payload)
                assert result is True, f"Failed for GPIO {reading['gpio']}"

        # Verify all data was saved
        sensor_repo = SensorRepository(test_session)

        for reading in sensor_readings:
            saved = await sensor_repo.get_latest_data(sample_esp_device.id, reading["gpio"])
            assert len(saved) >= 1, f"No data saved for GPIO {reading['gpio']}"
            assert saved[0].raw_value == reading["raw"]

    @pytest.mark.asyncio
    async def test_actuator_command_response_flow(
        self,
        test_session: AsyncSession,
        sample_esp_device: ESPDevice,
        sample_actuator_config: ActuatorConfig,
    ):
        """
        Test actuator command → ESP32 response → Server processes status.

        Flow:
        1. Server sends command to ESP32 (not tested here - that's publisher)
        2. ESP32 executes and sends status back
        3. Server processes status update
        """
        handler = ActuatorStatusHandler()

        # ESP32 sends status after executing command
        topic = "kaiser/god/esp/ESP_12AB34CD/actuator/18/status"
        status_payload = {
            "ts": int(time.time()),
            "esp_id": "ESP_12AB34CD",
            "gpio": 18,
            "actuator_type": "pump",
            "state": "on",
            "value": 255,
            "last_command": "on",
            "uptime": 3605,
            "error": None,
        }

        @asynccontextmanager
        async def mock_resilient_session():
            yield test_session

        with patch("src.mqtt.handlers.actuator_handler.resilient_session", mock_resilient_session):
            result = await handler.handle_actuator_status(topic, status_payload)

        assert result is True


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================


class TestEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_handle_malformed_json_topic_mismatch(
        self,
        test_session: AsyncSession,
        sample_esp_device: ESPDevice,
    ):
        """Handle when topic ESP ID doesn't match payload ESP ID."""
        handler = SensorDataHandler()
        handler.publisher = MagicMock()

        # Topic says ESP_12AB34CD but payload says different
        topic = "kaiser/god/esp/ESP_12AB34CD/sensor/34/data"
        payload = {
            "ts": int(time.time()),
            "esp_id": "ESP_DIFFERENT",  # Mismatch!
            "gpio": 34,
            "sensor_type": "ph",
            "raw": 2150,
            "value": 0.0,
            "unit": "",
            "quality": "good",
            "raw_mode": False,
        }

        @asynccontextmanager
        async def mock_resilient_session():
            yield test_session

        # Should use topic ESP ID, but payload should still be processed
        # (or rejected based on implementation)
        with patch("src.mqtt.handlers.sensor_handler.resilient_session", mock_resilient_session):
            result = await handler.handle_sensor_data(topic, payload)

        # Behavior depends on implementation - document the expected behavior
        # Current implementation uses topic ESP ID, ignores payload ESP ID
        assert result is True  # Or False, depending on validation rules

    @pytest.mark.asyncio
    async def test_handle_extreme_values(
        self, test_session: AsyncSession, sample_esp_device: ESPDevice
    ):
        """Handle extreme sensor values."""
        sensor_config = SensorConfig(
            esp_id=sample_esp_device.id,
            gpio=34,
            sensor_name="Test Sensor",
            sensor_type="analog",
            enabled=True,
            pi_enhanced=False,
        )
        test_session.add(sensor_config)
        await test_session.flush()

        handler = SensorDataHandler()
        handler.publisher = MagicMock()

        extreme_values = [0, -1000, 65535, 4294967295, 0.0001, -999999.99]

        @asynccontextmanager
        async def mock_resilient_session():
            yield test_session

        for raw_value in extreme_values:
            topic = "kaiser/god/esp/ESP_12AB34CD/sensor/34/data"
            payload = {
                "ts": int(time.time()),
                "esp_id": "ESP_12AB34CD",
                "gpio": 34,
                "sensor_type": "analog",
                "raw": raw_value,
                "value": raw_value,
                "unit": "raw",
                "quality": "good",
                "raw_mode": False,
            }

            with patch(
                "src.mqtt.handlers.sensor_handler.resilient_session", mock_resilient_session
            ):
                result = await handler.handle_sensor_data(topic, payload)

            assert result is True, f"Should handle extreme value: {raw_value}"

    def test_topic_with_special_characters(self):
        """Topic parsing handles edge cases correctly."""
        # Topics with numbers and underscores in ESP ID
        valid = TopicBuilder.parse_sensor_data_topic("kaiser/god/esp/ESP_00000000/sensor/0/data")
        assert valid is not None

        # Boundary GPIO values
        for gpio in [0, 39]:  # ESP32 GPIO range
            topic = f"kaiser/god/esp/ESP_12AB34CD/sensor/{gpio}/data"
            result = TopicBuilder.parse_sensor_data_topic(topic)
            assert result is not None
            assert result["gpio"] == gpio


# =============================================================================
# Performance and Concurrency Tests
# =============================================================================


class TestPerformance:
    """Test performance under load."""

    @pytest.mark.asyncio
    async def test_rapid_sensor_updates(
        self,
        test_session: AsyncSession,
        sample_esp_device: ESPDevice,
        sample_sensor_config: SensorConfig,
    ):
        """Handle rapid succession of sensor updates."""
        handler = SensorDataHandler()
        handler.publisher = MagicMock()

        @asynccontextmanager
        async def mock_resilient_session():
            yield test_session

        # Simulate 100 rapid updates
        topic = "kaiser/god/esp/ESP_12AB34CD/sensor/34/data"
        base_ts = int(time.time())

        with patch("src.mqtt.handlers.sensor_handler.resilient_session", mock_resilient_session):
            for i in range(100):
                payload = {
                    "ts": base_ts + i,  # Unique timestamp per update to avoid IntegrityError
                    "esp_id": "ESP_12AB34CD",
                    "gpio": 34,
                    "sensor_type": "ph",
                    "raw": 2150 + i,
                    "value": 0.0,
                    "unit": "",
                    "quality": "good",
                    "raw_mode": False,
                }

                result = await handler.handle_sensor_data(topic, payload)
                assert result is True

        # Verify all 100 readings were saved
        sensor_repo = SensorRepository(test_session)
        saved = await sensor_repo.get_latest_data(sample_esp_device.id, 34, limit=100)
        assert len(saved) == 100


# =============================================================================
# Heartbeat Handler Tests
# =============================================================================


class TestHeartbeatHandlerValidation:
    """Test HeartbeatHandler payload validation."""

    @pytest.fixture
    def heartbeat_handler(self):
        """Create HeartbeatHandler."""
        from src.mqtt.handlers.heartbeat_handler import HeartbeatHandler

        return HeartbeatHandler()

    @pytest.fixture
    def valid_heartbeat_payload(self):
        """
        Heartbeat payload matching ACTUAL ESP32 implementation.

        Reference: El Trabajante/src/services/communication/mqtt_client.cpp
        Function: publishHeartbeat() lines 451-462

        ESP32 sends: heap_free (not free_heap)
        Server accepts both for backward compatibility.
        """
        return {
            "esp_id": "ESP_12AB34CD",
            "zone_id": "greenhouse",
            "master_zone_id": "greenhouse-master",
            "zone_assigned": True,
            "ts": int(time.time()),
            "uptime": 3600,
            "heap_free": 245760,  # ESP32 Standard field name
            "wifi_rssi": -65,
            "sensor_count": 3,
            "actuator_count": 2,
        }

    def test_validate_complete_payload(self, heartbeat_handler, valid_heartbeat_payload):
        """Complete heartbeat payload passes validation."""
        result = heartbeat_handler._validate_payload(valid_heartbeat_payload)

        assert result["valid"] is True
        assert result["error"] == ""

    def test_validate_missing_required_fields(self, heartbeat_handler):
        """Heartbeat payload with missing required fields fails."""
        # Server requires these 4 fields (accepts both heap_free and free_heap)
        required_fields = ["ts", "uptime", "heap_free", "wifi_rssi"]

        for field in required_fields:
            payload = {
                "ts": int(time.time()),
                "uptime": 3600,
                "heap_free": 245760,  # ESP32 Standard field name
                "wifi_rssi": -65,
            }
            del payload[field]

            result = heartbeat_handler._validate_payload(payload)

            # Note: heap_free error message says "heap_free or free_heap"
            assert result["valid"] is False, f"Should fail for missing {field}"

    def test_validate_wrong_types(self, heartbeat_handler):
        """Heartbeat payload with wrong types fails."""
        # ts must be int
        result = heartbeat_handler._validate_payload(
            {
                "ts": "not_an_int",
                "uptime": 3600,
                "free_heap": 245760,
                "wifi_rssi": -65,
            }
        )
        assert result["valid"] is False

        # uptime must be int
        result = heartbeat_handler._validate_payload(
            {
                "ts": int(time.time()),
                "uptime": "3600",
                "free_heap": 245760,
                "wifi_rssi": -65,
            }
        )
        assert result["valid"] is False


class TestHeartbeatHandlerProcessing:
    """Test HeartbeatHandler processing with real database."""

    @pytest.mark.asyncio
    async def test_handle_heartbeat_success(
        self,
        test_session: AsyncSession,
        sample_esp_device: ESPDevice,
    ):
        """Successfully process heartbeat and update device status."""
        from src.mqtt.handlers.heartbeat_handler import HeartbeatHandler

        handler = HeartbeatHandler()

        topic = "kaiser/god/esp/ESP_12AB34CD/heartbeat"
        payload = {
            "ts": int(time.time()),
            "uptime": 3600,
            "free_heap": 245760,
            "wifi_rssi": -65,
        }

        @asynccontextmanager
        async def mock_resilient_session():
            yield test_session

        with patch("src.mqtt.handlers.heartbeat_handler.resilient_session", mock_resilient_session):
            result = await handler.handle_heartbeat(topic, payload)

        assert result is True

        # Verify device status was updated
        esp_repo = ESPRepository(test_session)
        device = await esp_repo.get_by_device_id("ESP_12AB34CD")
        assert device.status == "online"

    @pytest.mark.asyncio
    async def test_handle_heartbeat_unknown_device(self, test_session: AsyncSession):
        """Handle heartbeat from unknown device - Auto-Discovery creates device with pending_approval."""
        from src.mqtt.handlers.heartbeat_handler import HeartbeatHandler
        from src.db.repositories.esp_repo import ESPRepository

        handler = HeartbeatHandler()

        topic = "kaiser/god/esp/ESP_UNKNOWN1/heartbeat"
        payload = {
            "ts": int(time.time()),
            "uptime": 3600,
            "free_heap": 245760,
            "wifi_rssi": -65,
        }

        @asynccontextmanager
        async def mock_resilient_session():
            yield test_session

        # Mock MQTTClient for heartbeat ACK (Phase 2)
        mock_mqtt = MagicMock()
        mock_mqtt.publish = MagicMock(return_value=True)

        with patch("src.mqtt.handlers.heartbeat_handler.resilient_session", mock_resilient_session):
            with patch("src.mqtt.client.MQTTClient.get_instance", return_value=mock_mqtt):
                result = await handler.handle_heartbeat(topic, payload)

        # Auto-Discovery: unknown device is registered with pending_approval status
        assert result is True

        # Verify device was created with pending_approval status
        esp_repo = ESPRepository(test_session)
        device = await esp_repo.get_by_device_id("ESP_UNKNOWN1")
        assert device is not None
        assert device.status == "pending_approval"

    @pytest.mark.asyncio
    async def test_lwt_then_first_heartbeat_recovers_online_and_preserves_last_seen_policy(
        self,
        test_session: AsyncSession,
        sample_esp_device: ESPDevice,
    ):
        """LWT offline must preserve heartbeat ts; first valid heartbeat recovers online."""
        from src.mqtt.handlers.heartbeat_handler import HeartbeatHandler
        from src.mqtt.handlers.lwt_handler import LWTHandler

        esp_repo = ESPRepository(test_session)
        previous_heartbeat_ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        await esp_repo.update_status(
            sample_esp_device.device_id,
            "online",
            last_seen=previous_heartbeat_ts,
        )

        @asynccontextmanager
        async def mock_resilient_session():
            yield test_session

        mock_mqtt = MagicMock()
        mock_mqtt.publish = MagicMock(return_value=True)
        mock_ws = AsyncMock()
        mock_contract_repo = MagicMock()
        mock_contract_repo.upsert_terminal_event_authority = AsyncMock(
            return_value=(MagicMock(), False)
        )
        mock_adoption_service = MagicMock()
        mock_adoption_service.clear_cycle = AsyncMock()

        with patch("src.mqtt.handlers.lwt_handler.resilient_session", mock_resilient_session):
            with patch("src.mqtt.handlers.heartbeat_handler.resilient_session", mock_resilient_session):
                with patch("src.mqtt.client.MQTTClient.get_instance", return_value=mock_mqtt):
                    with patch(
                        "src.websocket.manager.WebSocketManager.get_instance",
                        new=AsyncMock(return_value=mock_ws),
                    ):
                        with patch(
                            "src.mqtt.handlers.lwt_handler.CommandContractRepository",
                            return_value=mock_contract_repo,
                        ):
                            with patch(
                                "src.mqtt.handlers.lwt_handler.AuditLogRepository"
                            ) as mock_lwt_audit:
                                with patch(
                                    "src.mqtt.handlers.heartbeat_handler.AuditLogRepository"
                                ) as mock_hb_audit:
                                    with patch(
                                        "src.mqtt.handlers.lwt_handler.get_state_adoption_service",
                                        return_value=mock_adoption_service,
                                    ):
                                        mock_lwt_audit.return_value.log_device_event = AsyncMock()
                                        mock_hb_audit.return_value.log_device_event = AsyncMock()

                                        lwt_handler = LWTHandler()
                                        heartbeat_handler = HeartbeatHandler()
                                        lwt_topic = (
                                            f"kaiser/god/esp/{sample_esp_device.device_id}/system/will"
                                        )
                                        lwt_payload = {
                                            "status": "offline",
                                            "reason": "unexpected_disconnect",
                                            "timestamp": int(time.time()),
                                        }
                                        lwt_result = await lwt_handler.handle_lwt(
                                            lwt_topic, lwt_payload
                                        )
                                        assert lwt_result is True

                                        after_lwt = await esp_repo.get_by_device_id(
                                            sample_esp_device.device_id
                                        )
                                        assert after_lwt is not None
                                        assert after_lwt.status == "offline"
                                        assert after_lwt.last_seen is not None
                                        assert int(after_lwt.last_seen.timestamp()) == int(
                                            previous_heartbeat_ts.timestamp()
                                        )

                                        heartbeat_ts = int(time.time())
                                        heartbeat_topic = (
                                            f"kaiser/god/esp/{sample_esp_device.device_id}/heartbeat"
                                        )
                                        heartbeat_payload = {
                                            "ts": heartbeat_ts,
                                            "uptime": 12,
                                            "free_heap": 210000,
                                            "wifi_rssi": -61,
                                        }
                                        hb_result = await heartbeat_handler.handle_heartbeat(
                                            heartbeat_topic, heartbeat_payload
                                        )
                                        assert hb_result is True
                                        timeout_result = (
                                            await heartbeat_handler.check_device_timeouts()
                                        )
                                        assert timeout_result["timed_out"] == 0

        after_heartbeat = await esp_repo.get_by_device_id(sample_esp_device.device_id)
        assert after_heartbeat is not None
        assert after_heartbeat.status == "online"
        hb_seen_ts = int(after_heartbeat.last_seen.timestamp())
        assert hb_seen_ts >= heartbeat_ts
        assert hb_seen_ts <= heartbeat_ts + 30

    @pytest.mark.asyncio
    async def test_stale_time_valid_payload_does_not_trigger_immediate_timeout(
        self,
        test_session: AsyncSession,
        sample_esp_device: ESPDevice,
    ):
        """Heartbeat with stale ts/time_valid=true must still keep device online."""
        from src.mqtt.handlers.heartbeat_handler import HeartbeatHandler

        handler = HeartbeatHandler()
        esp_repo = ESPRepository(test_session)
        topic = f"kaiser/god/esp/{sample_esp_device.device_id}/heartbeat"
        stale_payload = {
            "ts": int(datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp()),
            "time_valid": True,
            "uptime": 123,
            "free_heap": 220000,
            "wifi_rssi": -58,
        }

        @asynccontextmanager
        async def mock_resilient_session():
            yield test_session

        mock_mqtt = MagicMock()
        mock_mqtt.publish = MagicMock(return_value=True)
        with patch("src.mqtt.handlers.heartbeat_handler.resilient_session", mock_resilient_session):
            with patch("src.mqtt.client.MQTTClient.get_instance", return_value=mock_mqtt):
                before_hb = datetime.now(timezone.utc)
                result = await handler.handle_heartbeat(topic, stale_payload)
                timeout_result = await handler.check_device_timeouts()

        assert result is True
        assert timeout_result["timed_out"] == 0
        device = await esp_repo.get_by_device_id(sample_esp_device.device_id)
        assert device is not None
        assert device.status == "online"
        assert device.last_seen is not None
        assert int(device.last_seen.timestamp()) >= int(before_hb.timestamp())

    @pytest.mark.asyncio
    async def test_long_offline_then_heartbeat_recovers_online_stably(
        self,
        test_session: AsyncSession,
        sample_esp_device: ESPDevice,
    ):
        """Long offline phase followed by heartbeat must recover to stable online."""
        from src.mqtt.handlers.heartbeat_handler import HeartbeatHandler

        handler = HeartbeatHandler()
        esp_repo = ESPRepository(test_session)
        await esp_repo.update_status(
            sample_esp_device.device_id,
            "offline",
            last_seen=datetime.now(timezone.utc) - timedelta(hours=1),
        )

        topic = f"kaiser/god/esp/{sample_esp_device.device_id}/heartbeat"
        payload = {
            "ts": int(time.time()),
            "time_valid": True,
            "uptime": 88,
            "free_heap": 210000,
            "wifi_rssi": -62,
        }

        @asynccontextmanager
        async def mock_resilient_session():
            yield test_session

        mock_mqtt = MagicMock()
        mock_mqtt.publish = MagicMock(return_value=True)
        with patch("src.mqtt.handlers.heartbeat_handler.resilient_session", mock_resilient_session):
            with patch("src.mqtt.client.MQTTClient.get_instance", return_value=mock_mqtt):
                result = await handler.handle_heartbeat(topic, payload)
                timeout_result = await handler.check_device_timeouts()

        assert result is True
        assert timeout_result["timed_out"] == 0
        recovered = await esp_repo.get_by_device_id(sample_esp_device.device_id)
        assert recovered is not None
        assert recovered.status == "online"


# =============================================================================
# Pi-Enhanced Processing Tests
# =============================================================================


class TestPiEnhancedProcessing:
    """
    Test Pi-Enhanced sensor processing flow.

    Flow:
    1. ESP32 sends raw sensor data with raw_mode=True
    2. Server loads appropriate processor from library_loader
    3. Processor converts raw value to physical measurement
    4. Server publishes processed value back to ESP32
    5. Server saves both raw and processed values to database
    """

    @pytest.mark.asyncio
    async def test_pi_enhanced_triggers_for_raw_mode_sensor(
        self,
        test_session: AsyncSession,
        sample_esp_device: ESPDevice,
    ):
        """Pi-Enhanced processing triggered when raw_mode=True and pi_enhanced enabled."""
        # Create Pi-Enhanced sensor config
        sensor_config = SensorConfig(
            esp_id=sample_esp_device.id,
            gpio=34,
            sensor_name="pH Sensor",
            sensor_type="ph",
            enabled=True,
            pi_enhanced=True,
            calibration_data={"offset": 0.0, "slope": 1.0},
        )
        test_session.add(sensor_config)
        await test_session.flush()

        handler = SensorDataHandler()
        mock_publisher = MagicMock()
        handler.publisher = mock_publisher

        topic = "kaiser/god/esp/ESP_12AB34CD/sensor/34/data"
        payload = {
            "ts": int(time.time()),
            "esp_id": "ESP_12AB34CD",
            "gpio": 34,
            "sensor_type": "ph",
            "raw": 2150,
            "value": 0.0,  # ESP sends 0 because raw_mode
            "unit": "",
            "quality": "good",
            "raw_mode": True,  # Triggers Pi-Enhanced
        }

        @asynccontextmanager
        async def mock_resilient_session():
            yield test_session

        # Mock the library loader to return a fake processor
        mock_processor = MagicMock()
        mock_processor.process.return_value = MagicMock(value=7.2, unit="pH", quality="good")

        # Mock at the location where it's imported in _trigger_pi_enhanced_processing
        with patch("src.mqtt.handlers.sensor_handler.resilient_session", mock_resilient_session):
            with patch("src.sensors.library_loader.get_library_loader") as mock_loader:
                mock_loader_instance = MagicMock()
                mock_loader_instance.get_processor.return_value = mock_processor
                mock_loader.return_value = mock_loader_instance

                result = await handler.handle_sensor_data(topic, payload)

        assert result is True

        # Verify processor was called
        mock_processor.process.assert_called_once()

        # Verify processed data was published back
        mock_publisher.publish_pi_enhanced_response.assert_called_once()

    @pytest.mark.asyncio
    async def test_pi_enhanced_skipped_for_local_mode(
        self,
        test_session: AsyncSession,
        sample_esp_device: ESPDevice,
    ):
        """Pi-Enhanced processing skipped when raw_mode=False."""
        sensor_config = SensorConfig(
            esp_id=sample_esp_device.id,
            gpio=34,
            sensor_name="Temperature Sensor",
            sensor_type="temperature",
            enabled=True,
            pi_enhanced=True,  # Config says Pi-Enhanced...
        )
        test_session.add(sensor_config)
        await test_session.flush()

        handler = SensorDataHandler()
        mock_publisher = MagicMock()
        handler.publisher = mock_publisher

        topic = "kaiser/god/esp/ESP_12AB34CD/sensor/34/data"
        payload = {
            "ts": int(time.time()),
            "esp_id": "ESP_12AB34CD",
            "gpio": 34,
            "sensor_type": "temperature",
            "raw": 2150,
            "value": 23.5,  # ESP already processed
            "unit": "°C",
            "quality": "good",
            "raw_mode": False,  # ...but ESP processed locally
        }

        @asynccontextmanager
        async def mock_resilient_session():
            yield test_session

        with patch("src.mqtt.handlers.sensor_handler.resilient_session", mock_resilient_session):
            result = await handler.handle_sensor_data(topic, payload)

        assert result is True

        # Pi-Enhanced response should NOT be published
        mock_publisher.publish_pi_enhanced_response.assert_not_called()

        # Verify data saved with "local" processing mode
        sensor_repo = SensorRepository(test_session)
        saved = await sensor_repo.get_latest_data(sample_esp_device.id, 34)
        assert len(saved) >= 1
        assert saved[0].processing_mode == "local"
        assert saved[0].processed_value == 23.5

    @pytest.mark.asyncio
    async def test_pi_enhanced_fallback_on_processor_error(
        self,
        test_session: AsyncSession,
        sample_esp_device: ESPDevice,
    ):
        """Pi-Enhanced gracefully handles processor errors."""
        sensor_config = SensorConfig(
            esp_id=sample_esp_device.id,
            gpio=34,
            sensor_name="pH Sensor",
            sensor_type="ph",
            enabled=True,
            pi_enhanced=True,
        )
        test_session.add(sensor_config)
        await test_session.flush()

        handler = SensorDataHandler()
        mock_publisher = MagicMock()
        handler.publisher = mock_publisher

        topic = "kaiser/god/esp/ESP_12AB34CD/sensor/34/data"
        payload = {
            "ts": int(time.time()),
            "esp_id": "ESP_12AB34CD",
            "gpio": 34,
            "sensor_type": "ph",
            "raw": 2150,
            "value": 0.0,
            "unit": "",
            "quality": "good",
            "raw_mode": True,
        }

        @asynccontextmanager
        async def mock_resilient_session():
            yield test_session

        # Mock the library loader to return None (no processor found)
        with patch("src.mqtt.handlers.sensor_handler.resilient_session", mock_resilient_session):
            with patch("src.sensors.library_loader.get_library_loader") as mock_loader:
                mock_loader_instance = MagicMock()
                mock_loader_instance.get_processor.return_value = None
                mock_loader_instance.get_available_sensors.return_value = []
                mock_loader.return_value = mock_loader_instance

                result = await handler.handle_sensor_data(topic, payload)

        # Should still save raw data even if processing failed
        assert result is True

        # Verify data saved with error quality
        sensor_repo = SensorRepository(test_session)
        saved = await sensor_repo.get_latest_data(sample_esp_device.id, 34)
        assert len(saved) >= 1
        assert saved[0].quality == "error"


# =============================================================================
# Complete Workflow Tests
# =============================================================================


class TestCompleteWorkflows:
    """
    End-to-end workflow tests simulating real ESP32 behavior.

    These tests verify complete scenarios as they would occur in production.
    """

    @pytest.mark.asyncio
    async def test_greenhouse_temperature_control_flow(
        self,
        test_session: AsyncSession,
        sample_esp_device: ESPDevice,
    ):
        """
        Complete greenhouse automation flow:
        1. ESP32 sends temperature reading
        2. Server processes and saves
        3. Server could trigger actuator (logic not tested here)
        """
        from src.mqtt.handlers.sensor_handler import SensorDataHandler

        # Setup sensor config
        temp_sensor = SensorConfig(
            esp_id=sample_esp_device.id,
            gpio=4,
            sensor_name="Greenhouse Temperature",
            sensor_type="temperature",
            enabled=True,
            pi_enhanced=False,
        )
        test_session.add(temp_sensor)
        await test_session.flush()

        handler = SensorDataHandler()
        handler.publisher = MagicMock()

        # Simulate temperature readings over time
        readings = [
            {"raw": 2350, "value": 23.5, "quality": "good"},
            {"raw": 2400, "value": 24.0, "quality": "good"},
            {"raw": 2500, "value": 25.0, "quality": "good"},
            {"raw": 2600, "value": 26.0, "quality": "fair"},  # Getting warm
            {"raw": 2800, "value": 28.0, "quality": "poor"},  # Too hot!
        ]

        @asynccontextmanager
        async def mock_resilient_session():
            yield test_session

        base_ts = int(time.time())
        with patch("src.mqtt.handlers.sensor_handler.resilient_session", mock_resilient_session):
            for idx, reading in enumerate(readings):
                topic = "kaiser/god/esp/ESP_12AB34CD/sensor/4/data"
                payload = {
                    "ts": base_ts + idx,  # Unique timestamp per reading to avoid IntegrityError
                    "esp_id": "ESP_12AB34CD",
                    "gpio": 4,
                    "sensor_type": "temperature",
                    "raw": reading["raw"],
                    "value": reading["value"],
                    "unit": "°C",
                    "quality": reading["quality"],
                    "raw_mode": False,
                }

                result = await handler.handle_sensor_data(topic, payload)
                assert result is True

        # Verify all readings saved
        sensor_repo = SensorRepository(test_session)
        saved = await sensor_repo.get_latest_data(sample_esp_device.id, 4, limit=5)
        assert len(saved) == 5

        # Verify most recent is hottest
        assert saved[0].processed_value == 28.0
        assert saved[0].quality == "poor"

    @pytest.mark.asyncio
    async def test_multi_sensor_esp_batch_processing(
        self,
        test_session: AsyncSession,
        sample_esp_device: ESPDevice,
    ):
        """
        Process multiple sensors from single ESP32.

        Simulates real greenhouse ESP32 with:
        - Temperature sensor (GPIO 4)
        - Humidity sensor (GPIO 21)
        - Moisture sensor (GPIO 34)
        - pH sensor (GPIO 35)
        """
        from src.mqtt.handlers.sensor_handler import SensorDataHandler

        # Create all sensor configs
        sensors = [
            SensorConfig(
                esp_id=sample_esp_device.id,
                gpio=4,
                sensor_name="Temperature",
                sensor_type="temperature",
                enabled=True,
                pi_enhanced=False,
            ),
            SensorConfig(
                esp_id=sample_esp_device.id,
                gpio=21,
                sensor_name="Humidity",
                sensor_type="humidity",
                enabled=True,
                pi_enhanced=False,
            ),
            SensorConfig(
                esp_id=sample_esp_device.id,
                gpio=34,
                sensor_name="Moisture",
                sensor_type="moisture",
                enabled=True,
                pi_enhanced=False,
            ),
            SensorConfig(
                esp_id=sample_esp_device.id,
                gpio=35,
                sensor_name="pH",
                sensor_type="ph",
                enabled=True,
                pi_enhanced=True,  # pH uses Pi-Enhanced
            ),
        ]
        for s in sensors:
            test_session.add(s)
        await test_session.flush()

        handler = SensorDataHandler()
        handler.publisher = MagicMock()

        # Simulate batch of readings
        batch = [
            {"gpio": 4, "sensor_type": "temperature", "raw": 2350, "value": 23.5, "unit": "°C"},
            {"gpio": 21, "sensor_type": "humidity", "raw": 650, "value": 65.0, "unit": "%RH"},
            {"gpio": 34, "sensor_type": "moisture", "raw": 1800, "value": 1800, "unit": "raw"},
            {"gpio": 35, "sensor_type": "ph", "raw": 2150, "value": 0.0, "unit": ""},  # Pi-Enhanced
        ]

        @asynccontextmanager
        async def mock_resilient_session():
            yield test_session

        # Mock processor for pH
        mock_processor = MagicMock()
        mock_processor.process.return_value = MagicMock(value=7.2, unit="pH", quality="good")

        with patch("src.mqtt.handlers.sensor_handler.resilient_session", mock_resilient_session):
            with patch("src.sensors.library_loader.get_library_loader") as mock_loader:
                mock_loader_instance = MagicMock()
                mock_loader_instance.get_processor.return_value = mock_processor
                mock_loader.return_value = mock_loader_instance

                for reading in batch:
                    topic = f"kaiser/god/esp/ESP_12AB34CD/sensor/{reading['gpio']}/data"
                    payload = {
                        "ts": int(time.time()),
                        "esp_id": "ESP_12AB34CD",
                        "gpio": reading["gpio"],
                        "sensor_type": reading["sensor_type"],
                        "raw": reading["raw"],
                        "value": reading["value"],
                        "unit": reading["unit"],
                        "quality": "good",
                        "raw_mode": reading["gpio"] == 35,  # Only pH is raw_mode
                    }

                    result = await handler.handle_sensor_data(topic, payload)
                    assert result is True, f"Failed for GPIO {reading['gpio']}"

        # Verify all sensors have data
        sensor_repo = SensorRepository(test_session)
        for reading in batch:
            saved = await sensor_repo.get_latest_data(sample_esp_device.id, reading["gpio"])
            assert len(saved) >= 1, f"No data for GPIO {reading['gpio']}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
