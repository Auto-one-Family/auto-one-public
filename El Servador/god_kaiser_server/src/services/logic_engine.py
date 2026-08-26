"""
Cross-ESP Automation Engine (Background Task)

Evaluates logic rules in background, triggers actuator actions based on sensor conditions.
"""

import asyncio
import math
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence

from ..core.logging_config import get_logger
from ..core.metrics import (
    increment_logic_error,
    increment_logic_dispatch_skipped_config_pending,
    increment_logic_dispatch_skipped_offline,
    increment_safety_trigger,
)
from ..schemas.notification import NotificationCreate
from sqlalchemy import select

from ..db.repositories import LogicRepository, ESPRepository, SensorRepository, ActuatorRepository
from ..sensors.dose_calculators.active.linear_dose_calculator import calculate_dose_ml
from ..sensors.dose_calculators.active.volume_share import (
    compute_ratio_shares_from_volume,
)
from ..db.session import get_session
from ..websocket.manager import WebSocketManager
from .actuator_service import ActuatorService
from .concentration_auto_cal import enrich_sequences_for_auto_cal
from .logic_dose_ledger import (
    collect_dispatched_dose_pumps,
    extract_dose_pumps_from_actions,
    record_logic_dose_to_ledger,
)
from .state_adoption_service import get_state_adoption_service
from .notification_router import NotificationRouter
from .logic.actions import (
    ActuatorActionExecutor,
    BaseActionExecutor,
    DelayActionExecutor,
    DiagnosticsActionExecutor,
    NotificationActionExecutor,
    SequenceActionExecutor,
)
from .logic.actions.plugin_executor import PluginActionExecutor
from .logic.conditions import (
    BaseConditionEvaluator,
    CompoundConditionEvaluator,
    DiagnosticsConditionEvaluator,
    HysteresisConditionEvaluator,
    MetadataFilterEvaluator,
    NotRunningConditionEvaluator,
    SensorConditionEvaluator,
    SensorDiffConditionEvaluator,
    TimeConditionEvaluator,
)
from .logic.plan_setpoint_resolver import (
    ResolveResult,
    apply_resolved_value_to_conditions,
    extract_static_setpoint,
    log_applied_setpoint,
    measure_to_sensor_type,
    resolve_effective_setpoint,
)

logger = get_logger(__name__)

_OFFLINE_BACKOFF_SECONDS = (
    30  # Skip offline-ESP actuator rules for 30s after first failure (safety net)
)
_CONFIG_PENDING_BACKOFF_SECONDS = (
    15  # Skip config-pending-ESP actuator rules for 15s (shorter: state transitions fast)
)


class LogicEngine:
    """
    Cross-ESP Automation Engine (Background Task).

    Evaluates logic rules when sensor data arrives,
    triggers actuator actions based on conditions.
    """

    def __init__(
        self,
        logic_repo: LogicRepository,
        actuator_service: ActuatorService,
        websocket_manager: WebSocketManager,
        condition_evaluators: Optional[List[BaseConditionEvaluator]] = None,
        action_executors: Optional[List[BaseActionExecutor]] = None,
        conflict_manager=None,
        rate_limiter=None,
        session_factory=None,
    ):
        """
        Initialize Logic Engine.

        Args:
            logic_repo: LogicRepository instance
            actuator_service: ActuatorService instance
            websocket_manager: WebSocketManager instance
            condition_evaluators: Optional list of condition evaluators (creates defaults if None)
            action_executors: Optional list of action executors (creates defaults if None)
            conflict_manager: Optional ConflictManager instance (creates default if None)
            rate_limiter: Optional RateLimiter instance (creates default if None)
        """
        self.logic_repo = logic_repo
        self.actuator_service = actuator_service
        self.websocket_manager = websocket_manager
        self._running = False
        self._task: Optional[asyncio.Task] = None

        # AUT-1245: SequenceActionExecutor is created before condition wiring so
        # NotRunningConditionEvaluator can observe the same in-memory instance.
        shared_seq_exec: Optional[SequenceActionExecutor] = None

        # Setup condition evaluators
        if condition_evaluators is None:
            shared_seq_exec = SequenceActionExecutor()
            sensor_eval = SensorConditionEvaluator()
            sensor_diff_eval = SensorDiffConditionEvaluator()
            time_eval = TimeConditionEvaluator()
            hysteresis_eval = HysteresisConditionEvaluator()
            diagnostics_eval = DiagnosticsConditionEvaluator(session_factory=session_factory)
            not_running_eval = NotRunningConditionEvaluator(
                sequence_executor=shared_seq_exec,
                session_factory=session_factory,
            )
            metadata_filter_eval = MetadataFilterEvaluator()
            compound_eval = CompoundConditionEvaluator(
                [
                    sensor_eval,
                    sensor_diff_eval,
                    time_eval,
                    hysteresis_eval,
                    diagnostics_eval,
                    not_running_eval,
                    metadata_filter_eval,
                ]
            )
            self.condition_evaluators = [
                sensor_eval,
                sensor_diff_eval,
                time_eval,
                hysteresis_eval,
                diagnostics_eval,
                not_running_eval,
                metadata_filter_eval,
                compound_eval,
            ]
        else:
            self.condition_evaluators = condition_evaluators

        # Setup action executors
        if action_executors is None:
            actuator_exec = ActuatorActionExecutor(actuator_service)
            delay_exec = DelayActionExecutor()
            notification_exec = NotificationActionExecutor()
            plugin_exec = PluginActionExecutor(session_factory=session_factory)
            diag_action_exec = DiagnosticsActionExecutor(session_factory=session_factory)
            seq_exec = shared_seq_exec or SequenceActionExecutor()
            self.action_executors = [
                actuator_exec,
                delay_exec,
                notification_exec,
                plugin_exec,
                diag_action_exec,
                seq_exec,
            ]
            seq_exec.set_action_executors(self.action_executors)
        else:
            self.action_executors = action_executors

        # Setup safety components
        if conflict_manager is None:
            from .logic.safety.conflict_manager import ConflictManager

            self.conflict_manager = ConflictManager(websocket_manager=websocket_manager)
        else:
            self.conflict_manager = conflict_manager

        if rate_limiter is None:
            from .logic.safety.rate_limiter import RateLimiter

            self.rate_limiter = RateLimiter(logic_repo=logic_repo)
        else:
            self.rate_limiter = rate_limiter

        # Backoff cache: esp_id -> skip_until timestamp (avoids repeated DB queries for offline ESPs)
        self._offline_esp_skip: dict[str, datetime] = {}
        # AUT-60: Separate backoff for CONFIG_PENDING_AFTER_RESET ESPs
        self._config_pending_skip: dict[str, datetime] = {}

    async def start(self) -> None:
        """
        Start background evaluation task.

        Should be called on application startup.
        """
        if self._running:
            logger.warning("Logic Engine is already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._evaluation_loop())
        logger.info("Logic Engine started")

    async def stop(self) -> None:
        """
        Stop background task.

        Should be called on application shutdown.
        """
        if not self._running:
            return

        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("Logic Engine stopped")

    def invalidate_offline_backoff(self, esp_id: str) -> None:
        """Clear offline backoff cache for an ESP after confirmed reconnect.

        Called by heartbeat_handler after update_status("online") is committed.
        Removes the esp_id from _offline_esp_skip so the next action trigger
        proceeds immediately without waiting for the backoff TTL to expire.

        Both the modern path (_execute_actions) and the legacy path
        (_execute_action_legacy) share the same _offline_esp_skip dict,
        so a single pop() covers both.

        Args:
            esp_id: ESP device ID to clear from backoff cache
        """
        removed = self._offline_esp_skip.pop(esp_id, None)
        if removed:
            logger.info(
                "Offline backoff cache cleared for %s (was set until %s)",
                esp_id,
                removed.isoformat(),
            )

    def invalidate_config_pending_backoff(self, esp_id: str) -> None:
        """Clear config_pending backoff cache when ESP exits CONFIG_PENDING_AFTER_RESET.

        Called by heartbeat_handler when system_state transitions away from
        CONFIG_PENDING_AFTER_RESET (e.g. to OPERATIONAL).

        Args:
            esp_id: ESP device ID to clear from backoff cache
        """
        removed = self._config_pending_skip.pop(esp_id, None)
        if removed:
            logger.info(
                "Config pending backoff cache cleared for %s (was set until %s)",
                esp_id,
                removed.isoformat(),
            )

    async def evaluate_sensor_data(
        self,
        esp_id: str,
        gpio: int,
        sensor_type: str,
        value: float,
        zone_id: Optional[str] = None,
        subzone_id: Optional[str] = None,
        quality: Optional[str] = None,
    ) -> None:
        """
        Evaluate rules triggered by sensor data.

        Called by sensor_handler after sensor data is saved.
        This method is non-blocking and should be called via asyncio.create_task().

        Args:
            esp_id: ESP device ID
            gpio: GPIO pin number
            sensor_type: Sensor type (e.g., "temperature", "humidity")
            value: Sensor value
            zone_id: Zone ID at measurement time (Phase 0.1, for Phase 2.4 Subzone-Matching)
            subzone_id: Subzone ID at measurement time (Phase 0.1, for Phase 2.4 Subzone-Matching)
            quality: AUT-994 B2: Data quality flag (e.g. "critical" when the value fails
                SENSOR_PHYSICAL_LIMITS) — SensorConditionEvaluator refuses to dispatch on it.
        """
        try:
            # Get database session for this evaluation
            async for session in get_session():
                logic_repo = LogicRepository(session)

                # Find matching rules
                matching_rules = await logic_repo.get_rules_by_trigger_sensor(
                    esp_id=esp_id,
                    gpio=gpio,
                    sensor_type=sensor_type,
                )

                if not matching_rules:
                    logger.debug(
                        f"No matching rules for sensor: esp_id={esp_id}, "
                        f"gpio={gpio}, sensor_type={sensor_type}"
                    )
                    return

                # Prepare trigger data (Phase 0.1: zone_id/subzone_id for Phase 2.4 Subzone-Matching)
                trigger_data = {
                    "esp_id": esp_id,
                    "gpio": gpio,
                    "sensor_type": sensor_type,
                    "value": value,
                    "timestamp": int(time.time()),
                    "zone_id": zone_id,
                    "subzone_id": subzone_id,
                    "quality": quality,
                }

                # Evaluate each matching rule with batch-level lock tracking
                # Locks are held across the entire batch to enable ConflictManager
                # to block rules with larger priority values (lower conflict priority)
                # from overriding rules with smaller priority values (higher conflict priority)
                batch_locks = []
                try:
                    for rule in matching_rules:
                        await self._evaluate_rule(
                            rule, trigger_data, logic_repo, batch_locks=batch_locks
                        )
                finally:
                    # Release all locks at the end of the batch
                    for lock in batch_locks:
                        await self.conflict_manager.release_actuator(
                            esp_id=lock["esp_id"],
                            gpio=lock["gpio"],
                            rule_id=lock["rule_id"],
                        )

                break  # Exit after first session

        except Exception as e:
            logger.error(
                f"Error evaluating sensor data: {e}",
                exc_info=True,
            )

    async def evaluate_timer_triggered_rules(self) -> None:
        """
        Evaluate rules triggered by timer (time_window conditions).

        Should be called periodically by LogicScheduler.
        """
        try:
            # Get database session
            async for session in get_session():
                logic_repo = LogicRepository(session)

                # Get all enabled rules
                all_rules = await logic_repo.get_enabled_rules()

                # Filter rules with time_window conditions
                timer_rules = []
                for rule in all_rules:
                    # Use trigger_conditions (raw JSON) for type checking,
                    # NOT .conditions property which always wraps in list
                    raw_conditions = rule.trigger_conditions
                    has_time_condition = False

                    # Check if rule has time_window condition
                    if isinstance(raw_conditions, dict):
                        if raw_conditions.get("type") in ("time_window", "time"):
                            has_time_condition = True
                        elif raw_conditions.get("logic"):
                            # Compound condition - check sub-conditions
                            sub_conditions = raw_conditions.get("conditions", [])
                            for sub_cond in sub_conditions:
                                if sub_cond.get("type") in ("time_window", "time"):
                                    has_time_condition = True
                                    break
                    elif isinstance(raw_conditions, list):
                        for cond in raw_conditions:
                            if cond.get("type") in ("time_window", "time"):
                                has_time_condition = True
                                break

                    if has_time_condition:
                        timer_rules.append(rule)

                if not timer_rules:
                    logger.debug("No timer-triggered rules to evaluate")
                    return

                # Evaluate each timer rule with batch-level lock tracking
                batch_locks = []
                try:
                    for rule in timer_rules:
                        # Load latest sensor values so compound rules (time + sensor/hysteresis)
                        # can evaluate correctly in Phase 1.
                        sensor_values, offline_sensor_refs = (
                            await self._load_sensor_values_for_timer(rule, session)
                        )

                        # Build primary sensor_data from first available value so hysteresis
                        # evaluator can call _matches_sensor() and evaluate state transitions.
                        primary_sensor_data: dict = {}
                        if sensor_values:
                            first_val = next(iter(sensor_values.values()))
                            primary_sensor_data = {
                                "esp_id": first_val.get("esp_id"),
                                "gpio": first_val.get("gpio"),
                                "sensor_type": first_val.get("sensor_type"),
                                "value": first_val.get("value"),
                            }

                        # Fresh context per rule — prevents state bleed between rules and
                        # gives each evaluation the full sensor context it needs.
                        context = {
                            "current_time": datetime.now(timezone.utc),
                            "sensor_values": sensor_values,
                            "sensor_data": primary_sensor_data,
                            "_offline_sensor_refs": offline_sensor_refs,
                            "rule_id": str(rule.id),
                            "rule_name": rule.rule_name,
                            "condition_index": 0,
                        }

                        # Check if conditions are met (Phase 1 — now with sensor context)
                        conditions = rule.trigger_conditions
                        conditions_met = await self._check_conditions(
                            conditions, context, logic_operator=rule.logic_operator
                        )

                        # Prepare trigger data for timer-based execution
                        trigger_data = {
                            "type": "timer",
                            "timestamp": int(time.time()),
                            "rule_id": str(rule.id),
                        }

                        if conditions_met:
                            await self._evaluate_rule(
                                rule, trigger_data, logic_repo, batch_locks=batch_locks
                            )
                        else:
                            if offline_sensor_refs:
                                last_exec = await logic_repo.get_last_execution(rule.id)
                                if last_exec:
                                    hysteresis_eval = self._get_hysteresis_evaluator()
                                    if hysteresis_eval:
                                        active_keys = [
                                            key
                                            for key, state in list(hysteresis_eval._states.items())
                                            if key.startswith(f"{rule.id}:") and state.is_active
                                        ]
                                        for key in active_keys:
                                            hysteresis_eval.remove_state(key)
                                    off_actions = self._build_off_actions(rule.actions)
                                    if off_actions:
                                        await self._execute_actions(
                                            off_actions,
                                            {
                                                "type": "timer",
                                                "timestamp": int(time.time()),
                                                "rule_id": str(rule.id),
                                                "reason": "source_esp_offline",
                                            },
                                            rule.id,
                                            rule.rule_name,
                                            rule.priority,
                                            rule_is_critical=bool(getattr(rule, "is_critical", False)),
                                            session=session,
                                            batch_locks=batch_locks,
                                        )
                                        await session.commit()
                                        logger.warning(
                                            "Timer OFF: rule '%s' source ESP offline (%s), OFF sent",
                                            rule.rule_name,
                                            ", ".join(
                                                sorted(
                                                    {
                                                        str(ref.get("esp_id"))
                                                        for ref in offline_sensor_refs
                                                        if ref.get("esp_id")
                                                    }
                                                )
                                            ),
                                        )
                                        continue
                            # Pure time-window rule expired → send OFF if recently executed.
                            # Guard: only fire within 2× cooldown (or 120 s default) to
                            # avoid OFF spam on every 60-second tick for long-inactive rules.
                            last_exec = await logic_repo.get_last_execution(rule.id)
                            if last_exec:
                                time_since = (
                                    datetime.now(timezone.utc) - last_exec.timestamp
                                ).total_seconds()
                                cooldown_window = (
                                    rule.cooldown_seconds * 2 if rule.cooldown_seconds else 120
                                )
                                if time_since < cooldown_window:
                                    off_actions = self._build_off_actions(rule.actions)
                                    if off_actions:
                                        await self._execute_actions(
                                            off_actions,
                                            trigger_data,
                                            rule.id,
                                            rule.rule_name,
                                            rule.priority,
                                            rule_is_critical=bool(getattr(rule, "is_critical", False)),
                                            session=session,
                                            batch_locks=batch_locks,
                                        )
                                        await session.commit()
                                        logger.info(
                                            "Timer OFF: rule '%s' conditions_met=False, "
                                            "OFF sent (last execution %.0fs ago)",
                                            rule.rule_name,
                                            time_since,
                                        )
                finally:
                    for lock in batch_locks:
                        await self.conflict_manager.release_actuator(
                            esp_id=lock["esp_id"],
                            gpio=lock["gpio"],
                            rule_id=lock["rule_id"],
                        )

                break  # Exit after first session

        except Exception as e:
            logger.error(
                f"Error evaluating timer-triggered rules: {e}",
                exc_info=True,
            )

    async def trigger_reconnect_evaluation(self, esp_id: str) -> None:
        """Re-evaluate enabled rules whose actions target this ESP after MQTT reconnect.

        Uses ``type=reconnect`` in trigger_data so cooldown does not block on stale
        execution history from before LWT disconnect. Skips rules without fresh sensor
        context (same 5-minute staleness window as timer evaluation).

        Args:
            esp_id: Device ID that reconnected (must match action ``esp_id`` fields).
        """
        try:
            async for session in get_session():
                logic_repo = LogicRepository(session)
                all_rules = await logic_repo.get_enabled_rules()
                reconnect_rules = [
                    r for r in all_rules if esp_id in self._extract_target_esp_ids(r.actions)
                ]
                if not reconnect_rules:
                    logger.debug("Reconnect evaluation: no rules with actions on %s", esp_id)
                    return

                batch_locks: list = []
                try:
                    for rule in reconnect_rules:
                        sensor_values, _offline_sensor_refs = (
                            await self._load_sensor_values_for_timer(rule, session)
                        )
                        if not sensor_values:
                            logger.debug(
                                "Reconnect evaluation: skip %s (no fresh sensor context)",
                                rule.rule_name,
                            )
                            continue

                        first_val = next(iter(sensor_values.values()))
                        trigger_data = {
                            "type": "reconnect",
                            "esp_id": first_val.get("esp_id"),
                            "gpio": first_val.get("gpio"),
                            "sensor_type": first_val.get("sensor_type"),
                            "value": first_val.get("value"),
                            "timestamp": int(time.time()),
                        }

                        await self._evaluate_rule(
                            rule, trigger_data, logic_repo, batch_locks=batch_locks
                        )
                finally:
                    for lock in batch_locks:
                        await self.conflict_manager.release_actuator(
                            esp_id=lock["esp_id"],
                            gpio=lock["gpio"],
                            rule_id=lock["rule_id"],
                        )

                break

        except Exception as e:
            logger.error(
                "Error in reconnect evaluation for %s: %s",
                esp_id,
                e,
                exc_info=True,
            )

    async def _evaluate_rule(
        self,
        rule,
        trigger_data: dict,
        logic_repo: LogicRepository,
        batch_locks: list | None = None,
    ) -> None:
        """
        Evaluate a single rule.

        Args:
            rule: CrossESPLogic instance
            trigger_data: Sensor data that triggered the rule
            logic_repo: LogicRepository instance
        """
        # Concurrency: No engine-level lock by design.
        # ConflictManager (asyncio.Lock per esp:gpio) prevents concurrent actuator commands.
        # Cooldown checks have a ~10ms race window under burst load — acceptable for current scale.
        # Add engine-level lock only if rule evaluation rate exceeds ~100/s.
        start_time = time.time()
        rule_id_snapshot = getattr(rule, "id", None)
        rule_name_snapshot = str(getattr(rule, "rule_name", "unknown_rule"))
        trigger_snapshot = dict(trigger_data) if isinstance(trigger_data, dict) else {}
        actions_raw = getattr(rule, "actions", None) or []
        actions_snapshot = list(actions_raw) if isinstance(actions_raw, list) else []

        try:
            # Evaluate conditions first (needed for hysteresis deactivation path)
            sensor_values, offline_sensor_refs = await self._load_cross_sensor_values(
                rule.trigger_conditions, trigger_data, logic_repo.session
            )
            context = {
                "sensor_data": trigger_data,
                "sensor_values": sensor_values,
                "_offline_sensor_refs": offline_sensor_refs,
                "current_time": datetime.now(timezone.utc),
                "rule_id": str(rule.id),
                "rule_name": rule.rule_name,
                "condition_index": 0,
            }

            # AUT-1233 (Welle 5 T3): Read-at-tick plan setpoint resolution.
            # Opt-in only — resolve_effective_setpoint() returns None immediately
            # (no DB query against plan_segments) for the vast majority of rules
            # that never set follows_plan (T2). Non-subscribing rules fall through
            # to evaluate_conditions with rule.trigger_conditions unchanged, exactly
            # as before this issue (Given 2: bit-identical, zero extra DB access).
            resolved_setpoint: Optional[ResolveResult] = None
            evaluate_conditions = rule.trigger_conditions
            if rule.follows_plan:
                static_value, static_value_source = extract_static_setpoint(rule)
                resolved_setpoint = await resolve_effective_setpoint(
                    rule,
                    session=logic_repo.session,
                    static_value=static_value,
                    static_value_source=static_value_source,
                    at=context["current_time"],
                )
                if resolved_setpoint is not None:
                    if resolved_setpoint.value is not None:
                        sensor_type = measure_to_sensor_type(rule.plan_measure)
                        if sensor_type:
                            evaluate_conditions = apply_resolved_value_to_conditions(
                                rule.trigger_conditions, sensor_type, resolved_setpoint.value
                            )
                    # Historical application log — written for EVERY evaluation of a
                    # subscribing rule (plan_segment OR static_fallback origin), at the
                    # actual read point, independent of whether conditions later pass.
                    await log_applied_setpoint(
                        rule, resolved_setpoint, logic_repo.session, context["current_time"]
                    )

            # AUT-1317: per-action condition_refs need individual results.
            # Flat rules (no refs) keep a single _check_conditions call (D4 / wiring tests).
            has_routed_actions = self._rule_has_routed_actions(rule.actions)
            condition_results: Optional[List[bool]] = None
            if has_routed_actions:
                condition_results = await self._evaluate_individual_conditions(
                    evaluate_conditions, context
                )
                conditions_met = self._combine_condition_results(
                    condition_results, rule.logic_operator or "AND"
                )
            else:
                conditions_met = await self._check_conditions(
                    evaluate_conditions, context, logic_operator=rule.logic_operator
                )

            # Hysteresis deactivation: bypass cooldown (OFF must execute immediately).
            # AUT-1317: do NOT reuse this rule-wide path for routed rules — it would
            # force-OFF every actuator action (including geroutete ON). Routed safety
            # OFF uses action-level cooldown bypass instead.
            if (
                not conditions_met
                and context.get("_hysteresis_just_deactivated")
                and not has_routed_actions
            ):
                off_actions = []
                for action in rule.actions:
                    if action.get("type") in ("actuator_command", "actuator"):
                        off_actions.append(
                            {
                                **action,
                                "command": "OFF",
                                "value": 0.0,
                                "duration": 0,
                            }
                        )
                if off_actions:
                    logger.info(
                        f"Rule {rule.rule_name} hysteresis deactivated: "
                        f"sending OFF to {len(off_actions)} actuator(s)"
                    )
                    execution_result = await self._execute_actions(
                        off_actions,
                        trigger_data,
                        rule.id,
                        rule.rule_name,
                        rule.priority,
                        rule_is_critical=bool(getattr(rule, "is_critical", False)),
                        session=logic_repo.session,
                        batch_locks=batch_locks,
                    )
                    if not isinstance(execution_result, dict):
                        logger.error(
                            "Rule %s: _execute_actions returned non-dict type %s (coercing)",
                            rule_name_snapshot,
                            type(execution_result).__name__,
                        )
                        execution_result = {
                            "blocked_by_conflict": False,
                            "conflict_info": None,
                            "action_results": [],
                        }
                    execution_time_ms = int((time.time() - start_time) * 1000)
                    blocked_by_conflict = execution_result.get("blocked_by_conflict", False)
                    conflict_info = execution_result.get("conflict_info") or {}
                    conflict_message = conflict_info.get(
                        "message",
                        "Rule execution blocked due to actuator conflict",
                    )
                    await logic_repo.log_execution(
                        rule_id=rule.id,
                        trigger_data=trigger_data,
                        actions=off_actions,
                        success=not blocked_by_conflict,
                        execution_ms=execution_time_ms,
                        error_message=conflict_message if blocked_by_conflict else None,
                        metadata=(
                            {
                                "terminal_reason_code": "conflict_priority_lost",
                                "conflict_info": conflict_info,
                            }
                            if blocked_by_conflict
                            else None
                        ),
                        dose_ml=None,  # AO-5: OFF-Pfad = kein Volumen
                        flow_rate_ml_s_snapshot=None,  # AO-5
                    )
                    await logic_repo.session.commit()
                return

            # AUT-1317: select actions that pass their gate (flat = all under global).
            if has_routed_actions and condition_results is not None:
                actions_to_run = self._filter_actions_by_condition_gate(
                    rule.actions,
                    condition_results,
                    conditions_met,
                    rule.logic_operator or "AND",
                )
                should_early_exit = len(actions_to_run) == 0
            else:
                actions_to_run = list(rule.actions) if conditions_met else []
                should_early_exit = not conditions_met

            if should_early_exit:
                # AUT-41: structured warning when stale sensor data caused conditions to fail
                stale_reasons = context.get("_stale_reasons")
                if stale_reasons:
                    for reason in stale_reasons:
                        logger.warning(
                            "Rule '%s' condition not met due to stale sensor data: "
                            "sensor=%s:%s (%s), mode=%s, age=%.0fs, "
                            "freshness_limit=%.0fs (measurement_freshness_hours=%s)",
                            rule.rule_name,
                            reason.get("esp_id"),
                            reason.get("gpio"),
                            reason.get("sensor_type"),
                            reason.get("operating_mode"),
                            reason.get("age_seconds", 0),
                            reason.get("freshness_limit_seconds", 0),
                            reason.get("measurement_freshness_hours"),
                        )
                offline_sensor_refs = context.get("_offline_sensor_refs") or []
                if offline_sensor_refs:
                    logger.warning(
                        "Rule '%s' condition not met because referenced sensor ESP(s) are offline: %s",
                        rule.rule_name,
                        ", ".join(
                            sorted(
                                {
                                    str(ref.get("esp_id"))
                                    for ref in offline_sensor_refs
                                    if ref.get("esp_id")
                                }
                            )
                        ),
                    )
                    hysteresis_eval = self._get_hysteresis_evaluator()
                    if hysteresis_eval:
                        active_keys = [
                            key
                            for key, state in list(hysteresis_eval._states.items())
                            if key.startswith(f"{rule.id}:") and state.is_active
                        ]
                        if active_keys:
                            for key in active_keys:
                                hysteresis_eval.remove_state(key)
                            off_actions = self._build_off_actions(rule.actions)
                            if off_actions:
                                logger.info(
                                    "Rule %s: source ESP offline with %d active hysteresis state(s) -> sending OFF to %d actuator(s)",
                                    rule.rule_name,
                                    len(active_keys),
                                    len(off_actions),
                                )
                                await self._execute_actions(
                                    off_actions,
                                    {
                                        **trigger_data,
                                        "type": trigger_data.get("type", "sensor"),
                                        "reason": "source_esp_offline",
                                    },
                                    rule.id,
                                    rule.rule_name,
                                    rule.priority,
                                    rule_is_critical=bool(getattr(rule, "is_critical", False)),
                                    session=logic_repo.session,
                                    batch_locks=batch_locks,
                                )
                                await logic_repo.session.commit()
                                return
                else:
                    logger.debug(
                        f"Rule {rule.rule_name} conditions not met for trigger: {trigger_data}"
                    )
                return

            # Check cooldown (only for activation — prevents rapid ON-ON-ON).
            # AUT-1135 (A4): rule-update triggers only bypass cooldown when the update
            # actually changed conditions/actions (trigger_data["force"], set by
            # on_rule_updated()) — a save that only touches timer parameters must
            # respect the currently running cooldown.
            # Reconnect triggers bypass cooldown: LWT disconnect leaves stale execution history.
            # AUT-1317: safety-critical routed OFF bypasses cooldown on action level only.
            is_forced_bypass = bool(trigger_data.get("force"))
            is_reconnect_trigger = trigger_data.get("type") == "reconnect"
            if rule.cooldown_seconds and not is_forced_bypass and not is_reconnect_trigger:
                last_execution = await logic_repo.get_last_execution(rule.id)
                if last_execution:
                    time_since_last = datetime.now(timezone.utc) - last_execution.timestamp
                    if time_since_last.total_seconds() <= rule.cooldown_seconds:
                        remaining = int(rule.cooldown_seconds - time_since_last.total_seconds())
                        safety_off_actions = [
                            a
                            for a in actions_to_run
                            if self._is_safety_critical_routed_off(a)
                        ]
                        if safety_off_actions:
                            logger.info(
                                "Rule %s in cooldown but executing %d safety-critical "
                                "routed OFF action(s) (action-level bypass)",
                                rule.rule_name,
                                len(safety_off_actions),
                            )
                            actions_to_run = safety_off_actions
                        else:
                            logger.debug(
                                f"Rule {rule.rule_name} in cooldown: "
                                f"{time_since_last.total_seconds():.1f}s < {rule.cooldown_seconds}s"
                            )
                            # AUT-1020: write skip entry so rule.health batch can surface it (S5)
                            await logic_repo.log_execution(
                                rule_id=rule.id,
                                trigger_data={},
                                actions=[],
                                success=False,
                                execution_ms=0,
                                error_message=f"cooldown_active:{remaining}s",
                                metadata={
                                    "cooldown_seconds": rule.cooldown_seconds,
                                    "remaining_seconds": remaining,
                                    "consecutive_skip_count": 1,
                                },
                                is_skip=True,
                            )
                            await logic_repo.session.commit()
                            return

            # AUT-1115: Settle window after the last execution of a DIFFERENT rule
            # (e.g. EC-Verduennen waits after Nachfuellen) — same skip pattern as the
            # cooldown check above, just keyed on settle_after_rule_id instead of rule.id.
            if (
                rule.settle_after_rule_id
                and rule.settle_seconds
                and not is_forced_bypass
                and not is_reconnect_trigger
            ):
                settle_last_execution = await logic_repo.get_last_execution(
                    rule.settle_after_rule_id
                )
                if settle_last_execution:
                    time_since_settle = (
                        datetime.now(timezone.utc) - settle_last_execution.timestamp
                    )
                    if time_since_settle.total_seconds() <= rule.settle_seconds:
                        settle_remaining = int(
                            rule.settle_seconds - time_since_settle.total_seconds()
                        )
                        logger.debug(
                            f"Rule {rule.rule_name} settling after rule "
                            f"{rule.settle_after_rule_id}: "
                            f"{time_since_settle.total_seconds():.1f}s < {rule.settle_seconds}s"
                        )
                        await logic_repo.log_execution(
                            rule_id=rule.id,
                            trigger_data={},
                            actions=[],
                            success=False,
                            execution_ms=0,
                            error_message=f"settling:{settle_remaining}s",
                            metadata={
                                "settle_after_rule_id": str(rule.settle_after_rule_id),
                                "settle_seconds": rule.settle_seconds,
                                "remaining_seconds": settle_remaining,
                                "consecutive_skip_count": 1,
                            },
                            is_skip=True,
                        )
                        await logic_repo.session.commit()
                        return

            # Check rate limiting
            target_esp_ids = self._extract_target_esp_ids(actions_to_run)
            rate_result = await self.rate_limiter.check_rate_limit(
                rule_id=str(rule.id),
                rule_max_per_hour=rule.max_executions_per_hour,
                rule_max_per_day=rule.max_executions_per_day,
                rule_max_dose_ml_per_day=rule.max_dose_ml_per_day,
                esp_ids=target_esp_ids,
            )

            if not rate_result["allowed"]:
                increment_safety_trigger()
                logger.warning(f"Rule {rule.rule_name} rate limited: {rate_result['reason']}")
                # AUT-1020: write skip entry so rule.health batch can surface it (S5)
                await logic_repo.log_execution(
                    rule_id=rule.id,
                    trigger_data={},
                    actions=[],
                    success=False,
                    execution_ms=0,
                    error_message=f"rate_limit:{rate_result['reason']}",
                    metadata={"consecutive_skip_count": 1},
                    is_skip=True,
                )
                await logic_repo.session.commit()
                return

            # Execute actions (AUT-1317: gated subset; flat = all under global gate)
            logger.info(
                f"Rule {rule.rule_name} triggered: executing {len(actions_to_run)} actions"
            )

            # AUT-1112: chemistry feedforward (no-op unless rule_metadata.dose_config is set)
            # AUT-1233: resolved_setpoint (None for non-subscribing rules) overrides
            # dose_config["target_value"] with the SAME plan/static value already
            # resolved above — one resolve per tick, reused at both docking points.
            actions_with_dose_ml = await self._compute_chemistry_dose_ml(
                rule,
                actions_to_run,
                trigger_data,
                resolved_setpoint=resolved_setpoint,
                session=logic_repo.session,
            )
            enriched_actions, failed_dose_actions = await self._enrich_actions_with_duration(
                actions_with_dose_ml, session=logic_repo.session
            )
            # AUT-1371 K2: NULL-concentration → serielle Mess-Sequenz (Bestands-Bausteine).
            # Runs after duration enrichment so dose steps already carry duration_seconds.
            try:
                enriched_actions = await enrich_sequences_for_auto_cal(
                    logic_repo.session, enriched_actions
                )
            except Exception as auto_cal_err:
                logger.error(
                    "AUT-1371: sequence auto-cal enrichment failed for rule %s: %s",
                    rule_name_snapshot,
                    auto_cal_err,
                    exc_info=True,
                )
            # AUT-1396: attach measure_bindings onto sequence actions (observe-only).
            # Fast-path identity when rule has no measure_bindings.
            try:
                from .logic.measure_binding_hooks import attach_measure_bindings_to_sequences

                enriched_actions = attach_measure_bindings_to_sequences(
                    enriched_actions, getattr(rule, "rule_metadata", None)
                )
            except Exception as measure_bind_err:
                logger.error(
                    "AUT-1396: measure-binding attach failed for rule %s (observe-only): %s",
                    rule_name_snapshot,
                    measure_bind_err,
                    exc_info=True,
                )
            has_dose_failure = bool(failed_dose_actions)

            # AO-5: Dose-Audit-Extraktion aus enriched_actions (nutzt AO-2's _flow_rate_ml_s)
            _dose_total = sum(
                a.get("dose_ml", 0) or 0 for a in enriched_actions if a.get("dose_ml")
            )
            _flow_snapshot = next(
                (a.get("_flow_rate_ml_s") for a in enriched_actions if a.get("_flow_rate_ml_s")),
                None,
            )
            dose_ml_for_log = _dose_total if _dose_total > 0 else None
            flow_rate_for_log = _flow_snapshot

            execution_result = await self._execute_actions(
                enriched_actions,
                trigger_data,
                rule.id,
                rule.rule_name,
                rule.priority,
                rule_is_critical=bool(getattr(rule, "is_critical", False)),
                session=logic_repo.session,
                batch_locks=batch_locks,
            )
            if not isinstance(execution_result, dict):
                logger.error(
                    "Rule %s: _execute_actions returned non-dict type %s (coercing)",
                    rule_name_snapshot,
                    type(execution_result).__name__,
                )
                execution_result = {
                    "blocked_by_conflict": False,
                    "conflict_info": None,
                    "action_results": [],
                }

            # Update last_triggered timestamp
            rule.last_triggered = datetime.now(timezone.utc)

            # Log successful execution
            execution_time_ms = int((time.time() - start_time) * 1000)
            blocked_by_conflict = execution_result.get("blocked_by_conflict", False)
            conflict_info = execution_result.get("conflict_info") or {}
            conflict_message = conflict_info.get(
                "message",
                "Rule execution blocked due to actuator conflict",
            )
            success = not blocked_by_conflict and not has_dose_failure
            if blocked_by_conflict:
                error_message = conflict_message
            elif has_dose_failure:
                error_message = "One or more actions skipped: flow_rate_ml_s missing or uncalibrated"
            else:
                error_message = None

            history = await logic_repo.log_execution(
                rule_id=rule.id,
                trigger_data=trigger_data,
                actions=enriched_actions,  # AO-5: angereicherte Actions (mit duration_seconds)
                success=success,
                execution_ms=execution_time_ms,
                error_message=error_message,
                metadata=(
                    {
                        "terminal_reason_code": "conflict_priority_lost",
                        "conflict_info": conflict_info,
                    }
                    if blocked_by_conflict
                    else None
                ),
                dose_ml=dose_ml_for_log,  # AO-5
                flow_rate_ml_s_snapshot=flow_rate_for_log,  # AO-5
            )
            # AUT-1352: additive ledger logging only — does not alter dose timing.
            await self._maybe_record_logic_dose_ledger(
                session=logic_repo.session,
                rule=rule,
                logic_execution_id=history.id,
                enriched_actions=enriched_actions,
                execution_result=execution_result,
                blocked_by_conflict=blocked_by_conflict,
                has_dose_failure=has_dose_failure,
                success=success,
            )
            await logic_repo.session.commit()

        except Exception as e:
            increment_logic_error()
            logger.error(
                "Error evaluating rule %s: %s",
                rule_name_snapshot,
                e,
                exc_info=True,
            )

            # Log failed execution (rollback first in case session is broken)
            try:
                await logic_repo.session.rollback()
                execution_time_ms = int((time.time() - start_time) * 1000)
                if isinstance(rule_id_snapshot, uuid.UUID):
                    await logic_repo.log_execution(
                        rule_id=rule_id_snapshot,
                        trigger_data=trigger_snapshot,
                        actions=actions_snapshot,
                        success=False,
                        execution_ms=execution_time_ms,
                        error_message=str(e),
                        dose_ml=None,  # AO-5: Exception = kein Volumen abgegeben
                        flow_rate_ml_s_snapshot=None,  # AO-5
                    )
                    await logic_repo.session.commit()
                else:
                    logger.warning(
                        "Skipping execution error log: invalid rule id snapshot (%s)",
                        rule_id_snapshot,
                    )
            except Exception as log_err:
                logger.error(
                    "Failed to log execution error for %s: %s", rule_name_snapshot, log_err
                )

    @staticmethod
    def _action_has_condition_refs(action: Dict[str, Any]) -> bool:
        """True when action carries a non-empty condition_refs list (AUT-1317)."""
        refs = action.get("condition_refs")
        return isinstance(refs, list) and len(refs) > 0

    @classmethod
    def _rule_has_routed_actions(cls, actions: Sequence[Dict[str, Any]]) -> bool:
        """True when any action opts into per-action condition gating."""
        return any(cls._action_has_condition_refs(a) for a in actions)

    @staticmethod
    def _combine_condition_results(results: Sequence[bool], logic_operator: str) -> bool:
        """Combine per-condition booleans with AND/OR (empty → False)."""
        if not results:
            return False
        op = (logic_operator or "AND").upper()
        if op == "OR":
            return any(results)
        return all(results)

    @classmethod
    def _action_passes_condition_gate(
        cls,
        action: Dict[str, Any],
        condition_results: Sequence[bool],
        global_conditions_met: bool,
        rule_logic_operator: str,
    ) -> bool:
        """
        AUT-1317 per-action gate.

        - Absent/null/[] condition_refs → global rule gate (D4).
        - Non-empty refs → subset under condition_op (default rule.logic_operator).
        - Invalid index → fail closed.
        """
        refs = action.get("condition_refs")
        if refs is None or refs == []:
            return global_conditions_met
        if not isinstance(refs, list):
            return False
        subset: List[bool] = []
        for idx in refs:
            if not isinstance(idx, int) or idx < 0 or idx >= len(condition_results):
                return False
            subset.append(bool(condition_results[idx]))
        op = action.get("condition_op") or rule_logic_operator or "AND"
        return cls._combine_condition_results(subset, str(op))

    @classmethod
    def _filter_actions_by_condition_gate(
        cls,
        actions: Sequence[Dict[str, Any]],
        condition_results: Sequence[bool],
        global_conditions_met: bool,
        rule_logic_operator: str,
    ) -> List[Dict[str, Any]]:
        """Return actions whose condition gate is true."""
        return [
            a
            for a in actions
            if cls._action_passes_condition_gate(
                a, condition_results, global_conditions_met, rule_logic_operator
            )
        ]

    @classmethod
    def _is_safety_critical_routed_off(cls, action: Dict[str, Any]) -> bool:
        """
        AUT-1317: safety-critical gerouteter OFF — cooldown bypass on action level.

        Requires command=OFF, is_safety_critical, and non-empty condition_refs.
        Must not use the rule-wide _hysteresis_just_deactivated path.
        """
        if not cls._action_has_condition_refs(action):
            return False
        if not action.get("is_safety_critical"):
            return False
        if action.get("type") not in ("actuator_command", "actuator"):
            return False
        return action.get("command") == "OFF"

    async def _evaluate_individual_conditions(
        self, conditions, context: dict
    ) -> List[bool]:
        """
        Evaluate each top-level condition once; return per-index results (AUT-1317).

        Needed so condition_refs can gate actions on subsets without relying only on
        the aggregated conditions_met flag.
        """
        if isinstance(conditions, list):
            results: List[bool] = []
            for cond in conditions:
                results.append(await self._check_conditions(cond, context))
            return results
        met = await self._check_conditions(conditions, context)
        return [met]

    async def _check_conditions(
        self, conditions, sensor_data: dict, logic_operator: str = "AND"
    ) -> bool:
        """
        Check if conditions are met using modular evaluators.

        Supports:
        - Single condition: {'type': 'sensor_threshold', ...}
        - Compound conditions: {'logic': 'AND', 'conditions': [...]}
        - List of conditions: [{'type': 'sensor', ...}, ...] (from API)

        Args:
            conditions: Condition dict, compound dict, or list of condition dicts
            sensor_data: Sensor data to check against (or context dict)
            logic_operator: Logic operator for combining multiple conditions ("AND" or "OR")

        Returns:
            True if conditions are met, False otherwise
        """
        # Handle list of conditions (API stores conditions as List[Dict])
        if isinstance(conditions, list):
            if len(conditions) == 0:
                return False
            if len(conditions) == 1:
                # Single condition in list
                conditions = conditions[0]
            else:
                # Multiple conditions — wrap as compound using rule's logic_operator
                operator = logic_operator.upper() if logic_operator else "AND"
                conditions = {"logic": operator, "conditions": conditions}

        # Use modular evaluators if available
        if self.condition_evaluators:
            return await self._check_conditions_modular(conditions, sensor_data)

        # Fallback to legacy implementation
        return await self._check_conditions_legacy(conditions, sensor_data)

    async def _check_conditions_modular(self, conditions: dict, context: dict) -> bool:
        """Check conditions using modular evaluators."""
        # Handle compound conditions (AND/OR logic)
        if "logic" in conditions and "conditions" in conditions:
            # Find compound evaluator
            compound_eval = None
            for evaluator in self.condition_evaluators:
                if isinstance(evaluator, CompoundConditionEvaluator):
                    compound_eval = evaluator
                    break

            if compound_eval:
                return await compound_eval.evaluate(conditions, context)
            else:
                # Fallback to manual evaluation
                return await self._check_conditions_legacy(conditions, context)

        # Handle single condition - find appropriate evaluator
        cond_type = conditions.get("type", "unknown")

        for evaluator in self.condition_evaluators:
            if evaluator.supports(cond_type):
                return await evaluator.evaluate(conditions, context)

        # No evaluator found - use legacy
        logger.warning(f"No evaluator found for condition type: {cond_type}, using legacy")
        return await self._check_conditions_legacy(conditions, context)

    async def _check_conditions_legacy(self, conditions: dict, sensor_data: dict) -> bool:
        """
        Legacy condition checking (backward compatibility).

        Original implementation maintained for compatibility.
        """
        # Handle compound conditions (AND/OR logic)
        if "logic" in conditions and "conditions" in conditions:
            logic = conditions.get("logic", "AND").upper()
            sub_conditions = conditions.get("conditions", [])

            if logic == "AND":
                # All conditions must be met
                for condition in sub_conditions:
                    if not await self._check_single_condition(condition, sensor_data):
                        return False
                return True
            elif logic == "OR":
                # At least one condition must be met
                for condition in sub_conditions:
                    if await self._check_single_condition(condition, sensor_data):
                        return True
                return False
            else:
                logger.warning(f"Unknown logic operator: {logic}")
                return False

        # Handle single condition
        return await self._check_single_condition(conditions, sensor_data)

    async def _check_single_condition(self, condition: dict, sensor_data: dict) -> bool:
        """
        Check a single condition.

        Args:
            condition: Single condition dictionary
            sensor_data: Sensor data to check against

        Returns:
            True if condition is met, False otherwise
        """
        cond_type = condition.get("type")

        # Accept both "sensor_threshold" and "sensor" as valid condition types
        if cond_type in ("sensor_threshold", "sensor"):
            # Match on ESP + GPIO + optionally Sensor Type
            if condition.get("esp_id") != sensor_data.get("esp_id"):
                return False
            # GPIO comparison with type coercion (int vs str safety)
            try:
                if int(condition.get("gpio", -1)) != int(sensor_data.get("gpio", -2)):
                    return False
            except (ValueError, TypeError):
                return False
            # sensor_type is optional for "sensor" shorthand
            if condition.get("sensor_type") and condition.get("sensor_type") != sensor_data.get(
                "sensor_type"
            ):
                return False

            # Phase 2.4: Optional subzone filter (skip when condition.subzone_id not set)
            cond_subzone = condition.get("subzone_id")
            if cond_subzone and sensor_data.get("subzone_id") != cond_subzone:
                return False

            # AUT-994 B2: never dispatch on an implausible trigger reading. Mirrors the
            # guard in SensorConditionEvaluator for the legacy/fallback condition path.
            if sensor_data.get("quality") == "critical":
                return False

            operator = condition.get("operator")
            threshold = condition.get("value")
            actual = sensor_data.get("value")

            if actual is None:
                logger.warning(
                    f"Sensor data missing value for "
                    f"{sensor_data.get('esp_id')}:{sensor_data.get('gpio')}"
                )
                return False

            # Type-safe conversion to float
            try:
                actual = float(actual)
                threshold = float(threshold)
            except (ValueError, TypeError) as e:
                logger.error(f"Invalid numeric values for sensor condition: {e}")
                return False

            if operator == ">":
                return actual > threshold
            elif operator == ">=":
                return actual >= threshold
            elif operator == "<":
                return actual < threshold
            elif operator == "<=":
                return actual <= threshold
            elif operator == "==":
                return actual == threshold
            elif operator == "!=":
                return actual != threshold
            elif operator == "between":
                min_val = condition.get("min")
                max_val = condition.get("max")
                if min_val is None or max_val is None:
                    logger.warning("'between' operator requires 'min' and 'max' fields")
                    return False
                try:
                    return float(min_val) <= actual <= float(max_val)
                except (ValueError, TypeError):
                    return False
            else:
                logger.warning(f"Unknown operator: {operator}")
                return False

        elif cond_type in ("time_window", "time"):
            # Time window condition
            now = datetime.now(timezone.utc)
            start_hour = condition.get("start_hour", 0)
            end_hour = condition.get("end_hour", 24)
            days = condition.get("days_of_week")  # Optional: [0,1,2,3,4] = Mon-Fri

            # Check day of week if specified
            if days is not None:
                if now.weekday() not in days:
                    return False

            # Check time window with overnight wrapping support
            current_hour = now.hour
            if start_hour <= end_hour:
                return start_hour <= current_hour < end_hour
            else:
                # Wrapping case (e.g., 22:00 to 06:00)
                return current_hour >= start_hour or current_hour < end_hour

        else:
            logger.warning(f"Unknown condition type: {cond_type}")
            return False

    async def _compute_chemistry_dose_ml(
        self,
        rule,
        actions: list[dict],
        trigger_data: dict,
        resolved_setpoint: Optional[ResolveResult] = None,
        session=None,
    ) -> list[dict]:
        """
        AUT-1112: Compute dose_ml from rule.rule_metadata["dose_config"] (Ist/Soll/
        Volumen/Komponenten/Sicherheitsfaktor), before duration enrichment. AUT-1118
        (S8): dose_config may also carry max_delta_per_dose, capping how much a
        single dose may change current_value (Profi-Praxis-Amplituden-Deckel).

        No-op (actions returned unchanged) unless dose_config is set — this is the
        default for practically all existing rules, since rule_metadata defaults to
        {}. Fail-open per action: any error (missing config, invalid values, exception
        in calculate_dose_ml) skips only that action (WARNING-log, dose_ml left unset)
        and never blocks the rule or other actions, mirroring the pattern at
        _enrich_actions_with_duration()'s flow_rate_ml_s check below.

        components are assigned positionally, one per actuator action in rule
        order (top-level actions and sequence steps counted together) — e.g. for
        a 2-step EC sequence (Pump A, Pump B), components[0] dimensions Pump A's
        own dose_ml and components[1] dimensions Pump B's, each via its own
        concentration/ratio_share (NOT the combined total for both pumps).

        AUT-1355 U4-a: Divisor ``concentration`` is read from the matched pump's
        ``actuator_configs.concentration`` when set (>0). Runtime fallback only:
        if pump concentration is NULL/unset → ``dose_config.components[i].concentration``.
        ``ratio_share`` stays on dose_config. Formula unchanged (only source of divisor).

        AUT-1366 R1: ``dose_config.components[i].volume_share`` is the SSOT for
        intended volume fraction (additive JSONB; missing → equal shares).

        AUT-1367 R2: before ``calculate_dose_ml``, EC ``ratio_share`` is derived
        via shared ``compute_ratio_shares_from_volume`` (same helper as Assist).
        Formula body of ``calculate_dose_ml`` is unchanged.

        AUT-1233 (Welle 5 T3): ``resolved_setpoint`` is the SAME ResolveResult
        already produced once in _evaluate_rule for the primary (conditions)
        docking point — passed through here, not re-resolved. Only overrides
        dose_config["target_value"] when the rule subscribes AND a concrete
        value exists (resolved_setpoint.value is not None); this covers both
        origins (plan_segment and static_fallback) with the identical number
        the rule's own static_value would have produced anyway, so the
        override is a no-op for the static_fallback case in practice. Never
        introduces new chemistry — calculate_dose_ml() below is unchanged.

        Returns:
            actions with dose_ml written onto matching actuator actions where computable
        """
        dose_config = (rule.rule_metadata or {}).get("dose_config")
        if not dose_config:
            return actions

        current_value = trigger_data.get("value")
        target_value = dose_config.get("target_value")
        if resolved_setpoint is not None and resolved_setpoint.value is not None:
            target_value = resolved_setpoint.value
        volume_l = dose_config.get("volume_l")
        components = dose_config.get("components") or []
        safety_factor = dose_config.get("safety_factor")
        dilution_value = dose_config.get("dilution_value")
        max_delta_per_dose = dose_config.get("max_delta_per_dose")

        esp_uuid_cache: dict[str, object] = {}
        esp_repo = ESPRepository(session) if session is not None else None
        actuator_repo = ActuatorRepository(session) if session is not None else None

        async def _resolve_concentration(action: dict, component: dict) -> dict:
            """Prefer pump SSOT concentration; fallback to dose_config component."""
            if esp_repo is None or actuator_repo is None:
                return component
            esp_id_str = action.get("esp_id")
            gpio_raw = action.get("gpio")
            if not esp_id_str or gpio_raw is None:
                return component
            if esp_id_str not in esp_uuid_cache:
                esp = await esp_repo.get_by_device_id(esp_id_str)
                esp_uuid_cache[esp_id_str] = esp.id if esp else None
            esp_uuid = esp_uuid_cache.get(esp_id_str)
            if not esp_uuid:
                return component
            act = await actuator_repo.get_by_esp_and_gpio(esp_uuid, int(gpio_raw))
            pump_conc = act.concentration if act is not None else None
            if pump_conc is not None and pump_conc > 0:
                return {**component, "concentration": pump_conc}
            # Runtime fallback: dose_config.components[i].concentration (no backfill).
            return component

        # Collect actuator actions in the same positional order as components.
        actuator_slots: list[tuple[str, int | None, dict]] = []
        for action_idx, action in enumerate(actions):
            action_type = action.get("type")
            if action_type in ("actuator_command", "actuator"):
                actuator_slots.append(("top", action_idx, action))
            elif action_type == "sequence" and isinstance(action.get("steps"), list):
                for step_idx, step in enumerate(action["steps"]):
                    step_action = step.get("action") if isinstance(step, dict) else None
                    if isinstance(step_action, dict) and step_action.get("type") in (
                        "actuator_command",
                        "actuator",
                    ):
                        actuator_slots.append(("seq", step_idx, step_action))

        # Resolve pump concentrations for paired slots; keep dose_config
        # concentration on unpaired components. Derive ratio_share over the
        # FULL component set (Assist + LogicEngine share one helper) so a
        # 2-channel recipe stays 0.5/0.5 even when only one action is present.
        working_components: list[dict] = [dict(c) for c in components]
        pair_count = min(len(actuator_slots), len(working_components))
        for i in range(pair_count):
            _kind, _idx, act = actuator_slots[i]
            working_components[i] = await _resolve_concentration(
                act, working_components[i]
            )
        if working_components:
            try:
                ratio_shares = compute_ratio_shares_from_volume(working_components)
                for i, ratio in enumerate(ratio_shares):
                    working_components[i] = {
                        **working_components[i],
                        "ratio_share": ratio,
                    }
            except Exception as e:
                logger.warning(
                    "Chemistry ratio_share derivation skipped for rule %s — %s",
                    rule.rule_name,
                    e,
                )

        async def _apply(action: dict, component: dict) -> dict:
            try:
                dose_ml = calculate_dose_ml(
                    current_value=current_value,
                    target_value=target_value,
                    volume_l=volume_l,
                    components=[component],
                    safety_factor=safety_factor,
                    dilution_value=dilution_value,
                    max_delta_per_dose=max_delta_per_dose,
                )
                return {**action, "dose_ml": dose_ml}
            except Exception as e:
                logger.warning(
                    "Chemistry dose_ml computation skipped for rule %s on %s:GPIO%s — %s",
                    rule.rule_name, action.get("esp_id"), action.get("gpio"), e,
                )
                return action

        component_iter = iter(working_components)

        async def _apply_next(action: dict) -> dict:
            component = next(component_iter, None)
            if component is None:
                return action  # no matching component configured — leave unchanged
            return await _apply(action, component)

        result = []
        for action in actions:
            action_type = action.get("type")
            if action_type in ("actuator_command", "actuator"):
                result.append(await _apply_next(action))
            elif action_type == "sequence" and isinstance(action.get("steps"), list):
                new_steps = []
                for step in action["steps"]:
                    step_action = step.get("action") if isinstance(step, dict) else None
                    if isinstance(step_action, dict) and step_action.get("type") in (
                        "actuator_command",
                        "actuator",
                    ):
                        new_steps.append(
                            {**step, "action": await _apply_next(step_action)}
                        )
                    else:
                        new_steps.append(step)
                result.append({**action, "steps": new_steps})
            else:
                result.append(action)

        return result

    async def _enrich_actions_with_duration(
        self,
        actions: list[dict],
        session,
    ) -> tuple[list[dict], list[dict]]:
        """
        Resolve dose_ml → duration_seconds for actuator actions.

        For each action that has dose_ml set and > 0, looks up the actuator's
        flow_rate_ml_s (AO-1 dedicated column) and computes
        duration_seconds = ceil(dose_ml / flow_rate_ml_s), minimum 1 second.

        Actions without dose_ml (or dose_ml <= 0) are passed through unchanged.
        Actions where flow_rate_ml_s is missing or zero:
          AUT-1384 — if ``duration_seconds > 0`` is already on the action,
          pass through duration-driven (WARNING); otherwise move to failed.
          No blind dosing without an explicit duration.

        AUT-1111: type="sequence" actions are descended one level — each
        step["action"] with dose_ml is resolved via the same lookup. If any
        step's dose_ml cannot be resolved, the whole sequence action is moved
        to failed (mirrors top-level behavior; sequence_executor is unchanged).

        Returns:
            enriched: actions that are ready for execution (duration resolved or not needed)
            failed: actions skipped due to missing/uncalibrated flow_rate_ml_s
                (and no usable duration_seconds fallback)
        """
        enriched, failed = [], []
        esp_uuid_cache: dict[str, uuid.UUID | None] = {}
        esp_repo = ESPRepository(session)
        actuator_repo = ActuatorRepository(session)

        async def _resolve(action: dict) -> dict | None:
            """Resolve dose_ml -> duration_seconds for a single actuator action.

            Returns the enriched action, or None if flow_rate_ml_s is missing/
            uncalibrated and no duration_seconds fallback is available (AUT-1384).
            """
            dose_ml = action.get("dose_ml")
            if dose_ml is None or dose_ml <= 0:
                return action

            esp_id_str = action.get("esp_id")
            gpio_raw = action.get("gpio")
            if esp_id_str not in esp_uuid_cache:
                esp = await esp_repo.get_by_device_id(esp_id_str)
                esp_uuid_cache[esp_id_str] = esp.id if esp else None
            esp_uuid = esp_uuid_cache.get(esp_id_str)

            flow_rate = None
            if esp_uuid and gpio_raw is not None:
                act = await actuator_repo.get_by_esp_and_gpio(esp_uuid, int(gpio_raw))
                if act:
                    flow_rate = act.flow_rate_ml_s  # dedizierte Spalte (AO-1), NICHT actuator_metadata

            if not flow_rate or flow_rate <= 0:
                # AUT-1384: Behälterwechsel / uncalibrated pump — duration fallback.
                existing_duration = action.get("duration_seconds")
                try:
                    duration_fallback = (
                        float(existing_duration)
                        if existing_duration is not None
                        else 0.0
                    )
                except (TypeError, ValueError):
                    duration_fallback = 0.0
                if duration_fallback > 0:
                    logger.warning(
                        "dose_ml=%.2f on %s:GPIO%s — flow_rate_ml_s missing or "
                        "uncalibrated, using existing duration_seconds=%.1f "
                        "(AUT-1384 duration fallback)",
                        dose_ml,
                        esp_id_str,
                        gpio_raw,
                        duration_fallback,
                    )
                    return {**action, "duration_seconds": duration_fallback}
                logger.warning(
                    "dose_ml=%.2f on %s:GPIO%s — flow_rate_ml_s missing or uncalibrated, dosing skipped",
                    dose_ml, esp_id_str, gpio_raw
                )
                return None

            duration_seconds = max(1, math.ceil(dose_ml / flow_rate))
            return {**action, "duration_seconds": duration_seconds, "_flow_rate_ml_s": flow_rate}

        for action in actions:
            if action.get("type") == "sequence" and isinstance(action.get("steps"), list):
                new_steps = []
                sequence_failed = False
                for step in action["steps"]:
                    step_action = step.get("action") if isinstance(step, dict) else None
                    if isinstance(step_action, dict) and step_action.get("dose_ml") is not None:
                        resolved_step_action = await _resolve(step_action)
                        if resolved_step_action is None:
                            sequence_failed = True
                            break
                        new_steps.append({**step, "action": resolved_step_action})
                    else:
                        new_steps.append(step)

                if sequence_failed:
                    failed.append(action)
                else:
                    enriched.append({**action, "steps": new_steps})
                continue

            resolved_action = await _resolve(action)
            if resolved_action is None:
                failed.append(action)
                continue
            enriched.append(resolved_action)

        return enriched, failed

    def _sequence_executor(self) -> Optional[SequenceActionExecutor]:
        for executor in self.action_executors or []:
            if isinstance(executor, SequenceActionExecutor):
                return executor
        return None

    async def _maybe_record_logic_dose_ledger(
        self,
        *,
        session,
        rule,
        logic_execution_id: uuid.UUID,
        enriched_actions: list,
        execution_result: dict,
        blocked_by_conflict: bool,
        has_dose_failure: bool,
        success: bool,
    ) -> None:
        """
        AUT-1352 B1/B2/B3 — Hook after successful dispatch, before commit.

        Flat actuator doses: write ``top_up_dose`` in the same DB TX as
        ``log_execution``. Sequences are non-blocking
        (``SequenceActionExecutor.execute`` returns ``status=running``) — attach
        ledger context and write only on COMPLETED (see sequence_executor).

        Q1 documented gap: sequence partial abort → no ledger row (WARNING there).
        """
        if blocked_by_conflict or has_dose_failure or not success:
            return

        action_results = execution_result.get("action_results") or []
        dose_config = (getattr(rule, "rule_metadata", None) or {}).get("dose_config") or {}
        dose_components = dose_config.get("components") or []

        flat_pumps = collect_dispatched_dose_pumps(
            enriched_actions=enriched_actions,
            action_results=action_results,
            dose_config_components=dose_components,
        )
        if flat_pumps:
            try:
                await record_logic_dose_to_ledger(
                    session,
                    rule_id=rule.id,
                    logic_execution_id=logic_execution_id,
                    pumps=flat_pumps,
                    recipe_label=f"logic:{rule.id}",
                )
            except Exception as err:
                # Fail-open: never block rule commit / dosing path.
                logger.error(
                    "AUT-1352: flat ledger write failed for rule %s: %s",
                    getattr(rule, "rule_name", rule.id),
                    err,
                    exc_info=True,
                )

        seq_exec = self._sequence_executor()
        if seq_exec is None:
            return

        for result, action in zip(action_results, enriched_actions):
            if action.get("type") != "sequence":
                continue
            if not result.get("success"):
                continue
            data = result.get("data") or {}
            if data.get("noop") or data.get("skipped"):
                continue
            sequence_id = data.get("sequence_id")
            if not sequence_id:
                continue
            pumps = extract_dose_pumps_from_actions(
                [action], dose_config_components=dose_components
            )
            if not pumps:
                continue
            status = seq_exec.get_sequence_status(sequence_id)
            status_value = (status or {}).get("status")
            if status_value == "completed":
                try:
                    await record_logic_dose_to_ledger(
                        session,
                        rule_id=rule.id,
                        logic_execution_id=logic_execution_id,
                        pumps=pumps,
                        recipe_label=f"logic:{rule.id}",
                    )
                except Exception as err:
                    logger.error(
                        "AUT-1352: sequence ledger write (already completed) failed "
                        "for %s: %s",
                        sequence_id,
                        err,
                        exc_info=True,
                    )
            else:
                seq_exec.attach_logic_dose_ledger_context(
                    sequence_id,
                    logic_execution_id=logic_execution_id,
                    rule_id=rule.id,
                    pumps=pumps,
                    recipe_label=f"logic:{rule.id}",
                )

    async def _execute_actions(
        self,
        actions: list,
        trigger_data: dict,
        rule_id: uuid.UUID,
        rule_name: str,
        rule_priority: int = 100,
        session=None,
        batch_locks: list | None = None,
        rule_is_critical: bool = False,
    ) -> dict:
        """
        Execute actions for a triggered rule using modular executors.

        Args:
            actions: List of action dictionaries
            trigger_data: Sensor data that triggered the rule
            rule_id: UUID of the rule
            rule_name: Name of the rule
            rule_priority: Rule priority for conflicts/ordering (lower number = higher priority)
            session: Optional async DB session (Phase 2.4: for SubzoneRepository lookup)
            batch_locks: Optional batch-level lock tracking list.
                If provided, acquired locks are added here and NOT released
                in this method (caller is responsible for batch release).
            rule_is_critical: AUT-1336 — rule-level is_critical feeds existing ConflictManager
                safety path (OR with action.is_safety_critical). Default False = unchanged.
        """
        execution_outcome = {
            "blocked_by_conflict": False,
            "conflict_info": None,
            "action_results": [],
        }

        # Extract actuator actions for conflict management
        actuator_actions = [
            action for action in actions if action.get("type") in ("actuator_command", "actuator")
        ]

        # Duration-aware guard: if this rule already holds an active lock for
        # the same actuator+command (e.g. duration-based ON still running), skip
        # the entire action batch.  This prevents resetting the ESP32 auto-off
        # timer with redundant MQTT publishes every evaluation cycle.
        for action in actuator_actions:
            action_duration = action.get("duration_seconds") or action.get("duration", 0)
            action_command = action.get("command", "ON")
            if action_duration and int(action_duration) > 0:
                act_esp = action.get("esp_id")
                act_gpio = action.get("gpio")
                if act_esp and act_gpio is not None:
                    if self.conflict_manager.has_active_lock_for_rule(
                        esp_id=act_esp,
                        gpio=int(act_gpio),
                        rule_id=str(rule_id),
                        command=action_command,
                    ):
                        logger.debug(
                            "Rule %s: skipping %s on %s:GPIO%s — duration lock still active",
                            rule_name,
                            action_command,
                            act_esp,
                            act_gpio,
                        )
                        return execution_outcome

        # Acquire locks for all actuator actions
        acquired_locks = []
        for action in actuator_actions:
            # P0-Fix T9: Lock TTL must cover the actuator's duration to prevent
            # mid-execution override by lower-priority rules.
            action_duration = action.get("duration_seconds") or action.get("duration", 0)
            lock_ttl = (
                max(
                    self.conflict_manager.DEFAULT_LOCK_TTL_SECONDS,
                    int(action_duration) + 10 if action_duration else 0,
                )
                or None
            )

            # AUT-1336 Option A: rule.is_critical wires into existing ConflictManager
            # precedence (priority + is_safety_critical) — no new arbitration mechanism.
            can_execute, conflict = await self.conflict_manager.acquire_actuator(
                esp_id=action.get("esp_id"),
                gpio=action.get("gpio"),
                rule_id=str(rule_id),
                priority=rule_priority,
                command=action.get("command", "ON"),
                is_safety_critical=bool(
                    action.get("is_safety_critical", False) or rule_is_critical
                ),
                lock_ttl_seconds=lock_ttl,
            )

            if not can_execute:
                increment_safety_trigger()
                conflict_info = {
                    "actuator_key": (
                        conflict.actuator_key
                        if conflict
                        else f"{action.get('esp_id')}:{action.get('gpio')}"
                    ),
                    "trace_id": conflict.trace_id if conflict else None,
                    "winner_rule_id": conflict.winner_rule_id if conflict else None,
                    "loser_rule_id": str(rule_id),
                    "competing_rules": conflict.competing_rules if conflict else [str(rule_id)],
                    "arbitration_mode": (
                        "first_wins"
                        if conflict and conflict.resolution.value == "first_wins"
                        else "priority"
                    ),
                    "resolution": conflict.resolution.value if conflict else "blocked",
                    "message": (
                        conflict.message if conflict else "Actuator command blocked due to conflict"
                    ),
                }
                logger.warning(
                    "Actuator conflict for rule %s: %s",
                    rule_name,
                    conflict_info["message"],
                )
                await self._emit_conflict_alert(
                    session=session,
                    rule_id=rule_id,
                    rule_name=rule_name,
                    trigger_data=trigger_data,
                    action=action,
                    conflict_info=conflict_info,
                )
                # Ensure conflict is visible on existing UI path.
                try:
                    await self.websocket_manager.broadcast(
                        "logic_execution",
                        {
                            "rule_id": str(rule_id),
                            "rule_name": rule_name,
                            "trigger": trigger_data,
                            "action": action,
                            "success": False,
                            "error_code": "conflict_priority_lost",
                            "error": conflict_info["message"],
                            "conflict": conflict_info,
                            "timestamp": trigger_data.get("timestamp"),
                        },
                    )
                except Exception as ws_err:
                    logger.warning(
                        "WebSocket conflict broadcast failed for rule %s: %s",
                        rule_name,
                        ws_err,
                    )
                # Rollback already acquired locks
                for lock in acquired_locks:
                    await self.conflict_manager.release_actuator(
                        esp_id=lock["esp_id"], gpio=lock["gpio"], rule_id=lock["rule_id"]
                    )
                return {
                    "blocked_by_conflict": True,
                    "conflict_info": conflict_info,
                    "action_results": [],
                }

            acquired_locks.append(
                {
                    "esp_id": action.get("esp_id"),
                    "gpio": action.get("gpio"),
                    "rule_id": str(rule_id),
                }
            )

        # Create execution context (Phase 2.4: session for ActuatorActionExecutor subzone lookup)
        context = {
            "trigger_data": trigger_data,
            "rule_id": rule_id,
            "rule_name": rule_name,
            "session": session,
        }

        try:
            for action in actions:
                action_type = action.get("type")

                # Pre-check ESP online status for actuator actions — skip executor call entirely
                # when ESP is offline. This avoids ERROR noise from actuator_service for an
                # expected transient state. Reference pattern: sensor_scheduler_service.py:371
                if action_type in ("actuator_command", "actuator") and session:
                    esp_id_pre = action.get("esp_id")
                    gpio_pre = action.get("gpio")
                    if esp_id_pre:
                        adoption_service = get_state_adoption_service()
                        if not await adoption_service.is_adoption_completed(esp_id_pre):
                            logger.info(
                                "Rule %s: skip enforce for %s GPIO %s (adoption not completed)",
                                rule_name,
                                esp_id_pre,
                                gpio_pre,
                            )
                            continue
                        skip_until = self._offline_esp_skip.get(esp_id_pre)
                        if skip_until and datetime.now(timezone.utc) < skip_until:
                            continue  # Silent skip: still within backoff window
                        # AUT-60: config_pending backoff (separate from offline)
                        cp_skip_until = self._config_pending_skip.get(esp_id_pre)
                        if cp_skip_until and datetime.now(timezone.utc) < cp_skip_until:
                            continue  # Silent skip: still within config_pending backoff
                        esp_repo_pre = ESPRepository(session)
                        esp_device_pre = await esp_repo_pre.get_by_device_id(esp_id_pre)
                        if not esp_device_pre or not esp_device_pre.is_online:
                            self._offline_esp_skip[esp_id_pre] = datetime.now(
                                timezone.utc
                            ) + timedelta(seconds=_OFFLINE_BACKOFF_SECONDS)
                            increment_logic_dispatch_skipped_offline()
                            logger.warning(
                                f"Rule {rule_name}: ESP {esp_id_pre} is offline, "
                                f"skipping actuator action (GPIO {gpio_pre})"
                            )
                            # AUT-111: enter degraded state for critical rules
                            try:
                                await self._enter_degraded_state(
                                    rule_id,
                                    rule_name,
                                    f"target_esp_offline:{esp_id_pre}",
                                    session,
                                )
                            except Exception as deg_err:
                                logger.warning(
                                    "AUT-111: failed to enter degraded state for %s: %s",
                                    rule_name,
                                    deg_err,
                                )
                            continue
                        # AUT-60: Config Pending Readiness Gate
                        if esp_device_pre.config_pending:
                            self._config_pending_skip[esp_id_pre] = datetime.now(
                                timezone.utc
                            ) + timedelta(seconds=_CONFIG_PENDING_BACKOFF_SECONDS)
                            increment_logic_dispatch_skipped_config_pending()
                            logger.warning(
                                "Rule %s: ESP %s is in CONFIG_PENDING_AFTER_RESET, "
                                "skipping actuator action (GPIO %s). "
                                "Firmware would reject with CONFIG_PENDING_BLOCKED.",
                                rule_name,
                                esp_id_pre,
                                gpio_pre,
                            )
                            execution_outcome["action_results"].append(
                                {
                                    "type": action_type,
                                    "success": False,
                                    "message": (
                                        f"Rejected: ESP {esp_id_pre} is in "
                                        f"CONFIG_PENDING_AFTER_RESET (GPIO {gpio_pre})"
                                    ),
                                    "data": {
                                        "reason": "config_pending",
                                        "esp_id": esp_id_pre,
                                        "gpio": gpio_pre,
                                    },
                                }
                            )
                            continue
                        else:
                            # ESP back online and not config_pending — clear backoffs
                            self._offline_esp_skip.pop(esp_id_pre, None)
                            self._config_pending_skip.pop(esp_id_pre, None)
                            # AUT-111: recover from degraded state
                            try:
                                await self._exit_degraded_state(rule_id, rule_name, session)
                            except Exception as rec_err:
                                logger.warning(
                                    "AUT-111: failed to exit degraded state for %s: %s",
                                    rule_name,
                                    rec_err,
                                )

                # Use modular executors if available
                executor_found = False
                if self.action_executors:
                    for executor in self.action_executors:
                        if executor.supports(action_type):
                            executor_found = True
                            try:
                                action_result = await executor.execute(action, context)

                                # WebSocket broadcast (non-critical, must not interrupt execution).
                                # Skip broadcast for noop results to avoid flooding the frontend
                                # with redundant "logic_execution" events while actuator is active.
                                _is_noop = (
                                    action_result.data.get("noop", False)
                                    if action_result.data
                                    else False
                                )
                                if not _is_noop:
                                    try:
                                        await self.websocket_manager.broadcast(
                                            "logic_execution",
                                            {
                                                "rule_id": str(rule_id),
                                                "rule_name": rule_name,
                                                "trigger": trigger_data,
                                                "action": action,
                                                "success": action_result.success,
                                                "message": action_result.message,
                                                "timestamp": trigger_data.get("timestamp"),
                                            },
                                        )
                                    except Exception as ws_err:
                                        logger.warning(
                                            f"WebSocket broadcast failed for rule {rule_name}: {ws_err}"
                                        )

                                execution_outcome["action_results"].append(
                                    {
                                        "type": action_type,
                                        "success": bool(action_result.success),
                                        "message": action_result.message,
                                        "data": action_result.data if action_result.data else None,
                                    }
                                )

                                if action_result.success:
                                    # Distinguish real executions from noop skips
                                    is_noop = (
                                        action_result.data.get("noop", False)
                                        if action_result.data
                                        else False
                                    )
                                    if is_noop:
                                        logger.debug(
                                            "Rule %s: noop skip for %s - %s",
                                            rule_name,
                                            action_type,
                                            action_result.message,
                                        )
                                    else:
                                        logger.info(
                                            f"Rule {rule_name} executed action: {action_type} - {action_result.message}"
                                        )
                                else:
                                    logger.error(
                                        f"Rule {rule_name} failed to execute action: {action_type} - {action_result.message}"
                                    )

                            except Exception as e:
                                logger.error(
                                    f"Error executing action {action_type} for rule {rule_name}: {e}",
                                    exc_info=True,
                                )
                                execution_outcome["action_results"].append(
                                    {
                                        "type": action_type,
                                        "success": False,
                                        "message": str(e),
                                        "data": None,
                                    }
                                )

                            break

                # Fallback to legacy implementation for backward compatibility
                if not executor_found:
                    await self._execute_action_legacy(action, trigger_data, rule_id, rule_name)
        finally:
            if batch_locks is not None:
                # Batch mode: transfer locks to batch for deferred release
                batch_locks.extend(acquired_locks)
            else:
                # Non-batch mode: release locks immediately
                for lock in acquired_locks:
                    await self.conflict_manager.release_actuator(
                        esp_id=lock["esp_id"], gpio=lock["gpio"], rule_id=lock["rule_id"]
                    )
        return execution_outcome

    async def _execute_action_legacy(
        self,
        action: dict,
        trigger_data: dict,
        rule_id: uuid.UUID,
        rule_name: str,
    ) -> None:
        """
        Legacy action execution (backward compatibility).

        Original implementation maintained for compatibility.
        """
        action_type = action.get("type")

        # Support both "actuator_command" and "actuator" for backward compatibility
        if action_type in ("actuator_command", "actuator"):
            # Execute actuator command
            esp_id = action.get("esp_id")
            gpio = action.get("gpio")
            command = action.get("command", "ON")
            value = action.get("value", 1.0)
            # Support both "duration_seconds" and "duration" for backward compatibility
            # Use explicit None check to allow duration_seconds=0 as valid value
            duration = (
                action.get("duration_seconds")
                if "duration_seconds" in action
                else action.get("duration", 0)
            )

            # Pre-check ESP online status (mirrors modern path; session fetched via get_session())
            if esp_id:
                adoption_service = get_state_adoption_service()
                if not await adoption_service.is_adoption_completed(esp_id):
                    logger.info(
                        "Rule %s: legacy enforce skipped for %s GPIO %s (adoption not completed)",
                        rule_name,
                        esp_id,
                        gpio,
                    )
                    return
                skip_until = self._offline_esp_skip.get(esp_id)
                if skip_until and datetime.now(timezone.utc) < skip_until:
                    return  # Silent skip: still within backoff window
                # AUT-60: config_pending backoff (separate from offline)
                cp_skip_until = self._config_pending_skip.get(esp_id)
                if cp_skip_until and datetime.now(timezone.utc) < cp_skip_until:
                    return  # Silent skip: still within config_pending backoff
                async for session in get_session():
                    esp_repo_pre = ESPRepository(session)
                    esp_device_pre = await esp_repo_pre.get_by_device_id(esp_id)
                    if not esp_device_pre or not esp_device_pre.is_online:
                        self._offline_esp_skip[esp_id] = datetime.now(timezone.utc) + timedelta(
                            seconds=_OFFLINE_BACKOFF_SECONDS
                        )
                        increment_logic_dispatch_skipped_offline()
                        logger.warning(
                            f"Rule {rule_name}: ESP {esp_id} is offline, "
                            f"skipping actuator action (GPIO {gpio})"
                        )
                        # AUT-111: enter degraded state for critical rules
                        try:
                            await self._enter_degraded_state(
                                rule_id,
                                rule_name,
                                f"target_esp_offline:{esp_id}",
                                session,
                            )
                            await session.commit()
                        except Exception as deg_err:
                            logger.warning(
                                "AUT-111: failed to enter degraded (legacy): %s",
                                deg_err,
                            )
                        return
                    # AUT-60: Config Pending Readiness Gate
                    if esp_device_pre.config_pending:
                        self._config_pending_skip[esp_id] = datetime.now(timezone.utc) + timedelta(
                            seconds=_CONFIG_PENDING_BACKOFF_SECONDS
                        )
                        increment_logic_dispatch_skipped_config_pending()
                        logger.warning(
                            "Rule %s: ESP %s is in CONFIG_PENDING_AFTER_RESET, "
                            "skipping actuator action (GPIO %s). "
                            "Firmware would reject with CONFIG_PENDING_BLOCKED.",
                            rule_name,
                            esp_id,
                            gpio,
                        )
                        return
                    else:
                        self._offline_esp_skip.pop(esp_id, None)
                        self._config_pending_skip.pop(esp_id, None)
                        # AUT-111: recover from degraded state
                        try:
                            await self._exit_degraded_state(rule_id, rule_name, session)
                            await session.commit()
                        except Exception as rec_err:
                            logger.warning(
                                "AUT-111: failed to exit degraded (legacy): %s",
                                rec_err,
                            )

            cmd_result = await self.actuator_service.send_command(
                esp_id=esp_id,
                gpio=gpio,
                command=command,
                value=value,
                duration=duration,
                issued_by=f"logic:{rule_id}",
            )
            success = cmd_result.success

            # WebSocket broadcast (non-critical, must not interrupt execution)
            try:
                await self.websocket_manager.broadcast(
                    "logic_execution",
                    {
                        "rule_id": str(rule_id),
                        "rule_name": rule_name,
                        "trigger": trigger_data,
                        "action": {
                            "esp_id": esp_id,
                            "gpio": gpio,
                            "command": command,
                            "value": value,
                            "duration": duration,
                        },
                        "success": success,
                        "timestamp": trigger_data.get("timestamp"),
                    },
                )
            except Exception as ws_err:
                logger.warning(f"WebSocket broadcast failed for rule {rule_name}: {ws_err}")

            if success:
                logger.info(
                    f"Rule {rule_name} executed action: {command} on " f"ESP {esp_id} GPIO {gpio}"
                )
            else:
                logger.error(
                    f"Rule {rule_name} failed to execute action: {command} on "
                    f"ESP {esp_id} GPIO {gpio}"
                )

        else:
            logger.warning(f"Unknown action type: {action_type}")

    async def _load_cross_sensor_values(
        self, trigger_conditions, trigger_data: dict, session
    ) -> tuple[dict, list[dict]]:
        """
        Pre-load latest sensor values for cross-sensor conditions.

        When a rule references multiple sensors (e.g., AND: temp > 25 AND moisture < 40),
        only one sensor triggers the evaluation. For other sensors, we need to look up
        the latest value from the database.

        Args:
            trigger_conditions: Rule's trigger_conditions (list or dict)
            trigger_data: Current trigger sensor data (esp_id, gpio, sensor_type, value)
            session: SQLAlchemy async session

        Returns:
            Tuple:
            - sensor_values: Dict mapping "ESP_ID:GPIO" to value metadata
            - offline_sensor_refs: sensor refs skipped because ESP is offline
        """
        sensor_values = {}
        offline_sensor_refs: list[dict] = []

        # Include trigger data in sensor_values for consistency
        # Use sensor_type-specific key for multi-value sensors (SHT31 temp vs humidity)
        trigger_sensor_type = trigger_data.get("sensor_type")
        trigger_key = (
            f"{trigger_data.get('esp_id')}:{trigger_data.get('gpio')}:{trigger_sensor_type}"
            if trigger_sensor_type
            else f"{trigger_data.get('esp_id')}:{trigger_data.get('gpio')}"
        )
        sensor_values[trigger_key] = {
            "value": trigger_data.get("value"),
            "sensor_type": trigger_sensor_type,
        }
        # Also store untyped key for backward compatibility
        untyped_trigger_key = f"{trigger_data.get('esp_id')}:{trigger_data.get('gpio')}"
        if untyped_trigger_key != trigger_key:
            sensor_values[untyped_trigger_key] = {
                "value": trigger_data.get("value"),
                "sensor_type": trigger_sensor_type,
            }

        # Extract all sensor conditions from trigger_conditions
        conditions_to_check = []
        if isinstance(trigger_conditions, list):
            conditions_to_check = trigger_conditions
        elif isinstance(trigger_conditions, dict):
            if trigger_conditions.get("type") in ("sensor_threshold", "sensor"):
                conditions_to_check = [trigger_conditions]
            elif trigger_conditions.get("logic") in ("AND", "OR"):
                conditions_to_check = trigger_conditions.get("conditions", [])
            elif trigger_conditions.get("type") == "compound":
                conditions_to_check = trigger_conditions.get("conditions", [])

        # Find conditions that reference different sensors than the trigger
        cross_sensor_keys = []
        for cond in conditions_to_check:
            if cond.get("type") not in ("sensor_threshold", "sensor", "hysteresis"):
                continue
            cond_esp = cond.get("esp_id")
            cond_gpio = cond.get("gpio")
            if cond_esp is None or cond_gpio is None:
                continue
            # Include sensor_type in key for multi-value sensors (SHT31 temp vs humidity)
            cond_sensor_type = cond.get("sensor_type")
            sensor_key = (
                f"{cond_esp}:{cond_gpio}:{cond_sensor_type}"
                if cond_sensor_type
                else f"{cond_esp}:{cond_gpio}"
            )
            if sensor_key != trigger_key and sensor_key not in sensor_values:
                cross_sensor_keys.append((cond_esp, int(cond_gpio), cond_sensor_type))

        if not cross_sensor_keys:
            return sensor_values, offline_sensor_refs

        # Look up latest values from DB
        try:
            esp_repo = ESPRepository(session)
            sensor_repo = SensorRepository(session)

            for esp_id_str, gpio, sensor_type in cross_sensor_keys:
                # Include sensor_type in key for multi-value sensors (SHT31 temp vs humidity)
                sensor_key = (
                    f"{esp_id_str}:{gpio}:{sensor_type}" if sensor_type else f"{esp_id_str}:{gpio}"
                )
                # Look up ESP UUID from device_id
                esp_device = await esp_repo.get_by_device_id(esp_id_str)
                if not esp_device:
                    logger.debug(f"Cross-sensor lookup: ESP {esp_id_str} not found")
                    continue
                if not esp_device.is_online:
                    offline_sensor_refs.append(
                        {
                            "esp_id": esp_id_str,
                            "gpio": gpio,
                            "sensor_type": sensor_type,
                            "reason": "esp_offline",
                        }
                    )
                    logger.debug(
                        "Cross-sensor lookup skipped (ESP offline): %s:%s:%s",
                        esp_id_str,
                        gpio,
                        sensor_type,
                    )
                    continue

                # Get latest sensor reading
                reading = await sensor_repo.get_latest_reading(
                    esp_id=esp_device.id, gpio=gpio, sensor_type=sensor_type
                )
                if reading:
                    display_value = (
                        reading.processed_value
                        if reading.processed_value is not None
                        else reading.raw_value
                    )
                    entry = {
                        "value": display_value,
                        "sensor_type": reading.sensor_type,
                    }
                    # AUT-41: enrich with freshness metadata for require_fresh_data
                    age_seconds = (datetime.now(timezone.utc) - reading.timestamp).total_seconds()
                    entry["age_seconds"] = age_seconds
                    sensor_config = await sensor_repo.get_by_esp_gpio_and_type(
                        esp_id=esp_device.id, gpio=gpio, sensor_type=sensor_type
                    )
                    if sensor_config:
                        entry["operating_mode"] = sensor_config.operating_mode or "continuous"
                        entry["measurement_freshness_hours"] = getattr(
                            sensor_config, "measurement_freshness_hours", None
                        )
                    else:
                        entry["operating_mode"] = "continuous"
                        entry["measurement_freshness_hours"] = None

                    sensor_values[sensor_key] = entry
                    logger.debug(
                        f"Cross-sensor loaded: {sensor_key} = {display_value} "
                        f"({reading.sensor_type})"
                    )
                else:
                    logger.debug(f"Cross-sensor lookup: no data for {sensor_key}")

        except Exception as e:
            logger.warning(f"Failed to load cross-sensor values: {e}")

        return sensor_values, offline_sensor_refs

    async def _emit_conflict_alert(
        self,
        *,
        session,
        rule_id: uuid.UUID,
        rule_name: str,
        trigger_data: dict,
        action: dict,
        conflict_info: dict,
    ) -> None:
        """Persist actuator conflicts into the notification lifecycle (Alert-Center SSOT)."""
        if session is None:
            return

        actuator_key = str(conflict_info.get("actuator_key") or "unknown")
        trace_id = str(conflict_info.get("trace_id") or "")
        title = f"Regelkonflikt auf {actuator_key}"
        body = str(
            conflict_info.get("message")
            or "Aktor-Aktion wurde durch Konflikt-Arbitration blockiert."
        )
        correlation = f"logic_conflict:{trace_id}" if trace_id else None
        fingerprint = (
            f"logic_conflict:{trace_id}" if trace_id else f"logic_conflict:{rule_id}:{actuator_key}"
        )[:64]

        metadata = {
            "event_type": "conflict.arbitration",
            "rule_id": str(rule_id),
            "rule_name": rule_name,
            "trace_id": trace_id or None,
            "actuator_key": actuator_key,
            "winner_rule_id": conflict_info.get("winner_rule_id"),
            "loser_rule_id": conflict_info.get("loser_rule_id"),
            "competing_rules": conflict_info.get("competing_rules") or [],
            "arbitration_mode": conflict_info.get("arbitration_mode"),
            "resolution": conflict_info.get("resolution"),
            "trigger": trigger_data,
            "action": action,
            "ack_effect": "informational",
            "resolve_effect": "informational",
        }

        try:
            router = NotificationRouter(session)
            await router.route(
                NotificationCreate(
                    user_id=None,
                    channel="websocket",
                    severity="warning",
                    category="system",
                    title=title,
                    body=body,
                    metadata=metadata,
                    source="logic_engine",
                    correlation_id=correlation,
                    fingerprint=fingerprint,
                )
            )
        except Exception as notif_err:
            logger.warning(
                "Failed to persist conflict alert for rule %s: %s",
                rule_name,
                notif_err,
            )

    def _extract_sensor_refs_from_conditions(self, conditions) -> list[dict]:
        """
        Extract all sensor references from trigger_conditions.

        Handles three condition types that reference sensor data:
        - "sensor" / "sensor_threshold": Simple threshold conditions
        - "hysteresis": Hysteresis conditions (also have esp_id, gpio, sensor_type)

        Handles two compound formats:
        - {"type": "compound", "conditions": [...]}
        - {"logic": "AND"|"OR", "conditions": [...]}

        Args:
            conditions: Condition dict, compound dict, or list of conditions

        Returns:
            List of dicts with keys: esp_id, gpio, sensor_type
        """
        refs: list[dict] = []

        if isinstance(conditions, list):
            for cond in conditions:
                refs.extend(self._extract_sensor_refs_from_conditions(cond))
            return refs

        if not isinstance(conditions, dict):
            return refs

        cond_type = conditions.get("type", "")
        if cond_type in ("sensor", "sensor_threshold", "hysteresis"):
            esp_id = conditions.get("esp_id")
            gpio = conditions.get("gpio")
            sensor_type = conditions.get("sensor_type")
            if esp_id and sensor_type:
                refs.append({"esp_id": esp_id, "gpio": gpio, "sensor_type": sensor_type})
        elif cond_type == "compound":
            for sub in conditions.get("conditions", []):
                refs.extend(self._extract_sensor_refs_from_conditions(sub))
        elif conditions.get("logic") in ("AND", "OR") and conditions.get("conditions"):
            for sub in conditions["conditions"]:
                refs.extend(self._extract_sensor_refs_from_conditions(sub))

        return refs

    async def _load_sensor_values_for_timer(self, rule, session) -> tuple[dict, list[dict]]:
        """
        Load latest sensor values for all sensor references in a timer rule.

        Used by evaluate_timer_triggered_rules() to enrich Phase-1 context so
        compound rules (time_window + sensor/hysteresis) can evaluate correctly.

        Stale readings (older than 5 minutes) are excluded so the engine does
        not fire rules based on outdated data.

        Args:
            rule: CrossESPLogic rule instance
            session: Active SQLAlchemy async session

        Returns:
            Tuple:
            - sensor_values: Dict mapping "ESP_ID:GPIO:sensor_type" to sensor value dicts
            - offline_sensor_refs: referenced sensors skipped because ESP is offline
        """
        sensor_refs = self._extract_sensor_refs_from_conditions(rule.trigger_conditions)
        if not sensor_refs:
            return {}, []

        sensor_values: dict = {}
        offline_sensor_refs: list[dict] = []
        staleness_limit = datetime.now(timezone.utc) - timedelta(minutes=5)

        esp_repo = ESPRepository(session)
        sensor_repo = SensorRepository(session)

        for ref in sensor_refs:
            esp_id_str = ref["esp_id"]
            gpio = ref["gpio"]
            sensor_type = ref["sensor_type"]

            esp_device = await esp_repo.get_by_device_id(esp_id_str)
            if not esp_device:
                logger.debug(f"Timer sensor lookup: ESP {esp_id_str} not found")
                continue
            if not esp_device.is_online:
                offline_sensor_refs.append(
                    {
                        "esp_id": esp_id_str,
                        "gpio": gpio,
                        "sensor_type": sensor_type,
                        "reason": "esp_offline",
                    }
                )
                logger.debug(
                    "Timer sensor lookup skipped (ESP offline): %s:%s:%s",
                    esp_id_str,
                    gpio,
                    sensor_type,
                )
                continue

            reading = await sensor_repo.get_latest_reading(
                esp_id=esp_device.id,
                gpio=int(gpio),
                sensor_type=sensor_type,
            )
            if reading is None:
                logger.debug(f"Timer sensor lookup: no data for {esp_id_str}:{gpio}:{sensor_type}")
                continue

            # AUT-41: load sensor config once (needed for staleness logging + freshness metadata)
            sensor_config = await sensor_repo.get_by_esp_gpio_and_type(
                esp_id=esp_device.id, gpio=int(gpio), sensor_type=sensor_type
            )
            op_mode = "continuous"
            if sensor_config and sensor_config.operating_mode:
                op_mode = sensor_config.operating_mode

            if reading.timestamp < staleness_limit:
                age_s = (datetime.now(timezone.utc) - reading.timestamp).total_seconds()

                if op_mode in ("on_demand", "scheduled"):
                    logger.warning(
                        f"Timer sensor stale ({op_mode}): {esp_id_str}:{gpio}:{sensor_type} "
                        f"(age: {age_s:.0f}s) — rule '{rule.rule_name}' skipped for this sensor. "
                        f"User should re-measure."
                    )
                else:
                    logger.debug(
                        f"Timer sensor stale: {esp_id_str}:{gpio}:{sensor_type} "
                        f"(age: {age_s:.0f}s > 300s)"
                    )
                continue

            display_value = (
                reading.processed_value
                if reading.processed_value is not None
                else reading.raw_value
            )
            key = f"{esp_id_str}:{gpio}:{sensor_type}" if sensor_type else f"{esp_id_str}:{gpio}"
            age_s = (datetime.now(timezone.utc) - reading.timestamp).total_seconds()
            entry = {
                "esp_id": esp_id_str,
                "gpio": gpio,
                "sensor_type": sensor_type,
                "value": display_value,
                "age_seconds": age_s,
                "operating_mode": op_mode,
                "measurement_freshness_hours": (
                    getattr(sensor_config, "measurement_freshness_hours", None)
                    if sensor_config
                    else None
                ),
            }
            sensor_values[key] = entry
            logger.debug(f"Timer sensor loaded: {key} = {display_value} ({sensor_type})")

        return sensor_values, offline_sensor_refs

    def _extract_target_esp_ids(self, actions: list) -> List[str]:
        """
        Extract ESP IDs from actions for rate limiting.

        Args:
            actions: List of action dictionaries

        Returns:
            List of unique ESP IDs targeted by actions
        """
        esp_ids = set()
        for action in actions:
            if action.get("type") in ("actuator_command", "actuator"):
                esp_id = action.get("esp_id")
                if esp_id:
                    esp_ids.add(esp_id)
            elif action.get("type") == "sequence":
                # Extract ESP IDs from sequence steps
                steps = action.get("steps", [])
                for step in steps:
                    step_action = step.get("action", {})
                    if step_action.get("type") in ("actuator_command", "actuator"):
                        esp_id = step_action.get("esp_id")
                        if esp_id:
                            esp_ids.add(esp_id)
        return list(esp_ids)

    # =========================================================================
    # AUT-111: Degraded-State Tracking for Critical Rules
    # =========================================================================

    async def _enter_degraded_state(
        self,
        rule_id: uuid.UUID,
        rule_name: str,
        reason: str,
        session,
    ) -> None:
        """Mark a critical rule as degraded (once per transition).

        Sets degraded_since/degraded_reason on the DB row and emits a
        ``rule_degraded`` WebSocket event exactly once per entry.
        Non-critical rules are silently ignored.
        """
        from ..db.models.logic import CrossESPLogic

        stmt = select(CrossESPLogic).where(CrossESPLogic.id == rule_id)
        result = await session.execute(stmt)
        rule = result.scalar_one_or_none()
        if not rule or not rule.is_critical:
            return
        if rule.degraded_since is not None:
            return  # already degraded — no double-emit

        now = datetime.now(timezone.utc)
        rule.degraded_since = now
        rule.degraded_reason = reason[:64]
        await session.flush()

        try:
            await self.websocket_manager.broadcast(
                "rule_degraded",
                {
                    "rule_id": str(rule_id),
                    "rule_name": rule_name,
                    "degraded_since": now.isoformat(),
                    "degraded_reason": reason[:64],
                    "reason": reason[:64],
                    "is_critical": True,
                    "escalation_policy": rule.escalation_policy,
                },
            )
        except Exception as ws_err:
            logger.warning(
                "WebSocket rule_degraded broadcast failed for %s: %s",
                rule_name,
                ws_err,
            )
        logger.warning(
            "AUT-111: Rule '%s' entered DEGRADED state: %s",
            rule_name,
            reason[:64],
        )

    async def _exit_degraded_state(
        self,
        rule_id: uuid.UUID,
        rule_name: str,
        session,
    ) -> None:
        """Clear degraded state on recovery and emit ``rule_recovered`` once."""
        from ..db.models.logic import CrossESPLogic

        stmt = select(CrossESPLogic).where(CrossESPLogic.id == rule_id)
        result = await session.execute(stmt)
        rule = result.scalar_one_or_none()
        if not rule or rule.degraded_since is None:
            return  # not degraded — nothing to recover

        old_reason = rule.degraded_reason
        old_since = rule.degraded_since
        rule.degraded_since = None
        rule.degraded_reason = None
        await session.flush()

        try:
            await self.websocket_manager.broadcast(
                "rule_recovered",
                {
                    "rule_id": str(rule_id),
                    "rule_name": rule_name,
                    "recovered_at": datetime.now(timezone.utc).isoformat(),
                    "was_degraded_since": old_since.isoformat() if old_since else None,
                    "was_degraded_reason": old_reason,
                    "was_reason": old_reason,
                },
            )
        except Exception as ws_err:
            logger.warning(
                "WebSocket rule_recovered broadcast failed for %s: %s",
                rule_name,
                ws_err,
            )
        logger.info(
            "AUT-111: Rule '%s' RECOVERED from degraded state (was: %s since %s)",
            rule_name,
            old_reason,
            old_since.isoformat() if old_since else "?",
        )

    def _get_hysteresis_evaluator(self) -> Optional[HysteresisConditionEvaluator]:
        """Return the HysteresisConditionEvaluator from this engine's evaluator list.

        Returns:
            HysteresisConditionEvaluator instance, or None if not present.
        """
        for evaluator in self.condition_evaluators:
            if isinstance(evaluator, HysteresisConditionEvaluator):
                return evaluator
        return None

    def _build_off_actions(self, actions: list) -> list:
        """Build OFF-variant action list from a rule's ON actions.

        Creates an OFF command for every actuator action. Non-actuator action
        types (notifications, delays, …) are excluded — OFF only applies to
        hardware outputs.

        Args:
            actions: List of action dicts from a CrossESPLogic rule.

        Returns:
            List of action dicts with command='OFF', value=0.0, duration=0.
        """
        return [
            {**action, "command": "OFF", "value": 0.0, "duration": 0}
            for action in actions
            if action.get("type") in ("actuator_command", "actuator")
        ]

    # --- Bumpless Transfer helpers (Fix 1) ---

    @staticmethod
    def _extract_hysteresis_conditions(trigger_conditions) -> list[dict]:
        """Extract all hysteresis-type conditions from a trigger_conditions structure."""
        if isinstance(trigger_conditions, list):
            return [c for c in trigger_conditions if c.get("type") == "hysteresis"]
        if isinstance(trigger_conditions, dict):
            if trigger_conditions.get("type") == "hysteresis":
                return [trigger_conditions]
            if "conditions" in trigger_conditions:
                return [
                    c for c in trigger_conditions["conditions"] if c.get("type") == "hysteresis"
                ]
        return []

    @staticmethod
    def _get_condition_at_index(trigger_conditions, index: int) -> "dict | None":
        """Return the condition at position *index* in the full (unfiltered) list."""
        if isinstance(trigger_conditions, list):
            if 0 <= index < len(trigger_conditions):
                return trigger_conditions[index]
            return None
        if isinstance(trigger_conditions, dict):
            if "conditions" in trigger_conditions:
                sub = trigger_conditions["conditions"]
                if 0 <= index < len(sub):
                    return sub[index]
                return None
            if trigger_conditions.get("type") == "hysteresis" and index == 0:
                return trigger_conditions
        return None

    @staticmethod
    def _find_matching_hysteresis(new_conditions: list[dict], old_cond: dict) -> "dict | None":
        """Return the first condition in *new_conditions* pointing to the same sensor as *old_cond*."""
        for nc in new_conditions:
            if (
                nc.get("esp_id") == old_cond.get("esp_id")
                and nc.get("gpio") == old_cond.get("gpio")
                and nc.get("sensor_type") == old_cond.get("sensor_type")
            ):
                return nc
        return None

    @staticmethod
    def _hysteresis_params_changed(old_cond: dict, new_cond: dict) -> bool:
        """Return True if any threshold value changed between two hysteresis conditions."""
        _THRESHOLD_KEYS = (
            "activate_below",
            "deactivate_above",
            "activate_above",
            "deactivate_below",
        )
        return any(old_cond.get(k) != new_cond.get(k) for k in _THRESHOLD_KEYS)

    async def on_rule_updated(
        self, rule_id: str, old_trigger_conditions=None, force: bool = False
    ) -> None:
        """React to a rule update committed via the API.

        Called by logic_service.update_rule() after the DB commit.  Performs
        three steps in order:

        1. Selective hysteresis state reset ("Bumpless Transfer"): only reset
           states where the hysteresis condition itself changed.  Orthogonal
           changes (e.g. adding/removing a time_window) leave the hysteresis
           state untouched so the actuator does not flap.
        2. If any state was active (actuator was ON), immediately send an OFF
           command to the actuator — the new rule config determines whether ON
           should be re-sent.
        3. Re-evaluate the rule with the latest sensor values from DB so the
           new configuration takes effect without waiting for the next sensor
           event or timer tick.  If no fresh data is available (all readings
           older than 5 min) the re-evaluation is deferred to the next real
           sensor event.

        Args:
            rule_id: Rule UUID as string.
            old_trigger_conditions: The rule's trigger_conditions *before* the
                update.  When provided, enables bumpless transfer (only
                hysteresis states whose conditions actually changed are reset).
                When None, all hysteresis states for the rule are reset
                unconditionally (legacy behavior).
            force: AUT-1135 (A4). True only when the update actually changed
                conditions or actions (computed by the caller). Propagated into
                the Step-3c re-evaluation trigger's "force" field, which is the
                sole thing `_evaluate_rule()` checks to decide whether to bypass
                the rule's cooldown/settle window. A save that only touches timer
                parameters (cooldown_seconds, settle_seconds, ...) must NOT reset
                a currently running cooldown/settle window to zero.
        """
        try:
            async for session in get_session():
                logic_repo = LogicRepository(session)

                # Load rule from DB (needed for Steps 1, 2, and 3)
                try:
                    rule = await logic_repo.get_by_id(uuid.UUID(rule_id))
                except (ValueError, Exception) as exc:
                    logger.error("on_rule_updated: invalid rule_id '%s': %s", rule_id, exc)
                    return

                if not rule:
                    logger.warning("on_rule_updated: rule %s not found in DB", rule_id)
                    return

                # Step 1: selective hysteresis state reset — "Bumpless Transfer"
                # Only reset states whose hysteresis condition actually changed.
                # Orthogonal changes (e.g. adding/removing a time_window alongside
                # an unchanged hysteresis) must not disrupt the hysteresis state.
                hysteresis_eval = self._get_hysteresis_evaluator()
                active_keys: list[str] = []
                if hysteresis_eval:
                    if old_trigger_conditions is not None:
                        new_hysteresis = self._extract_hysteresis_conditions(
                            rule.trigger_conditions
                        )
                        existing_keys = [
                            k for k in hysteresis_eval._states if k.startswith(f"{rule_id}:")
                        ]
                        for state_key in existing_keys:
                            try:
                                condition_index = int(state_key.split(":", 1)[1])
                            except (ValueError, IndexError):
                                continue
                            old_cond = self._get_condition_at_index(
                                old_trigger_conditions, condition_index
                            )
                            if old_cond is None or old_cond.get("type") != "hysteresis":
                                # State for a non-hysteresis index: clean up
                                hysteresis_eval.remove_state(state_key)
                                continue
                            new_cond = self._find_matching_hysteresis(new_hysteresis, old_cond)
                            if new_cond is None or self._hysteresis_params_changed(
                                old_cond, new_cond
                            ):
                                # Condition removed or thresholds changed → reset
                                if hysteresis_eval.remove_state(state_key):
                                    active_keys.append(state_key)
                            # else: identical condition — preserve state (bumpless transfer)
                    else:
                        # No old conditions provided → unconditional reset (legacy fallback)
                        active_keys = hysteresis_eval.reset_states_for_rule(rule_id)

                # Step 2: send OFF to actuators that were active under the old config
                if active_keys:
                    off_trigger = {
                        "type": "rule_update",
                        "rule_id": rule_id,
                        "timestamp": int(time.time()),
                    }
                    off_actions = [
                        {**action, "command": "OFF", "value": 0.0, "duration": 0}
                        for action in rule.actions
                        if action.get("type") in ("actuator_command", "actuator")
                    ]
                    if off_actions:
                        logger.info(
                            "Rule %s updated while %d actuator(s) active — sending OFF",
                            rule.rule_name,
                            len(off_actions),
                        )
                        await self._execute_actions(
                            off_actions,
                            off_trigger,
                            rule.id,
                            rule.rule_name,
                            rule.priority,
                            rule_is_critical=bool(getattr(rule, "is_critical", False)),
                            session=session,
                        )
                        await session.commit()

                # Step 3: disabled-rule and pure-TimeWindow fast-paths
                #
                # Step 3a: disabled rule → send OFF (if previously executed) and exit early
                if not rule.enabled:
                    last_exec = await logic_repo.get_last_execution(rule.id)
                    if last_exec:
                        off_actions = self._build_off_actions(rule.actions)
                        if off_actions:
                            off_trigger = {
                                "type": "rule_update",
                                "rule_id": rule_id,
                                "timestamp": int(time.time()),
                            }
                            await self._execute_actions(
                                off_actions,
                                off_trigger,
                                rule.id,
                                rule.rule_name,
                                rule.priority,
                                rule_is_critical=bool(getattr(rule, "is_critical", False)),
                                session=session,
                            )
                            await session.commit()
                    logger.info(
                        "on_rule_updated: rule '%s' is disabled — re-evaluation skipped",
                        rule.rule_name,
                    )
                    break

                # Step 3b: pure TimeWindow (no sensor refs) → evaluate conditions directly.
                # These rules have no sensor readings to load. _load_sensor_values_for_timer
                # returns {} and the Stale-Data-Guard below would abort re-evaluation.
                # Instead, check the time condition directly using the current clock.
                sensor_refs = self._extract_sensor_refs_from_conditions(rule.trigger_conditions)
                if not sensor_refs:
                    re_eval_context = {
                        "current_time": datetime.now(timezone.utc),
                        "sensor_values": {},
                        "sensor_data": {},
                        "rule_id": str(rule.id),
                        "rule_name": rule.rule_name,
                        "condition_index": 0,
                    }
                    conditions_met = await self._check_conditions(
                        rule.trigger_conditions,
                        re_eval_context,
                        logic_operator=rule.logic_operator,
                    )
                    re_eval_trigger = {
                        "type": "rule_update",
                        "rule_id": rule_id,
                        "timestamp": int(time.time()),
                    }
                    if conditions_met:
                        await self._execute_actions(
                            rule.actions,
                            re_eval_trigger,
                            rule.id,
                            rule.rule_name,
                            rule.priority,
                            rule_is_critical=bool(getattr(rule, "is_critical", False)),
                            session=session,
                        )
                        await session.commit()
                        logger.info(
                            "on_rule_updated: pure-TimeWindow rule '%s' → "
                            "conditions_met=True, actions executed",
                            rule.rule_name,
                        )
                    else:
                        last_exec = await logic_repo.get_last_execution(rule.id)
                        if last_exec:
                            off_actions = self._build_off_actions(rule.actions)
                            if off_actions:
                                await self._execute_actions(
                                    off_actions,
                                    re_eval_trigger,
                                    rule.id,
                                    rule.rule_name,
                                    rule.priority,
                                    rule_is_critical=bool(getattr(rule, "is_critical", False)),
                                    session=session,
                                )
                                await session.commit()
                            logger.info(
                                "on_rule_updated: pure-TimeWindow rule '%s' → "
                                "conditions_met=False, OFF sent (last execution: %s)",
                                rule.rule_name,
                                last_exec.timestamp,
                            )
                        else:
                            logger.info(
                                "on_rule_updated: pure-TimeWindow rule '%s' → "
                                "conditions_met=False, no OFF needed (never executed)",
                                rule.rule_name,
                            )
                    break  # Step 3 complete for sensor-less rules

                # Step 3c: rules with sensor refs → re-evaluate with fresh values from DB
                sensor_values, _offline_sensor_refs = await self._load_sensor_values_for_timer(
                    rule, session
                )

                if not sensor_values:
                    logger.info(
                        "on_rule_updated: no fresh sensor data for rule '%s' "
                        "(all readings older than 5 min). Re-evaluation deferred "
                        "to next sensor event.",
                        rule.rule_name,
                    )
                    break

                first_val = next(iter(sensor_values.values()))
                primary_sensor_data: dict = {
                    "esp_id": first_val.get("esp_id"),
                    "gpio": first_val.get("gpio"),
                    "sensor_type": first_val.get("sensor_type"),
                    "value": first_val.get("value"),
                }

                re_eval_trigger = {
                    "type": "rule_update",
                    "rule_id": rule_id,
                    "timestamp": int(time.time()),
                    "force": force,
                    **primary_sensor_data,
                }
                batch_locks: list = []
                try:
                    await self._evaluate_rule(
                        rule, re_eval_trigger, logic_repo, batch_locks=batch_locks
                    )
                finally:
                    for lock in batch_locks:
                        await self.conflict_manager.release_actuator(
                            esp_id=lock["esp_id"],
                            gpio=lock["gpio"],
                            rule_id=lock["rule_id"],
                        )

                # Step 4: Post-Re-Eval OFF-Guard (BUG 1 — Compound rule, time-window change)
                #
                # Scenario: Bumpless Transfer correctly preserved the hysteresis state
                # (Step 1 was correct). Re-evaluation called _evaluate_rule which returned
                # with conditions_met=False but WITHOUT the _hysteresis_just_deactivated
                # path (sensor is still in deadband, threshold not crossed). The actuator
                # remains ON even though the compound condition is no longer satisfied.
                #
                # Fix: call _check_conditions() directly with the current sensor data
                # to get the authoritative conditions_met. If False AND active hysteresis
                # states remain, the compound failed while hysteresis held state → send OFF.
                #
                # Using _check_conditions() (not the state proxy) avoids spurious OFF
                # when conditions_met=True but states are still active (deadband + TW open).
                post_eval_context = {
                    "current_time": datetime.now(timezone.utc),
                    "sensor_values": sensor_values,
                    "sensor_data": primary_sensor_data,
                    "rule_id": str(rule.id),
                    "rule_name": rule.rule_name,
                    "condition_index": 0,
                }
                post_conditions_met = await self._check_conditions(
                    rule.trigger_conditions,
                    post_eval_context,
                    logic_operator=rule.logic_operator,
                )
                if not post_conditions_met:
                    hysteresis_eval = self._get_hysteresis_evaluator()
                    if hysteresis_eval:
                        remaining_active = [
                            key
                            for key, state in list(hysteresis_eval._states.items())
                            if key.startswith(f"{rule_id}:") and state.is_active
                        ]
                        if remaining_active:
                            logger.info(
                                "on_rule_updated: Post-Re-Eval OFF-Guard — rule '%s': "
                                "%d active hysteresis state(s) after conditions_met=False, "
                                "sending OFF",
                                rule.rule_name,
                                len(remaining_active),
                            )
                            for key in remaining_active:
                                hysteresis_eval.remove_state(key)
                            off_actions = self._build_off_actions(rule.actions)
                            if off_actions:
                                off_guard_trigger = {
                                    "type": "rule_update",
                                    "rule_id": rule_id,
                                    "timestamp": int(time.time()),
                                }
                                await self._execute_actions(
                                    off_actions,
                                    off_guard_trigger,
                                    rule.id,
                                    rule.rule_name,
                                    rule.priority,
                                    rule_is_critical=bool(getattr(rule, "is_critical", False)),
                                    session=session,
                                )
                                await session.commit()

                break  # Exit after first session

        except Exception as e:
            logger.error("on_rule_updated failed for rule %s: %s", rule_id, e, exc_info=True)

    async def _evaluation_loop(self) -> None:
        """
        Background evaluation loop.

        Currently runs periodically to check for any pending evaluations.
        In the future, this could be enhanced to handle queued evaluations.
        """
        logger.info("Logic Engine evaluation loop started")

        while self._running:
            try:
                # Sleep for a short interval
                await asyncio.sleep(1.0)

                # Future: Could process queued evaluations here
                # For now, evaluation is triggered directly by sensor_handler

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in evaluation loop: {e}", exc_info=True)
                await asyncio.sleep(5.0)  # Wait before retrying

        logger.info("Logic Engine evaluation loop stopped")


# Global Logic Engine instance (set by main.py on startup)
_logic_engine_instance: Optional[LogicEngine] = None


def get_logic_engine() -> Optional[LogicEngine]:
    """
    Get global Logic Engine instance.

    Returns:
        LogicEngine instance if initialized, None otherwise
    """
    return _logic_engine_instance


def set_logic_engine(instance: LogicEngine) -> None:
    """
    Set global Logic Engine instance.

    Should be called by main.py on startup.

    Args:
        instance: LogicEngine instance
    """
    global _logic_engine_instance
    _logic_engine_instance = instance
