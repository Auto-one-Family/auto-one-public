"""
AUT-1385 — Persist measured Nachfüll liters at refill-pump OFF (window end).

Flow sensor is a pure counter — never a rule trigger.
Window = Nachfüllpumpe ESP_57E1D4 GPIO25 ON→OFF (actuator_history).
At successful OFF: integrate flow over the window via
``FlowVolumeService.accumulate_refill_volume_l``, then write one
``fresh_water_refill`` ledger row (idempotent, pattern AUT-1352).

AUT-1397: Flow-sensor device/gpio come from ``rule_metadata.measure_bindings``
(``formula_params.ui_target=salt_calculator_volume_zugabe``). Mess→Ledger→Assist
path unchanged — only the sensor reference is resolved.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, NamedTuple, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logging_config import get_logger
from ..db.repositories.actuator_repo import ActuatorRepository
from ..db.repositories.esp_repo import ESPRepository
from ..db.repositories.logic_repo import LogicRepository
from ..db.repositories.nutrient_solution_batch_repo import (
    NutrientSolutionBatchRepository,
)
from ..schemas.tank import NutrientBatchCreate
from .flow_volume_service import (
    REFILL_FLOW_DEVICE_ID,
    REFILL_FLOW_GPIO,
    FlowVolumeService,
)
from .tank_service import TankService

logger = get_logger(__name__)

# Nachfüllpumpe — window bracket (not the flow sensor).
REFILL_PUMP_DEVICE_ID = REFILL_FLOW_DEVICE_ID  # ESP_57E1D4
REFILL_PUMP_GPIO = 25

UI_TARGET_SALT_CALCULATOR_VOLUME_ZUGABE = "salt_calculator_volume_zugabe"


class RefillFlowSensorRef(NamedTuple):
    device_id: str
    gpio: int
    source: str  # "measure_binding" | "legacy_default"


async def resolve_refill_flow_sensor(
    session: AsyncSession,
) -> RefillFlowSensorRef:
    """
    AUT-1397: Prefer flow sensor from measure_bindings (Frischwasser ui_target).

    Legacy REFILL_FLOW_* remains last-resort fallback until a binding is saved,
    so existing pumps keep measuring; logs mark the fallback explicitly.
    """
    try:
        logic_repo = LogicRepository(session)
        rules = await logic_repo.get_enabled_rules()
        for rule in rules:
            meta = rule.rule_metadata or {}
            bindings = meta.get("measure_bindings")
            if not isinstance(bindings, list):
                continue
            for binding in bindings:
                if not isinstance(binding, dict):
                    continue
                params = binding.get("formula_params") or {}
                if not isinstance(params, dict):
                    continue
                if params.get("ui_target") != UI_TARGET_SALT_CALCULATOR_VOLUME_ZUGABE:
                    continue
                refs = binding.get("sensor_refs") or []
                if not isinstance(refs, list) or not refs:
                    continue
                ref0 = refs[0]
                if not isinstance(ref0, dict):
                    continue
                esp_id = str(ref0.get("esp_id") or "").strip()
                gpio_raw = ref0.get("gpio")
                try:
                    gpio = int(gpio_raw)
                except (TypeError, ValueError):
                    continue
                if not esp_id or gpio < 0:
                    continue
                logger.info(
                    "AUT-1397: refill flow sensor from measure_binding " "rule=%s esp=%s gpio=%s",
                    getattr(rule, "rule_name", rule.id),
                    esp_id,
                    gpio,
                )
                return RefillFlowSensorRef(device_id=esp_id, gpio=gpio, source="measure_binding")
    except Exception as err:
        logger.error(
            "AUT-1397: measure_binding flow-sensor resolve failed: %s",
            err,
            exc_info=True,
        )

    logger.warning(
        "AUT-1397: no Frischwasser measure_binding — legacy flow sensor "
        "%s:GPIO%s (configure measure_bindings to replace hardcode)",
        REFILL_FLOW_DEVICE_ID,
        REFILL_FLOW_GPIO,
    )
    return RefillFlowSensorRef(
        device_id=REFILL_FLOW_DEVICE_ID,
        gpio=REFILL_FLOW_GPIO,
        source="legacy_default",
    )


def _ensure_aware(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts


async def ledger_has_refill_event(
    session: AsyncSession,
    *,
    tank_id: uuid.UUID,
    event_key: str,
    limit: int = 200,
) -> bool:
    """Idempotency: skip if a fresh_water_refill already carries this event_key."""
    repo = NutrientSolutionBatchRepository(session)
    entries = await repo.get_by_tank(tank_id, limit=limit)
    for entry in entries:
        if entry.entry_type != "fresh_water_refill":
            continue
        for component in entry.components or []:
            if not isinstance(component, dict):
                continue
            if str(component.get("refill_event_key", "")) == event_key:
                return True
    return False


async def _find_last_successful_on(
    actuator_repo: ActuatorRepository,
    *,
    esp_uuid: uuid.UUID,
    gpio: int,
    before: datetime,
) -> Optional[datetime]:
    """Most recent successful ON response before ``before`` (newest-first history)."""
    history = await actuator_repo.get_history(esp_uuid, gpio, limit=100)
    before_aware = _ensure_aware(before)
    for row in history:
        if not row.success:
            continue
        if str(row.command_type or "").upper() != "ON":
            continue
        ts = _ensure_aware(row.timestamp)
        if ts < before_aware:
            return ts
    return None


async def maybe_record_refill_volume_to_ledger(
    session: AsyncSession,
    *,
    device_id: str,
    esp_uuid: uuid.UUID,
    gpio: int,
    off_at: datetime,
    correlation_id: Optional[str] = None,
) -> Optional[Any]:
    """
    On refill-pump OFF: measure window liters and persist ``fresh_water_refill``.

    No-op unless ``device_id``/``gpio`` match the Nachfüllpumpe dock.
    Never raises into the MQTT handler — logs and returns None on failure.
    """
    try:
        if device_id != REFILL_PUMP_DEVICE_ID or int(gpio) != REFILL_PUMP_GPIO:
            return None

        esp_repo = ESPRepository(session)
        device = await esp_repo.get_by_device_id(device_id)
        if device is None or device.tank_id is None:
            logger.warning(
                "AUT-1385: refill OFF on %s:GPIO%s — no tank_id, skip ledger",
                device_id,
                gpio,
            )
            return None

        tank_id = device.tank_id
        off_aware = _ensure_aware(off_at)
        event_key = (
            correlation_id if correlation_id else f"{device_id}:{gpio}:{off_aware.isoformat()}"
        )

        if await ledger_has_refill_event(session, tank_id=tank_id, event_key=event_key):
            logger.info(
                "AUT-1385: skip refill ledger — event_key=%s already present",
                event_key,
            )
            return None

        actuator_repo = ActuatorRepository(session)
        on_at = await _find_last_successful_on(
            actuator_repo, esp_uuid=esp_uuid, gpio=gpio, before=off_aware
        )
        if on_at is None:
            logger.warning(
                "AUT-1385: refill OFF without prior ON window — skip "
                "(device=%s gpio=%s off_at=%s)",
                device_id,
                gpio,
                off_aware.isoformat(),
            )
            return None

        flow_sensor = await resolve_refill_flow_sensor(session)
        flow_svc = FlowVolumeService(session)
        # AUT-1397: sensor from measure_bindings (or legacy default).
        # Window still = pump ON→OFF; Assist/Ledger path unchanged.
        measured = await flow_svc.accumulate_refill_volume_l(
            on_at,
            off_aware,
            device_id=flow_sensor.device_id,
            gpio=flow_sensor.gpio,
            esp_uuid=(esp_uuid if flow_sensor.device_id == device_id else None),
        )
        volume_l = float(measured.volume_l)
        if volume_l <= 0:
            logger.info(
                "AUT-1385: refill window measured 0 L (samples=%s) — no ledger row",
                measured.sample_count,
            )
            return None

        tank_service = TankService(session)
        data = NutrientBatchCreate(
            entry_type="fresh_water_refill",
            volume_l=volume_l,
            components=[
                {
                    "kind": "product",
                    "name": "Frischwasser Nachfüllung",
                    # Schema requires a dose field; liters→ml keeps the measured volume.
                    "dose_ml_absolute": volume_l * 1000.0,
                    "role": "fresh_water",
                    "esp_id": device_id,
                    "gpio": gpio,
                    "refill_event_key": event_key,
                    "window_start": on_at.isoformat(),
                    "window_end": off_aware.isoformat(),
                    "flow_sample_count": measured.sample_count,
                    "flow_sensor_esp_id": flow_sensor.device_id,
                    "flow_sensor_gpio": flow_sensor.gpio,
                    "flow_sensor_source": flow_sensor.source,
                }
            ],
            acquisition_method="measured_flow",
            qualifier="approximate",
            recipe_label=f"refill:{device_id}:gpio{gpio}",
            occurred_at=off_aware,
            ec_was_measured=False,
            ph_was_measured=False,
        )
        response = await tank_service.create_batch(tank_id, data)
        logger.info(
            "AUT-1385: ledger fresh_water_refill written id=%s tank=%s "
            "volume_l=%.4f event_key=%s",
            response.id,
            tank_id,
            response.volume_l,
            event_key,
        )
        return response
    except Exception as err:
        logger.error(
            "AUT-1385: refill ledger write failed device=%s gpio=%s: %s",
            device_id,
            gpio,
            err,
            exc_info=True,
        )
        return None
