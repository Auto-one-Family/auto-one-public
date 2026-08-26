"""
Unit tests for TankService (AUT-1217, AUT-1225 Q4).
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.esp import ESPDevice
from src.db.models.nutrient_solution_batch import NUTRIENT_BATCH_ENTRY_TYPES
from src.db.models.plan_segment import PlanSegment
from src.db.models.subzone import SubzoneConfig
from src.db.models.zone import Zone
from src.db.repositories.system_config_repo import SystemConfigRepository
from src.schemas.tank import NutrientBatchCreate, TankCreate, SaltCalculatorAssistRequest
from src.sensors.dose_calculators.active.ec_control_anchor import (
    EC_DRIFT_THRESHOLD_CONFIG_KEY,
)
from src.services.tank_service import TankService


@pytest.fixture
async def zone(db_session: AsyncSession) -> Zone:
    z = Zone(zone_id="zelt_wohnzimmer", name="Zelt Wohnzimmer")
    db_session.add(z)
    await db_session.flush()
    await db_session.refresh(z)
    return z


@pytest.fixture
async def esp(db_session: AsyncSession, zone: Zone) -> ESPDevice:
    device = ESPDevice(
        device_id="ESP_TANK_SVC",
        name="Tank Service ESP",
        ip_address="192.168.1.51",
        mac_address="AA:BB:CC:DD:EE:51",
        firmware_version="1.0.0",
        hardware_type="ESP32_WROOM",
        status="online",
        zone_id=zone.zone_id,
        domain="wasser",
        capabilities={"max_sensors": 20, "max_actuators": 12},
    )
    db_session.add(device)
    await db_session.flush()
    await db_session.refresh(device)
    return device


@pytest.fixture
async def subzones(db_session: AsyncSession, esp: ESPDevice) -> list[SubzoneConfig]:
    rows = []
    for sid, name in (("topf_1", "Topf 1"), ("topf_2", "Topf 2")):
        row = SubzoneConfig(
            esp_id=esp.device_id,
            subzone_id=sid,
            subzone_name=name,
            parent_zone_id=esp.zone_id,
            assigned_gpios=[4],
        )
        db_session.add(row)
        rows.append(row)
    await db_session.flush()
    for row in rows:
        await db_session.refresh(row)
    return rows


@pytest.fixture
def service(db_session: AsyncSession) -> TankService:
    return TankService(db_session)


@pytest.mark.asyncio
async def test_create_tank_success(service: TankService, zone: Zone) -> None:
    result = await service.create_tank(
        TankCreate(
            zone_id=zone.zone_id,
            name="Mischbehälter",
            operation_mode="drain_to_waste",
            nominal_volume_l=25.0,
        )
    )
    assert result.zone_id == "zelt_wohnzimmer"
    assert result.name == "Mischbehälter"
    assert result.nominal_volume_l == 25.0


@pytest.mark.asyncio
async def test_get_volume_truth_unresolved_marks_drain_limit(
    service: TankService, zone: Zone
) -> None:
    """AUT-1377: fail-closed volume + known DtW/outflow limitation, no invented Ist."""
    tank = await service.create_tank(
        TankCreate(
            zone_id=zone.zone_id,
            name="Volume Display Tank",
            operation_mode="drain_to_waste",
            nominal_volume_l=25.0,
        )
    )
    result = await service.get_volume_truth(tank.id)
    assert result.tank_id == tank.id
    assert result.volume_l is None
    assert result.nominal_volume_l == pytest.approx(25.0)
    assert "drain_not_in_flow" in result.limitations


@pytest.mark.asyncio
async def test_get_volume_truth_unknown_tank_raises(service: TankService) -> None:
    with pytest.raises(ValueError, match="not found"):
        await service.get_volume_truth(uuid.uuid4())


@pytest.mark.asyncio
async def test_create_tank_unknown_zone_raises(service: TankService) -> None:
    with pytest.raises(ValueError, match="not found"):
        await service.create_tank(
            TankCreate(
                zone_id="ghost_zone",
                name="X",
                operation_mode="recirculating",
            )
        )


@pytest.mark.asyncio
async def test_assign_two_subzones(
    service: TankService, zone: Zone, subzones: list[SubzoneConfig]
) -> None:
    tank = await service.create_tank(
        TankCreate(
            zone_id=zone.zone_id,
            name="Tank Dual",
            operation_mode="drain_to_waste",
        )
    )
    a = await service.assign_subzone(tank.id, subzones[0].id, assigned_by=1)
    b = await service.assign_subzone(tank.id, subzones[1].id, assigned_by=1)
    assert a.subzone_config_id == str(subzones[0].id)
    assert b.subzone_config_id == str(subzones[1].id)
    assert a.tank_id == str(tank.id)


@pytest.mark.asyncio
async def test_assign_duplicate_raises(
    service: TankService, zone: Zone, subzones: list[SubzoneConfig]
) -> None:
    tank = await service.create_tank(
        TankCreate(
            zone_id=zone.zone_id,
            name="Tank Dup",
            operation_mode="drain_to_waste",
        )
    )
    await service.assign_subzone(tank.id, subzones[0].id)
    with pytest.raises(ValueError, match="already assigned"):
        await service.assign_subzone(tank.id, subzones[0].id)


@pytest.mark.asyncio
async def test_remove_subzone_assignment(
    service: TankService, zone: Zone, subzones: list[SubzoneConfig]
) -> None:
    tank = await service.create_tank(
        TankCreate(
            zone_id=zone.zone_id,
            name="Tank Rem",
            operation_mode="drain_to_waste",
        )
    )
    await service.assign_subzone(tank.id, subzones[0].id)
    assert await service.remove_subzone(tank.id, subzones[0].id) is True
    assert await service.remove_subzone(tank.id, subzones[0].id) is False


@pytest.mark.asyncio
@pytest.mark.parametrize("entry_type", list(NUTRIENT_BATCH_ENTRY_TYPES))
async def test_create_batch_each_entry_type(
    service: TankService, zone: Zone, entry_type: str
) -> None:
    tank = await service.create_tank(
        TankCreate(
            zone_id=zone.zone_id,
            name=f"Tank {entry_type}",
            operation_mode="drain_to_waste",
        )
    )
    result = await service.create_batch(
        tank.id,
        NutrientBatchCreate(
            entry_type=entry_type,
            volume_l=10.0 if entry_type != "remeasurement_only" else 0.0,
            components=[],
            acquisition_method="manual_entry",
            qualifier="approximate",
        ),
    )
    assert result.entry_type == entry_type
    assert result.tank_id == tank.id
    assert result.acquisition_method == "manual_entry"
    assert result.qualifier == "approximate"


@pytest.mark.asyncio
async def test_create_batch_product_form(service: TankService, zone: Zone) -> None:
    tank = await service.create_tank(
        TankCreate(
            zone_id=zone.zone_id,
            name="Tank Product",
            operation_mode="drain_to_waste",
        )
    )
    result = await service.create_batch(
        tank.id,
        NutrientBatchCreate(
            entry_type="full_reset",
            volume_l=20.0,
            components=[
                {"kind": "product", "name": "Bloom", "dose_ml_per_l": 1.5},
            ],
            acquisition_method="measured_level",
            qualifier="precise",
        ),
    )
    assert result.components[0]["kind"] == "product"
    assert result.components[0]["dose_ml_per_l"] == 1.5


@pytest.mark.asyncio
async def test_create_batch_salt_form(service: TankService, zone: Zone) -> None:
    tank = await service.create_tank(
        TankCreate(
            zone_id=zone.zone_id,
            name="Tank Salt",
            operation_mode="drain_to_waste",
        )
    )
    result = await service.create_batch(
        tank.id,
        NutrientBatchCreate(
            entry_type="top_up_dose",
            volume_l=5.0,
            components=[
                {
                    "kind": "salt",
                    "name": "CaNO3",
                    "conc_g_per_l": 0.8,
                    "elements": {"Ca": 0.19, "N": 0.12},
                },
            ],
            acquisition_method="manual_entry",
            qualifier="estimated",
        ),
    )
    assert result.components[0]["kind"] == "salt"
    assert result.components[0]["conc_g_per_l"] == 0.8


@pytest.mark.asyncio
async def test_create_batch_rejects_mixed_fields_on_component() -> None:
    with pytest.raises(ValidationError):
        NutrientBatchCreate(
            entry_type="full_reset",
            volume_l=1.0,
            components=[
                {
                    "kind": "product",
                    "name": "Bad",
                    "dose_ml_per_l": 1.0,
                    "conc_g_per_l": 0.5,
                }
            ],
            acquisition_method="manual_entry",
            qualifier="precise",
        )


@pytest.mark.asyncio
async def test_ec_never_measured_vs_measured_zero(
    service: TankService, zone: Zone
) -> None:
    tank = await service.create_tank(
        TankCreate(
            zone_id=zone.zone_id,
            name="Tank EC Dist",
            operation_mode="drain_to_waste",
        )
    )
    never = await service.create_batch(
        tank.id,
        NutrientBatchCreate(
            entry_type="remeasurement_only",
            volume_l=0.0,
            components=[],
            acquisition_method="manual_entry",
            qualifier="estimated",
            ec_was_measured=False,
        ),
    )
    zero = await service.create_batch(
        tank.id,
        NutrientBatchCreate(
            entry_type="remeasurement_only",
            volume_l=0.0,
            components=[],
            acquisition_method="manual_entry",
            qualifier="precise",
            ec_was_measured=True,
            ec_measured_after=0.0,
        ),
    )
    assert never.ec_was_measured is False
    assert never.ec_measured_after is None
    assert zero.ec_was_measured is True
    assert zero.ec_measured_after == 0.0


@pytest.mark.asyncio
async def test_create_batch_returns_persisted_object_for_anchor_dock(
    service: TankService, zone: Zone
) -> None:
    """create_batch returns a full NutrientBatchResponse (incl. warnings slot)."""
    tank = await service.create_tank(
        TankCreate(
            zone_id=zone.zone_id,
            name="Tank Anchor Dock",
            operation_mode="drain_to_waste",
        )
    )
    result = await service.create_batch(
        tank.id,
        NutrientBatchCreate(
            entry_type="system_incident",
            volume_l=0.0,
            components=[],
            acquisition_method="manual_entry",
            qualifier="approximate",
            recipe_label="Leckage",
        ),
    )
    assert result.id is not None
    assert isinstance(result.id, uuid.UUID)
    assert result.recipe_label == "Leckage"
    assert result.warnings == []


@pytest.mark.asyncio
async def test_create_batch_ec_anchor_noop_without_threshold(
    service: TankService, zone: Zone
) -> None:
    """Production default: no threshold → persist OK, no warning (AUT-1218)."""
    tank = await service.create_tank(
        TankCreate(
            zone_id=zone.zone_id,
            name="Tank EC NoOp",
            operation_mode="drain_to_waste",
        )
    )
    result = await service.create_batch(
        tank.id,
        NutrientBatchCreate(
            entry_type="full_reset",
            volume_l=20.0,
            components=[
                {
                    "kind": "product",
                    "name": "Bloom",
                    "dose_ml_per_l": 2.0,
                    "ec_contribution_ms_cm": 1.5,
                }
            ],
            acquisition_method="manual_entry",
            qualifier="precise",
            ec_was_measured=True,
            ec_measured_after=3.0,
        ),
    )
    assert result.id is not None
    assert result.ec_was_measured is True
    assert result.warnings == []


@pytest.mark.asyncio
async def test_create_batch_ec_anchor_warns_but_persists(
    service: TankService, zone: Zone, db_session: AsyncSession
) -> None:
    """Configured threshold + large drift → warning visible, write not blocked."""
    repo = SystemConfigRepository(db_session)
    await repo.set_config(
        config_key=EC_DRIFT_THRESHOLD_CONFIG_KEY,
        config_value={"value": 10.0},
        config_type="nutrient_batch",
    )
    tank = await service.create_tank(
        TankCreate(
            zone_id=zone.zone_id,
            name="Tank EC Drift",
            operation_mode="drain_to_waste",
        )
    )
    result = await service.create_batch(
        tank.id,
        NutrientBatchCreate(
            entry_type="full_reset",
            volume_l=20.0,
            components=[
                {
                    "kind": "product",
                    "name": "Bloom",
                    "dose_ml_per_l": 2.0,
                    "ec_contribution_ms_cm": 1.5,
                }
            ],
            acquisition_method="manual_entry",
            qualifier="precise",
            ec_was_measured=True,
            ec_measured_after=3.0,  # 100% drift vs expected 1.5
        ),
    )
    assert result.id is not None
    assert result.ec_measured_after == 3.0
    assert len(result.warnings) == 1
    assert "EC-Kontrollanker" in result.warnings[0]


# =============================================================================
# AUT-1346 — prior_volume_l / prior_ec_ms_cm (nullable, additive)
# =============================================================================


@pytest.mark.asyncio
async def test_create_batch_first_entry_prior_null(
    service: TankService, zone: Zone
) -> None:
    """No history → prior_* stay NULL (never invented)."""
    tank = await service.create_tank(
        TankCreate(
            zone_id=zone.zone_id,
            name="Tank Prior Null",
            operation_mode="drain_to_waste",
        )
    )
    result = await service.create_batch(
        tank.id,
        NutrientBatchCreate(
            entry_type="full_reset",
            volume_l=20.0,
            components=[],
            acquisition_method="manual_entry",
            qualifier="precise",
        ),
    )
    assert result.prior_volume_l is None
    assert result.prior_ec_ms_cm is None


@pytest.mark.asyncio
async def test_create_batch_writes_prior_from_history(
    service: TankService, zone: Zone
) -> None:
    """Second entry gets prior_volume from reconstructed ledger state."""
    tank = await service.create_tank(
        TankCreate(
            zone_id=zone.zone_id,
            name="Tank Prior Hist",
            operation_mode="drain_to_waste",
        )
    )
    await service.create_batch(
        tank.id,
        NutrientBatchCreate(
            entry_type="full_reset",
            volume_l=20.0,
            components=[],
            acquisition_method="manual_entry",
            qualifier="precise",
            ec_was_measured=True,
            ec_measured_after=1.4,
        ),
    )
    second = await service.create_batch(
        tank.id,
        NutrientBatchCreate(
            entry_type="fresh_water_refill",
            volume_l=5.0,
            components=[],
            acquisition_method="measured_flow",
            qualifier="approximate",
        ),
    )
    assert second.prior_volume_l == pytest.approx(20.0)
    assert second.prior_ec_ms_cm == pytest.approx(1.4)


# =============================================================================
# AUT-1343 — Salt calculator assist (read-only)
# =============================================================================


@pytest.mark.asyncio
async def test_compute_dose_assist_manual_override(
    service: TankService, zone: Zone
) -> None:
    tank = await service.create_tank(
        TankCreate(
            zone_id=zone.zone_id,
            name="Tank Assist",
            operation_mode="drain_to_waste",
        )
    )
    result = await service.compute_dose_assist(
        tank.id,
        SaltCalculatorAssistRequest(
            current_ec_us_cm=1400.0,
            target_ec_us_cm=1500.0,
            concentration=2.0,
            volume_alt_l=10.0,
            volume_zugabe_l=10.0,
            ec_wasser_us_cm=488.0,
        ),
    )
    assert result.volume_alt_source == "manual_override"
    assert result.dose_a_ml == pytest.approx(result.dose_b_ml)
    assert result.ec_after_dilution_us_cm == pytest.approx(944.0)
    assert result.expected_ec_us_cm == pytest.approx(1500.0)


@pytest.mark.asyncio
async def test_compute_dose_assist_from_ledger_volume(
    service: TankService, zone: Zone
) -> None:
    tank = await service.create_tank(
        TankCreate(
            zone_id=zone.zone_id,
            name="Tank Assist Ledger",
            operation_mode="drain_to_waste",
        )
    )
    await service.create_batch(
        tank.id,
        NutrientBatchCreate(
            entry_type="full_reset",
            volume_l=20.0,
            components=[],
            acquisition_method="manual_entry",
            qualifier="precise",
        ),
    )
    result = await service.compute_dose_assist(
        tank.id,
        SaltCalculatorAssistRequest(
            current_ec_us_cm=1300.0,
            target_ec_us_cm=1400.0,
            concentration=5.0,
        ),
    )
    assert result.volume_alt_l == pytest.approx(20.0)
    assert result.volume_alt_source == "ledger_reconstructed"
    assert result.dose_a_ml == pytest.approx(result.dose_b_ml)


@pytest.mark.asyncio
async def test_compute_dose_assist_requires_v_alt(
    service: TankService, zone: Zone
) -> None:
    tank = await service.create_tank(
        TankCreate(
            zone_id=zone.zone_id,
            name="Tank Assist Empty",
            operation_mode="drain_to_waste",
        )
    )
    with pytest.raises(ValueError, match="V_alt unresolved"):
        await service.compute_dose_assist(
            tank.id,
            SaltCalculatorAssistRequest(
                current_ec_us_cm=1000.0,
                target_ec_us_cm=1200.0,
                concentration=1.0,
            ),
        )


# =============================================================================
# Tank ↔ ESP Device Assignment (n:1, AUT-1223 Q2)
# =============================================================================


@pytest.fixture
async def esp2(db_session: AsyncSession, zone: Zone) -> ESPDevice:
    """Second ESP device for reassignment tests."""
    device = ESPDevice(
        device_id="ESP_TANK_SVC2",
        name="Tank Service ESP 2",
        ip_address="192.168.1.53",
        mac_address="AA:BB:CC:DD:EE:53",
        firmware_version="1.0.0",
        hardware_type="ESP32_WROOM",
        status="online",
        zone_id=zone.zone_id,
        domain="wasser",
        capabilities={"max_sensors": 20, "max_actuators": 12},
    )
    db_session.add(device)
    await db_session.flush()
    await db_session.refresh(device)
    return device


@pytest.mark.asyncio
async def test_list_tanks_returns_all(service: TankService, zone: Zone) -> None:
    await service.create_tank(
        TankCreate(zone_id=zone.zone_id, name="Tank List A", operation_mode="drain_to_waste")
    )
    await service.create_tank(
        TankCreate(zone_id=zone.zone_id, name="Tank List B", operation_mode="recirculating")
    )
    result = await service.list_tanks()
    names = {t.name for t in result}
    assert "Tank List A" in names
    assert "Tank List B" in names


@pytest.mark.asyncio
async def test_get_tank_found_and_not_found(service: TankService, zone: Zone) -> None:
    tank = await service.create_tank(
        TankCreate(zone_id=zone.zone_id, name="Tank Get", operation_mode="drain_to_waste")
    )
    found = await service.get_tank(tank.id)
    assert found is not None
    assert found.id == tank.id

    missing = await service.get_tank(uuid.uuid4())
    assert missing is None


@pytest.mark.asyncio
async def test_assign_device_to_tank_and_read_both_directions(
    service: TankService, zone: Zone, esp: ESPDevice
) -> None:
    tank = await service.create_tank(
        TankCreate(zone_id=zone.zone_id, name="Tank Device A", operation_mode="drain_to_waste")
    )
    result = await service.assign_device(tank.id, esp.device_id)
    assert result.tank_id == str(tank.id)
    assert result.device_id == esp.device_id

    devices = await service.get_devices_for_tank(tank.id)
    assert len(devices) == 1
    assert devices[0].device_id == esp.device_id

    found_tank = await service.get_tank_for_device(esp.device_id)
    assert found_tank is not None
    assert found_tank.id == tank.id


@pytest.mark.asyncio
async def test_assign_device_unknown_tank_raises(
    service: TankService, esp: ESPDevice
) -> None:
    with pytest.raises(ValueError, match="not found"):
        await service.assign_device(uuid.uuid4(), esp.device_id)


@pytest.mark.asyncio
async def test_assign_device_unknown_device_raises(
    service: TankService, zone: Zone
) -> None:
    tank = await service.create_tank(
        TankCreate(zone_id=zone.zone_id, name="Tank Device Unknown", operation_mode="drain_to_waste")
    )
    with pytest.raises(ValueError, match="not found"):
        await service.assign_device(tank.id, "ESP_DOES_NOT_EXIST")


@pytest.mark.asyncio
async def test_assign_device_rejects_non_wasser_domain(
    service: TankService, zone: Zone, esp: ESPDevice
) -> None:
    """AUT-1328: Domain != wasser must not become a tank member."""
    tank = await service.create_tank(
        TankCreate(
            zone_id=zone.zone_id, name="Tank Domain Reject", operation_mode="drain_to_waste"
        )
    )
    esp.domain = "luft"
    with pytest.raises(ValueError, match="requires domain 'wasser'"):
        await service.assign_device(tank.id, esp.device_id)
    assert await service.get_devices_for_tank(tank.id) == []
    assert await service.get_tank_for_device(esp.device_id) is None


@pytest.mark.asyncio
async def test_reassign_device_to_different_tank_replaces_previous(
    service: TankService, zone: Zone, esp: ESPDevice
) -> None:
    """n:1 cardinality: assigning to a new tank replaces the previous assignment."""
    tank_a = await service.create_tank(
        TankCreate(zone_id=zone.zone_id, name="Tank Reassign A", operation_mode="drain_to_waste")
    )
    tank_b = await service.create_tank(
        TankCreate(zone_id=zone.zone_id, name="Tank Reassign B", operation_mode="recirculating")
    )

    await service.assign_device(tank_a.id, esp.device_id)
    assert len(await service.get_devices_for_tank(tank_a.id)) == 1

    await service.assign_device(tank_b.id, esp.device_id)

    devices_a = await service.get_devices_for_tank(tank_a.id)
    devices_b = await service.get_devices_for_tank(tank_b.id)
    assert devices_a == []
    assert len(devices_b) == 1
    assert devices_b[0].device_id == esp.device_id

    found_tank = await service.get_tank_for_device(esp.device_id)
    assert found_tank is not None
    assert found_tank.id == tank_b.id


@pytest.mark.asyncio
async def test_clear_device_assignment(
    service: TankService, zone: Zone, esp: ESPDevice
) -> None:
    tank = await service.create_tank(
        TankCreate(zone_id=zone.zone_id, name="Tank Clear", operation_mode="drain_to_waste")
    )
    await service.assign_device(tank.id, esp.device_id)

    cleared = await service.clear_device_assignment(esp.device_id)
    assert cleared is True
    assert await service.get_tank_for_device(esp.device_id) is None
    assert await service.get_devices_for_tank(tank.id) == []

    # Clearing again (no assignment left) returns False, not an error.
    cleared_again = await service.clear_device_assignment(esp.device_id)
    assert cleared_again is False


@pytest.mark.asyncio
async def test_clear_device_assignment_unknown_device_raises(
    service: TankService,
) -> None:
    with pytest.raises(ValueError, match="not found"):
        await service.clear_device_assignment("ESP_DOES_NOT_EXIST")


@pytest.mark.asyncio
async def test_two_devices_can_be_assigned_to_same_tank(
    service: TankService, zone: Zone, esp: ESPDevice, esp2: ESPDevice
) -> None:
    """n:1 on the device side does not limit how many devices one tank can have."""
    tank = await service.create_tank(
        TankCreate(zone_id=zone.zone_id, name="Tank Multi Device", operation_mode="drain_to_waste")
    )
    await service.assign_device(tank.id, esp.device_id)
    await service.assign_device(tank.id, esp2.device_id)

    devices = await service.get_devices_for_tank(tank.id)
    assigned_ids = {d.device_id for d in devices}
    assert assigned_ids == {esp.device_id, esp2.device_id}


# =============================================================================
# Targets: canonical Soll from plan_segment@now (AUT-1225 Q4)
# =============================================================================


@pytest.mark.asyncio
async def test_get_targets_at_now_unknown_tank_raises(service: TankService) -> None:
    with pytest.raises(ValueError, match="not found"):
        await service.get_targets_at_now(uuid.uuid4())


@pytest.mark.asyncio
async def test_get_targets_at_now_without_segments_returns_null_values(
    service: TankService, zone: Zone
) -> None:
    """No plan_segment rows for the zone → both measures resolved_via=none."""
    tank = await service.create_tank(
        TankCreate(
            zone_id=zone.zone_id, name="Tank No Plan", operation_mode="drain_to_waste"
        )
    )
    result = await service.get_targets_at_now(tank.id)

    assert result.tank_id == tank.id
    assert result.zone_id == zone.zone_id
    assert result.subzone_config_id is None
    assert result.domain == "nutrient_solution"
    assert {t.measure for t in result.targets} == {"target_ec", "target_ph"}
    for target in result.targets:
        assert target.value is None
        assert target.unit is None
        assert target.segment_id is None
        assert target.resolved_via == "none"


@pytest.mark.asyncio
async def test_get_targets_at_now_with_covering_segment_returns_values(
    service: TankService, zone: Zone, db_session: AsyncSession
) -> None:
    """Zone-wide plan_segment covering 'now' resolves EC/pH via zone."""
    now = datetime.now(timezone.utc)
    ec_segment = PlanSegment(
        zone_id=zone.zone_id,
        domain="nutrient_solution",
        measure="target_ec",
        value=1.8,
        from_ts=now - timedelta(days=1),
        to_ts=now + timedelta(days=1),
        interp="step",
        status="active",
    )
    ph_segment = PlanSegment(
        zone_id=zone.zone_id,
        domain="nutrient_solution",
        measure="target_ph",
        value=5.8,
        from_ts=now - timedelta(days=1),
        to_ts=None,
        interp="step",
        status="active",
    )
    db_session.add_all([ec_segment, ph_segment])
    await db_session.flush()

    tank = await service.create_tank(
        TankCreate(
            zone_id=zone.zone_id, name="Tank With Plan", operation_mode="drain_to_waste"
        )
    )
    result = await service.get_targets_at_now(tank.id)

    by_measure = {t.measure: t for t in result.targets}
    assert by_measure["target_ec"].value == 1.8
    assert by_measure["target_ec"].unit == "µS/cm"
    assert by_measure["target_ec"].segment_id == ec_segment.id
    assert by_measure["target_ec"].resolved_via == "zone"
    assert by_measure["target_ph"].value == 5.8
    assert by_measure["target_ph"].unit == "pH"
    assert by_measure["target_ph"].resolved_via == "zone"


@pytest.mark.asyncio
async def test_get_targets_at_now_uses_first_assigned_subzone(
    service: TankService,
    zone: Zone,
    subzones: list[SubzoneConfig],
    db_session: AsyncSession,
) -> None:
    """Subzone-specific segment (assigned to first subzone) resolves via subzone."""
    now = datetime.now(timezone.utc)
    tank = await service.create_tank(
        TankCreate(
            zone_id=zone.zone_id, name="Tank Subzone Plan", operation_mode="drain_to_waste"
        )
    )
    await service.assign_subzone(tank.id, subzones[0].id)
    await service.assign_subzone(tank.id, subzones[1].id)

    ec_segment = PlanSegment(
        zone_id=zone.zone_id,
        domain="nutrient_solution",
        measure="target_ec",
        value=2.4,
        from_ts=now - timedelta(days=1),
        to_ts=None,
        interp="step",
        status="active",
    )
    db_session.add(ec_segment)
    await db_session.flush()

    from src.db.models.plan_segment import PlanSegmentSubzoneAssignment

    db_session.add(
        PlanSegmentSubzoneAssignment(
            plan_segment_id=ec_segment.id,
            subzone_config_id=subzones[0].id,
        )
    )
    await db_session.flush()

    result = await service.get_targets_at_now(tank.id)
    assert result.subzone_config_id == subzones[0].id

    by_measure = {t.measure: t for t in result.targets}
    assert by_measure["target_ec"].value == 2.4
    assert by_measure["target_ec"].resolved_via == "subzone"
    assert by_measure["target_ph"].resolved_via == "none"


@pytest.mark.asyncio
async def test_get_targets_at_now_includes_assigned_device_ids(
    service: TankService, zone: Zone, esp: ESPDevice
) -> None:
    tank = await service.create_tank(
        TankCreate(
            zone_id=zone.zone_id, name="Tank Targets Devices", operation_mode="drain_to_waste"
        )
    )
    await service.assign_device(tank.id, esp.device_id)

    result = await service.get_targets_at_now(tank.id)
    assert result.assigned_device_ids == [esp.device_id]
