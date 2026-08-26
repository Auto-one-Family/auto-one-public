"""
Unit tests for flow volume accumulation (AUT-1121 Variante A / AUT-1288).

Variante B (SUM dose_ml) is intentionally not covered — Nachfüll rules run
without dose_ml (AUT-1288).
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.services.flow_volume_service import (
    REFILL_FLOW_DEVICE_ID,
    REFILL_FLOW_GPIO,
    FlowVolumeService,
    execution_window,
    integrate_flow_rate_to_volume_l,
)


class TestIntegrateFlowRateToVolumeL:
    def test_constant_rate_over_one_minute(self) -> None:
        """6 L/min for 1 minute → 6 liters."""
        t0 = datetime(2026, 7, 23, 12, 0, 0, tzinfo=timezone.utc)
        t1 = t0 + timedelta(minutes=1)
        volume = integrate_flow_rate_to_volume_l([(t0, 6.0), (t1, 6.0)])
        assert volume == pytest.approx(6.0, abs=1e-6)

    def test_trapezoid_ramp(self) -> None:
        """0 → 10 L/min over 1 minute → average 5 L/min → 5 liters."""
        t0 = datetime(2026, 7, 23, 12, 0, 0, tzinfo=timezone.utc)
        t1 = t0 + timedelta(minutes=1)
        volume = integrate_flow_rate_to_volume_l([(t0, 0.0), (t1, 10.0)])
        assert volume == pytest.approx(5.0, abs=1e-6)

    def test_unsorted_samples_are_sorted(self) -> None:
        t0 = datetime(2026, 7, 23, 12, 0, 0, tzinfo=timezone.utc)
        t1 = t0 + timedelta(seconds=30)
        t2 = t0 + timedelta(seconds=60)
        volume = integrate_flow_rate_to_volume_l(
            [(t2, 6.0), (t0, 6.0), (t1, 6.0)]
        )
        assert volume == pytest.approx(6.0, abs=1e-6)

    def test_fewer_than_two_samples_returns_zero(self) -> None:
        t0 = datetime(2026, 7, 23, 12, 0, 0, tzinfo=timezone.utc)
        assert integrate_flow_rate_to_volume_l([]) == 0.0
        assert integrate_flow_rate_to_volume_l([(t0, 5.0)]) == 0.0

    def test_negative_rates_clamped(self) -> None:
        t0 = datetime(2026, 7, 23, 12, 0, 0, tzinfo=timezone.utc)
        t1 = t0 + timedelta(minutes=1)
        volume = integrate_flow_rate_to_volume_l([(t0, -3.0), (t1, -3.0)])
        assert volume == 0.0


class TestExecutionWindow:
    def test_window_uses_execution_time_ms(self) -> None:
        end = datetime(2026, 7, 23, 12, 0, 5, tzinfo=timezone.utc)
        execution = SimpleNamespace(timestamp=end, execution_time_ms=2500)
        start, got_end = execution_window(execution)  # type: ignore[arg-type]
        assert got_end == end
        assert start == end - timedelta(milliseconds=2500)

    def test_zero_execution_ms_collapses_window(self) -> None:
        end = datetime(2026, 7, 23, 12, 0, 5, tzinfo=timezone.utc)
        execution = SimpleNamespace(timestamp=end, execution_time_ms=0)
        start, got_end = execution_window(execution)  # type: ignore[arg-type]
        assert start == got_end == end


class TestFlowProcessorKFactorAlias:
    """AUT-849: pulses_per_liter + legacy calibration_factor."""

    def test_default_is_fs300a_330(self) -> None:
        from src.sensors.sensor_libraries.active.flow import FlowProcessor

        processor = FlowProcessor()
        result = processor.process(
            raw_value=330.0,
            params={"input_type": "frequency"},
        )
        # 330 Hz * 60 / 330 = 60 L/min
        assert result.quality != "error"
        assert result.value == pytest.approx(60.0, abs=0.05)
        assert result.metadata["pulses_per_liter"] == 330

    def test_pulses_per_liter_from_calibration(self) -> None:
        from src.sensors.sensor_libraries.active.flow import FlowProcessor

        processor = FlowProcessor()
        result = processor.process(
            raw_value=450.0,
            calibration={"pulses_per_liter": 450},
            params={"input_type": "frequency"},
        )
        # 450 Hz * 60 / 450 = 60 L/min
        assert result.value == pytest.approx(60.0, abs=0.05)

    def test_legacy_calibration_factor_alias(self) -> None:
        from src.sensors.sensor_libraries.active.flow import FlowProcessor

        processor = FlowProcessor()
        result = processor.process(
            raw_value=330.0,
            calibration={"calibration_factor": 330},
            params={"input_type": "frequency"},
        )
        assert result.value == pytest.approx(60.0, abs=0.05)
        assert result.metadata["pulses_per_liter"] == 330

    def test_params_pulses_override_legacy_calibration_factor(self) -> None:
        from src.sensors.sensor_libraries.active.flow import FlowProcessor

        processor = FlowProcessor()
        result = processor.process(
            raw_value=330.0,
            calibration={"calibration_factor": 450},
            params={"input_type": "frequency", "pulses_per_liter": 330},
        )
        assert result.value == pytest.approx(60.0, abs=0.05)


class TestRefillDockConstants:
    def test_aut1288_gpio_and_device(self) -> None:
        assert REFILL_FLOW_GPIO == 14
        assert REFILL_FLOW_DEVICE_ID == "ESP_57E1D4"


@pytest.mark.asyncio
async def test_accumulate_flow_volume_l_integrates_known_readings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Service path: known L/min samples in window → expected liters."""
    esp_id = uuid4()
    t0 = datetime(2026, 7, 23, 12, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(minutes=2)

    rows = [
        SimpleNamespace(
            timestamp=t0,
            processed_value=3.0,
            raw_value=None,
            sensor_type="flow",
            quality="excellent",
        ),
        SimpleNamespace(
            timestamp=t1,
            processed_value=3.0,
            raw_value=None,
            sensor_type="flow",
            quality="good",
        ),
    ]

    class _FakeSensorRepo:
        async def get_data_range(self, *_args, **_kwargs):
            return rows

    service = FlowVolumeService(session=SimpleNamespace())  # type: ignore[arg-type]
    monkeypatch.setattr(service, "sensor_repo", _FakeSensorRepo())

    result = await service.accumulate_flow_volume_l(esp_id, 14, t0, t1)
    # 3 L/min × 2 min = 6 L
    assert result.volume_l == pytest.approx(6.0, abs=1e-4)
    assert result.sample_count == 2
    assert result.gpio == 14


@pytest.mark.asyncio
async def test_accumulate_skips_quality_error_samples(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ISR/stop spikes (quality=error) must not inflate liters."""
    esp_id = uuid4()
    t0 = datetime(2026, 7, 27, 20, 25, 42, tzinfo=timezone.utc)
    t1 = t0 + timedelta(seconds=1)
    t2 = t0 + timedelta(seconds=2)

    rows = [
        SimpleNamespace(
            timestamp=t0,
            processed_value=8.15,
            raw_value=45.0,
            sensor_type="flow",
            quality="excellent",
        ),
        SimpleNamespace(
            timestamp=t1,
            processed_value=8.13,
            raw_value=45.0,
            sensor_type="flow",
            quality="excellent",
        ),
        # Pump-OFF spike — same pattern as live ESP_57E1D4 GPIO14 @ 22:25:44
        SimpleNamespace(
            timestamp=t2,
            processed_value=134.37,
            raw_value=742.0,
            sensor_type="flow",
            quality="error",
        ),
    ]

    class _FakeSensorRepo:
        async def get_data_range(self, *_args, **_kwargs):
            return rows

    service = FlowVolumeService(session=SimpleNamespace())  # type: ignore[arg-type]
    monkeypatch.setattr(service, "sensor_repo", _FakeSensorRepo())

    result = await service.accumulate_flow_volume_l(esp_id, 14, t0, t2)
    # Only t0→t1: avg ≈ 8.14 L/min × (1/60) min ≈ 0.1357 L — not +1.2 L from spike
    assert result.sample_count == 2
    assert result.volume_l == pytest.approx(8.14 / 60.0, abs=1e-3)
    assert result.volume_l < 0.5
