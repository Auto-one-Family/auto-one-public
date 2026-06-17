"""
Failure Recovery Tests (FAIL Category).

Tests emergency stop recovery, safe mode transitions, device offline handling,
and concurrent emergency operations.

Pattern: Hybrid - MockESP32Client (sync) + SafetyService (async with AsyncMock).
"""

import asyncio

import pytest
from unittest.mock import AsyncMock

from tests.esp32.mocks.mock_esp32_client import (
    MockESP32Client,
    SystemState,
)
from src.services.safety_service import SafetyService


@pytest.fixture(autouse=True)
def clear_emergency_stop_state():
    """Reset SafetyService global E-Stop state before and after each test."""
    SafetyService._global_emergency_stop_active.clear()
    yield
    SafetyService._global_emergency_stop_active.clear()


# =========================================================================
# ESP32 Emergency Recovery Workflow
# =========================================================================


class TestEmergencyRecoveryWorkflow:
    """Full emergency stop → block → clear → resume cycle."""

    @pytest.fixture
    def esp_fleet(self):
        """3 ESPs with active actuators for recovery testing."""
        esps = []
        for i in range(3):
            esp = MockESP32Client(esp_id=f"ESP_FAIL{i:04d}")
            esp.configure_zone("recovery_zone", "main_zone")
            esp.configure_actuator(gpio=25, actuator_type="pump")
            esp.configure_actuator(gpio=26, actuator_type="valve")
            esp.handle_command("actuator_set", {"gpio": 25, "value": 0.8, "mode": "pwm"})
            esp.handle_command("actuator_set", {"gpio": 26, "value": 1, "mode": "digital"})
            esps.append(esp)
        yield esps
        for esp in esps:
            esp.reset()

    def test_emergency_blocks_then_clear_resumes(self, esp_fleet):
        """Emergency → commands blocked → clear → commands work again."""
        esp = esp_fleet[0]

        # Verify actuators are active
        assert esp.get_actuator_state(25).pwm_value == 0.8
        assert esp.get_actuator_state(26).state is True

        # Emergency stop
        result = esp.handle_command("emergency_stop", {"reason": "overheat"})
        assert result["status"] == "ok"

        # All actuators stopped
        assert esp.get_actuator_state(25).pwm_value == 0.0
        assert esp.get_actuator_state(26).state is False

        # Commands blocked
        result = esp.handle_command("actuator_set", {"gpio": 25, "value": 0.5, "mode": "pwm"})
        assert result["status"] == "error"
        assert "emergency" in result["error"].lower()

        # Clear emergency
        result = esp.handle_command("clear_emergency", {})
        assert result["status"] == "ok"

        # Commands work again
        result = esp.handle_command("actuator_set", {"gpio": 25, "value": 0.6, "mode": "pwm"})
        assert result["status"] == "ok"
        assert esp.get_actuator_state(25).pwm_value == 0.6

    def test_emergency_isolates_per_device(self, esp_fleet):
        """Emergency on one ESP does not affect others."""
        esp0, esp1, esp2 = esp_fleet

        # Stop only esp0
        esp0.handle_command("emergency_stop", {"reason": "test"})

        # esp0 blocked
        result = esp0.handle_command("actuator_set", {"gpio": 25, "value": 0.5, "mode": "pwm"})
        assert result["status"] == "error"

        # esp1 and esp2 still operational
        result = esp1.handle_command("actuator_set", {"gpio": 25, "value": 0.3, "mode": "pwm"})
        assert result["status"] == "ok"
        assert esp1.get_actuator_state(25).pwm_value == 0.3

        result = esp2.handle_command("actuator_set", {"gpio": 26, "value": 0, "mode": "digital"})
        assert result["status"] == "ok"


# =========================================================================
# Safe Mode Recovery
# =========================================================================


class TestSafeModeRecovery:
    """Safe mode entry, behavior, and exit."""

    def test_safe_mode_stops_actuators_allows_sensor_reads(self):
        """Safe mode disables actuators but allows sensor reads."""
        esp = MockESP32Client(esp_id="ESP_SAFE001")
        esp.configure_zone("safe_zone", "main_zone")
        esp.configure_actuator(gpio=25, actuator_type="pump")
        esp.set_sensor_value(gpio=34, raw_value=25.5, sensor_type="DS18B20")
        esp.handle_command("actuator_set", {"gpio": 25, "value": 1, "mode": "digital"})

        # Enter safe mode
        esp.enter_safe_mode("sensor_fault")
        assert esp.get_system_state() == SystemState.SAFE_MODE

        # Actuator stopped and blocked
        assert esp.get_actuator_state(25).state is False
        result = esp.handle_command("actuator_set", {"gpio": 25, "value": 1, "mode": "digital"})
        assert result["status"] == "error"

        # Sensor reads still work
        result = esp.handle_command("sensor_read", {"gpio": 34})
        assert result["status"] == "ok"
        assert result["data"]["raw_value"] == 25.5

    def test_exit_safe_mode_restores_operational(self):
        """Exiting safe mode restores operational state."""
        esp = MockESP32Client(esp_id="ESP_SAFE002")
        esp.configure_zone("safe_zone", "main_zone")
        esp.configure_actuator(gpio=25, actuator_type="relay")

        esp.enter_safe_mode("test")
        assert esp.get_system_state() == SystemState.SAFE_MODE
        assert esp.get_actuator_state(25).emergency_stopped is True

        esp.exit_safe_mode()
        assert esp.get_system_state() == SystemState.OPERATIONAL
        assert esp.get_actuator_state(25).emergency_stopped is False

        # Commands work again
        result = esp.handle_command("actuator_set", {"gpio": 25, "value": 1, "mode": "digital"})
        assert result["status"] == "ok"
        assert esp.get_actuator_state(25).state is True


# =========================================================================
# Server-Side SafetyService Recovery
# =========================================================================


class TestSafetyServiceRecovery:
    """SafetyService emergency stop and recovery."""

    @pytest.fixture
    def safety_service(self):
        """SafetyService with mocked repos."""
        return SafetyService(
            actuator_repo=AsyncMock(),
            esp_repo=AsyncMock(),
        )

    @pytest.mark.asyncio
    async def test_global_emergency_blocks_all_then_clear_resumes(self, safety_service):
        """Global emergency blocks all ESPs, clear resumes."""
        await safety_service.emergency_stop_all()

        # All blocked
        assert await safety_service.is_emergency_stop_active() is True
        assert await safety_service.is_emergency_stop_active("ESP_ANY") is True

        result = await safety_service.validate_actuator_command("ESP_ANY", 25, "ON", 1.0)
        assert result.valid is False

        # Clear
        await safety_service.clear_emergency_stop()
        assert await safety_service.is_emergency_stop_active() is False

    @pytest.mark.asyncio
    async def test_device_emergency_only_blocks_that_device(self, safety_service):
        """Device-specific emergency only blocks that device."""
        await safety_service.emergency_stop_esp("ESP_BLOCK01")

        assert await safety_service.is_emergency_stop_active("ESP_BLOCK01") is True
        assert await safety_service.is_emergency_stop_active("ESP_OTHER01") is False

        # Clear specific device
        await safety_service.clear_emergency_stop("ESP_BLOCK01")
        assert await safety_service.is_emergency_stop_active("ESP_BLOCK01") is False

    @pytest.mark.asyncio
    async def test_multiple_device_emergencies_independent(self, safety_service):
        """Multiple device emergencies are independent."""
        await safety_service.emergency_stop_esp("ESP_A")
        await safety_service.emergency_stop_esp("ESP_B")

        # Clear only A
        await safety_service.clear_emergency_stop("ESP_A")

        assert await safety_service.is_emergency_stop_active("ESP_A") is False
        assert await safety_service.is_emergency_stop_active("ESP_B") is True

    @pytest.mark.asyncio
    async def test_concurrent_emergency_operations(self, safety_service):
        """Concurrent stop/clear operations maintain consistency (asyncio.Lock)."""

        async def stop_and_clear(esp_id: str):
            await safety_service.emergency_stop_esp(esp_id)
            await safety_service.clear_emergency_stop(esp_id)

        # 10 concurrent operations on different ESPs
        await asyncio.gather(*[stop_and_clear(f"ESP_CONC{i:03d}") for i in range(10)])

        # All should be cleared
        for i in range(10):
            assert await safety_service.is_emergency_stop_active(f"ESP_CONC{i:03d}") is False

    @pytest.mark.asyncio
    async def test_global_emergency_blocks_multiple_esps(self, safety_service):
        """Global emergency rejects commands from multiple ESPs."""
        await safety_service.emergency_stop_all()

        for i in range(5):
            result = await safety_service.validate_actuator_command(
                f"ESP_MULTI{i:03d}", 25, "ON", 1.0
            )
            assert result.valid is False
            assert "emergency" in result.error.lower()

    @pytest.mark.asyncio
    async def test_pwm_value_validation_still_works_after_clear(self, safety_service):
        """After clearing emergency, value validation still enforced."""
        await safety_service.emergency_stop_all()
        await safety_service.clear_emergency_stop()

        # Out-of-range value still rejected
        result = await safety_service.validate_actuator_command("ESP_VAL001", 25, "PWM", 1.5)
        assert result.valid is False
        assert "range" in result.error.lower()
