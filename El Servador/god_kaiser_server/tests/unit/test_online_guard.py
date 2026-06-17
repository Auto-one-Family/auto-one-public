"""
Unit Tests: V1-22 Online Guard

Verifies that actuator commands to offline ESPs are rejected early
by SafetyService.check_safety_constraints() before reaching MQTT.

With clean_session=true on both sides, the MQTT broker silently drops
messages to disconnected clients. The Online Guard provides explicit
error feedback instead of silent command loss.
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


class TestOnlineGuard:
    """Tests for V1-22: SafetyService rejects commands to offline ESPs."""

    @pytest.mark.critical
    @pytest.mark.safety
    @pytest.mark.asyncio
    async def test_offline_esp_command_rejected(self):
        """Command to offline ESP must be rejected with clear error."""
        # ARRANGE
        mock_actuator_repo = MagicMock()
        mock_esp_repo = MagicMock()

        mock_esp_device = MagicMock(
            id="uuid-1",
            is_online=False,
            status="offline",
        )
        mock_esp_repo.get_by_device_id = AsyncMock(return_value=mock_esp_device)

        service = SafetyService(
            actuator_repo=mock_actuator_repo,
            esp_repo=mock_esp_repo,
        )

        # ACT
        result = await service.check_safety_constraints(
            esp_id="ESP_OFFLINE_01",
            gpio=26,
            value=1.0,
        )

        # ASSERT
        assert result.valid is False, "Command to offline ESP should be rejected"
        assert (
            "offline" in result.error.lower()
        ), f"Error should mention 'offline', got: {result.error}"
        assert "ESP_OFFLINE_01" in result.error, f"Error should contain ESP ID, got: {result.error}"

    @pytest.mark.critical
    @pytest.mark.safety
    @pytest.mark.asyncio
    async def test_online_esp_command_passes_through(self):
        """Command to online ESP must pass the online guard and reach safety checks."""
        # ARRANGE
        mock_actuator_repo = MagicMock()
        mock_esp_repo = MagicMock()

        mock_esp_device = MagicMock(
            id="uuid-1",
            is_online=True,
            status="online",
        )
        mock_esp_repo.get_by_device_id = AsyncMock(return_value=mock_esp_device)

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

        # ACT
        result = await service.check_safety_constraints(
            esp_id="ESP_ONLINE_01",
            gpio=26,
            value=1.0,
        )

        # ASSERT
        assert result.valid is True, f"Online ESP command should pass, got error: {result.error}"

    @pytest.mark.safety
    @pytest.mark.asyncio
    async def test_offline_guard_before_actuator_checks(self):
        """Offline guard must reject BEFORE actuator lookup (no unnecessary DB query)."""
        # ARRANGE
        mock_actuator_repo = MagicMock()
        mock_esp_repo = MagicMock()

        mock_esp_device = MagicMock(
            id="uuid-1",
            is_online=False,
            status="offline",
        )
        mock_esp_repo.get_by_device_id = AsyncMock(return_value=mock_esp_device)

        service = SafetyService(
            actuator_repo=mock_actuator_repo,
            esp_repo=mock_esp_repo,
        )

        # ACT
        await service.check_safety_constraints(
            esp_id="ESP_OFFLINE_01",
            gpio=26,
            value=1.0,
        )

        # ASSERT — actuator lookup should NOT have been called
        mock_actuator_repo.get_by_esp_and_gpio.assert_not_called()

    @pytest.mark.safety
    @pytest.mark.asyncio
    async def test_offline_guard_error_contains_status(self):
        """Error message must include the actual device status."""
        # ARRANGE
        mock_actuator_repo = MagicMock()
        mock_esp_repo = MagicMock()

        mock_esp_device = MagicMock(
            id="uuid-1",
            is_online=False,
            status="timeout",
        )
        mock_esp_repo.get_by_device_id = AsyncMock(return_value=mock_esp_device)

        service = SafetyService(
            actuator_repo=mock_actuator_repo,
            esp_repo=mock_esp_repo,
        )

        # ACT
        result = await service.check_safety_constraints(
            esp_id="ESP_TIMEOUT_01",
            gpio=26,
            value=1.0,
        )

        # ASSERT
        assert result.valid is False
        assert (
            "timeout" in result.error
        ), f"Error should contain actual status 'timeout', got: {result.error}"

    @pytest.mark.safety
    @pytest.mark.asyncio
    async def test_validate_actuator_command_offline_rejected(self):
        """Full validation path: validate_actuator_command() also rejects offline ESP."""
        # ARRANGE
        mock_actuator_repo = MagicMock()
        mock_esp_repo = MagicMock()

        mock_esp_device = MagicMock(
            id="uuid-1",
            is_online=False,
            status="offline",
        )
        mock_esp_repo.get_by_device_id = AsyncMock(return_value=mock_esp_device)

        service = SafetyService(
            actuator_repo=mock_actuator_repo,
            esp_repo=mock_esp_repo,
        )

        # ACT
        result = await service.validate_actuator_command(
            esp_id="ESP_OFFLINE_01",
            gpio=26,
            command="ON",
            value=1.0,
        )

        # ASSERT
        assert result.valid is False, "Full validation should reject offline ESP"
        assert "offline" in result.error.lower()


class TestOnlineGuardDoesNotAffectEmergencyStop:
    """Verify emergency stop path is independent of online guard."""

    @pytest.mark.critical
    @pytest.mark.safety
    @pytest.mark.asyncio
    async def test_emergency_stop_flag_independent_of_online_status(self):
        """Emergency stop flag operations work regardless of device online status."""
        # ARRANGE
        mock_actuator_repo = MagicMock()
        mock_esp_repo = MagicMock()

        service = SafetyService(
            actuator_repo=mock_actuator_repo,
            esp_repo=mock_esp_repo,
        )

        # ACT — emergency stop uses in-memory flags, not DB device status
        await service.emergency_stop_esp("ESP_OFFLINE_01")
        is_active = await service.is_emergency_stop_active("ESP_OFFLINE_01")

        # ASSERT
        assert is_active is True, "Emergency stop flag should work for any ESP ID"

        # Clear and verify
        await service.clear_emergency_stop("ESP_OFFLINE_01")
        is_active_after = await service.is_emergency_stop_active("ESP_OFFLINE_01")
        assert is_active_after is False, "Emergency stop should be clearable"
