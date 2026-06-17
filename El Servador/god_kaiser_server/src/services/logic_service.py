"""
Logic Rules Management Service

Business logic for logic rule management, validation, and testing.
"""

import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy.exc import IntegrityError

from ..core.logging_config import get_logger
from ..db.models.logic import CrossESPLogic
from ..db.repositories import LogicRepository
from ..db.session import get_session
from ..schemas.logic import (
    ActionResult,
    ConditionResult,
    LogicRuleCreate,
    LogicRuleUpdate,
    RuleTestRequest,
    RuleTestResponse,
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
            max_executions_per_hour=rule_data.max_executions_per_hour,
            is_critical=rule_data.is_critical,
            escalation_policy=rule_data.escalation_policy,
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

        return created

    async def update_rule(
        self, rule_id: uuid.UUID, updates: LogicRuleUpdate
    ) -> Optional[CrossESPLogic]:
        """
        Update an existing logic rule with validation.

        Args:
            rule_id: Rule ID
            updates: Update data

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

        # Capture old trigger_conditions before applying updates so that
        # on_rule_updated() can perform a selective (bumpless transfer) reset.
        old_trigger_conditions = (
            list(rule.trigger_conditions)
            if isinstance(rule.trigger_conditions, list)
            else rule.trigger_conditions
        )

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
                str(rule.id), old_trigger_conditions=old_trigger_conditions
            )

        return rule

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
        all_conditions_met = True

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

            if not result:
                all_conditions_met = False

            condition_results.append(
                ConditionResult(
                    condition_index=idx,
                    condition_type=cond_type,
                    result=result,
                    details=details,
                    actual_value=actual_value,
                )
            )

        # Check logic operator
        logic_op = rule.logic_operator or "AND"
        if logic_op == "OR":
            would_trigger = any(c.result for c in condition_results)
        else:  # AND
            would_trigger = all_conditions_met and len(condition_results) > 0

        # Build action results (show what would happen)
        action_results = []
        if would_trigger:
            actions = rule.actions if isinstance(rule.actions, list) else [rule.actions]
            for act_idx, action in enumerate(actions):
                action_type = action.get("type", "unknown")
                details = ""
                if action_type in ("actuator_command", "actuator"):
                    details = (
                        f"{action.get('esp_id', '?')}:{action.get('gpio', '?')} "
                        f"{action.get('command', '?')}"
                    )
                elif action_type == "notification":
                    details = f"{action.get('channel', '?')} → {action.get('target', '?')}"
                elif action_type == "delay":
                    details = f"Wait {action.get('seconds', '?')}s"
                elif action_type == "sequence":
                    steps = action.get("steps", [])
                    details = f"Sequence with {len(steps)} steps"
                elif action_type in ("plugin", "autoops_trigger"):
                    details = f"Plugin: {action.get('plugin_id', '?')}"
                elif action_type == "run_diagnostic":
                    check = action.get("check_name")
                    details = f"Diagnostic: {check or 'full'}"
                else:
                    details = str(action)

                action_results.append(
                    ActionResult(
                        action_index=act_idx,
                        action_type=action_type,
                        would_execute=True,
                        details=details,
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
