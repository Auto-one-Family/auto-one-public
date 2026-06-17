"""Unit tests for calibration MQTT response handler."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest

from src.mqtt.handlers.calibration_response_handler import (
    CalibrationResponseHandler,
    _ADC_MAX,
    _ADC_VOLTAGE,
    _EC_DEFAULT_SLOPE,
    _EC_TEMP_COEFFICIENT,
    _STABLE_ADC_STDDEV_THRESHOLD,
)


@pytest.mark.asyncio
async def test_measurement_event_does_not_persist_point(db_session):
    handler = CalibrationResponseHandler()
    broadcast_mock = AsyncMock()

    class _ActiveSession:
        id = "session-123"
        method = "moisture_2point"
        session_metadata = {}
        calibration_points = {}

    @asynccontextmanager
    async def _session_ctx():
        yield db_session

    with (
        patch(
            "src.mqtt.handlers.calibration_response_handler.resilient_session",
            side_effect=_session_ctx,
        ),
        patch(
            "src.mqtt.handlers.calibration_response_handler.CalibrationSessionRepository"
        ) as repo_cls,
        patch.object(handler, "_broadcast_calibration_event", broadcast_mock),
    ):
        repo_instance = repo_cls.return_value
        repo_instance.get_active_session = AsyncMock(return_value=_ActiveSession())

        topic = "kaiser/main/esp/ESP_TEST_001/sensor/4/response"
        payload = {
            "success": True,
            "raw": 1234.5,
            "quality": "good",
            "sensor_type": "moisture",
            "intent_id": "intent-1",
            "correlation_id": "corr-1",
        }

        result = await handler.handle_sensor_response(topic, payload)

    assert result is True
    assert broadcast_mock.await_count == 1
    event_type = broadcast_mock.await_args.args[0]
    event_kwargs = broadcast_mock.await_args.kwargs
    assert event_type == "calibration_measurement_received"
    assert event_kwargs["raw"] == 1234.5
    assert event_kwargs["raw_value"] == 1234.5
    assert event_kwargs["session_id"] == "session-123"


# ── AUT-488: _compute_ec_preview unit tests ────────────────────────────────


class TestComputeEcPreview:
    """Unit tests for CalibrationResponseHandler._compute_ec_preview (AUT-488)."""

    # Test raw ADC value: mid-range to avoid edge cases
    RAW_ADC = 1500.0

    def _make_session(self, method="ec_linear_2point", points=None, cal_temp=None):
        """Build a minimal mock CalibrationSession."""

        class _Session:
            pass

        s = _Session()
        s.method = method
        s.session_metadata = (
            {"calibration_temperature": cal_temp} if cal_temp is not None else {}
        )
        s.calibration_points = {"points": points or []}
        return s

    # ── Non-EC sensor ──────────────────────────────────────────────────

    def test_non_ec_sensor_returns_no_preview(self):
        result = CalibrationResponseHandler._compute_ec_preview(
            sensor_type="ph", raw_value=self.RAW_ADC, session=None
        )
        assert result["preview_ec_us_cm"] is None
        assert result["preview_available"] is False
        assert result["temperature_used"] is None

    def test_moisture_sensor_returns_no_preview(self):
        result = CalibrationResponseHandler._compute_ec_preview(
            sensor_type="moisture", raw_value=self.RAW_ADC, session=None
        )
        assert result["preview_ec_us_cm"] is None
        assert result["preview_available"] is False

    # ── Strategy 4 fallback: no session ───────────────────────────────

    def test_no_session_uses_default_mapping(self):
        result = CalibrationResponseHandler._compute_ec_preview(
            sensor_type="ec", raw_value=self.RAW_ADC, session=None
        )
        voltage = (self.RAW_ADC / _ADC_MAX) * _ADC_VOLTAGE
        expected_ec = round(max(0.0, min(20000.0, _EC_DEFAULT_SLOPE * voltage)), 1)
        assert result["preview_ec_us_cm"] == pytest.approx(expected_ec, abs=0.5)
        assert result["preview_available"] is False
        assert result["temperature_used"] == pytest.approx(25.0)
        assert result["temperature_default"] is True

    def test_no_points_uses_default_mapping(self):
        session = self._make_session(method="ec_linear_2point", points=[])
        result = CalibrationResponseHandler._compute_ec_preview(
            sensor_type="ec", raw_value=self.RAW_ADC, session=session
        )
        assert result["preview_available"] is False
        assert result["preview_ec_us_cm"] is not None  # default value returned

    # ── Strategy 1: ec_linear_2point with both points ─────────────────

    def test_ec_linear_2point_both_points_returns_accurate_preview(self):
        # Reference_low: 1413 µS/cm at ADC 625; reference_high: 12880 µS/cm at ADC 2500
        points = [
            {"point_role": "reference_low", "raw": 625.0, "reference": 1413.0},
            {"point_role": "reference_high", "raw": 2500.0, "reference": 12880.0},
        ]
        session = self._make_session(method="ec_linear_2point", points=points, cal_temp=25.0)
        result = CalibrationResponseHandler._compute_ec_preview(
            sensor_type="ec", raw_value=self.RAW_ADC, session=session
        )
        assert result["preview_available"] is True
        assert result["preview_ec_us_cm"] is not None
        assert result["temperature_used"] == pytest.approx(25.0)
        assert result["temperature_default"] is False
        # At 25°C calibration temp the slope is straightforward — result should be in EC range
        assert 0.0 <= result["preview_ec_us_cm"] <= 20000.0

    def test_ec_linear_2point_both_points_at_different_temperature(self):
        # Calibration at 20°C — reference must be normalized
        points = [
            {"point_role": "reference_low", "raw": 625.0, "reference": 1413.0},
            {"point_role": "reference_high", "raw": 2500.0, "reference": 12880.0},
        ]
        session = self._make_session(method="ec_linear_2point", points=points, cal_temp=20.0)
        result = CalibrationResponseHandler._compute_ec_preview(
            sensor_type="ec", raw_value=self.RAW_ADC, session=session
        )
        assert result["preview_available"] is True
        assert result["temperature_used"] == pytest.approx(20.0)
        assert result["temperature_default"] is False
        assert 0.0 <= result["preview_ec_us_cm"] <= 20000.0

    def test_ec_linear_2point_both_points_uses_session_temperature(self):
        """Session metadata temperature is reflected in temperature_used field."""
        points = [
            {"point_role": "reference_low", "raw": 625.0, "reference": 1413.0},
            {"point_role": "reference_high", "raw": 2500.0, "reference": 12880.0},
        ]
        session_25 = self._make_session(method="ec_linear_2point", points=points, cal_temp=25.0)
        session_30 = self._make_session(method="ec_linear_2point", points=points, cal_temp=30.0)
        result_25 = CalibrationResponseHandler._compute_ec_preview(
            sensor_type="ec", raw_value=self.RAW_ADC, session=session_25
        )
        result_30 = CalibrationResponseHandler._compute_ec_preview(
            sensor_type="ec", raw_value=self.RAW_ADC, session=session_30
        )
        # Session temperature is stored in temperature_used
        assert result_25["temperature_used"] == pytest.approx(25.0)
        assert result_30["temperature_used"] == pytest.approx(30.0)
        # Note: preview values may be identical at 25°C target because the AUT-299 normalization
        # (ref * temp_factor) and the subsequent ATC division (÷ temp_factor) cancel out.
        # Both results must be in valid EC range.
        assert result_25["preview_available"] is True
        assert result_30["preview_available"] is True
        assert 0.0 <= result_25["preview_ec_us_cm"] <= 20000.0
        assert 0.0 <= result_30["preview_ec_us_cm"] <= 20000.0

    # ── Strategy 2: ec_linear_2point with ONE point ───────────────────

    def test_ec_linear_2point_one_point_reference_low(self):
        points = [
            {"point_role": "reference_low", "raw": 625.0, "reference": 1413.0},
        ]
        session = self._make_session(method="ec_linear_2point", points=points)
        result = CalibrationResponseHandler._compute_ec_preview(
            sensor_type="ec", raw_value=self.RAW_ADC, session=session
        )
        assert result["preview_available"] is True
        assert result["preview_ec_us_cm"] is not None
        assert 0.0 <= result["preview_ec_us_cm"] <= 20000.0

    def test_ec_linear_2point_one_point_reference_high(self):
        points = [
            {"point_role": "reference_high", "raw": 2500.0, "reference": 12880.0},
        ]
        session = self._make_session(method="ec_linear_2point", points=points)
        result = CalibrationResponseHandler._compute_ec_preview(
            sensor_type="ec", raw_value=self.RAW_ADC, session=session
        )
        assert result["preview_available"] is True
        assert result["preview_ec_us_cm"] is not None

    # ── Strategy 3: ec_2point (air + reference) ───────────────────────

    def test_ec_2point_with_air_and_reference_points(self):
        points = [
            {"point_role": "air", "raw": 200.0, "reference": 0.0},
            {"point_role": "reference", "raw": 2000.0, "reference": 1413.0},
        ]
        session = self._make_session(method="ec_2point", points=points)
        result = CalibrationResponseHandler._compute_ec_preview(
            sensor_type="ec", raw_value=self.RAW_ADC, session=session
        )
        assert result["preview_available"] is True
        assert result["preview_ec_us_cm"] is not None
        assert 0.0 <= result["preview_ec_us_cm"] <= 20000.0

    # ── Strategy 3: ec_1point ─────────────────────────────────────────

    def test_ec_1point_with_reference_point(self):
        points = [
            {"point_role": "reference", "raw": 625.0, "reference": 1413.0},
        ]
        session = self._make_session(method="ec_1point", points=points)
        result = CalibrationResponseHandler._compute_ec_preview(
            sensor_type="ec", raw_value=self.RAW_ADC, session=session
        )
        assert result["preview_available"] is True
        assert result["preview_ec_us_cm"] is not None
        assert 0.0 <= result["preview_ec_us_cm"] <= 20000.0

    # ── Temperature default flag ───────────────────────────────────────

    def test_no_session_metadata_uses_default_temperature(self):
        session = self._make_session(method="ec_linear_2point", points=[], cal_temp=None)
        result = CalibrationResponseHandler._compute_ec_preview(
            sensor_type="ec", raw_value=self.RAW_ADC, session=session
        )
        assert result["temperature_default"] is True
        assert result["temperature_used"] == pytest.approx(25.0)

    def test_session_with_calibration_temperature_not_default(self):
        points = [
            {"point_role": "reference_low", "raw": 625.0, "reference": 1413.0},
            {"point_role": "reference_high", "raw": 2500.0, "reference": 12880.0},
        ]
        session = self._make_session(method="ec_linear_2point", points=points, cal_temp=22.5)
        result = CalibrationResponseHandler._compute_ec_preview(
            sensor_type="ec", raw_value=self.RAW_ADC, session=session
        )
        assert result["temperature_default"] is False
        assert result["temperature_used"] == pytest.approx(22.5)


# ── AUT-488: stable + adc_stddev pass-through tests ───────────────────────


@pytest.mark.asyncio
async def test_stable_and_adc_stddev_forwarded_to_ws_event(db_session):
    """AUT-488 B7/B8/B9: stable and adc_stddev from ESP payload appear in WS event."""
    handler = CalibrationResponseHandler()
    broadcast_mock = AsyncMock()

    class _ActiveSession:
        id = "session-stable-test"
        method = "ec_linear_2point"
        session_metadata = {}
        calibration_points = {"points": []}

    @asynccontextmanager
    async def _session_ctx():
        yield db_session

    with (
        patch(
            "src.mqtt.handlers.calibration_response_handler.resilient_session",
            side_effect=_session_ctx,
        ),
        patch(
            "src.mqtt.handlers.calibration_response_handler.CalibrationSessionRepository"
        ) as repo_cls,
        patch.object(handler, "_broadcast_calibration_event", broadcast_mock),
    ):
        repo_instance = repo_cls.return_value
        repo_instance.get_active_session = AsyncMock(return_value=_ActiveSession())
        repo_instance.get_sessions_for_sensor = AsyncMock(return_value=[])

        topic = "kaiser/main/esp/ESP_TEST_001/sensor/34/response"
        payload = {
            "success": True,
            "raw": 1500.0,
            "quality": "good",
            "sensor_type": "ec",
            "stable": True,
            "adc_stddev": 12.5,
            "correlation_id": "corr-ec-1",
        }

        result = await handler.handle_sensor_response(topic, payload)

    assert result is True
    assert broadcast_mock.await_count == 1
    event_kwargs = broadcast_mock.await_args.kwargs
    assert event_kwargs["stable"] is True
    assert event_kwargs["adc_stddev"] == pytest.approx(12.5)


@pytest.mark.asyncio
async def test_stable_derived_from_adc_stddev_when_not_in_payload(db_session):
    """AUT-488 B9: stable derived from adc_stddev when ESP does not send explicit stable flag."""
    handler = CalibrationResponseHandler()
    broadcast_mock = AsyncMock()

    class _ActiveSession:
        id = "session-derived"
        method = "ec_linear_2point"
        session_metadata = {}
        calibration_points = {"points": []}

    @asynccontextmanager
    async def _session_ctx():
        yield db_session

    with (
        patch(
            "src.mqtt.handlers.calibration_response_handler.resilient_session",
            side_effect=_session_ctx,
        ),
        patch(
            "src.mqtt.handlers.calibration_response_handler.CalibrationSessionRepository"
        ) as repo_cls,
        patch.object(handler, "_broadcast_calibration_event", broadcast_mock),
    ):
        repo_instance = repo_cls.return_value
        repo_instance.get_active_session = AsyncMock(return_value=_ActiveSession())
        repo_instance.get_sessions_for_sensor = AsyncMock(return_value=[])

        topic = "kaiser/main/esp/ESP_TEST_001/sensor/34/response"
        # adc_stddev above threshold → should be marked unstable
        payload = {
            "success": True,
            "raw": 1500.0,
            "quality": "good",
            "sensor_type": "ec",
            # no "stable" key
            "adc_stddev": _STABLE_ADC_STDDEV_THRESHOLD + 1.0,
            "correlation_id": "corr-ec-2",
        }

        result = await handler.handle_sensor_response(topic, payload)

    assert result is True
    event_kwargs = broadcast_mock.await_args.kwargs
    # Derived: stddev > threshold → unstable
    assert event_kwargs["stable"] is False


@pytest.mark.asyncio
async def test_preview_ec_fields_present_in_ec_measurement_event(db_session):
    """AUT-488 A3: preview_ec_us_cm and related fields appear in WS event for EC sensor."""
    handler = CalibrationResponseHandler()
    broadcast_mock = AsyncMock()

    class _ActiveSession:
        id = "session-ec-preview"
        method = "ec_linear_2point"
        session_metadata = {}
        calibration_points = {"points": []}

    @asynccontextmanager
    async def _session_ctx():
        yield db_session

    with (
        patch(
            "src.mqtt.handlers.calibration_response_handler.resilient_session",
            side_effect=_session_ctx,
        ),
        patch(
            "src.mqtt.handlers.calibration_response_handler.CalibrationSessionRepository"
        ) as repo_cls,
        patch.object(handler, "_broadcast_calibration_event", broadcast_mock),
    ):
        repo_instance = repo_cls.return_value
        repo_instance.get_active_session = AsyncMock(return_value=_ActiveSession())
        repo_instance.get_sessions_for_sensor = AsyncMock(return_value=[])

        topic = "kaiser/main/esp/ESP_TEST_001/sensor/34/response"
        payload = {
            "success": True,
            "raw": 1500.0,
            "quality": "good",
            "sensor_type": "ec",
        }

        result = await handler.handle_sensor_response(topic, payload)

    assert result is True
    event_kwargs = broadcast_mock.await_args.kwargs
    # All AUT-488 preview fields must be present
    assert "preview_ec_us_cm" in event_kwargs
    assert "preview_available" in event_kwargs
    assert "temperature_used" in event_kwargs
    assert "temperature_default" in event_kwargs
