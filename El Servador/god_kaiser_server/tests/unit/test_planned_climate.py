"""
Unit tests: Planned climate targets + derived VPD band (AUT-1239 / Welle 6 K2).

GWT:
- Temp-Ziel + Feuchte-Ziel → beide Ziele + abgeleitetes VPD-Band (kein stored VPD)
- Nur Temp → erkennbar nicht berechenbar (missing humidity)
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.services.planned_climate import (
    CLIMATE_DOMAIN,
    CLIMATE_MEASURES,
    derive_vpd_band_from_planned,
    resolve_climate_targets_at,
)
from src.services.vpd_calculator import calculate_vpd


class TestDeriveVpdBandFromPlanned:
    """Pure derivation from two planned values — reuses calculate_vpd."""

    def test_both_targets_yield_point_band(self):
        temp_c = 24.0
        humidity_rh = 60.0
        expected = calculate_vpd(temp_c, humidity_rh)
        assert expected is not None

        result = derive_vpd_band_from_planned(temp_c, humidity_rh)

        assert result.computable is True
        assert result.reason is None
        assert result.vpd_kpa == expected
        assert result.vpd_min_kpa == expected
        assert result.vpd_max_kpa == expected
        assert result.source == "planned_targets"

    def test_tolerances_expand_band_via_corners(self):
        # No invented agronomic defaults — tolerances come from caller/segments.
        result = derive_vpd_band_from_planned(
            temperature_c=24.0,
            humidity_rh=60.0,
            temperature_tolerance=1.0,
            humidity_tolerance=5.0,
        )

        assert result.computable is True
        # Higher T + lower RH → higher VPD; lower T + higher RH → lower VPD
        high = calculate_vpd(25.0, 55.0)
        low = calculate_vpd(23.0, 65.0)
        assert high is not None and low is not None
        assert result.vpd_min_kpa == low
        assert result.vpd_max_kpa == high
        assert result.vpd_min_kpa <= result.vpd_kpa <= result.vpd_max_kpa

    def test_missing_humidity_not_silent(self):
        result = derive_vpd_band_from_planned(temperature_c=24.0, humidity_rh=None)

        assert result.computable is False
        assert result.reason == "missing_target_humidity"
        assert result.vpd_kpa is None
        assert result.vpd_min_kpa is None
        assert result.vpd_max_kpa is None

    def test_missing_temperature_not_silent(self):
        result = derive_vpd_band_from_planned(temperature_c=None, humidity_rh=60.0)

        assert result.computable is False
        assert result.reason == "missing_target_temperature"

    def test_both_missing_not_silent(self):
        result = derive_vpd_band_from_planned(temperature_c=None, humidity_rh=None)

        assert result.computable is False
        assert result.reason == "missing_target_temperature_and_humidity"

    def test_out_of_range_inputs_not_silent(self):
        result = derive_vpd_band_from_planned(temperature_c=24.0, humidity_rh=150.0)

        assert result.computable is False
        assert result.reason == "inputs_out_of_range"


class TestResolveClimateTargetsAt:
    """Resolution uses PlanSegmentRepository.resolve_at — same read path as EC/pH."""

    @pytest.mark.asyncio
    async def test_resolves_both_measures_and_derives_vpd(self):
        at = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
        temp_seg = MagicMock(
            id=uuid4(),
            value=24.0,
            tolerance=None,
            from_ts=datetime(2026, 7, 1, tzinfo=timezone.utc),
            to_ts=datetime(2026, 7, 15, tzinfo=timezone.utc),
        )
        hum_seg = MagicMock(
            id=uuid4(),
            value=60.0,
            tolerance=None,
            from_ts=datetime(2026, 7, 1, tzinfo=timezone.utc),
            to_ts=datetime(2026, 7, 15, tzinfo=timezone.utc),
        )

        session = AsyncMock()
        repo = MagicMock()
        repo.resolve_at = AsyncMock(side_effect=[temp_seg, hum_seg])

        result = await resolve_climate_targets_at(
            session=session,
            zone_id="zelt_test",
            at=at,
            subzone_config_id=None,
            _repo=repo,
        )

        assert result.domain == CLIMATE_DOMAIN
        assert result.zone_id == "zelt_test"
        assert {t.measure for t in result.targets} == set(CLIMATE_MEASURES)
        temp_t = next(t for t in result.targets if t.measure == "target_temperature")
        hum_t = next(t for t in result.targets if t.measure == "target_humidity")
        assert temp_t.value == 24.0
        assert hum_t.value == 60.0
        assert result.vpd_band.computable is True
        assert result.vpd_band.vpd_kpa == calculate_vpd(24.0, 60.0)

        # Exactly two resolve_at calls — domain=climate, one per measure
        assert repo.resolve_at.await_count == 2
        for call in repo.resolve_at.await_args_list:
            assert call.kwargs["domain"] == "climate"
            assert call.kwargs["zone_id"] == "zelt_test"
            assert call.kwargs["at"] == at

    @pytest.mark.asyncio
    async def test_missing_humidity_segment_marks_vpd_incomplete(self):
        at = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
        temp_seg = MagicMock(
            id=uuid4(),
            value=24.0,
            tolerance=None,
            from_ts=datetime(2026, 7, 1, tzinfo=timezone.utc),
            to_ts=None,
        )

        session = AsyncMock()
        repo = MagicMock()
        repo.resolve_at = AsyncMock(side_effect=[temp_seg, None])

        result = await resolve_climate_targets_at(
            session=session,
            zone_id="zelt_test",
            at=at,
            _repo=repo,
        )

        assert result.vpd_band.computable is False
        assert result.vpd_band.reason == "missing_target_humidity"
        hum_t = next(t for t in result.targets if t.measure == "target_humidity")
        assert hum_t.value is None
        assert hum_t.resolved_via == "none"
