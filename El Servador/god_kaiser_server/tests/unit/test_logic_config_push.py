"""
Unit tests for logic-router config-push trigger (Fix C).
"""

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.api.v1.logic import (
    _push_config_to_affected_esps,
    create_rule,
    delete_rule,
    toggle_rule,
    update_rule,
)
from src.schemas.logic import LogicRuleCreate, LogicRuleUpdate, RuleToggleRequest
from src.services.actuator_service import ActuatorSendCommandResult


def _mock_rule(rule_id: uuid.UUID | None = None, enabled: bool = True):
    rule = MagicMock()
    rule.id = rule_id or uuid.uuid4()
    rule.name = "Rule A"
    rule.description = "desc"
    rule.conditions = [{"type": "sensor"}]
    rule.actions = [{"type": "actuator_command", "esp_id": "ESP_AABBCCDD", "gpio": 5}]
    rule.logic_operator = "AND"
    rule.enabled = enabled
    rule.priority = 50
    rule.cooldown_seconds = 60
    rule.max_executions_per_hour = None
    rule.last_triggered = None
    rule.is_critical = False
    rule.escalation_policy = None
    rule.degraded_since = None
    rule.degraded_reason = None
    now = datetime.now(timezone.utc)
    rule.created_at = now
    rule.updated_at = now
    return rule


@pytest.mark.asyncio
async def test_create_rule_triggers_config_push():
    db = AsyncMock()
    current_user = SimpleNamespace(username="operator")
    created_rule = _mock_rule()

    request = LogicRuleCreate(
        name="Rule A",
        description="desc",
        conditions=[{"type": "sensor", "esp_id": "ESP_AABBCCDD", "gpio": 4}],
        actions=[{"type": "actuator_command", "esp_id": "ESP_AABBCCDD", "gpio": 5}],
        logic_operator="AND",
        enabled=True,
        priority=50,
        cooldown_seconds=60,
    )

    with (
        patch("src.api.v1.logic.LogicService") as logic_service_cls,
        patch(
            "src.api.v1.logic._push_config_to_affected_esps", new_callable=AsyncMock
        ) as push_mock,
    ):
        logic_service = MagicMock()
        logic_service.create_rule = AsyncMock(return_value=created_rule)
        logic_service_cls.return_value = logic_service

        with patch("src.api.v1.logic.LogicRepository") as logic_repo_cls:
            logic_repo = MagicMock()
            logic_repo.get_execution_count = AsyncMock(return_value=0)
            logic_repo.get_last_execution = AsyncMock(return_value=None)
            logic_repo_cls.return_value = logic_repo

            await create_rule(request=request, db=db, current_user=current_user)

        push_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_rule_triggers_config_push():
    db = AsyncMock()
    current_user = SimpleNamespace(username="operator")
    rule = _mock_rule()
    request = LogicRuleUpdate(name="Rule A updated")

    with (
        patch("src.api.v1.logic.LogicService") as logic_service_cls,
        patch(
            "src.api.v1.logic._push_config_to_affected_esps", new_callable=AsyncMock
        ) as push_mock,
    ):
        logic_service = MagicMock()
        logic_service.update_rule = AsyncMock(return_value=rule)
        logic_service_cls.return_value = logic_service

        with patch("src.api.v1.logic.LogicRepository") as logic_repo_cls:
            logic_repo = MagicMock()
            logic_repo.get_execution_count = AsyncMock(return_value=0)
            logic_repo.get_last_execution = AsyncMock(return_value=None)
            logic_repo_cls.return_value = logic_repo

            await update_rule(rule_id=rule.id, request=request, db=db, current_user=current_user)

        push_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_rule_triggers_config_push():
    db = AsyncMock()
    current_user = SimpleNamespace(username="operator")
    rule = _mock_rule()

    with (
        patch("src.api.v1.logic.LogicRepository") as logic_repo_cls,
        patch(
            "src.api.v1.logic._push_config_to_affected_esps", new_callable=AsyncMock
        ) as push_mock,
    ):
        logic_repo = MagicMock()
        logic_repo.get_by_id = AsyncMock(return_value=rule)
        logic_repo.delete = AsyncMock(return_value=None)
        logic_repo_cls.return_value = logic_repo

        await delete_rule(rule_id=rule.id, db=db, current_user=current_user)

        push_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_toggle_rule_triggers_config_push():
    db = AsyncMock()
    current_user = SimpleNamespace(username="operator")
    rule = _mock_rule(enabled=True)
    request = RuleToggleRequest(enabled=False, reason="maintenance")
    actuator_service = MagicMock()
    actuator_service.send_command = AsyncMock(
        return_value=ActuatorSendCommandResult(
            success=True,
            correlation_id="00000000-0000-4000-8000-000000000001",
            command_sent=True,
            safety_warnings=[],
        )
    )

    with (
        patch("src.api.v1.logic.LogicRepository") as logic_repo_cls,
        patch(
            "src.api.v1.logic._push_config_to_affected_esps", new_callable=AsyncMock
        ) as push_mock,
    ):
        logic_repo = MagicMock()
        logic_repo.get_by_id = AsyncMock(return_value=rule)
        logic_repo_cls.return_value = logic_repo

        await toggle_rule(
            rule_id=rule.id,
            request=request,
            db=db,
            current_user=current_user,
            actuator_service=actuator_service,
        )

        push_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_push_config_uses_coalesced_scheduler():
    """Config push helper always routes via coalesced scheduler."""
    db = AsyncMock()
    builder = MagicMock()
    builder.build_combined_config = AsyncMock(return_value={"sensors": [], "actuators": []})
    esp_service = MagicMock()
    esp_service.send_config_coalesced = AsyncMock(
        return_value={"scheduled": True, "merged": True}
    )

    with (
        patch("src.api.v1.logic.get_config_builder", return_value=builder),
        patch("src.api.v1.logic.get_esp_service", return_value=esp_service),
        patch("src.api.v1.logic.logger.info") as info_mock,
    ):
        await _push_config_to_affected_esps(db, {"ESP_FAIL_001"}, context="unit-test")
        esp_service.send_config_coalesced.assert_awaited_once()
        info_mock.assert_called()
