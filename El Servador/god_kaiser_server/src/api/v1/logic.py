"""
Logic Rules & Automation API Endpoints

Phase: 5 (Week 9-10) - API Layer
Priority: 🟡 HIGH
Status: IMPLEMENTED

Provides:
- GET /rules - List all rules
- POST /rules - Create rule
- GET /rules/{rule_id} - Get rule details
- PUT /rules/{rule_id} - Update rule
- DELETE /rules/{rule_id} - Delete rule
- POST /rules/{rule_id}/toggle - Enable/disable
- POST /rules/{rule_id}/test - Simulate execution
- GET /execution_history - Query history

References:
    - .claude/PI_SERVER_REFACTORING.md (Lines 164-172)
- services/logic_engine.py (Rule execution)
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, status

from ...core.exceptions import RuleNotFoundException, RuleValidationException
from ...core.logging_config import get_logger
from ...db.repositories import LogicRepository
from ...services.actuator_service import ActuatorService
from ...services.logic_service import LogicService, get_affected_esp_ids
from ...schemas import (
    ExecutionHistoryEntry,
    ExecutionHistoryResponse,
    LogicRuleCreate,
    LogicRuleListResponse,
    LogicRuleResponse,
    LogicRuleUpdate,
    RuleTestRequest,
    RuleTestResponse,
    RuleToggleRequest,
    RuleToggleResponse,
    TemplateDetailResponse,
    TemplateListResponse,
)
from ...schemas.common import PaginationMeta
from ..deps import (
    ActiveUser,
    DBSession,
    OperatorUser,
    get_actuator_service,
    get_config_builder,
    get_esp_service,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/logic", tags=["logic"])


def _build_rule_response(
    rule,
    exec_count: int = 0,
    last_exec_success: "bool | None" = None,
) -> LogicRuleResponse:
    """Build LogicRuleResponse from a CrossESPLogic instance (DRY helper)."""
    return LogicRuleResponse(
        id=rule.id,
        name=rule.name,
        description=rule.description,
        conditions=rule.conditions,
        actions=rule.actions,
        logic_operator=rule.logic_operator,
        enabled=rule.enabled,
        priority=rule.priority,
        cooldown_seconds=rule.cooldown_seconds,
        max_executions_per_hour=rule.max_executions_per_hour,
        last_triggered=rule.last_triggered,
        execution_count=exec_count,
        last_execution_success=last_exec_success,
        is_critical=rule.is_critical,
        escalation_policy=rule.escalation_policy,
        degraded_since=rule.degraded_since,
        degraded_reason=rule.degraded_reason,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


async def _push_config_to_affected_esps(db: DBSession, esp_ids: set[str], context: str) -> None:
    """Build and push combined config for each affected ESP (best effort)."""
    if not esp_ids:
        return

    config_builder = get_config_builder(db)
    esp_service = get_esp_service(db)

    for esp_id in esp_ids:
        try:
            combined_config = await config_builder.build_combined_config(esp_id, db)
            schedule_result = await esp_service.send_config_coalesced(
                device_id=esp_id,
                config=combined_config,
                reason_code="logic_config_change",
            )
            logger.info(
                "Config push coalesced for ESP %s after %s (merged=%s)",
                esp_id,
                context,
                schedule_result.get("merged", False),
            )
        except Exception as exc:
            logger.warning(
                "Failed to publish config to ESP %s after %s: %s",
                esp_id,
                context,
                exc,
            )


# =============================================================================
# List Rules
# =============================================================================


@router.get(
    "/rules",
    response_model=LogicRuleListResponse,
    summary="List logic rules",
    description="Get all automation rules.",
)
async def list_rules(
    db: DBSession,
    current_user: ActiveUser,
    enabled: Annotated[Optional[bool], Query(description="Filter by enabled status")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> LogicRuleListResponse:
    """
    List all logic rules.

    Args:
        db: Database session
        current_user: Authenticated user
        enabled: Optional enabled filter
        page: Page number
        page_size: Items per page

    Returns:
        Paginated list of rules
    """
    logic_repo = LogicRepository(db)

    # Get all rules
    rules = await logic_repo.get_all()

    # Apply filter
    if enabled is not None:
        rules = [r for r in rules if r.enabled == enabled]

    # Sort by priority (lower number = higher priority, shown first)
    rules.sort(key=lambda r: r.priority)

    # Pagination
    total_items = len(rules)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paginated = rules[start_idx:end_idx]

    # Build responses
    responses = []
    for rule in paginated:
        exec_count = await logic_repo.get_execution_count(rule.id)
        last_exec = await logic_repo.get_last_execution(rule.id)
        responses.append(
            _build_rule_response(rule, exec_count, last_exec.success if last_exec else None)
        )

    return LogicRuleListResponse(
        success=True,
        data=responses,
        pagination=PaginationMeta.from_pagination(page, page_size, total_items),
    )


# =============================================================================
# Degraded Rules (AUT-111)
# =============================================================================


@router.get(
    "/degraded",
    response_model=LogicRuleListResponse,
    summary="List degraded logic rules",
    description="Get all rules currently in degraded state (AUT-111).",
)
async def list_degraded_rules(
    db: DBSession,
    current_user: ActiveUser,
    critical_only: Annotated[bool, Query(description="Only return is_critical=True rules")] = False,
) -> LogicRuleListResponse:
    """List rules whose degraded_since is not null."""
    logic_repo = LogicRepository(db)
    rules = await logic_repo.get_degraded_rules(critical_only=critical_only)

    responses = []
    for rule in rules:
        exec_count = await logic_repo.get_execution_count(rule.id)
        last_exec = await logic_repo.get_last_execution(rule.id)
        responses.append(
            _build_rule_response(rule, exec_count, last_exec.success if last_exec else None)
        )

    return LogicRuleListResponse(
        success=True,
        data=responses,
        pagination=PaginationMeta.from_pagination(1, len(responses) or 1, len(responses)),
    )


# =============================================================================
# Get Rule
# =============================================================================


@router.get(
    "/rules/{rule_id}",
    response_model=LogicRuleResponse,
    responses={
        200: {"description": "Rule found"},
        404: {"description": "Rule not found"},
    },
    summary="Get logic rule",
    description="Get details of a specific rule.",
)
async def get_rule(
    rule_id: uuid.UUID,
    db: DBSession,
    current_user: ActiveUser,
) -> LogicRuleResponse:
    """
    Get logic rule by ID.

    Args:
        rule_id: Rule ID
        db: Database session
        current_user: Authenticated user

    Returns:
        Rule details
    """
    logic_repo = LogicRepository(db)

    rule = await logic_repo.get_by_id(rule_id)
    if not rule:
        raise RuleNotFoundException(rule_id)

    exec_count = await logic_repo.get_execution_count(rule.id)
    last_exec = await logic_repo.get_last_execution(rule.id)

    return _build_rule_response(rule, exec_count, last_exec.success if last_exec else None)


# =============================================================================
# Create Rule
# =============================================================================


@router.post(
    "/rules",
    response_model=LogicRuleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create logic rule",
    description="Create a new automation rule.",
)
async def create_rule(
    request: LogicRuleCreate,
    db: DBSession,
    current_user: OperatorUser,
) -> LogicRuleResponse:
    """
    Create a new logic rule.

    Args:
        request: Rule data
        db: Database session
        current_user: Operator or admin user

    Returns:
        Created rule
    """
    logic_repo = LogicRepository(db)
    logic_service = LogicService(logic_repo)

    # Create rule using LogicService (with validation)
    try:
        created = await logic_service.create_rule(request)
    except ValueError as e:
        raise RuleValidationException(str(e))

    logger.info(
        f"Logic rule created: '{created.name}' (ID: {created.id}) by {current_user.username}"
    )
    await _push_config_to_affected_esps(
        db,
        get_affected_esp_ids(created),
        context="logic rule create",
    )

    exec_count = await logic_repo.get_execution_count(created.id)
    last_exec = await logic_repo.get_last_execution(created.id)

    return _build_rule_response(created, exec_count, last_exec.success if last_exec else None)


# =============================================================================
# Update Rule
# =============================================================================


@router.put(
    "/rules/{rule_id}",
    response_model=LogicRuleResponse,
    responses={
        200: {"description": "Rule updated"},
        404: {"description": "Rule not found"},
    },
    summary="Update logic rule",
    description="Update an existing rule.",
)
async def update_rule(
    rule_id: uuid.UUID,
    request: LogicRuleUpdate,
    db: DBSession,
    current_user: OperatorUser,
) -> LogicRuleResponse:
    """
    Update logic rule.

    Args:
        rule_id: Rule ID
        request: Update data
        db: Database session
        current_user: Operator or admin user

    Returns:
        Updated rule
    """
    logic_repo = LogicRepository(db)
    logic_service = LogicService(logic_repo)

    # Update rule using LogicService (with validation)
    try:
        rule = await logic_service.update_rule(rule_id, request)
    except ValueError as e:
        raise RuleValidationException(str(e))

    if not rule:
        raise RuleNotFoundException(rule_id)

    exec_count = await logic_repo.get_execution_count(rule.id)
    last_exec = await logic_repo.get_last_execution(rule.id)

    logger.info(f"Logic rule updated: '{rule.name}' (ID: {rule.id}) by {current_user.username}")
    await _push_config_to_affected_esps(
        db,
        get_affected_esp_ids(rule),
        context="logic rule update",
    )

    return _build_rule_response(rule, exec_count, last_exec.success if last_exec else None)


# =============================================================================
# Delete Rule
# =============================================================================


@router.delete(
    "/rules/{rule_id}",
    response_model=LogicRuleResponse,
    responses={
        200: {"description": "Rule deleted"},
        404: {"description": "Rule not found"},
    },
    summary="Delete logic rule",
    description="Delete an automation rule.",
)
async def delete_rule(
    rule_id: uuid.UUID,
    db: DBSession,
    current_user: OperatorUser,
) -> LogicRuleResponse:
    """
    Delete logic rule.

    Args:
        rule_id: Rule ID
        db: Database session
        current_user: Operator or admin user

    Returns:
        Deleted rule
    """
    logic_repo = LogicRepository(db)

    rule = await logic_repo.get_by_id(rule_id)
    if not rule:
        raise RuleNotFoundException(rule_id)

    affected_esp_ids = get_affected_esp_ids(rule)

    # P0-Fix T9: Send OFF to all actuators before deleting the rule.
    # Without this, a deleted rule leaves actuators running with no controller.
    actuator_service = get_actuator_service(db)
    if rule.actions:
        for action in rule.actions:
            if action.get("type") in ("actuator_command", "actuator"):
                esp_id = action.get("esp_id")
                gpio = action.get("gpio")
                if esp_id is not None and gpio is not None:
                    try:
                        cmd_result = await actuator_service.send_command(
                            esp_id=str(esp_id),
                            gpio=int(gpio),
                            command="OFF",
                            value=0.0,
                            duration=0,
                            issued_by=f"rule_delete:{rule.id}",
                        )
                        if cmd_result.success:
                            logger.info(
                                "Rule '%s' deleted: sent OFF to %s GPIO %s",
                                rule.name,
                                esp_id,
                                gpio,
                            )
                        else:
                            logger.warning(
                                "Rule '%s' deleted: OFF to %s GPIO %s failed",
                                rule.name,
                                esp_id,
                                gpio,
                            )
                    except Exception as e:
                        logger.warning(
                            "Rule '%s' deleted: failed to send OFF to %s GPIO %s: %s",
                            rule.name,
                            esp_id,
                            gpio,
                            e,
                        )

    # P0-Fix T9: Reset hysteresis states and conflict locks in LogicEngine
    from ...services.logic_engine import get_logic_engine

    engine = get_logic_engine()
    if engine:
        hysteresis_eval = engine._get_hysteresis_evaluator()
        if hysteresis_eval:
            hysteresis_eval.reset_states_for_rule(str(rule_id))
        # Release any held conflict locks for this rule
        for action in rule.actions or []:
            if action.get("type") in ("actuator_command", "actuator"):
                act_esp = action.get("esp_id")
                act_gpio = action.get("gpio")
                if act_esp is not None and act_gpio is not None:
                    await engine.conflict_manager.release_actuator(
                        esp_id=str(act_esp),
                        gpio=int(act_gpio),
                        rule_id=str(rule_id),
                    )

    # Delete rule
    await logic_repo.delete(rule_id)
    await db.commit()

    logger.info(f"Logic rule deleted: '{rule.name}' (ID: {rule.id}) by {current_user.username}")
    await _push_config_to_affected_esps(
        db,
        affected_esp_ids,
        context="logic rule delete",
    )

    return _build_rule_response(rule, 0, None)


# =============================================================================
# Toggle Rule
# =============================================================================


@router.post(
    "/rules/{rule_id}/toggle",
    response_model=RuleToggleResponse,
    responses={
        200: {"description": "Rule toggled"},
        404: {"description": "Rule not found"},
    },
    summary="Toggle rule enabled/disabled",
    description="Enable or disable a rule.",
)
async def toggle_rule(
    rule_id: uuid.UUID,
    request: RuleToggleRequest,
    db: DBSession,
    current_user: OperatorUser,
    actuator_service: Annotated[ActuatorService, Depends(get_actuator_service)],
) -> RuleToggleResponse:
    """
    Toggle rule enabled state.

    When disabling a rule: sends OFF to all actuators controlled by this rule
    (T18-F2 fix: actuator stays on when rule is disabled).

    Args:
        rule_id: Rule ID
        request: Toggle request
        db: Database session
        current_user: Operator or admin user
        actuator_service: ActuatorService for sending OFF on disable

    Returns:
        Toggle response
    """
    logic_repo = LogicRepository(db)

    rule = await logic_repo.get_by_id(rule_id)
    if not rule:
        raise RuleNotFoundException(rule_id)

    previous_state = rule.enabled
    rule.enabled = request.enabled

    await db.flush()
    await db.commit()

    # T18-F2: When disabling rule, send OFF to all actuators it controls
    if not request.enabled and rule.actions:
        for action in rule.actions:
            if action.get("type") in ("actuator_command", "actuator"):
                esp_id = action.get("esp_id")
                gpio = action.get("gpio")
                if esp_id is not None and gpio is not None:
                    try:
                        cmd_result = await actuator_service.send_command(
                            esp_id=str(esp_id),
                            gpio=int(gpio),
                            command="OFF",
                            value=0.0,
                            duration=0,
                            issued_by=f"rule_toggle:{rule.id}",
                        )
                        if cmd_result.success:
                            logger.info(
                                f"Rule '{rule.name}' disabled: sent OFF to {esp_id} GPIO {gpio}"
                            )
                        else:
                            logger.warning(
                                f"Rule '{rule.name}' disabled: OFF to {esp_id} GPIO {gpio} failed"
                            )
                    except Exception as e:
                        logger.warning(
                            f"Rule '{rule.name}' disabled: failed to send OFF to "
                            f"{esp_id} GPIO {gpio}: {e}"
                        )
        # Keep conflict locks consistent with disable/delete behavior.
        from ...services.logic_engine import get_logic_engine

        engine = get_logic_engine()
        if engine:
            for action in rule.actions:
                if action.get("type") in ("actuator_command", "actuator"):
                    act_esp = action.get("esp_id")
                    act_gpio = action.get("gpio")
                    if act_esp is not None and act_gpio is not None:
                        await engine.conflict_manager.release_actuator(
                            esp_id=str(act_esp),
                            gpio=int(act_gpio),
                            rule_id=str(rule_id),
                        )

    action = "enabled" if request.enabled else "disabled"
    logger.info(
        f"Logic rule {action}: '{rule.name}' (ID: {rule.id}) by {current_user.username}"
        + (f" - Reason: {request.reason}" if request.reason else "")
    )
    await _push_config_to_affected_esps(
        db,
        get_affected_esp_ids(rule),
        context="logic rule toggle",
    )

    return RuleToggleResponse(
        success=True,
        message=f"Rule '{rule.name}' {action}",
        rule_id=rule.id,
        rule_name=rule.name,
        enabled=rule.enabled,
        previous_state=previous_state,
    )


# =============================================================================
# Test Rule
# =============================================================================


@router.post(
    "/rules/{rule_id}/test",
    response_model=RuleTestResponse,
    responses={
        200: {"description": "Test completed"},
        404: {"description": "Rule not found"},
    },
    summary="Test/simulate rule",
    description="Simulate rule execution with mock data.",
)
async def test_rule(
    rule_id: uuid.UUID,
    request: RuleTestRequest,
    db: DBSession,
    current_user: OperatorUser,
) -> RuleTestResponse:
    """
    Test/simulate rule execution.

    Args:
        rule_id: Rule ID
        request: Test parameters
        db: Database session
        current_user: Operator or admin user

    Returns:
        Test results
    """
    logic_repo = LogicRepository(db)
    logic_service = LogicService(logic_repo)

    rule = await logic_repo.get_by_id(rule_id)
    if not rule:
        raise RuleNotFoundException(rule_id)

    # Test rule using LogicService
    test_result = await logic_service.test_rule(rule, request)

    logger.info(
        f"Logic rule tested: '{rule.name}' (ID: {rule.id}) by {current_user.username} - "
        f"Would trigger: {test_result.would_trigger}, Dry run: {request.dry_run}"
    )

    return test_result


# =============================================================================
# Execution History
# =============================================================================


@router.get(
    "/execution_history",
    response_model=ExecutionHistoryResponse,
    summary="Get execution history",
    description="Query rule execution history.",
)
async def get_execution_history(
    db: DBSession,
    current_user: ActiveUser,
    rule_id: Annotated[Optional[uuid.UUID], Query(description="Filter by rule ID")] = None,
    success: Annotated[Optional[bool], Query(description="Filter by success")] = None,
    start_time: Annotated[Optional[datetime], Query(description="Start of time range")] = None,
    end_time: Annotated[Optional[datetime], Query(description="End of time range")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ExecutionHistoryResponse:
    """
    Get rule execution history.

    Args:
        db: Database session
        current_user: Authenticated user
        rule_id: Optional rule filter
        success: Optional success filter
        start_time: Start of time range
        end_time: End of time range
        limit: Max results

    Returns:
        Execution history
    """
    logic_repo = LogicRepository(db)

    # Default time range
    if not start_time:
        start_time = datetime.now(timezone.utc) - timedelta(days=7)
    if not end_time:
        end_time = datetime.now(timezone.utc)

    # Get history
    history = await logic_repo.get_execution_history(
        rule_id=rule_id,
        success=success,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
    )

    # Convert to response
    entries = []
    success_count = 0
    for entry in history:
        rule = await logic_repo.get_by_id(entry.logic_rule_id)
        rule_name = rule.rule_name if rule else "Unknown"

        # Extract trigger reason from trigger_data
        trigger_reason = "Unknown trigger"
        if entry.trigger_data:
            trigger_reason = str(entry.trigger_data.get("reason", entry.trigger_data))

        entries.append(
            ExecutionHistoryEntry(
                id=entry.id,
                rule_id=entry.logic_rule_id,
                rule_name=rule_name,
                triggered_at=entry.timestamp,
                trigger_reason=trigger_reason,
                actions_executed=entry.actions_executed or [],
                success=entry.success,
                error_message=entry.error_message,
                execution_time_ms=entry.execution_time_ms,
            )
        )

        if entry.success:
            success_count += 1

    success_rate = success_count / len(entries) if entries else None

    return ExecutionHistoryResponse(
        success=True,
        entries=entries,
        total_count=len(entries),
        success_rate=success_rate,
    )


# =============================================================================
# Templates
# =============================================================================


@router.get(
    "/templates",
    response_model=TemplateListResponse,
    summary="List available rule templates",
    description="Get list of available rule templates for creation.",
)
async def list_templates(
    db: DBSession,
    current_user: ActiveUser,
) -> TemplateListResponse:
    """
    List all available rule templates.

    Args:
        db: Database session
        current_user: Authenticated user

    Returns:
        List of template IDs and metadata
    """
    from ...services.logic.template_loader import get_template_loader

    loader = get_template_loader()
    template_ids = loader.list_templates()

    templates: list[dict] = []
    for template_id in template_ids:
        try:
            info = loader.get_template_info(template_id)
            templates.append(info)
        except Exception as e:
            logger.warning(f"Failed to load template info for {template_id}: {e}")

    return TemplateListResponse(
        success=True,
        templates=templates,
        total_count=len(templates),
    )


@router.get(
    "/templates/{template_id}",
    response_model=TemplateDetailResponse,
    responses={
        200: {"description": "Template info retrieved"},
        404: {"description": "Template not found"},
    },
    summary="Get template details",
    description="Get detailed information about a specific template.",
)
async def get_template(
    template_id: str,
    db: DBSession,
    current_user: ActiveUser,
) -> TemplateDetailResponse:
    """
    Get template details and parameter schema.

    Args:
        template_id: Template identifier
        db: Database session
        current_user: Authenticated user

    Returns:
        Template metadata and parameter schema
    """
    from ...services.logic.template_loader import get_template_loader, TemplateLoadError

    loader = get_template_loader()
    try:
        info = loader.get_template_info(template_id)
        return TemplateDetailResponse(success=True, template=info)
    except TemplateLoadError:
        raise RuleNotFoundException(template_id)


@router.post(
    "/templates/{template_id}/instantiate",
    response_model=LogicRuleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create rule from template",
    description="Instantiate a template with parameters and create a rule.",
)
async def instantiate_template(
    template_id: str,
    request: dict,
    db: DBSession,
    current_user: OperatorUser,
) -> LogicRuleResponse:
    """
    Instantiate a template with parameters and create a logic rule.

    Args:
        template_id: Template identifier
        request: Template parameters and rule metadata
        db: Database session
        current_user: Operator or admin user

    Returns:
        Created rule
    """
    from ...services.logic.template_loader import get_template_loader, TemplateLoadError

    loader = get_template_loader()

    try:
        # Extract rule name and description from request
        rule_name = request.get("rule_name")
        rule_description = request.get("description", "")
        template_params = request.get("parameters", {})

        if not rule_name:
            raise ValueError("rule_name is required")

        # Instantiate template
        instantiated = loader.instantiate(template_id, **template_params)

        # Create rule from instantiated template
        rule_data = LogicRuleCreate(
            name=rule_name,
            description=rule_description,
            conditions=instantiated.get("trigger_conditions", []),
            actions=instantiated.get("actions", []),
            logic_operator=instantiated.get("logic_operator", "AND"),
            enabled=request.get("enabled", True),
            priority=instantiated.get("priority", 50),
            cooldown_seconds=instantiated.get("cooldown_seconds"),
            max_executions_per_hour=instantiated.get("max_executions_per_hour"),
        )

        # Create rule
        logic_repo = LogicRepository(db)
        logic_service = LogicService(logic_repo)

        try:
            created = await logic_service.create_rule(rule_data)
        except ValueError as e:
            raise RuleValidationException(str(e))

        logger.info(
            f"Rule created from template '{template_id}': "
            f"'{created.name}' (ID: {created.id}) by {current_user.username}"
        )

        await _push_config_to_affected_esps(
            db,
            get_affected_esp_ids(created),
            context="logic rule create from template",
        )

        exec_count = await logic_repo.get_execution_count(created.id)
        last_exec = await logic_repo.get_last_execution(created.id)

        return _build_rule_response(created, exec_count, last_exec.success if last_exec else None)

    except TemplateLoadError:
        raise RuleNotFoundException(template_id)
    except ValueError as e:
        raise RuleValidationException(str(e))
