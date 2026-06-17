"""
Unit Tests: PWM Value Validation

CRITICAL SAFETY TESTS: These tests verify that PWM values are correctly
validated to prevent unsafe actuator states.

PWM Value Range:
- Server uses 0.0 - 1.0 (normalized float)
- ESP32 internally converts to 0-255 (8-bit PWM)
- Sending 0-255 values directly is a common error!

Safety Constraints:
- Values < 0.0 MUST be rejected
- Values > 1.0 MUST be rejected
- Emergency stop MUST block all commands
- Actuator-specific min/max values enforced
"""

import pytest
from unittest.mock import MagicMock, AsyncMock

from src.services.safety_service import SafetyService, SafetyCheckResult


@pytest.fixture(autouse=True)
def clear_emergency_stop_state():
    """Reset SafetyService global E-Stop state before and after each test."""
    SafetyService._global_emergency_stop_active.clear()
    yield
    SafetyService._global_emergency_stop_active.clear()


class TestPWMValueRangeValidation:
    """Tests for PWM value range validation (0.0 - 1.0)."""

    @pytest.mark.critical
    @pytest.mark.pwm
    @pytest.mark.asyncio
    async def test_pwm_value_below_zero_rejected(self):
        """PWM value < 0.0 must be rejected."""
        # ARRANGE
        mock_actuator_repo = MagicMock()
        mock_esp_repo = MagicMock()

        service = SafetyService(
            actuator_repo=mock_actuator_repo,
            esp_repo=mock_esp_repo,
        )

        # ACT
        result = await service.validate_actuator_command(
            esp_id="ESP_TEST001",
            gpio=25,
            command="PWM",
            value=-0.1,  # Invalid: below 0.0
        )

        # ASSERT
        assert result.valid is False, "Value -0.1 should be rejected (below 0.0)"
        assert (
            "out of range" in result.error.lower()
        ), f"Error should mention 'out of range', got: {result.error}"

    @pytest.mark.critical
    @pytest.mark.pwm
    @pytest.mark.asyncio
    async def test_pwm_value_above_one_rejected(self):
        """PWM value > 1.0 must be rejected."""
        # ARRANGE
        mock_actuator_repo = MagicMock()
        mock_esp_repo = MagicMock()

        service = SafetyService(
            actuator_repo=mock_actuator_repo,
            esp_repo=mock_esp_repo,
        )

        # ACT
        result = await service.validate_actuator_command(
            esp_id="ESP_TEST001",
            gpio=25,
            command="PWM",
            value=1.1,  # Invalid: above 1.0
        )

        # ASSERT
        assert result.valid is False, "Value 1.1 should be rejected (above 1.0)"
        assert (
            "out of range" in result.error.lower()
        ), f"Error should mention 'out of range', got: {result.error}"

    @pytest.mark.critical
    @pytest.mark.pwm
    @pytest.mark.asyncio
    async def test_pwm_value_255_rejected_with_warning(self):
        """PWM value 255 (8-bit scale) must be rejected with helpful error."""
        # ARRANGE
        mock_actuator_repo = MagicMock()
        mock_esp_repo = MagicMock()

        service = SafetyService(
            actuator_repo=mock_actuator_repo,
            esp_repo=mock_esp_repo,
        )

        # ACT
        result = await service.validate_actuator_command(
            esp_id="ESP_TEST001",
            gpio=25,
            command="PWM",
            value=255.0,  # Common error: using 0-255 instead of 0.0-1.0
        )

        # ASSERT
        assert result.valid is False, "Value 255.0 should be rejected (not using 0.0-1.0 scale)"
        assert (
            "0.0-1.0" in result.error or "0-255" in result.error
        ), f"Error should mention correct scale, got: {result.error}"

    @pytest.mark.pwm
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "valid_value",
        [
            0.0,  # Minimum (OFF)
            0.001,  # Just above minimum
            0.25,  # 25% - fractional
            0.33,  # 33% - fractional
            0.5,  # Middle (50%)
            0.75,  # 75% - fractional
            0.999,  # Just below maximum
            1.0,  # Maximum (FULL ON)
        ],
    )
    async def test_pwm_valid_values_accepted(self, valid_value):
        """Valid PWM values (0.0-1.0) pass initial validation."""
        # ARRANGE
        mock_actuator_repo = MagicMock()
        mock_esp_repo = MagicMock()
        mock_esp_repo.get_by_device_id = AsyncMock(return_value=MagicMock(id="uuid-1"))

        mock_actuator_config = MagicMock(
            min_value=0.0,
            max_value=1.0,
            enabled=True,
            actuator_name="Test Pump",
        )
        mock_actuator_repo.get_by_esp_and_gpio = AsyncMock(return_value=mock_actuator_config)
        mock_actuator_repo.get_state = AsyncMock(return_value=None)  # No existing state
        mock_actuator_repo.get_by_esp = AsyncMock(
            return_value=[mock_actuator_config]
        )  # For conflict check

        service = SafetyService(
            actuator_repo=mock_actuator_repo,
            esp_repo=mock_esp_repo,
        )

        # ACT
        result = await service.validate_actuator_command(
            esp_id="ESP_TEST001",
            gpio=25,
            command="PWM",
            value=valid_value,
        )

        # ASSERT
        assert (
            result.valid is True
        ), f"Value {valid_value} should be accepted (within 0.0-1.0), got error: {result.error}"


class TestEmergencyStopBlocksCommands:
    """Tests for emergency stop blocking PWM commands."""

    @pytest.mark.critical
    @pytest.mark.pwm
    @pytest.mark.safety
    @pytest.mark.asyncio
    async def test_emergency_stop_blocks_pwm_command(self):
        """PWM command must be rejected when emergency stop is active."""
        # ARRANGE
        mock_actuator_repo = MagicMock()
        mock_esp_repo = MagicMock()

        service = SafetyService(
            actuator_repo=mock_actuator_repo,
            esp_repo=mock_esp_repo,
        )

        # Activate emergency stop for this ESP
        await service.emergency_stop_esp("ESP_TEST001")

        # ACT
        result = await service.validate_actuator_command(
            esp_id="ESP_TEST001",
            gpio=25,
            command="PWM",
            value=0.5,  # Valid value, but E-Stop is active
        )

        # ASSERT
        assert result.valid is False, "PWM command should be rejected during emergency stop"
        assert (
            "emergency" in result.error.lower()
        ), f"Error should mention emergency stop, got: {result.error}"

    @pytest.mark.critical
    @pytest.mark.pwm
    @pytest.mark.safety
    @pytest.mark.asyncio
    async def test_global_emergency_stop_blocks_all_commands(self):
        """Global emergency stop blocks commands to all ESPs."""
        # ARRANGE
        mock_actuator_repo = MagicMock()
        mock_esp_repo = MagicMock()

        service = SafetyService(
            actuator_repo=mock_actuator_repo,
            esp_repo=mock_esp_repo,
        )

        # Activate GLOBAL emergency stop
        await service.emergency_stop_all()

        # ACT - Try commands on different ESPs
        result1 = await service.validate_actuator_command(
            esp_id="ESP_001",
            gpio=25,
            command="PWM",
            value=0.5,
        )
        result2 = await service.validate_actuator_command(
            esp_id="ESP_002",
            gpio=25,
            command="PWM",
            value=0.5,
        )

        # ASSERT
        assert result1.valid is False, "ESP_001 command should be blocked by global E-Stop"
        assert result2.valid is False, "ESP_002 command should be blocked by global E-Stop"
        assert (
            "global" in result1.error.lower() or "emergency" in result1.error.lower()
        ), f"Error should mention emergency, got: {result1.error}"


class TestActuatorSpecificLimits:
    """Tests for actuator-specific min/max value limits."""

    @pytest.mark.pwm
    @pytest.mark.asyncio
    async def test_value_outside_actuator_limits_rejected(self):
        """Value outside actuator's configured min/max is rejected."""
        # ARRANGE
        mock_actuator_repo = MagicMock()
        mock_esp_repo = MagicMock()
        mock_esp_repo.get_by_device_id = AsyncMock(return_value=MagicMock(id="uuid-1"))

        # Actuator configured with limited range (safety pump: 20%-80%)
        mock_actuator_config = MagicMock(
            min_value=0.2,  # 20% minimum
            max_value=0.8,  # 80% maximum
            enabled=True,
            actuator_name="Safety Pump",
        )
        mock_actuator_repo.get_by_esp_and_gpio = AsyncMock(return_value=mock_actuator_config)
        mock_actuator_repo.get_state = AsyncMock(return_value=None)
        mock_actuator_repo.get_by_esp = AsyncMock(return_value=[mock_actuator_config])

        service = SafetyService(
            actuator_repo=mock_actuator_repo,
            esp_repo=mock_esp_repo,
        )

        # ACT - Try value below actuator's min
        result = await service.check_safety_constraints(
            esp_id="ESP_TEST001",
            gpio=25,
            value=0.1,  # Below actuator's min_value of 0.2
        )

        # ASSERT
        assert result.valid is False, "Value 0.1 should be rejected (below actuator min 0.2)"
        assert (
            "out of" in result.error.lower() or "range" in result.error.lower()
        ), f"Error should mention range violation, got: {result.error}"

    @pytest.mark.pwm
    @pytest.mark.asyncio
    async def test_disabled_actuator_rejected(self):
        """Commands to disabled actuators are rejected."""
        # ARRANGE
        mock_actuator_repo = MagicMock()
        mock_esp_repo = MagicMock()
        mock_esp_repo.get_by_device_id = AsyncMock(return_value=MagicMock(id="uuid-1"))

        # Disabled actuator
        mock_actuator_config = MagicMock(
            min_value=0.0,
            max_value=1.0,
            enabled=False,  # DISABLED!
            actuator_name="Maintenance Pump",
        )
        mock_actuator_repo.get_by_esp_and_gpio = AsyncMock(return_value=mock_actuator_config)
        mock_actuator_repo.get_state = AsyncMock(return_value=None)
        mock_actuator_repo.get_by_esp = AsyncMock(return_value=[mock_actuator_config])

        service = SafetyService(
            actuator_repo=mock_actuator_repo,
            esp_repo=mock_esp_repo,
        )

        # ACT
        result = await service.check_safety_constraints(
            esp_id="ESP_TEST001",
            gpio=25,
            value=0.5,
        )

        # ASSERT
        assert result.valid is False, "Command to disabled actuator should be rejected"
        assert (
            "disabled" in result.error.lower()
        ), f"Error should mention actuator is disabled, got: {result.error}"


class TestEmergencyStopRelease:
    """Tests for emergency stop release functionality."""

    @pytest.mark.critical
    @pytest.mark.pwm
    @pytest.mark.safety
    @pytest.mark.asyncio
    async def test_emergency_stop_release_allows_commands(self):
        """
        SCENARIO: After E-Stop operator should be able to work again

        WORKFLOW:
        1. Activate E-Stop
        2. Command is blocked ✓
        3. Release E-Stop
        4. Command is accepted ✓

        PRACTICE: Recovery after emergency must work!
        """
        # ARRANGE
        mock_actuator_repo = MagicMock()
        mock_esp_repo = MagicMock()
        mock_esp_repo.get_by_device_id = AsyncMock(return_value=MagicMock(id="uuid-1"))

        mock_actuator_config = MagicMock(
            min_value=0.0,
            max_value=1.0,
            enabled=True,
            actuator_name="Test Pump",
        )
        mock_actuator_repo.get_by_esp_and_gpio = AsyncMock(return_value=mock_actuator_config)
        mock_actuator_repo.get_state = AsyncMock(return_value=None)
        mock_actuator_repo.get_by_esp = AsyncMock(return_value=[mock_actuator_config])

        service = SafetyService(
            actuator_repo=mock_actuator_repo,
            esp_repo=mock_esp_repo,
        )

        # 1. Activate E-Stop
        await service.emergency_stop_all()

        # 2. Command should be blocked
        result_blocked = await service.validate_actuator_command(
            esp_id="ESP_TEST001",
            gpio=25,
            command="PWM",
            value=0.5,
        )
        assert result_blocked.valid is False, "Command should be blocked during E-Stop"
        assert (
            "emergency" in result_blocked.error.lower()
        ), f"Error should mention emergency, got: {result_blocked.error}"

        # 3. Release E-Stop
        await service.clear_emergency_stop()

        # 4. Command should be accepted now
        result_allowed = await service.validate_actuator_command(
            esp_id="ESP_TEST001",
            gpio=25,
            command="PWM",
            value=0.5,
        )
        assert (
            result_allowed.valid is True
        ), f"Command should be accepted after E-Stop cleared, got error: {result_allowed.error}"


class TestPWMEdgeCases:
    """Test edge cases and error handling for PWM validation."""

    @pytest.mark.pwm
    @pytest.mark.critical
    @pytest.mark.asyncio
    @pytest.mark.parametrize("invalid_value", [1.0001, 1.001, 1.01, 1.1])
    async def test_pwm_slight_over_boundary_rejected(self, invalid_value):
        """
        SCENARIO: Rounding error leads to value > 1.0
        PRACTICE: JavaScript sometimes sends 1.0000001 due to floating-point errors
        """
        # ARRANGE
        mock_actuator_repo = MagicMock()
        mock_esp_repo = MagicMock()

        service = SafetyService(
            actuator_repo=mock_actuator_repo,
            esp_repo=mock_esp_repo,
        )

        # ACT
        result = await service.validate_actuator_command(
            esp_id="ESP_TEST001",
            gpio=25,
            command="PWM",
            value=invalid_value,
        )

        # ASSERT
        assert result.valid is False, f"Value {invalid_value} should be rejected (above 1.0)"
        assert (
            "range" in result.error.lower() or "out of" in result.error.lower()
        ), f"Error should mention range violation, got: {result.error}"

    @pytest.mark.pwm
    @pytest.mark.asyncio
    async def test_pwm_negative_fractional_rejected(self):
        """
        SCENARIO: Negative fractional values are rejected
        PRACTICE: Ensure small negative values like -0.001 don't slip through
        """
        # ARRANGE
        mock_actuator_repo = MagicMock()
        mock_esp_repo = MagicMock()

        service = SafetyService(
            actuator_repo=mock_actuator_repo,
            esp_repo=mock_esp_repo,
        )

        # ACT
        result = await service.validate_actuator_command(
            esp_id="ESP_TEST001",
            gpio=25,
            command="PWM",
            value=-0.001,  # Small negative value
        )

        # ASSERT
        assert result.valid is False, "Value -0.001 should be rejected (below 0.0)"
        assert (
            "range" in result.error.lower() or "out of" in result.error.lower()
        ), f"Error should mention range violation, got: {result.error}"
