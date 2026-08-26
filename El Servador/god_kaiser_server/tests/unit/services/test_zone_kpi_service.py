"""AUT-1530: Zone KPI honesty — no lux-as-PPFD DLI, no bmp280_humidity mix."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.zone_kpi_service import ZoneKPIService


def _make_kpi_service() -> ZoneKPIService:
    session = MagicMock()
    session.execute = AsyncMock()
    return ZoneKPIService(session)


class TestZoneKpiHonestyAut1530:
    """Cut unread DLI and non-existent BMP280 humidity from zone KPIs."""

    def test_calculate_dli_is_removed(self):
        service = _make_kpi_service()
        assert not hasattr(service, "calculate_dli")
        assert not hasattr(service, "_get_sensor_readings_24h")

    @pytest.mark.asyncio
    async def test_calculate_vpd_humidity_types_exclude_bmp280(self):
        service = _make_kpi_service()

        with patch.object(
            service, "_get_latest_sensor_value", new=AsyncMock(return_value=None)
        ) as mock_helper:
            await service.calculate_vpd("zone_test")

        assert mock_helper.await_count == 2
        temp_types = mock_helper.await_args_list[0].args[1]
        hum_types = mock_helper.await_args_list[1].args[1]
        assert "sht31_temp" in temp_types
        assert hum_types == ["sht31_humidity"]
        assert "bmp280_humidity" not in hum_types
        assert "bme280_humidity" not in hum_types

    @pytest.mark.asyncio
    async def test_calculate_vpd_keeps_sht31_pair(self):
        service = _make_kpi_service()

        async def _latest(_zone_id, sensor_types, domain=None):
            if "sht31_temp" in sensor_types:
                return 24.0
            if sensor_types == ["sht31_humidity"]:
                return 60.0
            return None

        with patch.object(service, "_get_latest_sensor_value", new=AsyncMock(side_effect=_latest)):
            result = await service.calculate_vpd("zone_sht31")

        assert result is not None
        assert result["temperature_c"] == 24.0
        assert result["humidity_pct"] == 60.0
        assert result["vpd_kpa"] > 0

    @pytest.mark.asyncio
    async def test_get_all_kpis_dli_is_none_without_lux_ppfd(self):
        service = _make_kpi_service()

        with (
            patch.object(
                service, "calculate_vpd", new=AsyncMock(return_value={"vpd_kpa": 1.1})
            ),
            patch.object(service, "calculate_growth_progress", new=AsyncMock(return_value=None)),
            patch.object(service, "get_zone_health_score", new=AsyncMock(return_value=None)),
        ):
            result = await service.get_all_kpis("zone_test")

        assert result["dli"] is None
        assert "dli_mol_m2_day" not in (result["dli"] or {})
        assert result["vpd"] == {"vpd_kpa": 1.1}
