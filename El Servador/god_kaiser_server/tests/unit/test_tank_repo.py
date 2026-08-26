"""
Unit tests for Tank / Assignment / Ledger repositories (AUT-1217).
"""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.esp import ESPDevice
from src.db.models.subzone import SubzoneConfig
from src.db.models.zone import Zone
from src.db.repositories.nutrient_solution_batch_repo import NutrientSolutionBatchRepository
from src.db.repositories.tank_repo import TankRepository
from src.db.repositories.tank_subzone_assignment_repo import TankSubzoneAssignmentRepository


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
        device_id="ESP_TANK_REPO",
        name="Tank Repo ESP",
        ip_address="192.168.1.50",
        mac_address="AA:BB:CC:DD:EE:50",
        firmware_version="1.0.0",
        hardware_type="ESP32_WROOM",
        status="online",
        zone_id=zone.zone_id,
        capabilities={"max_sensors": 20, "max_actuators": 12},
    )
    db_session.add(device)
    await db_session.flush()
    await db_session.refresh(device)
    return device


@pytest.fixture
async def subzone(db_session: AsyncSession, esp: ESPDevice) -> SubzoneConfig:
    row = SubzoneConfig(
        esp_id=esp.device_id,
        subzone_id="topf_1",
        subzone_name="Topf 1",
        parent_zone_id=esp.zone_id,
        assigned_gpios=[4, 5],
    )
    db_session.add(row)
    await db_session.flush()
    await db_session.refresh(row)
    return row


@pytest.mark.asyncio
async def test_tank_create_persists_zone_assignment(
    db_session: AsyncSession, zone: Zone
) -> None:
    repo = TankRepository(db_session)
    tank = await repo.create(
        zone_id=zone.zone_id,
        name="Mischbehälter A",
        operation_mode="drain_to_waste",
        nominal_volume_l=20.0,
    )
    await db_session.flush()

    fetched = await repo.get_by_id(tank.id)
    assert fetched is not None
    assert fetched.zone_id == "zelt_wohnzimmer"
    assert fetched.name == "Mischbehälter A"
    assert fetched.operation_mode == "drain_to_waste"
    assert fetched.nominal_volume_l == 20.0


@pytest.mark.asyncio
async def test_tank_subzone_assign_and_unassign(
    db_session: AsyncSession, zone: Zone, subzone: SubzoneConfig
) -> None:
    tank_repo = TankRepository(db_session)
    assign_repo = TankSubzoneAssignmentRepository(db_session)

    tank = await tank_repo.create(
        zone_id=zone.zone_id,
        name="Tank B",
        operation_mode="recirculating",
    )
    row = await assign_repo.assign(
        tank_id=tank.id,
        subzone_config_id=subzone.id,
        assigned_by=7,
    )
    assert row.assigned_by == 7
    assert row.tank_id == tank.id

    existing = await assign_repo.get_assignment(tank.id, subzone.id)
    assert existing is not None

    deleted = await assign_repo.unassign(tank.id, subzone.id)
    assert deleted is True
    assert await assign_repo.get_assignment(tank.id, subzone.id) is None


@pytest.mark.asyncio
async def test_ledger_create_entry_persists_acquisition_and_qualifier(
    db_session: AsyncSession, zone: Zone
) -> None:
    tank_repo = TankRepository(db_session)
    batch_repo = NutrientSolutionBatchRepository(db_session)

    tank = await tank_repo.create(
        zone_id=zone.zone_id,
        name="Tank Ledger",
        operation_mode="drain_to_waste",
    )
    entry = await batch_repo.create_entry(
        tank_id=tank.id,
        entry_type="full_reset",
        volume_l=15.0,
        components=[{"kind": "product", "name": "Grow A", "dose_ml_per_l": 2.0}],
        acquisition_method="manual_entry",
        qualifier="approximate",
        ec_was_measured=False,
        ph_was_measured=False,
    )
    await db_session.flush()

    fetched = await batch_repo.get_by_id(entry.id)
    assert fetched is not None
    assert fetched.acquisition_method == "manual_entry"
    assert fetched.qualifier == "approximate"
    assert fetched.ec_was_measured is False
    assert fetched.ec_measured_after is None


@pytest.mark.asyncio
async def test_ledger_ec_was_measured_false_differs_from_zero(
    db_session: AsyncSession, zone: Zone
) -> None:
    tank_repo = TankRepository(db_session)
    batch_repo = NutrientSolutionBatchRepository(db_session)

    tank = await tank_repo.create(
        zone_id=zone.zone_id,
        name="Tank EC",
        operation_mode="drain_to_waste",
    )
    never = await batch_repo.create_entry(
        tank_id=tank.id,
        entry_type="remeasurement_only",
        volume_l=0.0,
        components=[],
        acquisition_method="manual_entry",
        qualifier="estimated",
        ec_was_measured=False,
        ec_measured_after=None,
    )
    measured_zero = await batch_repo.create_entry(
        tank_id=tank.id,
        entry_type="remeasurement_only",
        volume_l=0.0,
        components=[],
        acquisition_method="manual_entry",
        qualifier="precise",
        ec_was_measured=True,
        ec_measured_after=0.0,
    )
    await db_session.flush()

    assert never.ec_was_measured is False
    assert never.ec_measured_after is None
    assert measured_zero.ec_was_measured is True
    assert measured_zero.ec_measured_after == 0.0
    assert never.id != measured_zero.id
