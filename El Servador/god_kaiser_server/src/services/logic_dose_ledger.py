"""
AUT-1352 — Logic dose → Stoffbilanz-Ledger (additives Logging only).

Writes ``top_up_dose`` rows via ``TankService.create_batch`` after a real MQTT
dispatch (flat) or sequence COMPLETED. Does NOT change dose timing, flow_rate
ceil, or actuator commands.

Q1 (documented gap): sequence partial abort → no ledger row (failure history /
sensor EC remain). Not silent — callers MUST log a WARNING on abort.
Q3: never writes ``ec_contribution*`` / ``ec_was_measured`` stays false.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logging_config import get_logger
from ..db.repositories.actuator_repo import ActuatorRepository
from ..db.repositories.esp_repo import ESPRepository
from ..db.repositories.nutrient_solution_batch_repo import (
    NutrientSolutionBatchRepository,
)
from ..schemas.tank import NutrientBatchCreate
from ..sensors.dose_calculators.active.ec_control_anchor import (
    PH_EC_EXCLUDED_ROLES,
    exclude_from_ec_composition,
)
from .tank_service import TankService

logger = get_logger(__name__)

# Re-export for callers/tests (canonical filter lives in ec_control_anchor).
__all__ = [
    "PH_EC_EXCLUDED_ROLES",
    "action_result_is_real_dispatch",
    "collect_dispatched_dose_pumps",
    "exclude_from_ec_composition",
    "extract_dose_pumps_from_actions",
    "infer_component_role",
    "ledger_has_logic_execution",
    "record_logic_dose_to_ledger",
]


def is_ph_component_role(role: Optional[str], name: Optional[str] = None) -> bool:
    """True when component is a pH dose (tagged or name heuristic)."""
    return exclude_from_ec_composition(
        {
            "role": role,
            "name": name,
            "exclude_from_ec_composition": False,
        }
    )


def infer_component_role(
    *,
    name: Optional[str] = None,
    dose_config_component: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Resolve role from dose_config component or name heuristic."""
    if dose_config_component:
        explicit = dose_config_component.get("role")
        if isinstance(explicit, str) and explicit.strip():
            return explicit.strip().lower()
        cfg_name = dose_config_component.get("name")
        if is_ph_component_role(None, str(cfg_name) if cfg_name else None):
            n = str(cfg_name).lower()
            if "plus" in n:
                return "ph_plus"
            return "ph_minus"
    if is_ph_component_role(None, name):
        n = (name or "").lower()
        if "plus" in n:
            return "ph_plus"
        return "ph_minus"
    return None


def extract_dose_pumps_from_actions(
    actions: Sequence[Dict[str, Any]],
    *,
    dose_config_components: Optional[Sequence[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Flatten enriched actions into one pump row per dose_ml > 0.

    Preserves per-pump ml (A≠B). Sequence steps are expanded; delays ignored.
    """
    components = list(dose_config_components or [])
    component_iter = iter(components)
    pumps: List[Dict[str, Any]] = []

    def _one(action: Dict[str, Any], step_name: Optional[str] = None) -> None:
        dose_ml = action.get("dose_ml")
        if dose_ml is None or float(dose_ml) <= 0:
            # Consume positional component even when no dose (keep A/B alignment).
            next(component_iter, None)
            return
        cfg = next(component_iter, None)
        cfg_name = None
        if isinstance(cfg, dict):
            cfg_name = cfg.get("name")
        label = (
            step_name
            or action.get("name")
            or (str(cfg_name) if cfg_name else None)
            or f"GPIO{action.get('gpio')}"
        )
        role = infer_component_role(name=str(label), dose_config_component=cfg)
        pumps.append(
            {
                "esp_id": action.get("esp_id"),
                "gpio": action.get("gpio"),
                "dose_ml": float(dose_ml),
                "name": str(label),
                "role": role,
            }
        )

    for action in actions:
        if not isinstance(action, dict):
            continue
        action_type = action.get("type")
        if action_type in ("actuator_command", "actuator"):
            _one(action)
        elif action_type == "sequence" and isinstance(action.get("steps"), list):
            for step in action["steps"]:
                if not isinstance(step, dict):
                    continue
                step_action = step.get("action")
                if isinstance(step_action, dict) and step_action.get("type") in (
                    "actuator_command",
                    "actuator",
                ):
                    _one(step_action, step.get("name"))

    return pumps


def action_result_is_real_dispatch(result: Dict[str, Any]) -> bool:
    """True when MQTT was dispatched (not noop / skipped / failed)."""
    if not result.get("success"):
        return False
    data = result.get("data") or {}
    if data.get("noop") or data.get("skipped"):
        return False
    return True


def collect_dispatched_dose_pumps(
    *,
    enriched_actions: Sequence[Dict[str, Any]],
    action_results: Sequence[Dict[str, Any]],
    dose_config_components: Optional[Sequence[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Flat-path pumps that actually dispatched in this tick.

    Sequences are excluded here (deferred to COMPLETED — non-blocking executor).
    """
    non_seq_results = [
        r for r in action_results if isinstance(r, dict) and r.get("type") != "sequence"
    ]
    if not any(action_result_is_real_dispatch(r) for r in non_seq_results):
        return []

    dispatched_keys: set[tuple[Any, Any]] = set()
    for result in non_seq_results:
        if not action_result_is_real_dispatch(result):
            continue
        data = result.get("data") or {}
        if data.get("esp_id") is not None:
            dispatched_keys.add((data.get("esp_id"), data.get("gpio")))

    flat_actions = [
        a
        for a in enriched_actions
        if isinstance(a, dict) and a.get("type") in ("actuator_command", "actuator")
    ]
    pumps = extract_dose_pumps_from_actions(
        flat_actions, dose_config_components=dose_config_components
    )
    if dispatched_keys:
        pumps = [
            p for p in pumps if (p.get("esp_id"), p.get("gpio")) in dispatched_keys
        ]
    return pumps


async def ledger_has_logic_execution(
    session: AsyncSession,
    *,
    tank_id: uuid.UUID,
    logic_execution_id: uuid.UUID,
    limit: int = 200,
) -> bool:
    """Idempotency: skip if any component already carries this logic_execution_id."""
    repo = NutrientSolutionBatchRepository(session)
    entries = await repo.get_by_tank(tank_id, limit=limit)
    needle = str(logic_execution_id)
    for entry in entries:
        for component in entry.components or []:
            if not isinstance(component, dict):
                continue
            if str(component.get("logic_execution_id", "")) == needle:
                return True
    return False


async def record_logic_dose_to_ledger(
    session: AsyncSession,
    *,
    rule_id: uuid.UUID,
    logic_execution_id: uuid.UUID,
    pumps: Sequence[Dict[str, Any]],
    recipe_label: Optional[str] = None,
) -> Optional[Any]:
    """
    Persist one ``top_up_dose`` with one component row per pump (echte ml).

    Returns the batch response, or None when skipped (no pumps / no tank /
    already exists / empty volume).
    """
    if not pumps:
        return None

    positive = [p for p in pumps if float(p.get("dose_ml") or 0) > 0]
    if not positive:
        return None

    # Tank via first pump ESP; mixed tanks → warn and use first non-null.
    esp_repo = ESPRepository(session)
    actuator_repo = ActuatorRepository(session)
    tank_id: Optional[uuid.UUID] = None
    for pump in positive:
        esp_id = pump.get("esp_id")
        if not esp_id:
            continue
        device = await esp_repo.get_by_device_id(str(esp_id))
        if device is None:
            logger.warning(
                "AUT-1352: ESP %s not found — skipping pump GPIO%s for ledger",
                esp_id,
                pump.get("gpio"),
            )
            continue
        if device.tank_id is None:
            logger.warning(
                "AUT-1352 Q4: esp.tank_id null for %s — no ledger entry for this dose "
                "(rule_id=%s logic_execution_id=%s)",
                esp_id,
                rule_id,
                logic_execution_id,
            )
            return None
        if tank_id is None:
            tank_id = device.tank_id
        elif device.tank_id != tank_id:
            logger.warning(
                "AUT-1352: mixed tank_id across pumps (%s vs %s) — using first %s",
                tank_id,
                device.tank_id,
                tank_id,
            )

    if tank_id is None:
        logger.warning(
            "AUT-1352: no tank_id resolvable for logic dose "
            "(rule_id=%s logic_execution_id=%s)",
            rule_id,
            logic_execution_id,
        )
        return None

    if await ledger_has_logic_execution(
        session, tank_id=tank_id, logic_execution_id=logic_execution_id
    ):
        logger.info(
            "AUT-1352: skip ledger write — logic_execution_id=%s already present",
            logic_execution_id,
        )
        return None

    tank_service = TankService(session)
    prior_volume_l, _prior_ec = await tank_service._derive_prior_state(tank_id)

    components: List[Dict[str, Any]] = []
    total_ml = 0.0
    for pump in positive:
        dose_ml = float(pump["dose_ml"])
        total_ml += dose_ml
        esp_id = pump.get("esp_id")
        gpio = pump.get("gpio")
        name = str(pump.get("name") or f"GPIO{gpio}")

        # Prefer actuator_name as human label when present.
        if esp_id is not None and gpio is not None:
            esp = await esp_repo.get_by_device_id(str(esp_id))
            if esp is not None:
                act = await actuator_repo.get_by_esp_and_gpio(esp.id, int(gpio))
                if act is not None and act.actuator_name:
                    name = act.actuator_name

        role = pump.get("role")
        component: Dict[str, Any] = {
            "kind": "product",
            "name": name,
            "dose_ml_absolute": dose_ml,
            "esp_id": esp_id,
            "gpio": gpio,
            "rule_id": str(rule_id),
            "logic_execution_id": str(logic_execution_id),
        }
        if prior_volume_l is not None and prior_volume_l > 0:
            component["dose_ml_per_l"] = dose_ml / float(prior_volume_l)
        # else: dose_ml_absolute-only product form (schema AUT-1352)

        if role:
            component["role"] = role
            if role in PH_EC_EXCLUDED_ROLES:
                component["exclude_from_ec_composition"] = True

        components.append(component)

    if total_ml <= 0:
        return None

    label = recipe_label or f"logic:{rule_id}"
    # Tag whole entry when any pH component present (Salzrechner filter).
    if any(c.get("exclude_from_ec_composition") for c in components):
        if ":ph" not in label:
            label = f"{label}:ph"

    data = NutrientBatchCreate(
        entry_type="top_up_dose",
        volume_l=total_ml / 1000.0,
        components=components,
        acquisition_method="computed_runtime_x_rate",
        qualifier="approximate",
        recipe_label=label,
        ec_was_measured=False,
        ph_was_measured=False,
    )
    response = await tank_service.create_batch(tank_id, data)
    logger.info(
        "AUT-1352: ledger top_up_dose written id=%s tank=%s volume_l=%.6f "
        "pumps=%d logic_execution_id=%s",
        response.id,
        tank_id,
        response.volume_l,
        len(components),
        logic_execution_id,
    )
    return response
