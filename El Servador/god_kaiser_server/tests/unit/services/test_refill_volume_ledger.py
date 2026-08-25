"""AUT-1385 — refill window → fresh_water_refill ledger + Assist resolve."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.zone import Zone
from src.schemas.tank import (
    NutrientBatchCreate,
    SaltCalculatorAssistRequest,
    TankCreate,
)
from src.services.flow_volume_service import FlowVolumeResult
from src.services.flow_volume_service import REFILL_FLOW_DEVICE_ID, REFILL_FLOW_GPIO
from src.services.refill_volume_ledger import (
    REFILL_PUMP_DEVICE_ID,
    REFILL_PUMP_GPIO,
    RefillFlowSensorRef,
    maybe_record_refill_volume_to_ledger,
    resolve_refill_flow_sensor,
)
from src.services.tank_service import TankService


@pytest.fixture
async def zone(db_session: AsyncSession) -> Zone:
    z = Zone(zone_id="zelt_refill_1385", name="Zelt Refill 1385")
    db_session.add(z)
    await db_session.flush()
    await db_session.refresh(z)
    return z


@pytest.fixture
def service(db_session: AsyncSession) -> TankService:
    return TankService(db_session)


@pytest.mark.asyncio
async def test_maybe_record_refill_ignores_non_refill_pump() -> None:
    session = AsyncMock()
    result = await maybe_record_refill_volume_to_ledger(
        session,
        device_id="ESP_OTHER",
        esp_uuid=uuid.uuid4(),
        gpio=25,
        off_at=datetime.now(timezone.utc),
    )
    assert result is None


@pytest.mark.asyncio
async def test_maybe_record_refill_writes_ledger_once() -> None:
    session = AsyncMock()
    tank_id = uuid.uuid4()
    esp_uuid = uuid.uuid4()
    off_at = datetime(2026, 7, 26, 10, 0, tzinfo=timezone.utc)
    on_at = off_at - timedelta(minutes=5)

    device = MagicMock()
    device.tank_id = tank_id
    device.device_id = REFILL_PUMP_DEVICE_ID

    on_row = MagicMock()
    on_row.success = True
    on_row.command_type = "ON"
    on_row.timestamp = on_at

    mock_esp_repo = AsyncMock()
    mock_esp_repo.get_by_device_id = AsyncMock(return_value=device)

    mock_act_repo = AsyncMock()
    mock_act_repo.get_history = AsyncMock(return_value=[on_row])

    mock_batch_repo = AsyncMock()
    mock_batch_repo.get_by_tank = AsyncMock(return_value=[])

    flow_result = FlowVolumeResult(
        volume_l=3.5,
        start=on_at,
        end=off_at,
        sample_count=12,
        esp_id=esp_uuid,
        gpio=14,
    )
    mock_flow = AsyncMock()
    mock_flow.accumulate_refill_volume_l = AsyncMock(return_value=flow_result)

    created = MagicMock()
    created.id = uuid.uuid4()
    created.volume_l = 3.5

    with (
        patch(
            "src.services.refill_volume_ledger.ESPRepository",
            return_value=mock_esp_repo,
        ),
        patch(
            "src.services.refill_volume_ledger.ActuatorRepository",
            return_value=mock_act_repo,
        ),
        patch(
            "src.services.refill_volume_ledger.NutrientSolutionBatchRepository",
            return_value=mock_batch_repo,
        ),
        patch(
            "src.services.refill_volume_ledger.FlowVolumeService",
            return_value=mock_flow,
        ),
        patch(
            "src.services.refill_volume_ledger.resolve_refill_flow_sensor",
            new_callable=AsyncMock,
            return_value=RefillFlowSensorRef(
                device_id="ESP_FLOW99",
                gpio=14,
                source="measure_binding",
            ),
        ),
        patch(
            "src.services.refill_volume_ledger.TankService"
        ) as mock_tank_cls,
    ):
        mock_tank = AsyncMock()
        mock_tank.create_batch = AsyncMock(return_value=created)
        mock_tank_cls.return_value = mock_tank

        first = await maybe_record_refill_volume_to_ledger(
            session,
            device_id=REFILL_PUMP_DEVICE_ID,
            esp_uuid=esp_uuid,
            gpio=REFILL_PUMP_GPIO,
            off_at=off_at,
            correlation_id="corr-refill-1",
        )
        assert first is created
        mock_tank.create_batch.assert_awaited_once()
        batch_data: NutrientBatchCreate = mock_tank.create_batch.await_args.args[1]
        assert batch_data.entry_type == "fresh_water_refill"
        assert batch_data.volume_l == pytest.approx(3.5)
        assert batch_data.acquisition_method == "measured_flow"
        assert batch_data.components[0]["refill_event_key"] == "corr-refill-1"
        assert batch_data.components[0]["flow_sensor_esp_id"] == "ESP_FLOW99"
        assert batch_data.components[0]["flow_sensor_source"] == "measure_binding"
        mock_flow.accumulate_refill_volume_l.assert_awaited_once()
        call_kwargs = mock_flow.accumulate_refill_volume_l.await_args.kwargs
        assert call_kwargs["device_id"] == "ESP_FLOW99"
        assert call_kwargs["gpio"] == 14


@pytest.mark.asyncio
async def test_resolve_refill_flow_sensor_from_measure_binding() -> None:
    session = AsyncMock()
    rule = MagicMock()
    rule.rule_name = "Frischwasser"
    rule.rule_metadata = {
        "measure_bindings": [
            {
                "sensor_refs": [
                    {"esp_id": "ESP_AABBCC", "gpio": 14, "sensor_type": "flow"}
                ],
                "hooks": ["on_start", "on_complete"],
                "formula_id": "difference",
                "formula_params": {
                    "ui_target": "salt_calculator_volume_zugabe",
                },
                "output_target": "ledger",
            }
        ]
    }
    mock_logic = AsyncMock()
    mock_logic.get_enabled_rules = AsyncMock(return_value=[rule])
    with patch(
        "src.services.refill_volume_ledger.LogicRepository",
        return_value=mock_logic,
    ):
        resolved = await resolve_refill_flow_sensor(session)
    assert resolved.device_id == "ESP_AABBCC"
    assert resolved.gpio == 14
    assert resolved.source == "measure_binding"


@pytest.mark.asyncio
async def test_resolve_refill_flow_sensor_legacy_fallback() -> None:
    session = AsyncMock()
    mock_logic = AsyncMock()
    mock_logic.get_enabled_rules = AsyncMock(return_value=[])
    with patch(
        "src.services.refill_volume_ledger.LogicRepository",
        return_value=mock_logic,
    ):
        resolved = await resolve_refill_flow_sensor(session)
    assert resolved.device_id == REFILL_FLOW_DEVICE_ID
    assert resolved.gpio == REFILL_FLOW_GPIO
    assert resolved.source == "legacy_default"


@pytest.mark.asyncio
async def test_resolve_volume_zugabe_manual_beats_measured(
    service: TankService, zone
) -> None:
    tank = await service.create_tank(
        TankCreate(
            zone_id=zone.zone_id,
            name="Tank Zugabe Manual",
            operation_mode="drain_to_waste",
        )
    )
    await service.create_batch(
        tank.id,
        NutrientBatchCreate(
            entry_type="fresh_water_refill",
            volume_l=4.0,
            components=[],
            acquisition_method="measured_flow",
            qualifier="approximate",
        ),
    )
    volume, source, occurred, label = await service._resolve_volume_zugabe(
        tank.id, 2.5
    )
    assert volume == pytest.approx(2.5)
    assert source == "manual"
    assert occurred is None
    assert label is None


@pytest.mark.asyncio
async def test_resolve_volume_zugabe_from_ledger(
    service: TankService, zone
) -> None:
    tank = await service.create_tank(
        TankCreate(
            zone_id=zone.zone_id,
            name="Tank Zugabe Measured",
            operation_mode="drain_to_waste",
        )
    )
    await service.create_batch(
        tank.id,
        NutrientBatchCreate(
            entry_type="fresh_water_refill",
            volume_l=4.0,
            components=[],
            acquisition_method="measured_flow",
            qualifier="approximate",
        ),
    )
    volume, source, occurred, label = await service._resolve_volume_zugabe(
        tank.id, 0.0
    )
    assert volume == pytest.approx(4.0)
    assert source == "measured"
    assert occurred is not None
    assert label is not None


@pytest.mark.asyncio
async def test_resolve_volume_zugabe_none_when_empty(
    service: TankService, zone
) -> None:
    tank = await service.create_tank(
        TankCreate(
            zone_id=zone.zone_id,
            name="Tank Zugabe Empty",
            operation_mode="drain_to_waste",
        )
    )
    volume, source, occurred, label = await service._resolve_volume_zugabe(
        tank.id, 0.0
    )
    assert volume == 0.0
    assert source == "none"
    assert occurred is None
    assert label is None


@pytest.mark.asyncio
async def test_compute_dose_assist_measured_zugabe_adjusts_v_alt(
    service: TankService, zone
) -> None:
    """Post-fill V_real=20 + measured zugabe=5 → V_alt=15, V_neu=20."""
    tank = await service.create_tank(
        TankCreate(
            zone_id=zone.zone_id,
            name="Tank Assist Prefill",
            operation_mode="drain_to_waste",
            fresh_water_ec_us_cm=400.0,
        )
    )
    await service.create_batch(
        tank.id,
        NutrientBatchCreate(
            entry_type="fresh_water_refill",
            volume_l=5.0,
            components=[],
            acquisition_method="measured_flow",
            qualifier="approximate",
        ),
    )

    truth = MagicMock()
    truth.volume_l = 20.0
    truth.source = "level_anchor_live"

    with patch(
        "src.services.tank_service.resolve_v_real",
        new=AsyncMock(return_value=truth),
    ):
        result = await service.compute_dose_assist(
            tank.id,
            SaltCalculatorAssistRequest(
                current_ec_us_cm=1400.0,
                target_ec_us_cm=1500.0,
                concentration=2.0,
                volume_zugabe_l=0.0,
            ),
        )

    assert result.volume_zugabe_l == pytest.approx(5.0)
    assert result.volume_zugabe_source == "measured"
    assert result.volume_alt_l == pytest.approx(15.0)
    assert result.volume_alt_source == "v_real_minus_measured_zugabe"
    assert result.volume_neu_l == pytest.approx(20.0)
