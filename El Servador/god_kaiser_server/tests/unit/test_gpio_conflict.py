"""
Unit Tests: GPIO Conflict Detection

Tests for GPIO conflict detection including:
- System-reserved pins (0,1,2,3,6-11)
- Input-only pins for actuators (34-39 on ESP32-WROOM)
- Sensor/Actuator conflicts on same GPIO
- Cross-ESP GPIO isolation (same GPIO on different ESPs is allowed)
- Board-specific constraints (ESP32-WROOM vs XIAO ESP32-C3)

SAFETY-CRITICAL: GPIO conflicts can cause hardware damage or incorrect
behavior. These tests verify proper pin protection.
"""

import pytest
import uuid
from unittest.mock import MagicMock, AsyncMock

from src.services.gpio_validation_service import (
    GpioValidationService,
    GpioConflictType,
    GpioValidationResult,
    SYSTEM_RESERVED_PINS,
)


class TestSystemPinProtection:
    """Tests for system-reserved pin protection."""

    @pytest.mark.critical
    @pytest.mark.gpio
    @pytest.mark.asyncio
    async def test_system_pins_rejected(self):
        """System-reserved pins (0,1,2,3,6-11) must be rejected."""
        # ARRANGE
        mock_session = MagicMock()
        mock_sensor_repo = MagicMock()
        mock_actuator_repo = MagicMock()
        mock_esp_repo = MagicMock()

        mock_esp = MagicMock(
            id=uuid.uuid4(),
            hardware_type="ESP32_WROOM",
        )
        mock_esp_repo.get_by_id = AsyncMock(return_value=mock_esp)

        service = GpioValidationService(
            session=mock_session,
            sensor_repo=mock_sensor_repo,
            actuator_repo=mock_actuator_repo,
            esp_repo=mock_esp_repo,
        )

        # ACT & ASSERT - Test each system pin
        for gpio in SYSTEM_RESERVED_PINS:
            result = await service.validate_gpio_available(
                esp_db_id=mock_esp.id,
                gpio=gpio,
                purpose="sensor",
            )

            assert result.available is False, f"GPIO {gpio} (system pin) should be rejected"
            assert (
                result.conflict_type == GpioConflictType.SYSTEM
            ), f"GPIO {gpio} conflict type should be SYSTEM"

    @pytest.mark.critical
    @pytest.mark.gpio
    @pytest.mark.asyncio
    async def test_gpio_0_flash_boot_rejected(self):
        """GPIO 0 (Boot-Strapping) must be rejected with clear message."""
        # ARRANGE
        mock_session = MagicMock()
        mock_sensor_repo = MagicMock()
        mock_actuator_repo = MagicMock()
        mock_esp_repo = MagicMock()

        mock_esp = MagicMock(
            id=uuid.uuid4(),
            hardware_type="ESP32_WROOM",
        )
        mock_esp_repo.get_by_id = AsyncMock(return_value=mock_esp)

        service = GpioValidationService(
            session=mock_session,
            sensor_repo=mock_sensor_repo,
            actuator_repo=mock_actuator_repo,
            esp_repo=mock_esp_repo,
        )

        # ACT
        result = await service.validate_gpio_available(
            esp_db_id=mock_esp.id,
            gpio=0,  # Boot-strapping pin
            purpose="sensor",
        )

        # ASSERT
        assert result.available is False, "GPIO 0 (boot-strapping) should be rejected"
        assert (
            "system" in result.message.lower() or "boot" in result.message.lower()
        ), f"Error message should explain why GPIO 0 is reserved, got: {result.message}"


class TestInputOnlyPins:
    """Tests for input-only pin restrictions."""

    @pytest.mark.gpio
    @pytest.mark.asyncio
    async def test_input_only_pins_rejected_for_actuator(self):
        """Input-only pins (34-39) must be rejected for actuators."""
        # ARRANGE
        mock_session = MagicMock()
        mock_sensor_repo = MagicMock()
        mock_actuator_repo = MagicMock()
        mock_esp_repo = MagicMock()

        mock_esp = MagicMock(
            id=uuid.uuid4(),
            hardware_type="ESP32_WROOM",
        )
        mock_esp_repo.get_by_id = AsyncMock(return_value=mock_esp)

        service = GpioValidationService(
            session=mock_session,
            sensor_repo=mock_sensor_repo,
            actuator_repo=mock_actuator_repo,
            esp_repo=mock_esp_repo,
        )

        # Test input-only pins
        input_only_pins = [34, 35, 36, 39]  # ESP32-WROOM

        for gpio in input_only_pins:
            # ACT
            result = await service.validate_gpio_available(
                esp_db_id=mock_esp.id,
                gpio=gpio,
                purpose="actuator",  # Actuators need OUTPUT mode
            )

            # ASSERT
            assert (
                result.available is False
            ), f"GPIO {gpio} (input-only) should be rejected for actuator"
            assert (
                "input" in result.message.lower()
            ), f"Error should mention input-only, got: {result.message}"

    @pytest.mark.gpio
    @pytest.mark.asyncio
    async def test_input_only_pins_allowed_for_sensor(self):
        """Input-only pins can be used for sensors (INPUT mode)."""
        # ARRANGE
        mock_session = MagicMock()
        mock_sensor_repo = MagicMock()
        mock_actuator_repo = MagicMock()
        mock_esp_repo = MagicMock()

        mock_esp = MagicMock(
            id=uuid.uuid4(),
            hardware_type="ESP32_WROOM",
        )
        mock_esp_repo.get_by_id = AsyncMock(return_value=mock_esp)

        # No existing sensors/actuators
        mock_sensor_repo.get_by_esp_and_gpio = AsyncMock(return_value=None)
        mock_actuator_repo.get_by_esp_and_gpio = AsyncMock(return_value=None)

        service = GpioValidationService(
            session=mock_session,
            sensor_repo=mock_sensor_repo,
            actuator_repo=mock_actuator_repo,
            esp_repo=mock_esp_repo,
        )

        # ACT - GPIO 34 (input-only) as sensor
        result = await service.validate_gpio_available(
            esp_db_id=mock_esp.id,
            gpio=34,
            purpose="sensor",  # Sensors use INPUT mode
        )

        # ASSERT
        assert (
            result.available is True
        ), f"GPIO 34 (input-only) should be allowed for sensor, got: {result.message}"


class TestSensorActuatorConflict:
    """Tests for sensor/actuator GPIO conflicts."""

    @pytest.mark.gpio
    @pytest.mark.asyncio
    async def test_actuator_on_sensor_gpio_rejected(self):
        """Actuator cannot use GPIO already assigned to sensor."""
        # ARRANGE
        mock_session = MagicMock()
        mock_sensor_repo = MagicMock()
        mock_actuator_repo = MagicMock()
        mock_esp_repo = MagicMock()

        esp_id = uuid.uuid4()
        mock_esp = MagicMock(
            id=esp_id,
            hardware_type="ESP32_WROOM",
        )
        mock_esp_repo.get_by_id = AsyncMock(return_value=mock_esp)

        # Existing sensor on GPIO 25
        mock_sensor = MagicMock(
            id=uuid.uuid4(),
            gpio=25,
            sensor_type="ds18b20",
            sensor_name="Temperature Sensor",
        )
        mock_sensor_repo.get_by_esp_and_gpio = AsyncMock(return_value=mock_sensor)
        mock_actuator_repo.get_by_esp_and_gpio = AsyncMock(return_value=None)

        service = GpioValidationService(
            session=mock_session,
            sensor_repo=mock_sensor_repo,
            actuator_repo=mock_actuator_repo,
            esp_repo=mock_esp_repo,
        )

        # ACT - Try to add actuator on GPIO 25 (occupied by sensor)
        result = await service.validate_gpio_available(
            esp_db_id=esp_id,
            gpio=25,
            purpose="actuator",
        )

        # ASSERT
        assert (
            result.available is False
        ), "Actuator should not be allowed on GPIO already used by sensor"
        assert (
            result.conflict_type == GpioConflictType.SENSOR
        ), f"Conflict type should be SENSOR, got {result.conflict_type}"

    @pytest.mark.gpio
    @pytest.mark.asyncio
    async def test_sensor_on_actuator_gpio_rejected(self):
        """Sensor cannot use GPIO already assigned to actuator."""
        # ARRANGE
        mock_session = MagicMock()
        mock_sensor_repo = MagicMock()
        mock_actuator_repo = MagicMock()
        mock_esp_repo = MagicMock()

        esp_id = uuid.uuid4()
        mock_esp = MagicMock(
            id=esp_id,
            hardware_type="ESP32_WROOM",
        )
        mock_esp_repo.get_by_id = AsyncMock(return_value=mock_esp)

        # No sensor on GPIO 25
        mock_sensor_repo.get_by_esp_and_gpio = AsyncMock(return_value=None)

        # Existing actuator on GPIO 25
        mock_actuator = MagicMock(
            id=uuid.uuid4(),
            gpio=25,
            actuator_type="pump",
            actuator_name="Water Pump",
        )
        mock_actuator_repo.get_by_esp_and_gpio = AsyncMock(return_value=mock_actuator)

        service = GpioValidationService(
            session=mock_session,
            sensor_repo=mock_sensor_repo,
            actuator_repo=mock_actuator_repo,
            esp_repo=mock_esp_repo,
        )

        # ACT - Try to add sensor on GPIO 25 (occupied by actuator)
        result = await service.validate_gpio_available(
            esp_db_id=esp_id,
            gpio=25,
            purpose="sensor",
        )

        # ASSERT
        assert (
            result.available is False
        ), "Sensor should not be allowed on GPIO already used by actuator"
        assert (
            result.conflict_type == GpioConflictType.ACTUATOR
        ), f"Conflict type should be ACTUATOR, got {result.conflict_type}"


class TestCrossESPIsolation:
    """Tests for GPIO isolation between different ESPs."""

    @pytest.mark.gpio
    @pytest.mark.asyncio
    async def test_same_gpio_different_esp_allowed(self):
        """Same GPIO on different ESP devices should be allowed."""
        # ARRANGE
        mock_session = MagicMock()
        mock_sensor_repo = MagicMock()
        mock_actuator_repo = MagicMock()
        mock_esp_repo = MagicMock()

        esp1_id = uuid.uuid4()
        esp2_id = uuid.uuid4()

        mock_esp2 = MagicMock(
            id=esp2_id,
            hardware_type="ESP32_WROOM",
        )
        mock_esp_repo.get_by_id = AsyncMock(return_value=mock_esp2)

        # ESP1 has sensor on GPIO 25 (but we're checking ESP2)
        # ESP2 has no sensor on GPIO 25
        mock_sensor_repo.get_by_esp_and_gpio = AsyncMock(return_value=None)
        mock_actuator_repo.get_by_esp_and_gpio = AsyncMock(return_value=None)

        service = GpioValidationService(
            session=mock_session,
            sensor_repo=mock_sensor_repo,
            actuator_repo=mock_actuator_repo,
            esp_repo=mock_esp_repo,
        )

        # ACT - Add sensor on GPIO 25 on ESP2 (ESP1 already uses GPIO 25)
        result = await service.validate_gpio_available(
            esp_db_id=esp2_id,
            gpio=25,
            purpose="sensor",
        )

        # ASSERT
        assert (
            result.available is True
        ), f"GPIO 25 on ESP2 should be allowed even if ESP1 uses it, got: {result.message}"


class TestBoardSpecificConstraints:
    """Tests for board-specific GPIO constraints."""

    @pytest.mark.gpio
    @pytest.mark.asyncio
    async def test_xiao_esp32c3_gpio_range(self):
        """XIAO ESP32-C3 has limited GPIO range (0-21)."""
        # ARRANGE
        mock_session = MagicMock()
        mock_sensor_repo = MagicMock()
        mock_actuator_repo = MagicMock()
        mock_esp_repo = MagicMock()

        mock_esp = MagicMock(
            id=uuid.uuid4(),
            hardware_type="XIAO_ESP32_C3",  # Different board!
        )
        mock_esp_repo.get_by_id = AsyncMock(return_value=mock_esp)

        service = GpioValidationService(
            session=mock_session,
            sensor_repo=mock_sensor_repo,
            actuator_repo=mock_actuator_repo,
            esp_repo=mock_esp_repo,
        )

        # ACT - Try GPIO 22 (valid on WROOM, invalid on C3)
        result = await service.validate_gpio_available(
            esp_db_id=mock_esp.id,
            gpio=22,
            purpose="sensor",
        )

        # ASSERT
        assert (
            result.available is False
        ), f"GPIO 22 should be rejected on XIAO ESP32-C3 (max 21), got: {result.message}"
        assert (
            "range" in result.message.lower()
        ), f"Error should mention GPIO range, got: {result.message}"

    @pytest.mark.gpio
    @pytest.mark.asyncio
    async def test_xiao_esp32c3_no_input_only_pins(self):
        """XIAO ESP32-C3 has no input-only pins (all bidirectional)."""
        # ARRANGE
        mock_session = MagicMock()
        mock_sensor_repo = MagicMock()
        mock_actuator_repo = MagicMock()
        mock_esp_repo = MagicMock()

        mock_esp = MagicMock(
            id=uuid.uuid4(),
            hardware_type="XIAO_ESP32_C3",
        )
        mock_esp_repo.get_by_id = AsyncMock(return_value=mock_esp)

        # No existing sensors/actuators
        mock_sensor_repo.get_by_esp_and_gpio = AsyncMock(return_value=None)
        mock_actuator_repo.get_by_esp_and_gpio = AsyncMock(return_value=None)

        service = GpioValidationService(
            session=mock_session,
            sensor_repo=mock_sensor_repo,
            actuator_repo=mock_actuator_repo,
            esp_repo=mock_esp_repo,
        )

        # ACT - GPIO 10 as actuator (would fail on WROOM if it was input-only)
        result = await service.validate_gpio_available(
            esp_db_id=mock_esp.id,
            gpio=10,  # Valid on C3, within range 0-21
            purpose="actuator",
        )

        # GPIO 10 is a system pin (Flash SPI D3), should still be rejected
        # But the test verifies input-only logic doesn't apply
        # Let's test with a valid GPIO like GPIO 20
        result = await service.validate_gpio_available(
            esp_db_id=mock_esp.id,
            gpio=20,  # Valid on C3, not system pin
            purpose="actuator",
        )

        # ASSERT
        assert (
            result.available is True
        ), f"GPIO 20 as actuator on XIAO C3 should be allowed (no input-only pins), got: {result.message}"
