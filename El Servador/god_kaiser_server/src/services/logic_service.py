"""
Logic Rules Management Service

Business logic for logic rule management, validation, and testing.
"""

import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy.exc import IntegrityError

from ..core.logging_config import get_logger
from ..db.models.logic import CrossESPLogic
from ..db.repositories import ActuatorRepository, ESPRepository, LogicRepository, SensorRepository
from ..db.session import get_session
from ..schemas.logic import (
    ActionResult,
    ConditionResult,
    LogicRuleCreate,
    LogicRuleUpdate,
    RuleBulkQuickUpdateResult,
    RuleTestRequest,
    RuleTestResponse,
)
from ..sensors.sensor_type_registry import (
    get_plausible_range_for_sensor_type,
    get_unit_for_sensor_type,
)
from .logic.actions import (
    BaseActionExecutor,
)
from .logic.conditions import (
    BaseConditionEvaluator,
    CompoundConditionEvaluator,
    HysteresisConditionEvaluator,
    MetadataFilterEvaluator,
    SensorConditionEvaluator,
    SensorDiffConditionEvaluator,
    TimeConditionEvaluator,
)
from .logic.conditions.diagnostics_evaluator import DiagnosticsConditionEvaluator
from .logic.validator import LogicValidator, ValidationResult

logger = get_logger(__name__)

# AUT-1268 E1: logic-rule thresholds are stored/compared in the canonical sensor
# unit (EC → µS/cm). No runtime conversion in the hysteresis evaluator.
_HYSTERESIS_THRESHOLD_KEYS = (
    "activate_below",
    "activate_above",
    "deactivate_below",
    "deactivate_above",
)


def get_affected_esp_ids(rule: CrossESPLogic) -> set[str]:
    """
    Extract all ESP IDs referenced by rule actions.

    Used for config-push fanout after rule CRUD/toggle so every affected ESP
    receives an updated combined configuration.
    """
    esp_ids: set[str] = set()
    for action in rule.actions or []:
        if not isinstance(action, dict):
            continue
        esp_id = action.get("esp_id")
        if esp_id is None:
            continue
        esp_ids.add(str(esp_id))
    return esp_ids


class LogicService:
    """
    Logic Rules Management Service.

    Provides business logic for:
    - Rule CRUD operations with validation
    - Rule testing/simulation
    - Rule querying by sensor/timer
    """

    def __init__(
        self,
        logic_repo: LogicRepository,
        validator: Optional[LogicValidator] = None,
        condition_evaluators: Optional[List[BaseConditionEvaluator]] = None,
        action_executors: Optional[List[BaseActionExecutor]] = None,
    ):
        """
        Initialize Logic Service.

        Args:
            logic_repo: LogicRepository instance
            validator: Optional LogicValidator instance (creates default if None)
            condition_evaluators: Optional list of condition evaluators (creates defaults if None)
            action_executors: Optional list of action executors (creates defaults if None)
        """
        self.logic_repo = logic_repo
        self.validator = validator or LogicValidator()

        # Setup default condition evaluators
        if condition_evaluators is None:
            sensor_eval = SensorConditionEvaluator()
            sensor_diff_eval = SensorDiffConditionEvaluator()
            time_eval = TimeConditionEvaluator()
            hysteresis_eval = HysteresisConditionEvaluator()
            diagnostics_eval = DiagnosticsConditionEvaluator(session_factory=get_session)
            metadata_filter_eval = MetadataFilterEvaluator()
            compound_eval = CompoundConditionEvaluator(
                [
                    sensor_eval,
                    sensor_diff_eval,
                    time_eval,
                    hysteresis_eval,
                    diagnostics_eval,
                    metadata_filter_eval,
                ]
            )
            self.condition_evaluators = [
                sensor_eval,
                sensor_diff_eval,
                time_eval,
                hysteresis_eval,
                diagnostics_eval,
                metadata_filter_eval,
                compound_eval,
            ]
        else:
            self.condition_evaluators = condition_evaluators

        # Setup default action executors (will need dependencies)
        # Note: These should be injected by the caller
        self.action_executors = action_executors or []

    async def create_rule(self, rule_data: LogicRuleCreate) -> CrossESPLogic:
        """
        Create a new logic rule with validation.

        Args:
            rule_data: Rule creation data

        Returns:
            Created CrossESPLogic instance

        Raises:
            ValueError: If validation fails
        """
        # Convert to dict for validation
        rule_dict = rule_data.model_dump()

        # Get existing rules for conflict checking
        existing_rules = await self.logic_repo.get_all()
        existing_dicts = [
            {
                "name": r.name,
                "conditions": r.conditions,
                "actions": r.actions,
            }
            for r in existing_rules
        ]

        # Validate rule
        validation_result = self.validator.validate(rule_dict, existing_dicts)

        if not validation_result.valid:
            errors = "; ".join(validation_result.errors)
            raise ValueError(f"Rule validation failed: {errors}")

        # Log warnings if any
        if validation_result.warnings:
            for warning in validation_result.warnings:
                logger.warning(f"Rule validation warning: {warning}")

        # AUT-994 B1: pump actions must never fire on stale sensor data
        await self._enforce_pump_freshness(rule_dict["conditions"], rule_dict["actions"])

        # Create rule
        rule = CrossESPLogic(
            rule_name=rule_data.name,
            description=rule_data.description,
            trigger_conditions=rule_data.conditions,
            actions=rule_data.actions,
            logic_operator=rule_data.logic_operator,
            enabled=rule_data.enabled,
            priority=rule_data.priority,
            cooldown_seconds=rule_data.cooldown_seconds,
            settle_after_rule_id=rule_data.settle_after_rule_id,
            settle_seconds=rule_data.settle_seconds,
            max_executions_per_hour=rule_data.max_executions_per_hour,
            max_executions_per_day=rule_data.max_executions_per_day,
            max_dose_ml_per_day=rule_data.max_dose_ml_per_day,
            is_critical=rule_data.is_critical,
            escalation_policy=rule_data.escalation_policy,
            rule_metadata=rule_data.rule_metadata,
            rule_group=rule_data.rule_group,
            follows_plan=rule_data.follows_plan,
            plan_zone_id=rule_data.plan_zone_id,
            plan_subzone_config_id=rule_data.plan_subzone_config_id,
            plan_domain=rule_data.plan_domain,
            plan_measure=rule_data.plan_measure,
        )

        try:
            created = await self.logic_repo.create(rule)
            await self.logic_repo.session.commit()
        except IntegrityError as e:
            await self.logic_repo.session.rollback()
            if "rule_name" in str(e) or "ix_cross_esp_logic_rule_name" in str(e):
                raise ValueError(f"Rule with name '{rule_data.name}' already exists")
            raise ValueError(f"Database constraint violation: {e}")

        logger.info(f"Logic rule created: '{created.name}' (ID: {created.id})")

        # AUT-1116/1117/1274: non-blocking warnings (paired-rule deadband,
        # pi_enhanced trigger sensor, threshold plausibility). Transient attribute
        # (not a DB column) — read by the API layer to populate
        # LogicRuleResponse.warnings, never persisted.
        created.rule_warnings = (
            await self._check_paired_rule_deadband(
                rule_data.conditions, rule_data.rule_metadata, self_rule_id=created.id
            )
            + await self._check_pi_enhanced_warning(rule_data.conditions)
            + self._check_threshold_plausibility(rule_data.conditions)
        )

        return created

    async def update_rule(
        self,
        rule_id: uuid.UUID,
        updates: LogicRuleUpdate,
        *,
        force_reeval: Optional[bool] = None,
    ) -> Optional[CrossESPLogic]:
        """
        Update an existing logic rule with validation.

        Args:
            rule_id: Rule ID
            updates: Update data
            force_reeval: AUT-1145 (S0). None (default) = auto-compute via
                _rule_behavior_changed() as usual — this is what PUT
                /rules/{rule_id} does and its behavior is unchanged. Bulk
                quick-field updates (bulk_quick_update_rules) pass False
                explicitly: a quick-field edit (e.g. a threshold value) DOES
                change `conditions` and would otherwise force-bypass a running
                cooldown/settle window (AUT-1135 Falle 2) — bulk edits must
                never do that, unlike a deliberate single-rule editor save.

        Returns:
            Updated CrossESPLogic instance, or None if not found

        Raises:
            ValueError: If validation fails
        """
        # Get existing rule
        rule = await self.logic_repo.get_by_id(rule_id)
        if not rule:
            return None

        # Get update data (only provided fields)
        update_dict = updates.model_dump(exclude_unset=True)

        # Merge with existing rule for validation
        rule_dict = {
            "name": update_dict.get("name", rule.name),
            "description": update_dict.get("description", rule.description),
            "conditions": update_dict.get("conditions", rule.conditions),
            "actions": update_dict.get("actions", rule.actions),
            "logic_operator": update_dict.get("logic_operator", rule.logic_operator),
            "enabled": update_dict.get("enabled", rule.enabled),
            "priority": update_dict.get("priority", rule.priority),
            "cooldown_seconds": update_dict.get("cooldown_seconds", rule.cooldown_seconds),
            "max_executions_per_hour": update_dict.get(
                "max_executions_per_hour", rule.max_executions_per_hour
            ),
        }

        # Get existing rules (excluding current rule) for conflict checking
        existing_rules = await self.logic_repo.get_all()
        existing_dicts = [
            {
                "name": r.name,
                "conditions": r.conditions,
                "actions": r.actions,
            }
            for r in existing_rules
            if r.id != rule_id
        ]

        # Validate updated rule
        validation_result = self.validator.validate(rule_dict, existing_dicts)

        if not validation_result.valid:
            errors = "; ".join(validation_result.errors)
            raise ValueError(f"Rule validation failed: {errors}")

        # Log warnings if any
        if validation_result.warnings:
            for warning in validation_result.warnings:
                logger.warning(f"Rule update validation warning: {warning}")

        # AUT-994 B1: pump actions must never fire on stale sensor data
        await self._enforce_pump_freshness(rule_dict["conditions"], rule_dict["actions"])

        # Capture old trigger_conditions before applying updates so that
        # on_rule_updated() can perform a selective (bumpless transfer) reset.
        old_trigger_conditions = (
            list(rule.trigger_conditions)
            if isinstance(rule.trigger_conditions, list)
            else rule.trigger_conditions
        )

        # AUT-1135 (A4): the rule_update re-evaluation trigger only bypasses the
        # rule's cooldown/settle window when the update actually changes what the
        # rule DOES (conditions, actions, or logic_operator). A save that only
        # touches timer parameters (cooldown_seconds, settle_seconds,
        # max_executions_per_hour, ...) must respect the currently running
        # cooldown/settle — otherwise every save resets it to zero.
        rule_behavior_changed = self._rule_behavior_changed(
            old_conditions=rule.conditions,
            old_actions=rule.actions,
            old_logic_operator=rule.logic_operator,
            new_conditions=rule_dict["conditions"],
            new_actions=rule_dict["actions"],
            new_logic_operator=rule_dict["logic_operator"],
        )
        # AUT-1145 (S0): force_reeval=None (single-rule PUT, default) keeps the
        # auto-computed value; bulk_quick_update_rules() passes False explicitly.
        force = rule_behavior_changed if force_reeval is None else force_reeval

        # Apply updates
        for field, value in update_dict.items():
            if field == "name":
                rule.rule_name = value
            elif field == "conditions":
                rule.trigger_conditions = value
            else:
                setattr(rule, field, value)

        await self.logic_repo.session.flush()
        await self.logic_repo.session.commit()

        logger.info(f"Logic rule updated: '{rule.name}' (ID: {rule.id})")

        # B3-fix: notify the running LogicEngine so it can reset hysteresis state,
        # send OFF to any actuators that were active, and re-evaluate immediately.
        from .logic_engine import get_logic_engine

        engine = get_logic_engine()
        if engine:
            await engine.on_rule_updated(
                str(rule.id),
                old_trigger_conditions=old_trigger_conditions,
                force=force,
            )

        # AUT-1116/1117/1274: non-blocking warnings (paired-rule deadband,
        # pi_enhanced trigger sensor, threshold plausibility). Transient attribute
        # (not a DB column) — read by the API layer to populate
        # LogicRuleResponse.warnings, never persisted.
        rule.rule_warnings = (
            await self._check_paired_rule_deadband(
                rule_dict["conditions"], rule.rule_metadata, self_rule_id=rule.id
            )
            + await self._check_pi_enhanced_warning(rule_dict["conditions"])
            + self._check_threshold_plausibility(rule_dict["conditions"])
        )

        return rule

    @staticmethod
    def _rule_behavior_changed(
        *,
        old_conditions: Any,
        old_actions: Any,
        old_logic_operator: Optional[str],
        new_conditions: Any,
        new_actions: Any,
        new_logic_operator: Optional[str],
    ) -> bool:
        """AUT-1135 (A4): single source of truth for "did this update change what
        the rule DOES" (conditions, actions, or the AND/OR combinator) vs. a save
        that only touched timer/limit parameters (cooldown_seconds, settle_seconds,
        max_executions_per_hour, priority, enabled, ...).

        Used by update_rule() to decide whether the rule_update re-evaluation
        trigger may bypass the rule's cooldown/settle window (force=True) or must
        respect it like any other trigger (force=False).
        """

        def _as_condition_list(value: Any) -> Any:
            # Mirrors CrossESPLogic.conditions property: a single legacy-format
            # condition dict is equivalent to a one-element list, not a distinct
            # value — comparing raw shapes would report a "change" that never happened.
            return value if isinstance(value, list) else [value]

        old_actions_normalized = list(old_actions) if isinstance(old_actions, list) else old_actions
        return (
            _as_condition_list(new_conditions) != _as_condition_list(old_conditions)
            or new_actions != old_actions_normalized
            or new_logic_operator != old_logic_operator
        )

    # =========================================================================
    # AUT-1145 (S0): Bulk Quick-Update — thin loop, no second write path
    # =========================================================================

    @staticmethod
    def _patch_quick_field_conditions(
        conditions: Any,
        *,
        threshold_value: Optional[float] = None,
        hysteresis_on_value: Optional[float] = None,
        hysteresis_off_value: Optional[float] = None,
        start_hour: Optional[int] = None,
        start_minute: Optional[int] = None,
        end_hour: Optional[int] = None,
        end_minute: Optional[int] = None,
        days_of_week: Optional[List[int]] = None,
    ) -> List[Dict[str, Any]]:
        """AUT-1145: apply bulk quick-field values onto the first matching
        condition(s) of a rule's (possibly compound) conditions.

        Returns a plain conditions list — the caller feeds it into a normal
        LogicRuleUpdate(conditions=...) and persists via update_rule() like any
        other PUT /rules/{id} payload. This function never touches the DB and
        is NOT a second write path, only a pre-processing step required because
        `conditions` is a whole-field PATCH, not a per-key JSON merge.

        Raises ValueError if a quick-field was requested but no condition of
        the matching type exists on this rule (caller reports this per rule_id
        instead of aborting the whole batch).
        """
        wants_patch = any(
            v is not None
            for v in (
                threshold_value,
                hysteresis_on_value,
                hysteresis_off_value,
                start_hour,
                start_minute,
                end_hour,
                end_minute,
                days_of_week,
            )
        )
        patched = False

        def _walk(node: Any) -> Any:
            nonlocal patched
            if isinstance(node, list):
                return [_walk(item) for item in node]
            if not isinstance(node, dict):
                return node
            if node.get("logic") in ("AND", "OR"):
                return {**node, "conditions": _walk(node.get("conditions", []))}

            cond_type = node.get("type")
            if threshold_value is not None and cond_type in ("sensor_threshold", "sensor"):
                patched = True
                return {**node, "value": threshold_value}
            if cond_type == "hysteresis" and (
                hysteresis_on_value is not None or hysteresis_off_value is not None
            ):
                updated = dict(node)
                if node.get("activate_above") is not None:
                    if hysteresis_on_value is not None:
                        updated["activate_above"] = hysteresis_on_value
                    if hysteresis_off_value is not None:
                        updated["deactivate_below"] = hysteresis_off_value
                elif node.get("activate_below") is not None:
                    if hysteresis_on_value is not None:
                        updated["activate_below"] = hysteresis_on_value
                    if hysteresis_off_value is not None:
                        updated["deactivate_above"] = hysteresis_off_value
                else:
                    return node
                patched = True
                return updated
            if cond_type in ("time_window", "time") and any(
                v is not None
                for v in (start_hour, start_minute, end_hour, end_minute, days_of_week)
            ):
                updated = dict(node)
                if start_hour is not None:
                    updated["start_hour"] = start_hour
                if start_minute is not None:
                    updated["start_minute"] = start_minute
                if end_hour is not None:
                    updated["end_hour"] = end_hour
                if end_minute is not None:
                    updated["end_minute"] = end_minute
                if days_of_week is not None:
                    updated["days_of_week"] = days_of_week
                patched = True
                return updated
            return node

        conditions_list = list(conditions) if isinstance(conditions, list) else [conditions]
        result = _walk(conditions_list)
        if wants_patch and not patched:
            raise ValueError("Rule has no matching condition for the requested quick-field(s)")
        return result

    async def bulk_quick_update_rules(
        self,
        rule_ids: List[uuid.UUID],
        *,
        active: Optional[bool] = None,
        threshold_value: Optional[float] = None,
        hysteresis_on_value: Optional[float] = None,
        hysteresis_off_value: Optional[float] = None,
        start_hour: Optional[int] = None,
        start_minute: Optional[int] = None,
        end_hour: Optional[int] = None,
        end_minute: Optional[int] = None,
        days_of_week: Optional[List[int]] = None,
    ) -> List[RuleBulkQuickUpdateResult]:
        """AUT-1145 (S0): Bulk quick-field update for the group-card Schnellfeld.

        THIN LOOP around the existing single-rule update_rule() — every rule_id
        goes through the exact same validation and config-push a single PUT
        /rules/{id} would trigger. No second write path.

        force_reeval=False is passed explicitly on every call (AUT-1135 Falle
        2): a quick-field threshold/zeiten edit DOES change `conditions`, which
        would otherwise make _rule_behavior_changed() return True and
        force-bypass a currently running cooldown/settle window. Unlike a
        deliberate single-rule editor save (where that bypass is the intended
        "admin intent must take effect immediately"), a bulk quick-edit across
        possibly many rules must never do that — the existing cooldown
        reference point (real last execution) stays untouched.

        priority and cooldown_seconds are never touched here — the group-card
        quick-field intentionally excludes them (AUT-1145 SOLL, editor-only).
        """
        wants_condition_patch = any(
            v is not None
            for v in (
                threshold_value,
                hysteresis_on_value,
                hysteresis_off_value,
                start_hour,
                start_minute,
                end_hour,
                end_minute,
                days_of_week,
            )
        )

        results: List[RuleBulkQuickUpdateResult] = []
        for rule_id in rule_ids:
            try:
                rule = await self.logic_repo.get_by_id(rule_id)
                if not rule:
                    results.append(
                        RuleBulkQuickUpdateResult(
                            rule_id=rule_id, success=False, error="Rule not found"
                        )
                    )
                    continue

                update_fields: Dict[str, Any] = {}
                if active is not None:
                    update_fields["enabled"] = active
                if wants_condition_patch:
                    update_fields["conditions"] = self._patch_quick_field_conditions(
                        rule.conditions,
                        threshold_value=threshold_value,
                        hysteresis_on_value=hysteresis_on_value,
                        hysteresis_off_value=hysteresis_off_value,
                        start_hour=start_hour,
                        start_minute=start_minute,
                        end_hour=end_hour,
                        end_minute=end_minute,
                        days_of_week=days_of_week,
                    )

                if update_fields:
                    await self.update_rule(
                        rule_id, LogicRuleUpdate(**update_fields), force_reeval=False
                    )
                results.append(RuleBulkQuickUpdateResult(rule_id=rule_id, success=True))
            except ValueError as e:
                results.append(
                    RuleBulkQuickUpdateResult(rule_id=rule_id, success=False, error=str(e))
                )

        return results

    async def validate_rule(
        self, rule_data: Dict[str, Any], existing_rules: Optional[List[CrossESPLogic]] = None
    ) -> ValidationResult:
        """
        Validate a rule without creating/updating it.

        Args:
            rule_data: Rule data dictionary
            existing_rules: Optional list of existing rules for conflict checking

        Returns:
            ValidationResult with validation status
        """
        existing_dicts = None
        if existing_rules:
            existing_dicts = [
                {
                    "name": r.name,
                    "conditions": r.conditions,
                    "actions": r.actions,
                }
                for r in existing_rules
            ]

        return self.validator.validate(rule_data, existing_dicts)

    async def test_rule(
        self, rule: CrossESPLogic, test_request: RuleTestRequest
    ) -> RuleTestResponse:
        """
        Test/simulate rule execution with mock data.

        Args:
            rule: Rule to test
            test_request: Test parameters with mock data

        Returns:
            RuleTestResponse with test results
        """
        # Evaluate conditions with mock data
        condition_results = []

        conditions = rule.conditions
        if isinstance(conditions, dict) and conditions.get("logic"):
            # Compound condition
            conditions_list = conditions.get("conditions", [])
        elif isinstance(conditions, list):
            conditions_list = conditions
        else:
            conditions_list = [conditions]

        for idx, condition in enumerate(conditions_list):
            cond_type = condition.get("type", "unknown")
            result = False
            details = ""
            actual_value = None

            # Find appropriate evaluator
            evaluator = None
            for eval_obj in self.condition_evaluators:
                if eval_obj.supports(cond_type):
                    evaluator = eval_obj
                    break

            if cond_type in ("sensor_threshold", "sensor"):
                esp_id = condition.get("esp_id", "")
                gpio = condition.get("gpio", 0)

                # Get mock value, or fall back to latest real sensor reading from DB
                mock_key = f"{esp_id}:{gpio}"
                if test_request.mock_sensor_values and mock_key in test_request.mock_sensor_values:
                    actual_value = test_request.mock_sensor_values[mock_key]
                else:
                    # Query latest real sensor data from DB
                    actual_value = await self._get_latest_sensor_value(esp_id, gpio)
                    if actual_value is None:
                        actual_value = 0.0

                # Create context
                context = {
                    "sensor_data": {
                        "esp_id": esp_id,
                        "gpio": gpio,
                        "value": actual_value,
                        "sensor_type": condition.get("sensor_type"),
                    }
                }

                if evaluator:
                    result = await evaluator.evaluate(condition, context)

                operator = condition.get("operator", "==")
                threshold = condition.get("value", 0)
                details = f"{esp_id}:{gpio} ({actual_value}) {operator} {threshold}"

            elif cond_type in ("time_window", "time"):
                # Create context with mock time
                current_time = None
                if test_request.mock_time:
                    # Parse HH:MM format
                    try:
                        parts = test_request.mock_time.split(":")
                        from datetime import time

                        current_time = time(int(parts[0]), int(parts[1]))
                        # Convert to datetime for evaluation
                        from datetime import datetime, timezone

                        current_time = datetime.combine(
                            datetime.now(timezone.utc).date(), current_time
                        )
                    except (ValueError, IndexError):
                        pass

                context = {"current_time": current_time}

                if evaluator:
                    result = await evaluator.evaluate(condition, context)

                start_time = condition.get("start_time") or condition.get("start_hour", 0)
                end_time = condition.get("end_time") or condition.get("end_hour", 24)
                details = f"Time {test_request.mock_time or 'now'} in [{start_time}, {end_time}]"

            elif cond_type == "hysteresis":
                # AUT-1124: Dry-run must use the same HysteresisConditionEvaluator
                # as the live path (logic_engine → hysteresis_evaluator.evaluate).
                # LogicService defaults create the evaluator without session_factory,
                # so /test does not persist LogicHysteresisState. API constructs a
                # fresh LogicService per request → no cross-request state bleed into
                # the LogicEngine instance.
                esp_id = condition.get("esp_id", "")
                gpio = condition.get("gpio", 0)

                mock_key = f"{esp_id}:{gpio}"
                if test_request.mock_sensor_values and mock_key in test_request.mock_sensor_values:
                    actual_value = test_request.mock_sensor_values[mock_key]
                else:
                    actual_value = await self._get_latest_sensor_value(esp_id, gpio)
                    if actual_value is None:
                        actual_value = 0.0

                context = {
                    "rule_id": str(rule.id),
                    "condition_index": idx,
                    "sensor_data": {
                        "esp_id": esp_id,
                        "gpio": gpio,
                        "value": actual_value,
                        "sensor_type": condition.get("sensor_type"),
                    },
                }

                if evaluator:
                    result = await evaluator.evaluate(condition, context)

                if condition.get("activate_below") is not None:
                    details = (
                        f"{esp_id}:{gpio} ({actual_value}) hysteresis "
                        f"activate_below={condition.get('activate_below')} "
                        f"deactivate_above={condition.get('deactivate_above')}"
                    )
                else:
                    details = (
                        f"{esp_id}:{gpio} ({actual_value}) hysteresis "
                        f"activate_above={condition.get('activate_above')} "
                        f"deactivate_below={condition.get('deactivate_below')}"
                    )

            condition_results.append(
                ConditionResult(
                    condition_index=idx,
                    condition_type=cond_type,
                    result=result,
                    details=details,
                    actual_value=actual_value,
                )
            )

        # AUT-1337: reuse AUT-1317 per-action condition_refs gate (Live-Engine helpers).
        # No second evaluation path — LogicEngine static/class methods only.
        from .logic_engine import LogicEngine

        logic_op = rule.logic_operator or "AND"
        results_bool = [c.result for c in condition_results]
        global_conditions_met = LogicEngine._combine_condition_results(results_bool, logic_op)

        raw_actions = rule.actions if isinstance(rule.actions, list) else [rule.actions]
        actions: List[Dict[str, Any]] = [a for a in raw_actions if isinstance(a, dict)]
        has_routed_actions = LogicEngine._rule_has_routed_actions(actions)

        action_results: List[ActionResult] = []
        if has_routed_actions:
            # WYSIWYG: report every action with individual gate (Fall-1 visible even when
            # global AND is false).
            would_trigger = False
            for act_idx, action in enumerate(actions):
                would_execute = LogicEngine._action_passes_condition_gate(
                    action,
                    results_bool,
                    global_conditions_met,
                    logic_op,
                )
                if would_execute:
                    would_trigger = True
                action_results.append(
                    ActionResult(
                        action_index=act_idx,
                        action_type=action.get("type", "unknown"),
                        would_execute=would_execute,
                        details=self._format_test_action_details(action),
                        dry_run=test_request.dry_run,
                    )
                )
        else:
            # D4 / legacy: flat AND/OR over all conditions; actions only if global gate.
            would_trigger = global_conditions_met
            if would_trigger:
                for act_idx, action in enumerate(actions):
                    action_results.append(
                        ActionResult(
                            action_index=act_idx,
                            action_type=action.get("type", "unknown"),
                            would_execute=True,
                            details=self._format_test_action_details(action),
                            dry_run=test_request.dry_run,
                        )
                    )

        return RuleTestResponse(
            success=True,
            rule_id=rule.id,
            rule_name=rule.name,
            would_trigger=would_trigger,
            condition_results=condition_results,
            action_results=action_results,
            dry_run=test_request.dry_run,
        )

    @staticmethod
    def _format_test_action_details(action: Dict[str, Any]) -> str:
        """Human-readable action summary for dry-run test results (no I/O)."""
        action_type = action.get("type", "unknown")
        if action_type in ("actuator_command", "actuator"):
            return (
                f"{action.get('esp_id', '?')}:{action.get('gpio', '?')} "
                f"{action.get('command', '?')}"
            )
        if action_type == "notification":
            return f"{action.get('channel', '?')} → {action.get('target', '?')}"
        if action_type == "delay":
            return f"Wait {action.get('seconds', '?')}s"
        if action_type == "sequence":
            steps = action.get("steps", [])
            return f"Sequence with {len(steps)} steps"
        if action_type in ("plugin", "autoops_trigger"):
            return f"Plugin: {action.get('plugin_id', '?')}"
        if action_type == "run_diagnostic":
            check = action.get("check_name")
            return f"Diagnostic: {check or 'full'}"
        return str(action)

    async def get_rules_with_sensor(
        self, esp_id: str, gpio: int, sensor_type: str
    ) -> List[CrossESPLogic]:
        """
        Get rules that trigger on a specific sensor.

        Args:
            esp_id: ESP device ID
            gpio: GPIO pin number
            sensor_type: Sensor type

        Returns:
            List of matching rules
        """
        return await self.logic_repo.get_rules_by_trigger_sensor(
            esp_id=esp_id, gpio=gpio, sensor_type=sensor_type
        )

    async def get_rules_with_timer(self) -> List[CrossESPLogic]:
        """
        Get all enabled rules that have time_window conditions.

        Returns:
            List of rules with timer conditions
        """
        all_rules = await self.logic_repo.get_enabled_rules()

        timer_rules = []
        for rule in all_rules:
            conditions = rule.conditions

            # Check if rule has time_window condition
            if isinstance(conditions, dict):
                if conditions.get("type") in ("time_window", "time"):
                    timer_rules.append(rule)
                elif conditions.get("logic"):
                    # Compound condition - check sub-conditions
                    sub_conditions = conditions.get("conditions", [])
                    for sub_cond in sub_conditions:
                        if sub_cond.get("type") in ("time_window", "time"):
                            timer_rules.append(rule)
                            break
            elif isinstance(conditions, list):
                for cond in conditions:
                    if cond.get("type") in ("time_window", "time"):
                        timer_rules.append(rule)
                        break

        return timer_rules

    async def _get_latest_sensor_value(self, esp_id: str, gpio: int) -> Optional[float]:
        """
        Get the latest real sensor value from the database.

        Uses the logic_repo's session to query sensor_data directly,
        matching by device_id string and gpio pin.

        Args:
            esp_id: ESP device ID string (e.g., "ESP_00000001")
            gpio: GPIO pin number

        Returns:
            Latest processed_value or raw_value, or None if no data found
        """
        try:
            from sqlalchemy import text

            result = await self.logic_repo.session.execute(
                text(
                    "SELECT sd.processed_value, sd.raw_value "
                    "FROM sensor_data sd "
                    "JOIN esp_devices ed ON sd.esp_id = ed.id "
                    "WHERE ed.device_id = :esp_id AND sd.gpio = :gpio "
                    "ORDER BY sd.timestamp DESC LIMIT 1"
                ),
                {"esp_id": esp_id, "gpio": gpio},
            )
            row = result.fetchone()
            if row:
                return float(row[0]) if row[0] is not None else float(row[1])
        except Exception as e:
            logger.warning(f"Failed to fetch latest sensor value for {esp_id}:{gpio}: {e}")
        return None

    @staticmethod
    def _flatten_sensor_conditions(conditions: Any) -> List[Dict[str, Any]]:
        """Recursively collect every sensor condition from a (possibly nested) structure.

        Handles single dicts, flat lists, and arbitrarily nested compound conditions
        ({"logic": "AND"/"OR", "conditions": [...]}) — a sensor condition buried inside
        a compound sub-item must still be subject to the pump-freshness check.
        """
        collected: List[Dict[str, Any]] = []

        def _walk(node: Any) -> None:
            if isinstance(node, list):
                for item in node:
                    _walk(item)
            elif isinstance(node, dict):
                if node.get("logic") in ("AND", "OR"):
                    _walk(node.get("conditions", []))
                elif node.get("type") in ("sensor_threshold", "sensor"):
                    collected.append(node)
                # Other condition types (time_window, hysteresis, ...) carry no
                # require_fresh_data flag and are intentionally ignored here.

        _walk(conditions)
        return collected

    @staticmethod
    def _iter_actuator_actions(actions: List[Dict[str, Any]]):
        """Yield every actuator action dict, descending one level into sequence steps.

        A rule can target a pump directly (type "actuator"/"actuator_command") or inside
        a sequence step ({"action": {...}}). Nested sequences are rejected by the sequence
        executor, so a single level of descent is sufficient.
        """
        for action in actions:
            if not isinstance(action, dict):
                continue
            action_type = action.get("type")
            if action_type in ("actuator_command", "actuator"):
                yield action
            elif action_type == "sequence":
                for step in action.get("steps", []) or []:
                    if not isinstance(step, dict):
                        continue
                    step_action = step.get("action")
                    if isinstance(step_action, dict) and step_action.get("type") in (
                        "actuator_command",
                        "actuator",
                    ):
                        yield step_action

    # =========================================================================
    # AUT-1145 (S0): Rule Group Derivation — single source of truth
    # =========================================================================

    @staticmethod
    def _condition_types(conditions: Any) -> set:
        """Collect every condition 'type' value from a (possibly nested) structure.

        Mirrors the _walk descent pattern of _flatten_sensor_conditions(), but
        collects the type of every condition instead of filtering to one kind —
        derive_rule_group() needs to know which mechanics a rule combines.
        """
        types: set = set()

        def _walk(node: Any) -> None:
            if isinstance(node, list):
                for item in node:
                    _walk(item)
            elif isinstance(node, dict):
                if node.get("logic") in ("AND", "OR"):
                    _walk(node.get("conditions", []))
                cond_type = node.get("type")
                if cond_type:
                    types.add(cond_type)

        _walk(conditions)
        return types

    # sensor_type -> Messgrößen-Kategorie, spiegelt AggCategory / getSensorAggCategory()
    # 1:1 (El Frontend/src/utils/sensorDefaults.ts:1610-1654). Python kann die TS-Datei
    # nicht importieren, daher hier dupliziert — bei Änderungen an AggCategory von Hand
    # synchron halten. Nur die substring-Regeln werden gespiegelt (die dortige
    # SENSOR_TYPE_CONFIG-Fallback-Tabelle ist reines Editor-Detail ohne Entsprechung in
    # echten condition.sensor_type-Werten, siehe AUT-1163-Analyse).
    _SENSOR_TYPE_KEYWORDS: tuple[tuple[str, str], ...] = (
        ("temp", "temperatur"),
        ("humid", "luftfeuchte"),
        ("pressure", "luftdruck"),
        ("light", "licht"),
        ("lux", "licht"),
        ("co2", "co2"),
        ("moisture", "bodenfeuchte"),
        ("soil", "bodenfeuchte"),
        ("flow", "durchfluss"),
    )

    @staticmethod
    def _sensor_type_to_messgroesse(sensor_type: Optional[str]) -> Optional[str]:
        """AUT-1173 (TAX-5): map a condition's sensor_type to its Messgrößen-Kategorie.

        Real sensor_type values are not always the canonical name (e.g. the
        "Luftbefeuchtung" rule stores "sht31_humidity", not "humidity") — mirrors
        the frontend's substring-matching approach for exactly that reason, not a
        stricter exact-match dict.
        """
        if not sensor_type:
            return None
        lowered = sensor_type.lower()
        if lowered == "ph":
            return "ph"
        if lowered == "ec":
            return "ec"
        if lowered == "ds18b20":
            return "temperatur"
        for keyword, category in LogicService._SENSOR_TYPE_KEYWORDS:
            if keyword in lowered:
                return category
        return None

    @staticmethod
    def derive_rule_group(
        rule_group: Optional[str],
        conditions: Any,
        actions: List[Dict[str, Any]],
        rule_metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """AUT-1173 (TAX-5): single source of truth for a rule's display group —
        Variante C (Robin's decision, AUT-1163).

        An explicit `rule_group` override always wins. Otherwise the group is
        derived in this fixed axis order:

        1. Sicherheit — at least one actuator action switches an actuator OFF.
           Checked FIRST, independent of the condition's shape. This is the fix
           for AUT-1163's root cause: the old code checked "hysteresis+actuator"
           before the safety branch, so a hysteresis-shaped emergency shutdown
           (e.g. "temp > 40 -> heater OFF, < 35 -> heater ON") was swallowed by
           "klima" and never reached the safety check at all.
        2. Messgröße — at least one sensor/threshold/hysteresis condition exists
           -> category via _sensor_type_to_messgroesse() on the FIRST such
           condition in definition order (ties never resolved via the action).
           A time+sensor combination lands here too, never in "zeitplan".
        3. Zeitplan — only time-window condition(s), no sensor condition at all.
        4. Sonstiges — everything else, including an unresolvable sensor_type.

        `rule_metadata` is accepted for call-site/schema compatibility but no
        longer inspected: AUT-1163 (L4, Option a) retired "alarm"/"dosierung" as
        their own groups — rule execution (dosing/notifying/switching) becomes a
        display badge INSIDE the Messgröße group instead (AUT-1176/TAX-8).

        NEVER re-implement this in the frontend — Monitor and Editor views
        would drift apart (the exact failure AUT-1145 fixes).
        """
        if rule_group:
            return rule_group

        actuator_actions = list(LogicService._iter_actuator_actions(actions or []))
        if any(a.get("command") == "OFF" for a in actuator_actions):
            return "sicherheit"

        def _first_sensor_condition(node: Any) -> Optional[Dict[str, Any]]:
            """Mirrors the _walk descent pattern of _condition_types() (AUT-1173,
            TAX-5, L2): first sensor/threshold/hysteresis condition in definition
            order wins ties — never the targeted actuator, which carries no formal
            measurand in the data model (that would be a fragile heuristic)."""
            if isinstance(node, list):
                for item in node:
                    found = _first_sensor_condition(item)
                    if found is not None:
                        return found
                return None
            if isinstance(node, dict):
                if node.get("logic") in ("AND", "OR"):
                    return _first_sensor_condition(node.get("conditions", []))
                if node.get("type") in ("sensor", "sensor_threshold", "hysteresis"):
                    return node
            return None

        first_sensor_condition = _first_sensor_condition(conditions)
        if first_sensor_condition is not None:
            category = LogicService._sensor_type_to_messgroesse(
                first_sensor_condition.get("sensor_type")
            )
            return category or "sonstiges"

        condition_types = LogicService._condition_types(conditions)
        if condition_types & {"time_window", "time"}:
            return "zeitplan"
        return "sonstiges"

    @staticmethod
    def _extract_hysteresis_thresholds(conditions: Any) -> Dict[str, float]:
        """Find the first hysteresis condition in a (possibly compound) condition
        structure and return its activate_below/activate_above values, if present.

        Mirrors the _walk descent pattern of _flatten_sensor_conditions(), but
        stops at the first hysteresis condition instead of collecting all matches
        — a rule pairing (DP4) has exactly one relevant trigger threshold per side.
        """

        def _walk(node: Any) -> Optional[Dict[str, Any]]:
            if isinstance(node, list):
                for item in node:
                    found = _walk(item)
                    if found is not None:
                        return found
                return None
            if isinstance(node, dict):
                if node.get("logic") in ("AND", "OR"):
                    return _walk(node.get("conditions", []))
                if node.get("type") == "hysteresis":
                    return node
            return None

        condition = _walk(conditions)
        if not condition:
            return {}
        thresholds: Dict[str, float] = {}
        if condition.get("activate_below") is not None:
            thresholds["activate_below"] = condition["activate_below"]
        if condition.get("activate_above") is not None:
            thresholds["activate_above"] = condition["activate_above"]
        return thresholds

    async def _check_paired_rule_deadband(
        self,
        conditions: Any,
        rule_metadata: Optional[Dict[str, Any]],
        self_rule_id: Optional[uuid.UUID] = None,
    ) -> List[str]:
        """
        AUT-1116 (DP4): Non-blocking warning when this rule's hysteresis trigger
        threshold overlaps with its paired rule's threshold (rule_metadata.paired_rule_id,
        e.g. EC-Anheben <-> EC-Senken, pH-Plus <-> pH-Minus).

        Fail-open (mirrors _compute_chemistry_dose_ml() in logic_engine.py): any lookup
        or parsing problem just skips the warning (WARNING-log) — NEVER raises, NEVER
        blocks rule creation/update. Leitplanke: keine Blocker fuer die Logic Engine.
        """
        warnings: List[str] = []
        paired_rule_id = (rule_metadata or {}).get("paired_rule_id")
        if not paired_rule_id:
            return warnings

        try:
            paired_uuid = uuid.UUID(str(paired_rule_id))
            if self_rule_id and paired_uuid == self_rule_id:
                return warnings

            paired_rule = await self.logic_repo.get_by_id(paired_uuid)
            if not paired_rule:
                return warnings

            my_thresholds = self._extract_hysteresis_thresholds(conditions)
            paired_thresholds = self._extract_hysteresis_thresholds(paired_rule.conditions)

            low = my_thresholds.get("activate_below", paired_thresholds.get("activate_below"))
            high = my_thresholds.get("activate_above", paired_thresholds.get("activate_above"))

            if low is not None and high is not None and low >= high:
                message = (
                    f"Totband-Warnung: Schwelle {low} ueberlappt mit gekoppelter Regel "
                    f"'{paired_rule.name}' (Schwelle {high}) — kein Sicherheitsabstand "
                    "zwischen den Regeln, moegliches Gegendosieren/Flattern."
                )
                logger.warning(message)
                warnings.append(message)
        except Exception as e:
            logger.warning("DP4 deadband check skipped (paired_rule_id=%s): %s", paired_rule_id, e)

        return warnings

    @staticmethod
    def _collect_ec_ph_trigger_sensors(conditions: Any) -> List[Dict[str, Any]]:
        """Recursively collect every EC/pH sensor reference from a (possibly nested)
        condition structure.

        Unlike _flatten_sensor_conditions() (which intentionally excludes hysteresis
        conditions — they carry no require_fresh_data flag), this DOES include
        "hysteresis" conditions: EC/pH dosing rules in this system use type="hysteresis"
        (see AUT-1102 E1/E7, seed rules "EC Steuerung"/"PH MINUS").
        """
        collected: List[Dict[str, Any]] = []

        def _walk(node: Any) -> None:
            if isinstance(node, list):
                for item in node:
                    _walk(item)
            elif isinstance(node, dict):
                if node.get("logic") in ("AND", "OR"):
                    _walk(node.get("conditions", []))
                elif node.get("type") in ("sensor_threshold", "sensor", "hysteresis"):
                    sensor_type = str(node.get("sensor_type") or "").lower()
                    if sensor_type in ("ec", "ph"):
                        collected.append(node)

        _walk(conditions)
        return collected

    @staticmethod
    def _check_threshold_plausibility(conditions: Any) -> List[str]:
        """
        AUT-1274: Non-blocking warning when a hysteresis threshold lies far outside
        the typical operating range for its sensor_type (canonical unit from F1 SSOT).

        Fail-open: NEVER raises, NEVER blocks save. Example (E1=µS/cm): EC threshold
        ``1.6`` warns; ``1600`` does not.
        """
        warnings: List[str] = []

        def _walk(node: Any) -> None:
            if isinstance(node, list):
                for item in node:
                    _walk(item)
                return
            if not isinstance(node, dict):
                return
            if node.get("logic") in ("AND", "OR"):
                _walk(node.get("conditions", []))
                return
            if node.get("type") != "hysteresis":
                return
            sensor_type = str(node.get("sensor_type") or "")
            plausible = get_plausible_range_for_sensor_type(sensor_type)
            if not plausible:
                return
            unit = get_unit_for_sensor_type(sensor_type) or ""
            unit_suffix = f" ({unit})" if unit else ""
            for key in _HYSTERESIS_THRESHOLD_KEYS:
                raw = node.get(key)
                if raw is None:
                    continue
                try:
                    value = float(raw)
                except (TypeError, ValueError):
                    continue
                if value < plausible["min"] or value > plausible["max"]:
                    hint = ""
                    if sensor_type.lower() == "ec" and value < plausible["min"]:
                        hint = " — meintest du mS/cm?"
                    message = (
                        f"Plausibilitaets-Warnung: {key}={value} liegt weit ausserhalb "
                        f"des typischen {sensor_type}-Bereichs"
                        f"{unit_suffix} [{plausible['min']}…{plausible['max']}]{hint}"
                    )
                    logger.warning(message)
                    warnings.append(message)

        try:
            _walk(conditions)
        except Exception as e:
            logger.warning("AUT-1274 threshold plausibility check skipped: %s", e)
        return warnings

    async def _check_pi_enhanced_warning(self, conditions: Any) -> List[str]:
        """
        AUT-1117 (S7, DP7): Non-blocking warning when an EC-/pH-Dosier-Regel's trigger
        sensor is NOT pi_enhanced=True. ATC temperature compensation only runs for
        pi_enhanced sensors (sensor_handler.py:332) — otherwise the rule doses on the
        unkompensierten Rohwert (sensor_handler.py:847, value=processed_value or raw_value).

        Reuses the same warnings mechanism as S6/DP4 — fail-open, NEVER raises, NEVER
        blocks rule creation/update.
        """
        warnings: List[str] = []
        try:
            for condition in self._collect_ec_ph_trigger_sensors(conditions):
                esp_id = condition.get("esp_id")
                gpio = condition.get("gpio")
                if esp_id is None or gpio is None:
                    continue
                try:
                    gpio_int = int(gpio)
                except (ValueError, TypeError):
                    continue

                esp_repo = ESPRepository(self.logic_repo.session)
                sensor_repo = SensorRepository(self.logic_repo.session)

                esp_device = await esp_repo.get_by_device_id(esp_id)
                if not esp_device:
                    continue

                sensor_config = await sensor_repo.get_by_esp_and_gpio(esp_device.id, gpio_int)
                if sensor_config and not sensor_config.pi_enhanced:
                    message = (
                        f"pi_enhanced-Warnung: Trigger-Sensor {esp_id}:{gpio} "
                        f"({condition.get('sensor_type')}) hat pi_enhanced=False — "
                        "die Regel dosiert auf unkompensierten Rohwerten (keine ATC-Korrektur)."
                    )
                    logger.warning(message)
                    warnings.append(message)
        except Exception as e:
            logger.warning("DP7 pi_enhanced check skipped: %s", e)

        return warnings

    async def _enforce_pump_freshness(self, conditions: Any, actions: List[Dict[str, Any]]) -> None:
        """
        AUT-994 B1: A rule that dispatches to a dosing pump (ActuatorConfig.hardware_type
        == "pump") must only trigger on fresh sensor data — a stale pH/EC reading must
        never be allowed to start a pump. No AUT-645 dependency: this only requires the
        require_fresh_data flag already present on SensorCondition (default False).

        Covers pumps addressed both directly and inside sequence steps, and sensor
        conditions nested inside compound conditions.

        Raises:
            ValueError: If any action targets a pump but not all sensor conditions
                set require_fresh_data=True.
        """
        if not isinstance(actions, list):
            return

        esp_repo = ESPRepository(self.logic_repo.session)
        actuator_repo = ActuatorRepository(self.logic_repo.session)

        targets_pump = False
        for actuator_action in self._iter_actuator_actions(actions):
            esp_id = actuator_action.get("esp_id")
            gpio = actuator_action.get("gpio")
            if esp_id is None or gpio is None:
                continue
            try:
                gpio_int = int(gpio)
            except (ValueError, TypeError):
                continue

            esp_device = await esp_repo.get_by_device_id(esp_id)
            if not esp_device:
                continue

            actuator = await actuator_repo.get_by_esp_and_gpio(esp_device.id, gpio_int)
            if actuator and actuator.hardware_type == "pump":
                targets_pump = True
                break

        if not targets_pump:
            return

        sensor_conditions = self._flatten_sensor_conditions(conditions)
        missing_fresh = [
            f"{c.get('esp_id')}:{c.get('gpio')}"
            for c in sensor_conditions
            if not c.get("require_fresh_data")
        ]
        if missing_fresh:
            raise ValueError(
                "Rule targets a pump actuator — all sensor conditions must set "
                f"require_fresh_data=True to prevent dosing on stale data. "
                f"Missing require_fresh_data on: {', '.join(missing_fresh)}"
            )
