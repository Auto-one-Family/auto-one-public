"""
AUT-1396 [M-3]: Observe-only measure-binding hooks on sequence lifecycle.

Reuses sequence_executor start/COMPLETED anchors (same places as auto-cal).
Never blocks, delays, or aborts sequence execution — failures are recorded only.
Auto-cal (``_aut1371_auto_cal`` / concentration_auto_cal) is untouched.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from ...core.logging_config import get_logger
from ...sensors.derived_measurements.registry import get_formula
from .measure_live_reader import (
    MeasureReadFailure,
    MeasureReadSuccess,
    read_live_sensor_for_measure,
)


logger = get_logger(__name__)

MEASURE_BINDINGS_ACTION_KEY = "_measure_bindings"
MEASURE_BINDING_RUNTIME_KEY = "measure_binding_runtime"
MEASURE_BINDING_RESULTS_KEY = "measure_binding_results"

# Hook → sample slot for wave-1 difference formula (t0 earliest, t1 latest).
_HOOK_SAMPLE_ORDER = ("on_start", "after_action", "after_settle", "on_complete")


def attach_measure_bindings_to_sequences(
    actions: List[dict],
    rule_metadata: Optional[Dict[str, Any]],
) -> List[dict]:
    """
    Copy ``rule_metadata.measure_bindings`` onto sequence actions (observe-only).

    Fast-path: no bindings → return the same list object (identity, zero work).
    """
    bindings = None
    if isinstance(rule_metadata, dict):
        bindings = rule_metadata.get("measure_bindings")
    if not bindings:
        return actions

    out: List[dict] = []
    changed = False
    for action in actions:
        if (
            isinstance(action, dict)
            and action.get("type") == "sequence"
            and MEASURE_BINDINGS_ACTION_KEY not in action
        ):
            rewritten = dict(action)
            rewritten[MEASURE_BINDINGS_ACTION_KEY] = deepcopy(bindings)
            out.append(rewritten)
            changed = True
        else:
            out.append(action)
    return out if changed else actions


def init_measure_binding_runtime(
    progress_metadata: Dict[str, Any], bindings: Sequence[Any]
) -> None:
    """Seed runtime state on sequence progress.metadata (start hook)."""
    if not bindings:
        return
    by_index: Dict[str, Dict[str, Any]] = {}
    for i, binding in enumerate(bindings):
        if not isinstance(binding, dict):
            continue
        by_index[str(i)] = {
            "binding": binding,
            "samples": {},
            "status": "pending",
            "error": None,
            "derived_value": None,
            "output_target": binding.get("output_target"),
            "formula_id": binding.get("formula_id"),
        }
    progress_metadata[MEASURE_BINDING_RUNTIME_KEY] = {"by_index": by_index}
    progress_metadata.setdefault(MEASURE_BINDING_RESULTS_KEY, [])


async def run_measure_binding_hook(
    progress_metadata: Dict[str, Any],
    *,
    hook: str,
    session: Any = None,
) -> None:
    """
    Process all bindings that list ``hook``. Observe-only — never raises to caller.

    Missing/stale sensor → mark that binding failed; do not touch sequence status.
    """
    try:
        runtime = progress_metadata.get(MEASURE_BINDING_RUNTIME_KEY)
        if not isinstance(runtime, dict):
            return
        by_index = runtime.get("by_index")
        if not isinstance(by_index, dict) or not by_index:
            return

        async def _process(active_session: Any) -> None:
            for idx, state in by_index.items():
                if not isinstance(state, dict):
                    continue
                if state.get("status") == "failed":
                    continue
                binding = state.get("binding") or {}
                hooks = binding.get("hooks") or []
                if hook not in hooks:
                    continue
                await _sample_binding_at_hook(
                    active_session,
                    state,
                    binding=binding,
                    hook=hook,
                    binding_index=idx,
                )
                await _maybe_finalize_binding(state, binding_index=idx)

        if session is not None:
            await _process(session)
        else:
            from ...db.session import get_session

            async for active_session in get_session():
                await _process(active_session)
                break

        _publish_results(progress_metadata)
    except Exception as err:
        # Absolute fail-open: never propagate into sequence control flow.
        logger.error(
            "AUT-1396: measure-binding hook=%s failed (observe-only): %s",
            hook,
            err,
            exc_info=True,
        )


async def _sample_binding_at_hook(
    session: Any,
    state: Dict[str, Any],
    *,
    binding: Dict[str, Any],
    hook: str,
    binding_index: str,
) -> None:
    samples = state.setdefault("samples", {})
    if hook in samples:
        return

    refs = binding.get("sensor_refs") or []
    if not refs:
        _mark_failed(state, "Messung nicht möglich: sensor_refs fehlt")
        return

    # Wave-1: one primary sensor ref (first); multi-ref formulas later.
    ref = refs[0]
    if not isinstance(ref, dict):
        _mark_failed(state, "Messung nicht möglich: ungültige sensor_ref")
        return

    try:
        result = await read_live_sensor_for_measure(
            session,
            esp_id=str(ref.get("esp_id") or ""),
            gpio=int(ref["gpio"]),
            sensor_type=ref.get("sensor_type"),
        )
    except Exception as err:
        _mark_failed(
            state,
            f"Messung nicht möglich: Lese-Fehler ({err})",
        )
        logger.error(
            "AUT-1396: live read exception binding=%s hook=%s: %s",
            binding_index,
            hook,
            err,
            exc_info=True,
        )
        return

    if isinstance(result, MeasureReadFailure) or not getattr(result, "ok", False):
        reason = getattr(result, "reason", "missing")
        _mark_failed(
            state,
            f"Messung nicht möglich: Sensor-Wert fehlt/veraltet ({reason})",
        )
        samples[hook] = {
            "ok": False,
            "reason": reason,
            "at": datetime.now(timezone.utc).isoformat(),
        }
        return

    assert isinstance(result, MeasureReadSuccess)
    samples[hook] = {
        "ok": True,
        "value": result.value,
        "age_seconds": result.age_seconds,
        "sensor_type": result.sensor_type,
        "at": datetime.now(timezone.utc).isoformat(),
    }


async def _maybe_finalize_binding(state: Dict[str, Any], *, binding_index: str) -> None:
    if state.get("status") in ("ok", "failed"):
        return
    binding = state.get("binding") or {}
    hooks: List[str] = list(binding.get("hooks") or [])
    if not hooks:
        _mark_failed(state, "Messung nicht möglich: hooks fehlt")
        return

    samples = state.get("samples") or {}
    # Wait until every configured hook has a sample attempt.
    if any(h not in samples for h in hooks):
        return

    if any(not (samples.get(h) or {}).get("ok") for h in hooks):
        if state.get("status") != "failed":
            _mark_failed(state, "Messung nicht möglich: Sensor-Wert fehlt/veraltet")
        return

    ordered = [h for h in _HOOK_SAMPLE_ORDER if h in hooks]
    if len(ordered) < 2:
        # Single-hook binding: store last sample as derived passthrough (no formula).
        last = samples[ordered[0]]["value"] if ordered else None
        state["status"] = "ok"
        state["derived_value"] = last
        state["error"] = None
        return

    t0 = samples[ordered[0]]["value"]
    t1 = samples[ordered[-1]]["value"]
    formula_id = binding.get("formula_id")
    formula = get_formula(str(formula_id)) if formula_id else None
    if formula is None:
        _mark_failed(state, f"Messung nicht möglich: unbekannte formula_id={formula_id}")
        return

    try:
        derived = formula(t0, t1, binding.get("formula_params") or {})
    except Exception as err:
        _mark_failed(state, f"Messung nicht möglich: Formel-Fehler ({err})")
        logger.error(
            "AUT-1396: formula failed binding=%s: %s",
            binding_index,
            err,
            exc_info=True,
        )
        return

    if derived is None:
        _mark_failed(state, "Messung nicht möglich: Formel lieferte keinen Wert")
        return

    state["status"] = "ok"
    state["derived_value"] = derived
    state["error"] = None


def _mark_failed(state: Dict[str, Any], message: str) -> None:
    state["status"] = "failed"
    state["error"] = message
    state["derived_value"] = None


def _publish_results(progress_metadata: Dict[str, Any]) -> None:
    runtime = progress_metadata.get(MEASURE_BINDING_RUNTIME_KEY) or {}
    by_index = runtime.get("by_index") or {}
    results: List[Dict[str, Any]] = []
    ledger_entries: List[Dict[str, Any]] = []
    for idx, state in by_index.items():
        if not isinstance(state, dict):
            continue
        if state.get("status") not in ("ok", "failed"):
            continue
        entry = {
            "binding_index": int(idx) if str(idx).isdigit() else idx,
            "status": state.get("status"),
            "error": state.get("error"),
            "derived_value": state.get("derived_value"),
            "formula_id": state.get("formula_id"),
            "output_target": state.get("output_target"),
            "samples": state.get("samples") or {},
        }
        results.append(entry)
        if state.get("output_target") == "ledger":
            ledger_entries.append(entry)

    progress_metadata[MEASURE_BINDING_RESULTS_KEY] = results
    if ledger_entries:
        # Wave-1: persist ledger-bound results in execution metadata for M-6;
        # no new ledger table / no dose-ledger side effects.
        progress_metadata["measure_binding_ledger_entries"] = ledger_entries
