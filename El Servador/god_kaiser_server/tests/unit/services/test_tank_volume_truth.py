"""AUT-1563: V_real from persisted dose_config.volume_l — no name/GPIO magic."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.esp import ESPDevice
from src.db.models.logic import CrossESPLogic
from src.db.models.sensor import SensorConfig
from src.db.models.zone import Zone
from src.schemas.tank import TankCreate
from src.services.tank_service import TankService
from src.services.tank_volume_truth import (
    VOLUME_SOURCE_DOSE_CONFIG,
    resolve_v_real,
)


def _assert_no_name_magic_exports() -> None:
    import src.services.tank_volume_truth as module

    assert not hasattr(module, "LEVEL_ANCHOR_LITERS")
    assert not hasattr(module, "LEVEL_ANCHOR_SENSOR_NAME")


async def _tank_with_esp(
    db_session: AsyncSession,
    *,
    device_id: str = "ESP_AABBCC12",
    sensor_name: str = "20 Liter",
    gpio: int = 14,
) -> tuple:
    zone = Zone(zone_id="zelt_vreal", name="Zelt Vreal")
    db_session.add(zone)
    await db_session.flush()

    service = TankService(db_session)
    tank = await service.create_tank(
        TankCreate(
            zone_id=zone.zone_id,
            name="Mischbehälter",
            operation_mode="drain_to_waste",
            nominal_volume_l=25.0,
        )
    )
    device = ESPDevice(
        device_id=device_id,
        name="Vreal ESP",
        ip_address="192.168.1.80",
        mac_address="AA:BB:CC:DD:EE:80",
        firmware_version="1.0.0",
        hardware_type="ESP32_WROOM",
        status="online",
        zone_id=zone.zone_id,
        tank_id=tank.id,
        capabilities={"max_sensors": 20, "max_actuators": 12},
    )
    db_session.add(device)
    await db_session.flush()
    sensor = SensorConfig(
        esp_id=device.id,
        gpio=gpio,
        sensor_type="liquid_level",
        sensor_name=sensor_name,
        enabled=True,
    )
    db_session.add(sensor)
    await db_session.flush()
    return tank, device


def _rule(
    *,
    rule_name: str,
    esp_id: str,
    volume_l: float | None,
    enabled: bool = True,
) -> CrossESPLogic:
    meta = {}
    if volume_l is not None:
        meta = {"dose_config": {"volume_l": volume_l, "target_value": 1.6}}
    return CrossESPLogic(
        rule_name=rule_name,
        description="AUT-1563 volume rule",
        trigger_conditions=[
            {
                "type": "sensor",
                "esp_id": esp_id,
                "gpio": 34,
                "sensor_type": "ec",
                "operator": "<",
                "value": 1.5,
            }
        ],
        actions=[
            {
                "type": "actuator",
                "esp_id": esp_id,
                "gpio": 5,
                "command": "ON",
                "value": 1.0,
            }
        ],
        logic_operator="AND",
        enabled=enabled,
        priority=50,
        rule_metadata=meta,
    )


def test_name_magic_constants_removed() -> None:
    _assert_no_name_magic_exports()


@pytest.mark.asyncio
async def test_resolve_v_real_uses_dose_config_volume_l(
    db_session: AsyncSession,
) -> None:
    tank, device = await _tank_with_esp(db_session, sensor_name="20 Liter", gpio=14)
    db_session.add(_rule(rule_name="dose_18", esp_id=device.device_id, volume_l=18.5))
    await db_session.flush()

    truth = await resolve_v_real(db_session, tank.id)

    assert truth is not None
    assert truth.volume_l == pytest.approx(18.5)
    assert truth.source == VOLUME_SOURCE_DOSE_CONFIG
    assert truth.level_gpio is None
    assert truth.flow_delta_l == 0.0


@pytest.mark.asyncio
async def test_resolve_v_real_ignores_20_liter_name_without_volume_l(
    db_session: AsyncSession,
) -> None:
    tank, _device = await _tank_with_esp(db_session, sensor_name="20 Liter", gpio=14)

    truth = await resolve_v_real(db_session, tank.id)

    assert truth is None


@pytest.mark.asyncio
async def test_resolve_v_real_ignores_unrelated_rule_volume(
    db_session: AsyncSession,
) -> None:
    tank, _device = await _tank_with_esp(db_session, device_id="ESP_AABBCC12")
    db_session.add(_rule(rule_name="other_tank", esp_id="ESP_FFFFFF", volume_l=99.0))
    await db_session.flush()

    truth = await resolve_v_real(db_session, tank.id)

    assert truth is None


@pytest.mark.asyncio
async def test_resolve_v_real_skips_non_positive_volume_l(
    db_session: AsyncSession,
) -> None:
    tank, device = await _tank_with_esp(db_session)
    db_session.add(_rule(rule_name="zero_vol", esp_id=device.device_id, volume_l=0.0))
    await db_session.flush()

    truth = await resolve_v_real(db_session, tank.id)

    assert truth is None


@pytest.mark.asyncio
async def test_resolve_v_real_ignores_measure_binding_on_other_tank(
    db_session: AsyncSession,
) -> None:
    tank, device = await _tank_with_esp(db_session, device_id="ESP_BBBBBB12")
    rule = _rule(rule_name="dose_other_tank", esp_id="ESP_AAAAAA12", volume_l=40.0)
    rule.rule_metadata = {
        "dose_config": {"volume_l": 40.0, "target_value": 1.6},
        "measure_bindings": [
            {
                "sensor_refs": [
                    {
                        "esp_id": device.device_id,
                        "gpio": 34,
                        "sensor_type": "ec",
                    }
                ],
                "hooks": ["on_start"],
                "formula_id": "difference",
                "formula_params": {},
                "output_target": "execution_metadata",
            }
        ],
    }
    db_session.add(rule)
    await db_session.flush()

    truth = await resolve_v_real(db_session, tank.id)

    assert truth is None


@pytest.mark.asyncio
async def test_resolve_v_real_ignores_cross_esp_action_on_this_tank(
    db_session: AsyncSession,
) -> None:
    tank, device = await _tank_with_esp(db_session, device_id="ESP_BBBBBB12")
    rule = _rule(rule_name="cross_esp_dose", esp_id="ESP_AAAAAA12", volume_l=40.0)
    rule.actions = list(rule.actions) + [
        {
            "type": "actuator",
            "esp_id": device.device_id,
            "gpio": 6,
            "command": "ON",
            "value": 1.0,
        }
    ]
    db_session.add(rule)
    await db_session.flush()

    truth = await resolve_v_real(db_session, tank.id)

    assert truth is None
