"""
Unit tests for FlowProcessor — verifies time-normalization fix (AUT-860).

Root cause: time_window defaulted to 1.0s instead of actual measurement window.
Fix: time_window must be supplied via params["time_window"] (seconds),
     derived from MQTT payload field "window_ms" / 1000.0.
"""

import pytest

from src.sensors.sensor_libraries.active.flow import FlowProcessor


@pytest.fixture
def processor() -> FlowProcessor:
    return FlowProcessor()


class TestFlowProcessorTimeNormalization:
    """Verify pulse→L/min conversion with correct time windows."""

    def test_normal_30s_window(self, processor: FlowProcessor) -> None:
        """1135 pulses / 30 s → ~6.88 L/min (was 206.36 with old default)."""
        result = processor.process(raw_value=1135.0, params={"time_window": 30.0})
        assert result.quality != "error", f"Unexpected error: {result.metadata}"
        assert abs(result.value - 6.88) < 0.05, f"Expected ~6.88 L/min, got {result.value}"
        assert result.unit == "L/min"

    def test_short_post_config_window(self, processor: FlowProcessor) -> None:
        """343 pulses / 9 s → ~6.93 L/min (post-config-push shortened window)."""
        result = processor.process(raw_value=343.0, params={"time_window": 9.0})
        assert result.quality != "error", f"Unexpected error: {result.metadata}"
        assert abs(result.value - 6.93) < 0.1, f"Expected ~6.93 L/min, got {result.value}"

    def test_both_windows_consistent(self, processor: FlowProcessor) -> None:
        """Confirm 1135/30s and 343/9s give same flow rate (within 1%)."""
        r1 = processor.process(raw_value=1135.0, params={"time_window": 30.0})
        r2 = processor.process(raw_value=343.0, params={"time_window": 9.0})
        assert r1.quality != "error"
        assert r2.quality != "error"
        assert (
            abs(r1.value - r2.value) < 0.15
        ), f"Flow rate inconsistent across window lengths: {r1.value} vs {r2.value}"

    def test_both_pass_validation(self, processor: FlowProcessor) -> None:
        """Both corrected values must be below 100 L/min validate() threshold."""
        r1 = processor.process(raw_value=1135.0, params={"time_window": 30.0})
        r2 = processor.process(raw_value=343.0, params={"time_window": 9.0})
        assert r1.quality != "error"
        assert r2.quality != "error"
        assert r1.value < 100.0
        assert r2.value < 100.0


class TestFlowProcessorMissingTimeWindow:
    """Verify that missing time_window returns quality=error (not silent 1.0 default)."""

    def test_no_params_returns_error(self, processor: FlowProcessor) -> None:
        result = processor.process(raw_value=1135.0)
        assert result.quality == "error"
        assert result.metadata.get("error") == "time_window_missing"

    def test_empty_params_returns_error(self, processor: FlowProcessor) -> None:
        result = processor.process(raw_value=1135.0, params={})
        assert result.quality == "error"
        assert result.metadata.get("error") == "time_window_missing"

    def test_params_without_time_window_returns_error(self, processor: FlowProcessor) -> None:
        result = processor.process(raw_value=1135.0, params={"input_type": "pulses"})
        assert result.quality == "error"
        assert result.metadata.get("error") == "time_window_missing"

    def test_old_bug_value_not_emitted(self, processor: FlowProcessor) -> None:
        """The old buggy 206.36 must never be emitted silently."""
        result = processor.process(raw_value=1135.0, params={})
        assert result.value != pytest.approx(
            206.36, abs=1.0
        ), "Old bug value 206.36 emitted — time_window=1.0 default was not removed"


class TestFlowProcessorZeroFlow:
    """Edge cases: zero pulses, zero time window."""

    def test_zero_pulses(self, processor: FlowProcessor) -> None:
        result = processor.process(raw_value=0.0, params={"time_window": 30.0})
        assert result.quality != "error" or result.value == 0.0
        assert result.value == 0.0

    def test_zero_time_window(self, processor: FlowProcessor) -> None:
        result = processor.process(raw_value=1135.0, params={"time_window": 0.0})
        assert result.value == 0.0


class TestFlowProcessorFrequencyMode:
    """Frequency input_type should be unaffected by time_window change."""

    def test_frequency_mode_works_without_time_window(self, processor: FlowProcessor) -> None:
        """input_type=frequency does not require time_window."""
        result = processor.process(
            raw_value=37.83,  # Hz: 6.9 L/min * 330/60
            params={"input_type": "frequency"},
        )
        assert result.quality != "error"
        assert abs(result.value - 6.88) < 0.2
