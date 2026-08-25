"""
Plan Setpoint Resolver (AUT-1233 / Welle 5 T3)

Read-at-tick resolver that lets a CrossESPLogic rule read the currently
planned setpoint from plan_segments (T2, AUT-1232) — but ONLY for rules that
opted in via `follows_plan` (T2 opt-in flag). Non-subscribing rules never
call `resolve_effective_setpoint()` at all — the caller in logic_engine.py
checks `rule.follows_plan` before importing/calling anything here, so this
module never touches the database for the vast majority of rules.

Option A (Read-at-tick), NOT Option B (Push-at-boundary):
- No writeback into CrossESPLogic / rule configuration. Ever.
- Every evaluation of a subscribing rule re-resolves "now" fresh; nothing is
  cached across ticks beyond the in-request ResolveResult.
- Every evaluation of a subscribing rule (whether resolved from a segment or
  falling back to its own static value) is written to `applied_setpoint_logs`
  (T2 model) via `log_applied_setpoint()` — this IS the historical record,
  not a second copy of the setpoint.

No chemistry/dosing math lives here. This module only produces a target
NUMBER (or leaves the rule's own number untouched via static_fallback);
Ist/Soll/Volumen dose_ml computation stays entirely in
LogicEngine._compute_chemistry_dose_ml() (AUT-1112), which is not modified.

measure -> sensor_type mapping: plan_segment.PLAN_MEASURES are named
"target_<sensor_type>" (target_ec, target_ph, target_temperature,
target_humidity, target_co2) — matching the lowercase SENSOR_TYPE_* constants
in core/constants.py. "light_regime" / "recipe_ref" are non-numeric plan
measures and are intentionally not mapped (no matching sensor_type; the
resolver still resolves plan_segment.value for a rule subscribed to one of
these, but condition/dose_config substitution never applies to them since
there is no numeric sensor threshold to replace).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logging_config import get_logger
from ...db.repositories.applied_setpoint_log_repo import AppliedSetpointLogRepository
from ...db.repositories.plan_segment_repo import PlanSegmentRepository

logger = get_logger(__name__)

_MEASURE_PREFIX = "target_"


def measure_to_sensor_type(measure: Optional[str]) -> Optional[str]:
    """Map a plan measure (e.g. 'target_ec') to its matching sensor_type ('ec').

    Returns None for non-numeric measures (light_regime, recipe_ref) or when
    measure is unset — callers must treat None as "no condition/dose_config
    substitution possible for this measure".
    """
    if not measure or not measure.startswith(_MEASURE_PREFIX):
        return None
    sensor_type = measure[len(_MEASURE_PREFIX) :]
    return sensor_type or None


@dataclass
class ResolveResult:
    """Effective setpoint for one rule at one evaluation tick.

    Attributes:
        value: The value to apply. segment.value when origin == "plan_segment",
            the rule's own static_value when origin == "static_fallback".
            None only when neither a covering segment nor a determinable
            static value exists (caller must skip substitution AND logging
            in that edge case — never invent a value).
        origin: "plan_segment" | "static_fallback"
        segment_id: PlanSegment.id when origin == "plan_segment", else None
        static_value_source: Where static_value came from (for observability
            only, e.g. "dose_config.target_value" or "trigger_conditions.value");
            None when origin == "plan_segment" or when no static value existed.
    """

    value: Optional[float]
    origin: str
    segment_id: Optional[uuid.UUID] = None
    static_value_source: Optional[str] = None


# Canonical family name from measure_to_sensor_type → live sensor_type aliases.
# EC/pH already match 1:1 (ec/ph). Temperature/humidity live as sht31_*.
# No new sensor type — follows_plan substitution must hit SHT31 rules (AUT-1536).
_MEASURE_SENSOR_TYPE_ALIASES: dict[str, frozenset[str]] = {
    "temperature": frozenset({"temperature", "sht31_temp"}),
    "humidity": frozenset({"humidity", "sht31_humidity"}),
}


def _condition_sensor_type_matches(condition: dict, sensor_type: str) -> bool:
    cond_sensor_type = condition.get("sensor_type")
    if not cond_sensor_type:
        return False
    cond = str(cond_sensor_type).lower()
    canonical = sensor_type.lower()
    aliases = _MEASURE_SENSOR_TYPE_ALIASES.get(canonical)
    if aliases is not None:
        return cond in aliases
    return cond == canonical


def _condition_reference_value(condition: dict) -> Optional[float]:
    """Best-effort single representative numeric value for a condition leaf.

    sensor_threshold/sensor: condition["value"], or the midpoint of
    min/max for operator == "between".
    hysteresis: the OFF-side threshold (deactivate_below / deactivate_above) —
    that is the configured setpoint; the activate_* edge is only the one-sided
    Totband on the wrong side of Soll.
    """
    cond_type = condition.get("type")
    if cond_type in ("sensor_threshold", "sensor"):
        if condition.get("operator") == "between":
            min_v, max_v = condition.get("min"), condition.get("max")
            if min_v is None or max_v is None:
                return None
            try:
                return (float(min_v) + float(max_v)) / 2.0
            except (TypeError, ValueError):
                return None
        value = condition.get("value")
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    if cond_type == "hysteresis":
        # Cooling: Aus = deactivate_below (= Soll). Heating: Aus = deactivate_above.
        for off_key in ("deactivate_below", "deactivate_above"):
            off_v = condition.get(off_key)
            if off_v is not None:
                try:
                    return float(off_v)
                except (TypeError, ValueError):
                    continue
    return None


def _find_first_matching_value(conditions: Any, sensor_type: str) -> Optional[float]:
    """Recursively find the first condition leaf whose sensor_type matches,
    returning its representative numeric value (see _condition_reference_value).
    """
    if isinstance(conditions, list):
        for item in conditions:
            found = _find_first_matching_value(item, sensor_type)
            if found is not None:
                return found
        return None
    if isinstance(conditions, dict):
        if "logic" in conditions and "conditions" in conditions:
            return _find_first_matching_value(conditions["conditions"], sensor_type)
        if _condition_sensor_type_matches(conditions, sensor_type):
            return _condition_reference_value(conditions)
        return None
    return None


def _apply_value_to_condition(condition: dict, resolved_value: float) -> dict:
    """Return a copy of ``condition`` with its threshold field(s) shifted to
    ``resolved_value``. Caller has already verified sensor_type match.

    - sensor_threshold/sensor, operator != "between": condition["value"] is
      replaced directly.
    - sensor_threshold/sensor, operator == "between": min/max are recentred
      on resolved_value, preserving the configured band width.
    - hysteresis: one-sided Totband — OFF threshold locks to resolved_value
      (Soll), ON threshold keeps the configured gap on the wrong side only.
      Cooling (activate_above/deactivate_below): Aus = Soll, Ein = Soll + gap.
      Heating (activate_below/deactivate_above): Aus = Soll, Ein = Soll - gap.
    """
    new_condition = dict(condition)
    cond_type = condition.get("type")

    if cond_type in ("sensor_threshold", "sensor"):
        if condition.get("operator") == "between":
            min_v, max_v = condition.get("min"), condition.get("max")
            try:
                min_v, max_v = float(min_v), float(max_v)
            except (TypeError, ValueError):
                return new_condition
            half_width = abs(max_v - min_v) / 2.0
            new_condition["min"] = resolved_value - half_width
            new_condition["max"] = resolved_value + half_width
        else:
            new_condition["value"] = resolved_value
        return new_condition

    if cond_type == "hysteresis":
        for a_key, b_key in (
            ("activate_above", "deactivate_below"),
            ("activate_below", "deactivate_above"),
        ):
            a, b = condition.get(a_key), condition.get(b_key)
            if a is not None and b is not None:
                try:
                    a, b = float(a), float(b)
                except (TypeError, ValueError):
                    continue
                gap = abs(a - b)
                if a_key == "activate_above":
                    # pH-Minus / Kühlung: kein Totband unter Soll
                    new_condition[b_key] = resolved_value
                    new_condition[a_key] = resolved_value + gap
                else:
                    # pH-Plus / Heizung: kein Totband über Soll
                    new_condition[b_key] = resolved_value
                    new_condition[a_key] = resolved_value - gap
                break
        return new_condition

    return new_condition


def apply_resolved_value_to_conditions(
    conditions: Any, sensor_type: str, resolved_value: float
) -> Any:
    """Deep-copy ``conditions`` (dict, list, or compound {'logic','conditions'})
    and replace the threshold field(s) of any leaf condition whose
    sensor_type matches ``sensor_type`` with ``resolved_value``. Leaves that
    don't match are deep-copied unchanged. Never mutates the input — caller
    (LogicEngine._evaluate_rule) passes the returned copy to
    _check_conditions(), the original rule.trigger_conditions stays intact
    in the DB (no writeback, AUT-1233 Fix-Philosophie).
    """
    if isinstance(conditions, list):
        return [
            apply_resolved_value_to_conditions(item, sensor_type, resolved_value)
            for item in conditions
        ]
    if isinstance(conditions, dict):
        if "logic" in conditions and "conditions" in conditions:
            return {
                **conditions,
                "conditions": apply_resolved_value_to_conditions(
                    conditions["conditions"], sensor_type, resolved_value
                ),
            }
        if _condition_sensor_type_matches(conditions, sensor_type):
            return _apply_value_to_condition(conditions, resolved_value)
        return dict(conditions)
    return conditions


def extract_static_setpoint(rule) -> tuple[Optional[float], Optional[str]]:
    """Best-effort extraction of a subscribing rule's OWN static setpoint —
    used as the value returned when no plan_segment covers "now" (Given 3),
    and as the audit value logged for that tick's applied_setpoint_logs row.

    Lookup order (first hit wins):
    1. rule.rule_metadata["dose_config"]["target_value"] — chemistry rules
       (AUT-1112) carry their Soll-value here.
    2. First trigger_conditions leaf whose sensor_type matches
       measure_to_sensor_type(rule.plan_measure).

    Returns:
        (value, source) — source documents the origin for observability
        only ("dose_config.target_value" | "trigger_conditions.value");
        (None, None) when no static value could be determined at all.
    """
    dose_config = (getattr(rule, "rule_metadata", None) or {}).get("dose_config")
    if dose_config:
        target = dose_config.get("target_value")
        if target is not None:
            try:
                return float(target), "dose_config.target_value"
            except (TypeError, ValueError):
                pass

    sensor_type = measure_to_sensor_type(getattr(rule, "plan_measure", None))
    if sensor_type:
        found = _find_first_matching_value(getattr(rule, "trigger_conditions", None), sensor_type)
        if found is not None:
            return found, "trigger_conditions.value"

    return None, None


async def resolve_effective_setpoint(
    rule,
    *,
    session: AsyncSession,
    static_value: Optional[float] = None,
    static_value_source: Optional[str] = None,
    at: Optional[datetime] = None,
) -> Optional[ResolveResult]:
    """
    Resolve the effective setpoint for ``rule`` at ``at`` (default: now).

    Opt-in only (AUT-1233 Fix-Philosophie): returns None IMMEDIATELY — no
    query against plan_segments — when ``rule.follows_plan`` is falsy. This
    is the mandatory free fast path for the overwhelming majority of rules
    (Given 2: bit-identical behaviour, zero extra DB access).

    When ``rule.follows_plan`` is True:
    - queries PlanSegmentRepository.resolve_at() for the rule's
      zone/subzone x domain x measure (from the T2 plan_* fields);
    - a covering segment wins → ResolveResult(value=segment.value,
      origin="plan_segment", segment_id=segment.id) (Given 1);
    - no covering segment → ResolveResult(value=static_value,
      origin="static_fallback") — never a failure, never None value when
      static_value was supplied by the caller (Given 3);
    - any DB error resolving the segment is fail-open: logged, then treated
      exactly like "no covering segment" (static fallback) — a plan_segment
      outage must never stop a rule from dosing/regulating with its own
      static value.

    Args:
        rule: CrossESPLogic instance (needs follows_plan, plan_zone_id,
            plan_domain, plan_measure, plan_subzone_config_id)
        session: AsyncSession for the plan_segment lookup
        static_value: The rule's own configured value to fall back to
            (see extract_static_setpoint()); may be None if undeterminable
        static_value_source: Where static_value came from (observability)
        at: Evaluation timestamp; defaults to now (UTC)

    Returns:
        None when the rule does not subscribe (no DB access at all).
        ResolveResult otherwise — .value is None only if static_value was
        also None (caller must skip substitution/logging in that edge case).
    """
    if not getattr(rule, "follows_plan", False):
        return None

    effective_at = at or datetime.now(timezone.utc)

    plan_zone_id = getattr(rule, "plan_zone_id", None)
    plan_domain = getattr(rule, "plan_domain", None)
    plan_measure = getattr(rule, "plan_measure", None)

    if not plan_zone_id or not plan_domain or not plan_measure:
        # Subscribed but incompletely configured — never fail the rule;
        # treat exactly like "no covering segment".
        logger.warning(
            "Rule %s: follows_plan=True but incomplete plan_* fields "
            "(zone_id=%s, domain=%s, measure=%s) — static fallback",
            getattr(rule, "rule_name", getattr(rule, "id", "?")),
            plan_zone_id,
            plan_domain,
            plan_measure,
        )
        return ResolveResult(
            value=static_value, origin="static_fallback", static_value_source=static_value_source
        )

    try:
        repo = PlanSegmentRepository(session)
        segment = await repo.resolve_at(
            zone_id=plan_zone_id,
            domain=plan_domain,
            measure=plan_measure,
            at=effective_at,
            subzone_config_id=getattr(rule, "plan_subzone_config_id", None),
        )
    except Exception as e:
        # Fail-open: a plan_segment DB hiccup must never kill/deactivate the rule.
        logger.error(
            "Rule %s: plan_segment lookup failed, using static fallback — %s",
            getattr(rule, "rule_name", getattr(rule, "id", "?")),
            e,
            exc_info=True,
        )
        return ResolveResult(
            value=static_value, origin="static_fallback", static_value_source=static_value_source
        )

    if segment is not None and segment.value is not None:
        return ResolveResult(value=segment.value, origin="plan_segment", segment_id=segment.id)

    return ResolveResult(
        value=static_value, origin="static_fallback", static_value_source=static_value_source
    )


async def log_applied_setpoint(
    rule,
    resolved: ResolveResult,
    session: AsyncSession,
    effective_at: datetime,
) -> None:
    """
    Write one immutable applied_setpoint_logs row (T2 model) for a
    subscribing rule's evaluation tick — regardless of whether the value
    came from a plan_segment or the rule's own static fallback (DoD:
    "unabhängig davon, ob der Wert aus einem Plan-Segment oder aus dem
    statischen Fallback stammt"). Never called for non-subscribing rules
    (caller-side follows_plan gate — see resolve_effective_setpoint()).

    Fail-open: any DB error here is logged and swallowed. An audit-log
    write failure must never abort rule evaluation (matches the
    fire-and-forget error handling used elsewhere in LogicEngine, e.g.
    HysteresisConditionEvaluator._persist_state()).

    Commits immediately (independent of the rest of the rule's own
    transaction boundaries) so this row survives even when the rule's
    evaluation later returns early without its own explicit commit (e.g.
    conditions not met at logic_engine.py:685 — no History-Eintrag there,
    but the setpoint audit row must still persist per DoD).
    """
    if resolved.value is None:
        logger.warning(
            "Rule %s: skipping applied_setpoint_log — no concrete value "
            "(neither plan_segment nor determinable static value) for %s/%s",
            getattr(rule, "rule_name", getattr(rule, "id", "?")),
            getattr(rule, "plan_domain", None),
            getattr(rule, "plan_measure", None),
        )
        return

    try:
        repo = AppliedSetpointLogRepository(session)
        await repo.create(
            zone_id=rule.plan_zone_id,
            subzone_config_id=rule.plan_subzone_config_id,
            domain=rule.plan_domain,
            measure=rule.plan_measure,
            applied_value=resolved.value,
            effective_at=effective_at,
            rule_id=rule.id,
            segment_id=resolved.segment_id,
            origin=resolved.origin,
        )
        await session.commit()
    except Exception as e:
        logger.error(
            "Rule %s: failed to write applied_setpoint_log — %s",
            getattr(rule, "rule_name", getattr(rule, "id", "?")),
            e,
            exc_info=True,
        )
        try:
            await session.rollback()
        except Exception:
            logger.error(
                "Rule %s: rollback after applied_setpoint_log failure also failed",
                getattr(rule, "rule_name", getattr(rule, "id", "?")),
                exc_info=True,
            )
