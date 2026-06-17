"""
Emergency-Stop Tests.

Tests both ESP32-side (MockESP32Client) and Server-side (SafetyService)
emergency stop behavior.

CRITICAL CORRECTIONS from analysis:
- Emergency uses QoS 1 (NOT QoS 2)
- Recovery is MANUAL (2-phase: clear + resume), NOT automatic
- Server SafetyService uses "__ALL__" key for global emergency
- ESP MockClient sets emergency_stopped flag on all actuators
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from tests.esp32.mocks.mock_esp32_client import (
    MockESP32Client,
    BrokerMode,
    SystemState,
)
from src.services.safety_service import SafetyService, SafetyCheckResult, EmergencyState

# =========================================================================
# ESP32 Mock Emergency Stop Tests
# =========================================================================


class TestESPEmergencyStopActivation:
    """Emergency stop behavior on MockESP32Client."""

    @pytest.fixture
    def esp_with_actuators(self):
        """ESP with zone and active actuators."""
        esp = MockESP32Client(esp_id="ESP_EM000001")
        esp.configure_zone("test_zone", "main_zone")
        esp.configure_actuator(gpio=25, actuator_type="pwm")
        esp.configure_actuator(gpio=26, actuator_type="relay")
        esp.configure_actuator(gpio=27, actuator_type="pwm")

        # Activate actuators
        esp.handle_command("actuator_set", {"gpio": 25, "value": 0.75, "mode": "pwm"})
        esp.handle_command("actuator_set", {"gpio": 26, "value": 1, "mode": "digital"})
        esp.handle_command("actuator_set", {"gpio": 27, "value": 0.5, "mode": "pwm"})
        return esp

    def test_emergency_stops_all_actuators(self, esp_with_actuators):
        """All actuators go to 0 on emergency stop."""
        esp = esp_with_actuators

        assert esp.get_actuator_state(25).pwm_value == 0.75
        assert esp.get_actuator_state(26).state is True
        assert esp.get_actuator_state(27).pwm_value == 0.5

        result = esp.handle_command("emergency_stop", {"reason": "test"})
        assert result["status"] == "ok"

        assert esp.get_actuator_state(25).pwm_value == 0.0
        assert esp.get_actuator_state(26).state is False
        assert esp.get_actuator_state(27).pwm_value == 0.0

    def test_emergency_sets_flag_on_all_actuators(self, esp_with_actuators):
        """emergency_stopped flag is set on every actuator."""
        esp = esp_with_actuators
        esp.handle_command("emergency_stop", {"reason": "test"})

        for gpio in [25, 26, 27]:
            assert esp.get_actuator_state(gpio).emergency_stopped is True

    def test_emergency_blocks_new_commands(self, esp_with_actuators):
        """New actuator commands are rejected during emergency stop."""
        esp = esp_with_actuators
        esp.handle_command("emergency_stop", {"reason": "test"})

        result = esp.handle_command("actuator_set", {"gpio": 25, "value": 1.0, "mode": "pwm"})

        assert result["status"] == "error"
        assert "emergency" in result["error"].lower()

    def test_emergency_publishes_qos_1_not_qos_2(self, esp_with_actuators):
        """
        Emergency stop messages use QoS 1, NOT QoS 2.
        CRITICAL: This was a documented correction.
        """
        esp = esp_with_actuators
        esp.clear_published_messages()
        esp.handle_command("emergency_stop", {"reason": "test"})

        messages = esp.get_published_messages()
        emergency_msgs = [m for m in messages if "emergency" in m["topic"]]

        assert len(emergency_msgs) >= 1
        for msg in emergency_msgs:
            assert msg["qos"] == 1, f"Emergency QoS should be 1, got {msg['qos']}"

    def test_emergency_publishes_to_device_and_broadcast_topics(self, esp_with_actuators):
        """Emergency publishes to both device-specific and broadcast topics."""
        esp = esp_with_actuators
        esp.clear_published_messages()
        esp.handle_command("emergency_stop", {"reason": "test"})

        messages = esp.get_published_messages()
        topics = [m["topic"] for m in messages]

        # Device-specific emergency topic
        device_topic = [t for t in topics if "ESP_EM000001" in t and "emergency" in t]
        assert len(device_topic) >= 1

        # Broadcast emergency topic
        broadcast_topic = [t for t in topics if "broadcast/emergency" in t]
        assert len(broadcast_topic) >= 1

    def test_emergency_returns_stopped_actuator_list(self, esp_with_actuators):
        """Emergency stop response lists all stopped actuator GPIOs."""
        esp = esp_with_actuators
        result = esp.handle_command("emergency_stop", {"reason": "test"})

        assert "stopped_actuators" in result
        assert set(result["stopped_actuators"]) == {25, 26, 27}


class TestESPEmergencyRecovery:
    """
    Emergency recovery tests.
    CRITICAL: Recovery is MANUAL (clear_emergency command required).
    """

    @pytest.fixture
    def stopped_esp(self):
        """ESP in emergency stop state."""
        esp = MockESP32Client(esp_id="ESP_EM000002")
        esp.configure_zone("test_zone", "main_zone")
        esp.configure_actuator(gpio=25, actuator_type="pwm")
        esp.configure_actuator(gpio=26, actuator_type="relay")
        esp.handle_command("actuator_set", {"gpio": 25, "value": 0.5, "mode": "pwm"})
        esp.handle_command("emergency_stop", {"reason": "test"})
        return esp

    def test_no_automatic_recovery(self, stopped_esp):
        """Emergency state persists - no automatic recovery."""
        esp = stopped_esp

        # Even after time passes, emergency is still active
        assert esp.get_actuator_state(25).emergency_stopped is True
        assert esp.get_actuator_state(26).emergency_stopped is True

        # Commands still blocked
        result = esp.handle_command("actuator_set", {"gpio": 25, "value": 0.5, "mode": "pwm"})
        assert result["status"] == "error"

    def test_clear_emergency_removes_flags(self, stopped_esp):
        """clear_emergency command removes emergency_stopped flags."""
        esp = stopped_esp

        result = esp.handle_command("clear_emergency", {})
        assert result["status"] == "ok"

        for gpio in [25, 26]:
            assert esp.get_actuator_state(gpio).emergency_stopped is False

    def test_clear_emergency_returns_cleared_list(self, stopped_esp):
        """clear_emergency returns list of cleared actuator GPIOs."""
        esp = stopped_esp
        result = esp.handle_command("clear_emergency", {})

        assert "cleared_actuators" in result
        assert set(result["cleared_actuators"]) == {25, 26}

    def test_clear_specific_actuator(self, stopped_esp):
        """Can clear emergency for a specific actuator GPIO."""
        esp = stopped_esp

        result = esp.handle_command("clear_emergency", {"gpio": 25})
        assert result["status"] == "ok"

        # Only GPIO 25 cleared
        assert esp.get_actuator_state(25).emergency_stopped is False
        assert esp.get_actuator_state(26).emergency_stopped is True

    def test_after_clear_commands_work_again(self, stopped_esp):
        """After clearing emergency, actuator commands work again."""
        esp = stopped_esp

        esp.handle_command("clear_emergency", {})

        result = esp.handle_command("actuator_set", {"gpio": 25, "value": 0.75, "mode": "pwm"})
        assert result["status"] == "ok"
        assert esp.get_actuator_state(25).pwm_value == 0.75


class TestESPSafeModeEmergency:
    """Test safe mode interaction with emergency stop."""

    def test_safe_mode_stops_all_actuators(self):
        """Entering safe mode stops all actuators."""
        esp = MockESP32Client(esp_id="ESP_EM000003")
        esp.configure_zone("test_zone", "main_zone")
        esp.configure_actuator(gpio=25, actuator_type="pwm")
        esp.handle_command("actuator_set", {"gpio": 25, "value": 0.75, "mode": "pwm"})

        esp.enter_safe_mode("high_temperature")

        assert esp.get_system_state() == SystemState.SAFE_MODE
        assert esp.get_actuator_state(25).pwm_value == 0.0
        assert esp.get_actuator_state(25).emergency_stopped is True

    def test_safe_mode_blocks_commands(self):
        """Safe mode blocks actuator commands."""
        esp = MockESP32Client(esp_id="ESP_EM000004")
        esp.configure_zone("test_zone", "main_zone")
        esp.configure_actuator(gpio=25, actuator_type="relay")
        esp.enter_safe_mode("test")

        result = esp.handle_command("actuator_set", {"gpio": 25, "value": 1, "mode": "digital"})
        assert result["status"] == "error"
        assert "SAFE_MODE" in result["error"]

    def test_exit_safe_mode_clears_emergency_flags(self):
        """Exiting safe mode clears emergency_stopped flags."""
        esp = MockESP32Client(esp_id="ESP_EM000005")
        esp.configure_zone("test_zone", "main_zone")
        esp.configure_actuator(gpio=25, actuator_type="relay")
        esp.enter_safe_mode("test")

        assert esp.get_actuator_state(25).emergency_stopped is True

        esp.exit_safe_mode()

        assert esp.get_system_state() == SystemState.OPERATIONAL
        assert esp.get_actuator_state(25).emergency_stopped is False


# =========================================================================
# Server-Side SafetyService Emergency Stop Tests
# =========================================================================


class TestSafetyServiceEmergencyStop:
    """Server-side SafetyService emergency stop validation."""

    @pytest.fixture
    def safety_service(self):
        """SafetyService with mocked repositories.

        Configures mock actuator with valid range (0.0–1.0) so that
        validate_actuator_command can reach SafetyCheckResult(valid=True)
        after an emergency stop is cleared.  Without this setup the
        AsyncMock default return values for get_by_esp_and_gpio cause a
        TypeError when safety_service.py compares float < AsyncMock.
        """
        actuator_repo = AsyncMock()
        esp_repo = AsyncMock()

        # Provide a real-looking ESP device so check_safety_constraints
        # does not fail with "ESP device not found".
        mock_esp = MagicMock()
        mock_esp.id = 1
        esp_repo.get_by_device_id.return_value = mock_esp

        # Provide an actuator config with a valid value range so the
        # range check (value < min_value or value > max_value) passes.
        mock_actuator = MagicMock()
        mock_actuator.enabled = True
        mock_actuator.min_value = 0.0
        mock_actuator.max_value = 1.0
        mock_actuator.timeout_seconds = None
        actuator_repo.get_by_esp_and_gpio.return_value = mock_actuator
        # get_by_esp is called during GPIO conflict check in check_safety_constraints.
        # Return empty list so no false GPIO-conflict warnings are raised.
        actuator_repo.get_by_esp.return_value = []
        actuator_repo.get_state.return_value = None

        SafetyService._global_emergency_stop_active.clear()
        yield SafetyService(actuator_repo=actuator_repo, esp_repo=esp_repo)
        SafetyService._global_emergency_stop_active.clear()

    @pytest.mark.asyncio
    async def test_global_emergency_blocks_all_commands(self, safety_service):
        """Global emergency stop blocks commands for any ESP."""
        await safety_service.emergency_stop_all()

        result = await safety_service.validate_actuator_command(
            esp_id="ESP_ANY001", gpio=25, command="ON", value=1.0
        )

        assert result.valid is False
        assert "emergency" in result.error.lower()

    @pytest.mark.asyncio
    async def test_device_specific_emergency(self, safety_service):
        """Device-specific emergency only blocks that device."""
        await safety_service.emergency_stop_esp("ESP_STOP01")

        # Stopped device should be blocked
        result = await safety_service.validate_actuator_command(
            esp_id="ESP_STOP01", gpio=25, command="ON", value=1.0
        )
        assert result.valid is False

        # Other devices should NOT be blocked (no global stop)
        is_active = await safety_service.is_emergency_stop_active("ESP_OTHER1")
        assert is_active is False

    @pytest.mark.asyncio
    async def test_clear_global_emergency(self, safety_service):
        """Clearing global emergency allows commands again."""
        await safety_service.emergency_stop_all()

        is_active = await safety_service.is_emergency_stop_active()
        assert is_active is True

        await safety_service.clear_emergency_stop()

        is_active = await safety_service.is_emergency_stop_active()
        assert is_active is False

    @pytest.mark.asyncio
    async def test_clear_device_emergency(self, safety_service):
        """Clearing device-specific emergency allows that device."""
        await safety_service.emergency_stop_esp("ESP_CLEAR1")

        is_active = await safety_service.is_emergency_stop_active("ESP_CLEAR1")
        assert is_active is True

        await safety_service.clear_emergency_stop("ESP_CLEAR1")

        is_active = await safety_service.is_emergency_stop_active("ESP_CLEAR1")
        assert is_active is False

    @pytest.mark.asyncio
    async def test_value_range_validation(self, safety_service):
        """SafetyService validates PWM value range 0.0-1.0."""
        # Value too high
        result = await safety_service.validate_actuator_command(
            esp_id="ESP_VAL001", gpio=25, command="PWM", value=1.5
        )
        assert result.valid is False
        assert "range" in result.error.lower()

        # Value too low
        result = await safety_service.validate_actuator_command(
            esp_id="ESP_VAL001", gpio=25, command="PWM", value=-0.1
        )
        assert result.valid is False

    @pytest.mark.asyncio
    async def test_emergency_state_enum_matches_esp32(self):
        """EmergencyState enum values match ESP32 actuator_types.h."""
        assert EmergencyState.NORMAL.value == "normal"
        assert EmergencyState.ACTIVE.value == "active"
        assert EmergencyState.CLEARING.value == "clearing"
        assert EmergencyState.RESUMING.value == "resuming"

    @pytest.mark.asyncio
    async def test_concurrent_emergency_operations(self, safety_service):
        """SafetyService is thread-safe with asyncio.Lock."""
        import asyncio

        # Concurrent emergency stop and clear operations
        async def stop_and_clear():
            await safety_service.emergency_stop_esp("ESP_CONC01")
            await safety_service.clear_emergency_stop("ESP_CONC01")

        # Run multiple concurrent operations
        await asyncio.gather(*[stop_and_clear() for _ in range(10)])

        # Should be in a consistent state (cleared)
        is_active = await safety_service.is_emergency_stop_active("ESP_CONC01")
        assert is_active is False

    @pytest.mark.asyncio
    async def test_emergency_reaction_time_under_100ms(self, safety_service):
        """Emergency stop must complete within 100ms for safety compliance."""
        import time

        t0 = time.monotonic_ns()
        await safety_service.emergency_stop_esp("ESP_TIMING01")
        t1 = time.monotonic_ns()

        elapsed_ms = (t1 - t0) / 1_000_000
        assert elapsed_ms < 100, f"Emergency stop took {elapsed_ms:.1f}ms, must be < 100ms"

        # Verify it actually worked
        is_active = await safety_service.is_emergency_stop_active("ESP_TIMING01")
        assert is_active is True

    @pytest.mark.asyncio
    async def test_multiple_clear_emergency_is_idempotent(self, safety_service):
        """Multiple clear_emergency calls must not corrupt state."""
        await safety_service.emergency_stop_esp("ESP_IDEM01")
        assert await safety_service.is_emergency_stop_active("ESP_IDEM01") is True

        # User panic-clicks clear 5 times
        for _ in range(5):
            await safety_service.clear_emergency_stop("ESP_IDEM01")

        # State must be consistent
        assert await safety_service.is_emergency_stop_active("ESP_IDEM01") is False

        # Actuator commands must work again
        result = await safety_service.validate_actuator_command(
            esp_id="ESP_IDEM01", gpio=25, command="ON", value=1.0
        )
        assert result.valid is True
