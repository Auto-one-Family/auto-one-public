"""
Tests for Boot-Loop Detection (Safety-Critical).

Validates that the ESP32 detects rapid reboots (>5 in 60s) and enters safe mode
instead of continuing to crash, preventing an unresponsive device.

Firmware reference: El Trabajante/src/main.cpp (~lines 80-120)
    - Counts boots within a 60-second window
    - >5 boots in 60s → enterSafeMode()
    - Boot after 61s → counter resets to 1

These tests simulate the boot-loop detection logic.
"""

import pytest

from .mocks.mock_esp32_client import MockESP32Client, SystemState


class BootLoopSimulator:
    """
    Simulates ESP32 boot-loop detection from main.cpp setup().

    Tracks boot_count and last_boot_time, entering safe mode
    when too many reboots occur in a short window.
    """

    BOOT_LOOP_THRESHOLD = 5
    BOOT_WINDOW_MS = 60000

    def __init__(self, mock: MockESP32Client):
        self.mock = mock
        self._millis: int = 0
        self._boot_count: int = 0
        self._last_boot_time: int | None = None  # None = no previous boot
        self._in_safe_mode: bool = False
        self._normal_boot_executed: bool = False

    @property
    def boot_count(self) -> int:
        return self._boot_count

    @property
    def in_safe_mode(self) -> bool:
        return self._in_safe_mode

    @property
    def normal_boot_executed(self) -> bool:
        return self._normal_boot_executed

    def set_millis(self, ms: int):
        self._millis = ms

    def advance_time(self, ms: int):
        self._millis += ms

    def simulate_boot(self) -> str:
        """
        Simulate a boot cycle (setup() in main.cpp).

        Returns:
            "normal" or "safe_mode"
        """
        # Read persisted state (simulates NVS read)
        if self._last_boot_time is None:
            elapsed = self.BOOT_WINDOW_MS + 1  # First boot ever
        elif self._millis >= self._last_boot_time:
            elapsed = self._millis - self._last_boot_time
        else:
            # Handle millis overflow
            elapsed = (0xFFFFFFFF - self._last_boot_time) + self._millis + 1

        if elapsed < self.BOOT_WINDOW_MS:
            self._boot_count += 1
        else:
            self._boot_count = 1  # Reset

        if self._boot_count > self.BOOT_LOOP_THRESHOLD:
            self._in_safe_mode = True
            self._normal_boot_executed = False
            self.mock.enter_safe_mode("boot_loop_detected")
            return "safe_mode"

        # Save state (simulates NVS write)
        self._last_boot_time = self._millis
        self._in_safe_mode = False
        self._normal_boot_executed = True
        return "normal"

    def clear_nvs(self):
        """Simulate NVS clear (manual recovery)."""
        self._boot_count = 0
        self._last_boot_time = None
        self._in_safe_mode = False


class TestBootLoopDetection:
    """Tests for Boot-Loop Detection (Safety-Critical)."""

    @pytest.fixture
    def sim(self):
        mock = MockESP32Client(esp_id="ESP_BOOT_TEST", kaiser_id="god")
        mock.configure_zone("boot-zone", "main-zone", "boot-subzone")
        simulator = BootLoopSimulator(mock)
        yield simulator
        mock.reset()

    def test_five_boots_in_60s_is_normal(self, sim):
        """BL-001: 5 boots in 60s is still normal operation."""
        for i in range(5):
            sim.set_millis(i * 10000)  # Every 10s
            result = sim.simulate_boot()

        assert result == "normal"
        assert sim.boot_count == 5
        assert sim.in_safe_mode is False

    def test_six_boots_in_60s_triggers_safe_mode(self, sim):
        """BL-002: 6 boots in 60s triggers safe mode."""
        for i in range(6):
            sim.set_millis(i * 5000)  # Every 5s
            result = sim.simulate_boot()

        assert result == "safe_mode"
        assert sim.in_safe_mode is True
        assert sim.mock.system_state == SystemState.SAFE_MODE

    def test_boot_after_61s_resets_counter(self, sim):
        """BL-003: Boot after 61s resets counter to 1."""
        # 5 rapid boots
        for i in range(5):
            sim.set_millis(i * 1000)
            sim.simulate_boot()

        assert sim.boot_count == 5

        # Boot 61s after the LAST boot (at 4000ms), so 65000ms
        sim.set_millis(65000)
        result = sim.simulate_boot()

        assert result == "normal"
        assert sim.boot_count == 1

    def test_millis_overflow_handled(self, sim):
        """BL-004: millis() overflow is handled correctly."""
        # Boot near overflow
        sim.set_millis(4294967290)
        sim.simulate_boot()

        # Boot after overflow (5ms later in real time)
        sim.set_millis(5)
        result = sim.simulate_boot()

        # Should count as rapid boot (only ~10ms apart)
        assert result == "normal"
        assert sim.boot_count == 2

    def test_safe_mode_prevents_normal_boot(self, sim):
        """BL-005: Safe mode prevents normal boot sequence execution."""
        for i in range(6):
            sim.set_millis(i * 2000)
            sim.simulate_boot()

        assert sim.in_safe_mode is True
        assert sim.normal_boot_executed is False

    def test_manual_recovery_via_nvs_clear(self, sim):
        """BL-006: Manual recovery via NVS clear resets boot counter."""
        # Trigger safe mode
        for i in range(6):
            sim.set_millis(i * 2000)
            sim.simulate_boot()

        assert sim.in_safe_mode is True

        # Manual recovery
        sim.clear_nvs()
        sim.mock.exit_safe_mode()

        sim.set_millis(100000)
        result = sim.simulate_boot()

        assert result == "normal"
        assert sim.boot_count == 1
        assert sim.in_safe_mode is False
