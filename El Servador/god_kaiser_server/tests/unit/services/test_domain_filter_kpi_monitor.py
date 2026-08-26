"""
AUT-1087: Optional domain pre-filter in zone KPI and monitor data services.

P4 tests — ZoneKPIService:
    - domain kwarg propagates through the calculation chain
    - domain=None preserves backward-compatible (zone-wide) behaviour

P5 tests — MonitorDataService (VPD inheritance):
    - domain='luft' keeps only luft-ESP in esp_uuids; VPD sensor entry
      appears transitively because it belongs to that ESP
    - domain='boden' with 0 devices returns a valid empty ZoneMonitorData
    - domain=None includes all ESPs (regression guard)

P6 tests — MonitorDataService (AUT-1179 n:m sensor-subzone):
    - sensor n:m-assigned to two subzones appears in both (not "Keine Subzone")
    - legacy GPIO-assigned sensor still resolved correctly (regression guard)
    - sensor assigned via BOTH n:m and GPIO to the same subzone appears once (dedup)
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.monitor_data_service import MonitorDataService
from src.services.zone_kpi_service import ZoneKPIService


# =============================================================================
# Shared helpers
# =============================================================================


def _scalars_result(items):
    """Mock session.execute() result consumed via .scalars().all()."""
    scalars = MagicMock()
    scalars.all.return_value = items
    result = MagicMock()
    result.scalars.return_value = scalars
    return result


def _all_result(rows):
    """Mock session.execute() result consumed via .all()."""
    result = MagicMock()
    result.all.return_value = rows
    return result


def _scalar_one_or_none_result(value):
    """Mock session.execute() result consumed via .scalar_one_or_none()."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _make_kpi_service():
    """ZoneKPIService backed by a fully mocked async session."""
    session = MagicMock()
    session.execute = AsyncMock()
    return ZoneKPIService(session), session


# =============================================================================
# P4: ZoneKPIService domain filter propagation
# =============================================================================


class TestZoneKPIServiceDomainFilter:
    """AUT-1087 P4: domain parameter propagates through the KPI chain."""

    @pytest.mark.asyncio
    async def test_calculate_vpd_forwards_domain_to_helper(self):
        """calculate_vpd(domain='luft') passes domain to _get_latest_sensor_value."""
        service, _ = _make_kpi_service()

        with patch.object(
            service, "_get_latest_sensor_value", new=AsyncMock(return_value=None)
        ) as mock_helper:
            await service.calculate_vpd("zone_luft", domain="luft")

        # Two calls: temp types + humidity types
        assert mock_helper.await_count == 2
        for c in mock_helper.await_args_list:
            assert c.kwargs.get("domain") == "luft", (
                "domain='luft' must be forwarded to _get_latest_sensor_value"
            )

    @pytest.mark.asyncio
    async def test_calculate_vpd_no_domain_passes_none_to_helper(self):
        """calculate_vpd() without domain forwards None (backward-compat guard)."""
        service, _ = _make_kpi_service()

        with patch.object(
            service, "_get_latest_sensor_value", new=AsyncMock(return_value=None)
        ) as mock_helper:
            await service.calculate_vpd("zone_test")

        for c in mock_helper.await_args_list:
            assert c.kwargs.get("domain") is None

    @pytest.mark.asyncio
    async def test_get_all_kpis_forwards_domain_to_vpd_only(self):
        """get_all_kpis(domain='luft') passes domain to vpd but NOT health/growth."""
        service, _ = _make_kpi_service()

        with (
            patch.object(service, "calculate_vpd", new=AsyncMock(return_value=None)) as m_vpd,
            patch.object(service, "calculate_growth_progress", new=AsyncMock(return_value=None)) as m_growth,
            patch.object(service, "get_zone_health_score", new=AsyncMock(return_value=None)) as m_health,
        ):
            result = await service.get_all_kpis("zone_luft", domain="luft")

        m_vpd.assert_called_once_with("zone_luft", domain="luft")
        # Growth and health are intentionally zone-wide (AUT-1087 explicit exclusion)
        m_growth.assert_called_once_with("zone_luft")
        m_health.assert_called_once_with("zone_luft")
        assert result["zone_id"] == "zone_luft"
        assert result["dli"] is None

    @pytest.mark.asyncio
    async def test_get_all_kpis_no_domain_is_backward_compatible(self):
        """get_all_kpis() without domain keeps existing zone-wide behaviour."""
        service, _ = _make_kpi_service()

        with (
            patch.object(
                service, "calculate_vpd", new=AsyncMock(return_value={"vpd_kpa": 1.2})
            ) as m_vpd,
            patch.object(service, "calculate_growth_progress", new=AsyncMock(return_value=None)),
            patch.object(service, "get_zone_health_score", new=AsyncMock(return_value=None)),
        ):
            result = await service.get_all_kpis("zone_test")

        # domain=None must be forwarded explicitly (not omitted)
        m_vpd.assert_called_once_with("zone_test", domain=None)
        assert result["vpd"] == {"vpd_kpa": 1.2}
        assert result["dli"] is None

    @pytest.mark.asyncio
    async def test_get_latest_sensor_value_returns_none_for_empty_domain(self):
        """_get_latest_sensor_value with domain='boden' and no data returns None, no exception."""
        service, session = _make_kpi_service()
        session.execute.return_value = _scalar_one_or_none_result(None)

        result = await service._get_latest_sensor_value(
            "zone_test", ["sht31_temp"], domain="boden"
        )

        assert result is None


# =============================================================================
# P5: MonitorDataService — VPD inheritance via domain-filtered esp_uuids
# =============================================================================


def _fake_esp(device_id: str, uuid: str, domain=None, zone_name: str = "Test Zone"):
    """SimpleNamespace mimicking ESPDevice for MonitorDataService queries."""
    return SimpleNamespace(
        id=uuid,
        device_id=device_id,
        zone_id="zone_test",
        zone_name=zone_name,
        domain=domain,
        status="online",
    )


def _fake_sensor_cfg(esp_uuid: str, gpio: int, sensor_type: str, sensor_id=None):
    """SimpleNamespace mimicking SensorConfig (enabled=True implied by mock filter).

    ``sensor_id`` is the SensorConfig primary-key UUID, used by the n:m lookup
    (AUT-1179).  Defaults to a fresh uuid4 so existing call-sites need no change.
    """
    return SimpleNamespace(
        id=sensor_id or uuid.uuid4(),
        esp_id=esp_uuid,
        gpio=gpio,
        sensor_type=sensor_type,
        sensor_name=sensor_type,
        enabled=True,
        operating_mode=None,
    )


def _fake_actuator_cfg(esp_uuid: str, gpio: int, actuator_type: str, actuator_id=None):
    """SimpleNamespace mimicking ActuatorConfig for monitor n:m tests."""
    return SimpleNamespace(
        id=actuator_id or uuid.uuid4(),
        esp_id=esp_uuid,
        gpio=gpio,
        actuator_type=actuator_type,
        actuator_name=actuator_type,
        enabled=True,
    )


def _build_side_effect(esps, subzone_cfgs, sensor_rows, actuator_rows, actuator_states):
    """
    Factory for session.execute() side_effect in get_zone_monitor_data.

    Execution order inside the method:
    0 → ESPs           (scalars)
    1 → SubzoneConfigs (scalars)
    2 → SensorConfigs  (all — tuples of (SensorConfig, device_id_str))
    3 → ActuatorConfigs(all — tuples of (ActuatorConfig, device_id_str))
    4 → ActuatorStates (scalars)
    """
    call_seq = [0]

    def side_effect(_stmt):
        idx = call_seq[0]
        call_seq[0] += 1
        if idx == 0:
            return _scalars_result(esps)
        if idx == 1:
            return _scalars_result(subzone_cfgs)
        if idx == 2:
            return _all_result(sensor_rows)
        if idx == 3:
            return _all_result(actuator_rows)
        if idx == 4:
            return _scalars_result(actuator_states)
        raise AssertionError(f"Unexpected session.execute() call #{idx}")  # pragma: no cover

    return side_effect


def _make_monitor_service(esps, subzone_cfgs, sensor_rows, actuator_rows, actuator_states):
    """Build MonitorDataService with fully mocked session for given data fixtures.

    Suitable for tests where subzone_cfgs is empty: the service's
    get_assignments_for_subzones() returns early (no execute call) so the
    session.execute() call sequence remains at positions 0–4.
    """
    session = MagicMock()
    session.execute = AsyncMock(
        side_effect=_build_side_effect(
            esps, subzone_cfgs, sensor_rows, actuator_rows, actuator_states
        )
    )
    return MonitorDataService(session)


# =============================================================================
# Helpers for P6: n:m sensor-subzone tests (AUT-1179)
#
# When subzone_cfgs is NON-EMPTY, get_assignments_for_subzones() calls
# session.execute() → adds positions in the call sequence:
#   0 → ESPs
#   1 → SubzoneConfigs
#   2 → n:m SensorSubzoneAssignments
#   3 → n:m ActuatorSubzoneAssignments  (Verortung)
#   4 → SensorConfigs
#   5 → ActuatorConfigs
#   6 → ActuatorStates
# =============================================================================


def _fake_subzone_cfg_nm(esp_id: str, subzone_id: str, subzone_name: str, pk_uuid, assigned_gpios=None):
    """SimpleNamespace mimicking SubzoneConfig for n:m test scenarios."""
    return SimpleNamespace(
        id=pk_uuid,
        esp_id=esp_id,
        subzone_id=subzone_id,
        subzone_name=subzone_name,
        parent_zone_id="zone_test",
        assigned_gpios=assigned_gpios or [],
    )


def _fake_nm_assignment(sensor_config_id, subzone_config_id):
    """SimpleNamespace mimicking SensorSubzoneAssignment junction-table row."""
    return SimpleNamespace(
        sensor_config_id=sensor_config_id,
        subzone_config_id=subzone_config_id,
    )


def _fake_actuator_nm_assignment(actuator_config_id, subzone_config_id):
    """SimpleNamespace mimicking ActuatorSubzoneAssignment junction-table row."""
    return SimpleNamespace(
        actuator_config_id=actuator_config_id,
        subzone_config_id=subzone_config_id,
    )


def _build_side_effect_with_nm(
    esps,
    subzone_cfgs,
    nm_rows,
    sensor_rows,
    actuator_rows,
    actuator_states,
    actuator_nm_rows=None,
):
    """
    Factory for session.execute() side_effect when subzone_cfgs is non-empty.

    Execution order inside the method (AUT-1179 + actuator Verortung):
    0 → ESPs                          (scalars)
    1 → SubzoneConfigs                (scalars)
    2 → n:m SensorSubzoneAssignments  (scalars)
    3 → n:m ActuatorSubzoneAssignments (scalars)
    4 → SensorConfigs                 (all — tuples)
    5 → ActuatorConfigs               (all — tuples)
    6 → ActuatorStates                (scalars)
    """
    if actuator_nm_rows is None:
        actuator_nm_rows = []
    call_seq = [0]

    def side_effect(_stmt):
        idx = call_seq[0]
        call_seq[0] += 1
        if idx == 0:
            return _scalars_result(esps)
        if idx == 1:
            return _scalars_result(subzone_cfgs)
        if idx == 2:
            return _scalars_result(nm_rows)
        if idx == 3:
            return _scalars_result(actuator_nm_rows)
        if idx == 4:
            return _all_result(sensor_rows)
        if idx == 5:
            return _all_result(actuator_rows)
        if idx == 6:
            return _scalars_result(actuator_states)
        raise AssertionError(f"Unexpected session.execute() call #{idx}")  # pragma: no cover

    return side_effect


def _make_monitor_service_with_nm(
    esps,
    subzone_cfgs,
    nm_rows,
    sensor_rows,
    actuator_rows,
    actuator_states,
    actuator_nm_rows=None,
):
    """Build MonitorDataService with fully mocked session for n:m test scenarios.

    Use this variant when subzone_cfgs is non-empty (sensor + actuator n:m
    execute calls are present at positions 2–3 in the call sequence).
    """
    session = MagicMock()
    session.execute = AsyncMock(
        side_effect=_build_side_effect_with_nm(
            esps,
            subzone_cfgs,
            nm_rows,
            sensor_rows,
            actuator_rows,
            actuator_states,
            actuator_nm_rows=actuator_nm_rows,
        )
    )
    return MonitorDataService(session)


class TestMonitorDataServiceDomainFilter:
    """AUT-1087 P5: VPD inheritance via domain-filtered ESP query."""

    @pytest.mark.asyncio
    async def test_domain_luft_includes_vpd_sensor_entry(self):
        """
        VPD inheritance test (AUT-1087 P5 core):

        When domain='luft' is requested, ESP_70705C (domain='luft') stays in
        esp_uuids.  Its VPD SensorConfig (sensor_type='vpd', VIRTUAL) is picked
        up by the existing SensorConfig.esp_id.in_(esp_uuids) join — transitively,
        without any new code.  This test verifies that 'vpd' appears in the
        returned sensor list.
        """
        luft_uuid = "uuid-7070"
        luft_esp = _fake_esp("ESP_70705C", uuid=luft_uuid, domain="luft")

        sensor_rows = [
            (_fake_sensor_cfg(luft_uuid, 0, "sht31_temp"), "ESP_70705C"),
            (_fake_sensor_cfg(luft_uuid, 0, "sht31_humidity"), "ESP_70705C"),
            (_fake_sensor_cfg(luft_uuid, 0, "vpd"), "ESP_70705C"),  # VIRTUAL
        ]

        service = _make_monitor_service(
            esps=[luft_esp],
            subzone_cfgs=[],
            sensor_rows=sensor_rows,
            actuator_rows=[],
            actuator_states=[],
        )

        with patch("src.db.repositories.sensor_repo.SensorRepository") as MockRepo:
            MockRepo.return_value.get_latest_readings_batch_by_config = AsyncMock(return_value={})
            result = await service.get_zone_monitor_data("zone_test", domain="luft")

        all_types = [s.sensor_type for g in result.subzones for s in g.sensors]
        assert "vpd" in all_types, (
            "VPD entry must be included for domain='luft': it belongs to ESP_70705C "
            "which passes the domain filter — inheritance is transitive via esp_uuids"
        )
        assert "sht31_temp" in all_types
        assert "sht31_humidity" in all_types

    @pytest.mark.asyncio
    async def test_domain_luft_excludes_wasser_sensor_types(self):
        """
        domain='luft': wasser ESP (ESP_AEAE64) is absent from esp_uuids;
        its ph/ec/ds18b20 sensors must NOT appear.
        The mock returns only the luft ESP (simulating a domain-filtered DB query).
        """
        luft_uuid = "uuid-7070"
        luft_esp = _fake_esp("ESP_70705C", uuid=luft_uuid, domain="luft")

        sensor_rows = [
            (_fake_sensor_cfg(luft_uuid, 0, "sht31_temp"), "ESP_70705C"),
        ]

        service = _make_monitor_service(
            esps=[luft_esp],  # wasser ESP absent — simulates domain filter applied in DB
            subzone_cfgs=[],
            sensor_rows=sensor_rows,
            actuator_rows=[],
            actuator_states=[],
        )

        with patch("src.db.repositories.sensor_repo.SensorRepository") as MockRepo:
            MockRepo.return_value.get_latest_readings_batch_by_config = AsyncMock(return_value={})
            result = await service.get_zone_monitor_data("zone_test", domain="luft")

        all_types = [s.sensor_type for g in result.subzones for s in g.sensors]
        assert "ph" not in all_types
        assert "ec" not in all_types
        assert "ds18b20" not in all_types

    @pytest.mark.asyncio
    async def test_domain_boden_no_devices_returns_valid_empty_monitor_data(self):
        """
        domain='boden' (0 devices in zone) must return a valid ZoneMonitorData
        with empty subzones and zero counts — no exception raised.
        """
        service = _make_monitor_service(
            esps=[],  # 0 devices for domain='boden'
            subzone_cfgs=[],
            sensor_rows=[],
            actuator_rows=[],
            actuator_states=[],
        )

        # SensorRepository must NOT be called when esps is empty (early return)
        with patch("src.db.repositories.sensor_repo.SensorRepository") as MockRepo:
            result = await service.get_zone_monitor_data("zone_test", domain="boden")

        MockRepo.assert_not_called()
        assert result.zone_id == "zone_test"
        assert result.subzones == []
        assert result.sensor_count == 0
        assert result.actuator_count == 0
        assert result.alarm_count == 0

    @pytest.mark.asyncio
    async def test_no_domain_includes_all_esps_in_zone(self):
        """
        Without domain, get_zone_monitor_data returns sensors from ALL ESPs
        in the zone (regression guard: default behaviour unchanged).
        """
        luft_uuid = "uuid-7070"
        wasser_uuid = "uuid-AEAE"
        luft_esp = _fake_esp("ESP_70705C", uuid=luft_uuid, domain="luft")
        wasser_esp = _fake_esp("ESP_AEAE64", uuid=wasser_uuid, domain="wasser")

        sensor_rows = [
            (_fake_sensor_cfg(luft_uuid, 0, "sht31_temp"), "ESP_70705C"),
            (_fake_sensor_cfg(wasser_uuid, 0, "ph"), "ESP_AEAE64"),
        ]

        service = _make_monitor_service(
            esps=[luft_esp, wasser_esp],
            subzone_cfgs=[],
            sensor_rows=sensor_rows,
            actuator_rows=[],
            actuator_states=[],
        )

        with patch("src.db.repositories.sensor_repo.SensorRepository") as MockRepo:
            MockRepo.return_value.get_latest_readings_batch_by_config = AsyncMock(return_value={})
            result = await service.get_zone_monitor_data("zone_test")  # no domain

        all_types = [s.sensor_type for g in result.subzones for s in g.sensors]
        assert "sht31_temp" in all_types, "luft sensor must appear without domain filter"
        assert "ph" in all_types, "wasser sensor must appear without domain filter"

    @pytest.mark.asyncio
    async def test_esp_query_excludes_soft_deleted_devices(self):
        """Zone-monitor ESP load must filter deleted_at IS NULL (ghost soft-deletes)."""
        captured: list = []

        async def capture_execute(stmt):
            captured.append(stmt)
            return _scalars_result([])

        session = MagicMock()
        session.execute = AsyncMock(side_effect=capture_execute)
        service = MonitorDataService(session)
        await service.get_zone_monitor_data("zelt_wohnzimmer")

        assert captured, "expected at least the ESP select"
        compiled = str(captured[0].compile(compile_kwargs={"literal_binds": True}))
        assert "deleted_at" in compiled.lower()
        assert "zelt_wohnzimmer" in compiled


# =============================================================================
# P6: MonitorDataService — n:m sensor-subzone assignments (AUT-1179)
# =============================================================================


class TestMonitorDataServiceNmAssignments:
    """AUT-1179: sensor_subzone_assignments junction table visibility in zone monitor."""

    @pytest.mark.asyncio
    async def test_nm_sensor_appears_in_all_assigned_subzones(self):
        """
        Core acceptance criterion (AUT-1179):

        A sensor n:m-assigned to two subzones via sensor_subzone_assignments must
        appear in BOTH subzones in the monitor output — not under "Keine Subzone".
        The two subzones have no GPIO entries (assigned_gpios=[]) so the legacy
        GPIO path would not resolve the sensor at all.
        """
        esp_uuid = "uuid-esp-nm01"
        sensor_uuid = uuid.uuid4()
        sc_pk_a = uuid.uuid4()
        sc_pk_b = uuid.uuid4()

        esp = _fake_esp("ESP_NM01", uuid=esp_uuid)

        # Two subzones — no GPIO assignments (n:m-only scenario)
        subzone_a = _fake_subzone_cfg_nm(
            esp_id="ESP_NM01",
            subzone_id="subzone_alpha",
            subzone_name="Alpha",
            pk_uuid=sc_pk_a,
        )
        subzone_b = _fake_subzone_cfg_nm(
            esp_id="ESP_NM01",
            subzone_id="subzone_beta",
            subzone_name="Beta",
            pk_uuid=sc_pk_b,
        )

        sensor = _fake_sensor_cfg(esp_uuid, gpio=5, sensor_type="ph", sensor_id=sensor_uuid)

        nm_rows = [
            _fake_nm_assignment(sensor_uuid, sc_pk_a),
            _fake_nm_assignment(sensor_uuid, sc_pk_b),
        ]

        service = _make_monitor_service_with_nm(
            esps=[esp],
            subzone_cfgs=[subzone_a, subzone_b],
            nm_rows=nm_rows,
            sensor_rows=[(sensor, "ESP_NM01")],
            actuator_rows=[],
            actuator_states=[],
        )

        with patch("src.db.repositories.sensor_repo.SensorRepository") as MockRepo:
            MockRepo.return_value.get_latest_readings_batch_by_config = AsyncMock(return_value={})
            result = await service.get_zone_monitor_data("zone_test")

        # Collect (subzone_id, sensor_types) from result
        subzone_map = {g.subzone_id: [s.sensor_type for s in g.sensors] for g in result.subzones}

        assert "subzone_alpha" in subzone_map, "Sensor must appear in subzone_alpha"
        assert "subzone_beta" in subzone_map, "Sensor must appear in subzone_beta"
        assert "ph" in subzone_map["subzone_alpha"], "ph sensor must be in subzone_alpha"
        assert "ph" in subzone_map["subzone_beta"], "ph sensor must be in subzone_beta"

        # Must NOT appear under "Keine Subzone" (None key)
        keine_subzone_sensors = subzone_map.get(None, [])
        assert "ph" not in keine_subzone_sensors, (
            "ph sensor must not fall back to 'Keine Subzone' when n:m assignments exist"
        )

    @pytest.mark.asyncio
    async def test_gpio_sensor_unaffected_by_nm_extension(self):
        """
        Regression guard (AUT-1179):

        A legacy 1:1 GPIO-assigned sensor with no n:m assignments must still
        appear in the correct subzone via the GPIO path — unchanged behaviour.
        """
        esp_uuid = "uuid-esp-gpio01"
        sensor_uuid = uuid.uuid4()
        sc_pk = uuid.uuid4()

        esp = _fake_esp("ESP_GPIO01", uuid=esp_uuid)

        # Subzone with GPIO 5 assigned
        subzone = _fake_subzone_cfg_nm(
            esp_id="ESP_GPIO01",
            subzone_id="subzone_gpio",
            subzone_name="GPIO Subzone",
            pk_uuid=sc_pk,
            assigned_gpios=[5],
        )

        sensor = _fake_sensor_cfg(esp_uuid, gpio=5, sensor_type="moisture", sensor_id=sensor_uuid)

        service = _make_monitor_service_with_nm(
            esps=[esp],
            subzone_cfgs=[subzone],
            nm_rows=[],  # no n:m assignments
            sensor_rows=[(sensor, "ESP_GPIO01")],
            actuator_rows=[],
            actuator_states=[],
        )

        with patch("src.db.repositories.sensor_repo.SensorRepository") as MockRepo:
            MockRepo.return_value.get_latest_readings_batch_by_config = AsyncMock(return_value={})
            result = await service.get_zone_monitor_data("zone_test")

        subzone_map = {g.subzone_id: [s.sensor_type for s in g.sensors] for g in result.subzones}

        assert "subzone_gpio" in subzone_map, "GPIO-assigned sensor must appear in its subzone"
        assert "moisture" in subzone_map["subzone_gpio"], "moisture sensor must be in subzone_gpio"

        keine_subzone_sensors = subzone_map.get(None, [])
        assert "moisture" not in keine_subzone_sensors, (
            "GPIO-assigned sensor must not appear under 'Keine Subzone'"
        )

    @pytest.mark.asyncio
    async def test_sensor_nm_and_gpio_same_subzone_deduplicated(self):
        """
        Deduplication guard (AUT-1179):

        A sensor assigned via BOTH the GPIO path and the n:m path to the SAME
        subzone must appear exactly once in that subzone — no duplicate entries.
        """
        esp_uuid = "uuid-esp-dup01"
        sensor_uuid = uuid.uuid4()
        sc_pk = uuid.uuid4()

        esp = _fake_esp("ESP_DUP01", uuid=esp_uuid)

        # Subzone with GPIO 7 assigned
        subzone = _fake_subzone_cfg_nm(
            esp_id="ESP_DUP01",
            subzone_id="subzone_dup",
            subzone_name="Dup Subzone",
            pk_uuid=sc_pk,
            assigned_gpios=[7],
        )

        sensor = _fake_sensor_cfg(esp_uuid, gpio=7, sensor_type="ec", sensor_id=sensor_uuid)

        # Also n:m-assign the same sensor to the same subzone
        nm_rows = [_fake_nm_assignment(sensor_uuid, sc_pk)]

        service = _make_monitor_service_with_nm(
            esps=[esp],
            subzone_cfgs=[subzone],
            nm_rows=nm_rows,
            sensor_rows=[(sensor, "ESP_DUP01")],
            actuator_rows=[],
            actuator_states=[],
        )

        with patch("src.db.repositories.sensor_repo.SensorRepository") as MockRepo:
            MockRepo.return_value.get_latest_readings_batch_by_config = AsyncMock(return_value={})
            result = await service.get_zone_monitor_data("zone_test")

        subzone_map = {g.subzone_id: [s.sensor_type for s in g.sensors] for g in result.subzones}

        assert "subzone_dup" in subzone_map
        ec_count = subzone_map["subzone_dup"].count("ec")
        assert ec_count == 1, (
            f"ec sensor must appear exactly once in subzone_dup, got {ec_count} entries "
            "(GPIO + n:m pointing to same subzone must be deduplicated)"
        )


class TestMonitorDataServiceActuatorNmAssignments:
    """Actuator n:m Verortung visibility in zone monitor."""

    @pytest.mark.asyncio
    async def test_nm_actuator_appears_in_all_assigned_subzones(self):
        """Actuator with two n:m assignments appears in both subzones."""
        esp_uuid = "uuid-esp-act-nm01"
        actuator_uuid = uuid.uuid4()
        sc_pk_a = uuid.uuid4()
        sc_pk_b = uuid.uuid4()

        esp = _fake_esp("ESP_ACTNM01", uuid=esp_uuid)
        subzone_a = _fake_subzone_cfg_nm(
            esp_id="ESP_ACTNM01",
            subzone_id="act_alpha",
            subzone_name="Act Alpha",
            pk_uuid=sc_pk_a,
        )
        subzone_b = _fake_subzone_cfg_nm(
            esp_id="ESP_ACTNM01",
            subzone_id="act_beta",
            subzone_name="Act Beta",
            pk_uuid=sc_pk_b,
        )
        actuator = _fake_actuator_cfg(
            esp_uuid, gpio=12, actuator_type="pump", actuator_id=actuator_uuid
        )
        actuator_nm_rows = [
            _fake_actuator_nm_assignment(actuator_uuid, sc_pk_a),
            _fake_actuator_nm_assignment(actuator_uuid, sc_pk_b),
        ]

        service = _make_monitor_service_with_nm(
            esps=[esp],
            subzone_cfgs=[subzone_a, subzone_b],
            nm_rows=[],
            sensor_rows=[],
            actuator_rows=[(actuator, "ESP_ACTNM01")],
            actuator_states=[],
            actuator_nm_rows=actuator_nm_rows,
        )

        with patch("src.db.repositories.sensor_repo.SensorRepository") as MockRepo:
            MockRepo.return_value.get_latest_readings_batch_by_config = AsyncMock(
                return_value={}
            )
            result = await service.get_zone_monitor_data("zone_test")

        subzone_map = {
            g.subzone_id: [a.actuator_type for a in g.actuators] for g in result.subzones
        }
        assert "pump" in subzone_map.get("act_alpha", [])
        assert "pump" in subzone_map.get("act_beta", [])
        assert "pump" not in subzone_map.get(None, [])
