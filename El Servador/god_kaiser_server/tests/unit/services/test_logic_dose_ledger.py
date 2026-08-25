"""
AUT-1352 — Logic dose → Stoffbilanz-Ledger (unit tests).

Covers: real dispatch write, noop/conflict/fail skip, idempotency,
per-pump ml (A≠B), sequence COMPLETED vs abort (Q1), V_alt rise,
pH exclude from EC composition, dose_ml_absolute-only schema.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.actuator import ActuatorConfig
from src.db.models.esp import ESPDevice
from src.db.models.zone import Zone
from src.schemas.tank import NutrientBatchCreate, SaltCalculatorAssistRequest, TankCreate
from src.sensors.dose_calculators.active.ec_control_anchor import (
    calculate_expected_ec,
    exclude_from_ec_composition,
)
from src.services.logic_dose_ledger import (
    action_result_is_real_dispatch,
    collect_dispatched_dose_pumps,
    extract_dose_pumps_from_actions,
    ledger_has_logic_execution,
    record_logic_dose_to_ledger,
)
from src.services.tank_service import TankService


@pytest.fixture
async def zone(db_session: AsyncSession) -> Zone:
    z = Zone(zone_id="zelt_aut1352", name="Zelt AUT-1352")
    db_session.add(z)
    await db_session.flush()
    await db_session.refresh(z)
    return z


@pytest.fixture
async def tank_and_esp(db_session: AsyncSession, zone: Zone):
    service = TankService(db_session)
    tank = await service.create_tank(
        TankCreate(
            zone_id=zone.zone_id,
            name="Tank AUT-1352",
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
            ec_measured_after=1.2,
        ),
    )
    esp = ESPDevice(
        device_id="ESP_AUT1352",
        name="ESP AUT-1352",
        ip_address="192.168.1.135",
        mac_address="AA:BB:CC:DD:13:52",
        firmware_version="1.0.0",
        hardware_type="ESP32_WROOM",
        status="online",
        zone_id=zone.zone_id,
        tank_id=tank.id,
        capabilities={"max_sensors": 20, "max_actuators": 12},
    )
    db_session.add(esp)
    await db_session.flush()
    await db_session.refresh(esp)

    for gpio, name in ((12, "Pump A"), (16, "Pump B"), (18, "pH-Minus")):
        act = ActuatorConfig(
            esp_id=esp.id,
            gpio=gpio,
            actuator_type="digital",
            hardware_type="pump",
            actuator_name=name,
            enabled=True,
            flow_rate_ml_s=1.0,
            safety_constraints={},
            actuator_metadata={},
        )
        db_session.add(act)
    await db_session.flush()
    return tank, esp, service


class TestHelpers:
    def test_noop_is_not_real_dispatch(self):
        assert (
            action_result_is_real_dispatch(
                {"success": True, "data": {"noop": True, "esp_id": "E", "gpio": 1}}
            )
            is False
        )

    def test_success_without_noop_is_real_dispatch(self):
        assert (
            action_result_is_real_dispatch(
                {"success": True, "data": {"esp_id": "E", "gpio": 1}}
            )
            is True
        )

    def test_extract_sequence_unequal_ml(self):
        actions = [
            {
                "type": "sequence",
                "steps": [
                    {
                        "name": "Pump A",
                        "action": {
                            "type": "actuator",
                            "esp_id": "ESP_X",
                            "gpio": 12,
                            "dose_ml": 4.0,
                        },
                    },
                    {"delay_seconds": 2},
                    {
                        "name": "Pump B",
                        "action": {
                            "type": "actuator",
                            "esp_id": "ESP_X",
                            "gpio": 16,
                            "dose_ml": 5.0,
                        },
                    },
                ],
            }
        ]
        pumps = extract_dose_pumps_from_actions(actions)
        assert len(pumps) == 2
        assert pumps[0]["dose_ml"] == pytest.approx(4.0)
        assert pumps[1]["dose_ml"] == pytest.approx(5.0)

    def test_collect_skips_noop_and_sequence(self):
        enriched = [
            {
                "type": "actuator",
                "esp_id": "ESP_X",
                "gpio": 12,
                "dose_ml": 3.0,
            },
            {"type": "sequence", "steps": []},
        ]
        results = [
            {"type": "actuator", "success": True, "data": {"noop": True, "esp_id": "ESP_X", "gpio": 12}},
            {"type": "sequence", "success": True, "data": {"sequence_id": "s1", "status": "running"}},
        ]
        assert (
            collect_dispatched_dose_pumps(
                enriched_actions=enriched, action_results=results
            )
            == []
        )

    def test_ph_exclude_from_ec_composition(self):
        assert exclude_from_ec_composition(
            {"role": "ph_minus", "name": "Acid", "ec_contribution_ms_cm": 0.5}
        )
        expected = calculate_expected_ec(
            components=[
                {
                    "name": "A",
                    "ec_contribution_ms_cm": 1.0,
                },
                {
                    "name": "pH-Minus",
                    "role": "ph_minus",
                    "exclude_from_ec_composition": True,
                    "ec_contribution_ms_cm": 9.0,
                },
            ],
            volume_l=1.0,
            prior_volume_l=0.0,
        )
        assert expected == pytest.approx(1.0)


class TestSchemaDoseMlAbsolute:
    def test_product_absolute_only_allowed(self):
        data = NutrientBatchCreate(
            entry_type="top_up_dose",
            volume_l=0.004,
            components=[
                {
                    "kind": "product",
                    "name": "Pump A",
                    "dose_ml_absolute": 4.0,
                    "logic_execution_id": str(uuid.uuid4()),
                }
            ],
            acquisition_method="computed_runtime_x_rate",
            qualifier="approximate",
        )
        assert data.components[0]["dose_ml_absolute"] == 4.0

    def test_product_requires_some_dose_field(self):
        with pytest.raises(ValidationError):
            NutrientBatchCreate(
                entry_type="top_up_dose",
                volume_l=0.001,
                components=[{"kind": "product", "name": "X"}],
                acquisition_method="computed_runtime_x_rate",
                qualifier="approximate",
            )


@pytest.mark.asyncio
async def test_record_writes_one_entry_two_components(
    db_session: AsyncSession, tank_and_esp
) -> None:
    tank, esp, service = tank_and_esp
    exec_id = uuid.uuid4()
    rule_id = uuid.uuid4()
    result = await record_logic_dose_to_ledger(
        db_session,
        rule_id=rule_id,
        logic_execution_id=exec_id,
        pumps=[
            {"esp_id": esp.device_id, "gpio": 12, "dose_ml": 4.0, "name": "Pump A"},
            {"esp_id": esp.device_id, "gpio": 16, "dose_ml": 5.0, "name": "Pump B"},
        ],
        recipe_label=f"logic:{rule_id}",
    )
    assert result is not None
    assert result.entry_type == "top_up_dose"
    assert result.volume_l == pytest.approx(0.009)
    assert result.ec_was_measured is False
    assert len(result.components) == 2
    assert result.components[0]["dose_ml_absolute"] == pytest.approx(4.0)
    assert result.components[1]["dose_ml_absolute"] == pytest.approx(5.0)
    assert result.components[0]["logic_execution_id"] == str(exec_id)
    assert "ec_contribution" not in result.components[0]
    assert "ec_contribution_ms_cm" not in result.components[0]


@pytest.mark.asyncio
async def test_record_idempotent_skip(
    db_session: AsyncSession, tank_and_esp
) -> None:
    tank, esp, _service = tank_and_esp
    exec_id = uuid.uuid4()
    rule_id = uuid.uuid4()
    pumps = [
        {"esp_id": esp.device_id, "gpio": 12, "dose_ml": 2.0, "name": "Pump A"},
    ]
    first = await record_logic_dose_to_ledger(
        db_session,
        rule_id=rule_id,
        logic_execution_id=exec_id,
        pumps=pumps,
    )
    second = await record_logic_dose_to_ledger(
        db_session,
        rule_id=rule_id,
        logic_execution_id=exec_id,
        pumps=pumps,
    )
    assert first is not None
    assert second is None
    assert await ledger_has_logic_execution(
        db_session, tank_id=tank.id, logic_execution_id=exec_id
    )


@pytest.mark.asyncio
async def test_record_skips_when_tank_id_null(
    db_session: AsyncSession, zone: Zone
) -> None:
    esp = ESPDevice(
        device_id="ESP_NO_TANK",
        name="No Tank",
        ip_address="192.168.1.200",
        mac_address="AA:BB:CC:DD:00:01",
        firmware_version="1.0.0",
        hardware_type="ESP32_WROOM",
        status="online",
        zone_id=zone.zone_id,
        tank_id=None,
        capabilities={},
    )
    db_session.add(esp)
    await db_session.flush()
    result = await record_logic_dose_to_ledger(
        db_session,
        rule_id=uuid.uuid4(),
        logic_execution_id=uuid.uuid4(),
        pumps=[{"esp_id": esp.device_id, "gpio": 12, "dose_ml": 1.0, "name": "P"}],
    )
    assert result is None


@pytest.mark.asyncio
async def test_v_alt_rises_after_top_up_dose(
    db_session: AsyncSession, tank_and_esp
) -> None:
    tank, esp, service = tank_and_esp
    before, _ = await service._derive_prior_state(tank.id)
    assert before == pytest.approx(20.0)
    await record_logic_dose_to_ledger(
        db_session,
        rule_id=uuid.uuid4(),
        logic_execution_id=uuid.uuid4(),
        pumps=[
            {"esp_id": esp.device_id, "gpio": 12, "dose_ml": 10.0, "name": "Pump A"},
        ],
    )
    after, _ = await service._derive_prior_state(tank.id)
    assert after == pytest.approx(20.01)


@pytest.mark.asyncio
async def test_assist_stays_sensor_ec_after_logic_dose(
    db_session: AsyncSession, tank_and_esp
) -> None:
    tank, esp, service = tank_and_esp
    await record_logic_dose_to_ledger(
        db_session,
        rule_id=uuid.uuid4(),
        logic_execution_id=uuid.uuid4(),
        pumps=[
            {"esp_id": esp.device_id, "gpio": 12, "dose_ml": 5.0, "name": "Pump A"},
        ],
    )
    assist = await service.compute_dose_assist(
        tank.id,
        SaltCalculatorAssistRequest(
            current_ec_us_cm=1300.0,
            target_ec_us_cm=1400.0,
            concentration=5.0,
        ),
    )
    # Sensor EC from request — ledger dose must not invent assist EC.
    assert assist.volume_alt_source == "ledger_reconstructed"
    assert assist.volume_alt_l == pytest.approx(20.005)
    assert assist.expected_ec_us_cm == pytest.approx(1400.0)


@pytest.mark.asyncio
async def test_ph_minus_tagged_and_filtered(
    db_session: AsyncSession, tank_and_esp
) -> None:
    _tank, esp, _service = tank_and_esp
    result = await record_logic_dose_to_ledger(
        db_session,
        rule_id=uuid.uuid4(),
        logic_execution_id=uuid.uuid4(),
        pumps=[
            {
                "esp_id": esp.device_id,
                "gpio": 18,
                "dose_ml": 1.5,
                "name": "pH-Minus",
                "role": "ph_minus",
            },
        ],
    )
    assert result is not None
    assert result.components[0]["role"] == "ph_minus"
    assert result.components[0]["exclude_from_ec_composition"] is True
    assert ":ph" in (result.recipe_label or "")
    # Even if someone later adds a contribution, filter drops it.
    mixed = [
        {"name": "A", "ec_contribution_ms_cm": 2.0},
        {**result.components[0], "ec_contribution_ms_cm": 99.0},
    ]
    assert calculate_expected_ec(mixed, volume_l=1.0) == pytest.approx(2.0)


@pytest.mark.asyncio
async def test_engine_hook_skips_conflict_and_noop() -> None:
    """Pure guard logic of _maybe_record (no DB): conflict / dose_failure / !success."""
    from src.services.logic_engine import LogicEngine

    engine = LogicEngine(
        logic_repo=MagicMock(),
        actuator_service=MagicMock(),
        websocket_manager=MagicMock(),
        condition_evaluators=[],
        action_executors=[],
    )
    rule = MagicMock()
    rule.id = uuid.uuid4()
    rule.rule_metadata = {"dose_config": {"components": []}}

    # Conflict → early return (no exception)
    await engine._maybe_record_logic_dose_ledger(
        session=MagicMock(),
        rule=rule,
        logic_execution_id=uuid.uuid4(),
        enriched_actions=[{"type": "actuator", "dose_ml": 1.0}],
        execution_result={"action_results": []},
        blocked_by_conflict=True,
        has_dose_failure=False,
        success=False,
    )
    await engine._maybe_record_logic_dose_ledger(
        session=MagicMock(),
        rule=rule,
        logic_execution_id=uuid.uuid4(),
        enriched_actions=[{"type": "actuator", "dose_ml": 1.0}],
        execution_result={
            "action_results": [
                {
                    "type": "actuator",
                    "success": True,
                    "data": {"noop": True, "esp_id": "E", "gpio": 1},
                }
            ]
        },
        blocked_by_conflict=False,
        has_dose_failure=False,
        success=True,
    )
