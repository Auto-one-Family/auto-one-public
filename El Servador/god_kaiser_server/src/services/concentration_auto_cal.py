"""
AUT-1371 K2 Weg A — self-measuring concentration calibration.

Trigger: ``actuator_configs.concentration IS NULL`` (no armed flag).
Formula: 1:1 port of FE ``concentrationFromDeltaEc``.
SSOT write: ``actuator_configs.concentration`` only.
Uses existing sequence_executor steps (actuator + delay_seconds); no new engine.

Safety (Revision 3): every Actuator-ON step carries explicit ``duration_seconds``
(bounded command-driven FW timer). Mix/Messbox is ONE bounded ON step — never
ON + separate OFF.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from statistics import median
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logging_config import get_logger
from ..db.repositories.actuator_repo import ActuatorRepository
from ..db.repositories.esp_repo import ESPRepository
from ..db.repositories.sensor_repo import SensorRepository
from ..sensors.dose_calculators.active.concentration_from_delta_ec import (
    concentration_from_delta_ec,
)
from .tank_volume_truth import resolve_v_real


logger = get_logger(__name__)

# AUT-1371 / AUT-1115 / AUT-1345: ≥ 5 min settle; live Mischzeit was 120 s.
AUTO_CAL_SETTLE_SECONDS = 300
# Reject refine updates that deviate more than 50% from current SSOT.
AUTO_CAL_OUTLIER_RATIO = 0.5
# Freshness: EWMA when fewer than 3 accepted history samples in metadata.
AUTO_CAL_EWMA_ALPHA = 0.3
AUTO_CAL_HISTORY_MAX = 3
AUTO_CAL_META_KEY = "concentration_auto_cal"
AUTO_CAL_ACTION_KEY = "_aut1371_auto_cal"
MIX_PUMP_NAME_HINT = "messbox"


async def enrich_sequences_for_auto_cal(
    session: AsyncSession,
    actions: list[dict],
) -> list[dict]:
    """
    When a sequence doses part_a/part_b pumps, attach auto-cal metadata.

    If any stock pump has ``concentration IS NULL``, rewrite steps to
    A → Mix(bounded ON=settle) → delay settle → B → Mix → delay settle.
    If all are already calibrated, keep original steps and only attach meta
    for Nachschärfung (no settle rewrite).

    Idempotent: skips sequences that already carry ``_aut1371_auto_cal``.
    """
    out: list[dict] = []
    for action in actions:
        if action.get("type") != "sequence" or not isinstance(action.get("steps"), list):
            out.append(action)
            continue
        if action.get(AUTO_CAL_ACTION_KEY):
            out.append(action)
            continue

        plan = await _build_auto_cal_plan(session, action["steps"])
        if plan is None:
            out.append(action)
            continue

        rewritten = deepcopy(action)
        rewritten["steps"] = plan["steps"]
        rewritten[AUTO_CAL_ACTION_KEY] = plan["meta"]
        if plan["rewritten"]:
            min_duration = AUTO_CAL_SETTLE_SECONDS * 2 + 120
            current_max = int(rewritten.get("max_duration_seconds") or 0)
            rewritten["max_duration_seconds"] = max(current_max, min_duration)
        out.append(rewritten)
        logger.info(
            "AUT-1371: enriched sequence auto-cal pumps=%s rewritten=%s settle=%ss",
            [p["gpio"] for p in plan["meta"]["pumps"]],
            plan["rewritten"],
            plan["meta"]["settle_seconds"],
        )
    return out


async def finalize_auto_cal_from_sequence(
    session: AsyncSession,
    *,
    meta: dict[str, Any],
    started_at: Optional[datetime],
    completed_at: Optional[datetime],
) -> list[dict[str, Any]]:
    """
    After sequence COMPLETED: measure ΔEC per pump, resolve V_real, write SSOT.

    Fail-closed on missing V_real / EC / dose_ml — never invents numbers.
    Returns list of write reports (empty if nothing written).
    """
    if not meta:
        return []

    tank_id_raw = meta.get("tank_id")
    pumps = meta.get("pumps") or []
    if not tank_id_raw or not pumps:
        return []

    tank_id = UUID(str(tank_id_raw))
    volume = await resolve_v_real(session, tank_id, as_of=completed_at)
    if volume is None or volume.volume_l <= 0:
        logger.warning(
            "AUT-1371: skip auto-cal write — V_real unresolved tank_id=%s",
            tank_id,
        )
        return []

    ec_esp_id = meta.get("ec_esp_id")
    if not ec_esp_id:
        logger.warning("AUT-1371: skip auto-cal — no ec_esp_id in metadata")
        return []

    sensor_repo = SensorRepository(session)
    esp_repo = ESPRepository(session)
    ec_device = await esp_repo.get_by_device_id(str(ec_esp_id))
    if ec_device is None:
        logger.warning("AUT-1371: EC ESP %s not found", ec_esp_id)
        return []

    settle_s = float(meta.get("settle_seconds") or AUTO_CAL_SETTLE_SECONDS)
    t0 = started_at or datetime.now(timezone.utc)
    if t0.tzinfo is None:
        t0 = t0.replace(tzinfo=timezone.utc)
    t_end = completed_at or datetime.now(timezone.utc)
    if t_end.tzinfo is None:
        t_end = t_end.replace(tzinfo=timezone.utc)

    ec0 = await _ec_near(sensor_repo, ec_device.id, t0)
    if ec0 is None:
        logger.warning("AUT-1371: skip auto-cal — EC₀ missing")
        return []

    reports: list[dict[str, Any]] = []
    previous_ec = ec0
    cursor = t0
    for pump in pumps:
        duration_s = float(pump.get("duration_s") or 0)
        flow = pump.get("flow_rate_ml_s")
        if flow is None or float(flow) <= 0 or duration_s <= 0:
            logger.warning(
                "AUT-1371: skip pump gpio=%s — missing flow_rate or duration",
                pump.get("gpio"),
            )
            continue
        dose_ml = float(flow) * duration_s
        cursor = datetime.fromtimestamp(
            cursor.timestamp() + duration_s + settle_s,
            tz=timezone.utc,
        )
        sample_at = min(cursor, t_end)
        ec1 = await _ec_near(sensor_repo, ec_device.id, sample_at)
        if ec1 is None:
            logger.warning(
                "AUT-1371: skip pump gpio=%s — EC₁ missing at %s",
                pump.get("gpio"),
                sample_at.isoformat(),
            )
            continue

        measured = concentration_from_delta_ec(previous_ec, ec1, volume.volume_l, dose_ml)
        if measured is None or measured <= 0:
            logger.warning(
                "AUT-1371: non-positive concentration gpio=%s ec0=%s ec1=%s V=%s ml=%s",
                pump.get("gpio"),
                previous_ec,
                ec1,
                volume.volume_l,
                dose_ml,
            )
            previous_ec = ec1
            continue

        report = await _apply_concentration_update(
            session,
            actuator_config_id=UUID(str(pump["actuator_config_id"])),
            measured=measured,
            context={
                "ec0": previous_ec,
                "ec1": ec1,
                "dose_ml": dose_ml,
                "v_real_l": volume.volume_l,
                "v_source": volume.source,
            },
        )
        if report is not None:
            reports.append(report)
        previous_ec = ec1

    return reports


def merge_concentration_update(
    current: Optional[float],
    measured: float,
    history: list[float],
    *,
    outlier_ratio: float = AUTO_CAL_OUTLIER_RATIO,
    ewma_alpha: float = AUTO_CAL_EWMA_ALPHA,
) -> tuple[Optional[float], str, list[float]]:
    """
    Pure update policy for tests.

    Returns ``(new_value_or_None_if_rejected, reason, new_history)``.
    """
    if measured <= 0 or measured != measured:
        return None, "invalid_measured", list(history)

    if current is None or current <= 0:
        hist = [measured]
        return measured, "initial", hist

    if abs(measured / current - 1.0) > outlier_ratio:
        return None, "outlier_rejected", list(history)

    hist = (list(history) + [measured])[-AUTO_CAL_HISTORY_MAX:]
    if len(hist) >= 3:
        return float(median(hist)), "median_window", hist
    refined = (1.0 - ewma_alpha) * float(current) + ewma_alpha * measured
    return refined, "ewma", hist


async def _build_auto_cal_plan(
    session: AsyncSession,
    steps: list[dict],
) -> Optional[dict[str, Any]]:
    esp_repo = ESPRepository(session)
    actuator_repo = ActuatorRepository(session)

    dose_pumps: list[dict[str, Any]] = []
    mix_candidates: list[tuple[str, int]] = []
    tank_id: Optional[UUID] = None
    dose_esp_device_id: Optional[str] = None
    existing_settle: Optional[float] = None

    for step in steps:
        if not isinstance(step, dict):
            continue
        if "delay_seconds" in step and "action" not in step:
            try:
                existing_settle = float(step["delay_seconds"])
            except (TypeError, ValueError):
                pass
            continue
        action = step.get("action")
        if not isinstance(action, dict):
            continue
        if action.get("type") not in ("actuator", "actuator_command"):
            continue
        if str(action.get("command", "ON")).upper() != "ON":
            continue
        esp_id_str = action.get("esp_id")
        gpio_raw = action.get("gpio")
        if not esp_id_str or gpio_raw is None:
            continue
        esp = await esp_repo.get_by_device_id(str(esp_id_str))
        if esp is None:
            continue
        act = await actuator_repo.get_by_esp_and_gpio(esp.id, int(gpio_raw))
        if act is None:
            continue
        role = (act.dose_role or "").strip().lower()
        if role in ("part_a", "part_b"):
            needs_cal = act.concentration is None or float(act.concentration) <= 0
            duration = action.get("duration_seconds")
            if duration is None:
                duration = action.get("duration_s")
            # Boundedness: refuse to plan a dose without explicit duration.
            if duration is None or float(duration) <= 0:
                logger.warning(
                    "AUT-1371: skip auto-cal — unbounded ON gpio=%s (no duration_seconds)",
                    gpio_raw,
                )
                return None
            dose_pumps.append(
                {
                    "esp_id": esp.device_id,
                    "gpio": int(gpio_raw),
                    "dose_role": role,
                    "duration_s": float(duration),
                    "flow_rate_ml_s": act.flow_rate_ml_s,
                    "actuator_config_id": str(act.id),
                    "needs_cal": needs_cal,
                    "action": action,
                }
            )
            if esp.tank_id is not None:
                tank_id = esp.tank_id
            dose_esp_device_id = esp.device_id
        else:
            name = (act.actuator_name or "").lower()
            if MIX_PUMP_NAME_HINT in name or int(gpio_raw) == 13:
                mix_candidates.append((esp.device_id, int(gpio_raw)))

    if not dose_pumps or tank_id is None:
        return None

    # Preserve part_a then part_b order when both present.
    role_order = {"part_a": 0, "part_b": 1}
    dose_pumps.sort(key=lambda p: role_order.get(p["dose_role"], 99))

    needs_seed = any(p["needs_cal"] for p in dose_pumps)
    mix_esp, mix_gpio = await _resolve_mix_pump(session, dose_esp_device_id, mix_candidates)

    if needs_seed:
        settle = float(AUTO_CAL_SETTLE_SECONDS)
        new_steps = _build_seed_steps(dose_pumps, mix_esp, mix_gpio, settle)
        rewritten = True
    else:
        settle = float(existing_settle) if existing_settle and existing_settle > 0 else 120.0
        new_steps = list(steps)
        rewritten = False

    return {
        "steps": new_steps,
        "rewritten": rewritten,
        "meta": {
            "tank_id": str(tank_id),
            "ec_esp_id": dose_esp_device_id,
            "settle_seconds": settle,
            "mix_esp_id": mix_esp,
            "mix_gpio": mix_gpio,
            "rewritten": rewritten,
            "pumps": [
                {
                    "esp_id": p["esp_id"],
                    "gpio": p["gpio"],
                    "dose_role": p["dose_role"],
                    "duration_s": p["duration_s"],
                    "flow_rate_ml_s": p["flow_rate_ml_s"],
                    "actuator_config_id": p["actuator_config_id"],
                    "needs_cal": p["needs_cal"],
                }
                for p in dose_pumps
            ],
        },
    }


def _build_seed_steps(
    dose_pumps: list[dict[str, Any]],
    mix_esp: Optional[str],
    mix_gpio: Optional[int],
    settle: float,
) -> list[dict]:
    """
    Serielle Mess-Sequenz: Dose → Mix bounded ON → Settle delay (je Pumpe).

    Mix is a single ON with ``duration_seconds=settle`` — FW timer ends it.
    No separate OFF step (AUT-1371 Revision 3 / VERIFY-PLAN Pflicht).
    """
    new_steps: list[dict] = []
    for pump in dose_pumps:
        dose_action = deepcopy(pump["action"])
        # Normalize duration key for FW/command path.
        if (
            dose_action.get("duration_seconds") is None
            and dose_action.get("duration_s") is not None
        ):
            dose_action["duration_seconds"] = dose_action["duration_s"]
        new_steps.append(
            {
                "name": f"AutoCal Dose {pump['dose_role']}",
                "action": dose_action,
            }
        )
        if mix_esp is not None and mix_gpio is not None:
            new_steps.append(
                {
                    "name": f"AutoCal Mix {pump['dose_role']}",
                    "action": {
                        "type": "actuator",
                        "esp_id": mix_esp,
                        "gpio": mix_gpio,
                        "command": "ON",
                        "value": 1,
                        "duration_seconds": settle,
                    },
                }
            )
        new_steps.append(
            {
                "name": f"AutoCal Settle {pump['dose_role']}",
                "delay_seconds": settle,
            }
        )
    return new_steps


async def _resolve_mix_pump(
    session: AsyncSession,
    dose_esp_device_id: Optional[str],
    candidates: list[tuple[str, int]],
) -> tuple[Optional[str], Optional[int]]:
    if candidates:
        return candidates[0]
    if not dose_esp_device_id:
        return None, None
    esp_repo = ESPRepository(session)
    actuator_repo = ActuatorRepository(session)
    esp = await esp_repo.get_by_device_id(dose_esp_device_id)
    if esp is None:
        return None, None
    actuators = await actuator_repo.get_by_esp(esp.id)
    for act in actuators:
        name = (act.actuator_name or "").lower()
        if MIX_PUMP_NAME_HINT in name or act.gpio == 13:
            return esp.device_id, int(act.gpio)
    return None, None


async def _ec_near(
    sensor_repo: SensorRepository,
    esp_uuid: UUID,
    at: datetime,
) -> Optional[float]:
    """EC reading at or before ``at``; fallback to absolute latest on ESP."""
    rows = await sensor_repo.query_data(
        esp_id=esp_uuid,
        sensor_type="ec",
        end_time=at,
        limit=1,
    )
    reading = rows[0] if rows else None
    if reading is None:
        reading = await sensor_repo.get_latest_reading_for_esp(esp_uuid, "ec")
    if reading is None:
        return None
    value = reading.processed_value
    if value is None:
        value = reading.raw_value
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


async def _apply_concentration_update(
    session: AsyncSession,
    *,
    actuator_config_id: UUID,
    measured: float,
    context: dict[str, Any],
) -> Optional[dict[str, Any]]:
    actuator_repo = ActuatorRepository(session)
    act = await actuator_repo.get_by_id(actuator_config_id)
    if act is None:
        return None

    meta = dict(act.actuator_metadata or {})
    cal_meta = dict(meta.get(AUTO_CAL_META_KEY) or {})
    history = [float(x) for x in (cal_meta.get("history") or []) if x is not None]

    new_value, reason, new_history = merge_concentration_update(
        act.concentration, measured, history
    )
    if new_value is None:
        logger.info(
            "AUT-1371: concentration update rejected gpio=%s reason=%s measured=%.4f current=%s",
            act.gpio,
            reason,
            measured,
            act.concentration,
        )
        return {
            "actuator_config_id": str(act.id),
            "gpio": act.gpio,
            "rejected": True,
            "reason": reason,
            "measured": measured,
        }

    act.concentration = round(float(new_value), 4)
    cal_meta.update(
        {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "source": reason,
            "last_measured": round(float(measured), 4),
            "history": [round(float(x), 4) for x in new_history],
            **context,
        }
    )
    meta[AUTO_CAL_META_KEY] = cal_meta
    act.actuator_metadata = meta
    await session.flush()
    logger.info(
        "AUT-1371: wrote concentration gpio=%s value=%.4f reason=%s V=%s",
        act.gpio,
        act.concentration,
        reason,
        context.get("v_real_l"),
    )
    return {
        "actuator_config_id": str(act.id),
        "gpio": act.gpio,
        "rejected": False,
        "reason": reason,
        "concentration": act.concentration,
        "measured": measured,
    }
