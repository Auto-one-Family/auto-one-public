"""
Unit Tests: AUT-111 Critical-Rule Degraded-Handling

Tests:
- Migration fields exist on model
- Engine enter/exit degraded state
- No double-emit on repeated enter
- API patch critical flag
- Escalation policy validation
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.db.models.logic import CrossESPLogic
from src.schemas.logic import (
    LogicRuleCreate,
    LogicRuleUpdate,
    LogicRuleResponse,
    _validate_escalation_policy,
)

# =============================================================================
# Model field presence (migration sanity)
# =============================================================================


class TestCriticalDegradedModelFields:
    """Verify AUT-111 columns exist on CrossESPLogic."""

    def test_is_critical_default(self):
        rule = CrossESPLogic.__table__
        col = rule.c.is_critical
        assert col is not None
        assert col.default.arg is False

    def test_escalation_policy_nullable(self):
        col = CrossESPLogic.__table__.c.escalation_policy
        assert col is not None
        assert col.nullable is True

    def test_degraded_since_nullable(self):
        col = CrossESPLogic.__table__.c.degraded_since
        assert col is not None
        assert col.nullable is True

    def test_degraded_reason_varchar64(self):
        col = CrossESPLogic.__table__.c.degraded_reason
        assert col is not None
        assert col.nullable is True
        assert col.type.length == 64


# =============================================================================
# Escalation policy validation
# =============================================================================


class TestEscalationPolicyValidation:
    """Validate escalation_policy shape checking."""

    def test_none_is_valid(self):
        assert _validate_escalation_policy(None) is None

    def test_empty_dict_is_valid(self):
        result = _validate_escalation_policy({})
        assert result == {}

    def test_full_valid_policy(self):
        policy = {
            "notify": ["email", "websocket"],
            "retry_interval_s": 60,
            "max_retries": 5,
            "failover_actions": [{"type": "actuator", "esp_id": "ESP_AABB", "gpio": 4}],
        }
        result = _validate_escalation_policy(policy)
        assert result == policy

    def test_unknown_key_rejected(self):
        with pytest.raises(ValueError, match="Unknown escalation_policy keys"):
            _validate_escalation_policy({"unknown_key": True})

    def test_invalid_notify_channel(self):
        with pytest.raises(ValueError, match="Invalid notify channel"):
            _validate_escalation_policy({"notify": ["sms"]})

    def test_notify_must_be_list(self):
        with pytest.raises(ValueError, match="notify must be a list"):
            _validate_escalation_policy({"notify": "email"})

    def test_retry_interval_out_of_range(self):
        with pytest.raises(ValueError, match="retry_interval_s must be 1..3600"):
            _validate_escalation_policy({"retry_interval_s": 0})

    def test_max_retries_out_of_range(self):
        with pytest.raises(ValueError, match="max_retries must be 0..100"):
            _validate_escalation_policy({"max_retries": -1})

    def test_failover_actions_must_be_list(self):
        with pytest.raises(ValueError, match="failover_actions must be a list"):
            _validate_escalation_policy({"failover_actions": "not_a_list"})

    def test_non_dict_rejected(self):
        with pytest.raises(ValueError, match="must be a JSON object"):
            _validate_escalation_policy("string_value")


# =============================================================================
# Schema validation (Create/Update)
# =============================================================================


class TestSchemaIsCriticalField:
    """Verify is_critical and escalation_policy in Create/Update schemas."""

    def test_create_defaults_is_critical_false(self):
        data = LogicRuleCreate(
            name="Test Rule",
            conditions=[
                {"type": "sensor", "esp_id": "ESP_AABB", "gpio": 1, "operator": ">", "value": 5}
            ],
            actions=[{"type": "actuator", "esp_id": "ESP_CCDD", "gpio": 2, "command": "ON"}],
        )
        assert data.is_critical is False
        assert data.escalation_policy is None

    def test_create_with_is_critical_true(self):
        data = LogicRuleCreate(
            name="Critical Rule",
            conditions=[
                {"type": "sensor", "esp_id": "ESP_AABB", "gpio": 1, "operator": ">", "value": 5}
            ],
            actions=[{"type": "actuator", "esp_id": "ESP_CCDD", "gpio": 2, "command": "ON"}],
            is_critical=True,
            escalation_policy={"notify": ["websocket"], "max_retries": 3},
        )
        assert data.is_critical is True
        assert data.escalation_policy["max_retries"] == 3

    def test_create_rejects_invalid_escalation(self):
        with pytest.raises(Exception):
            LogicRuleCreate(
                name="Bad Policy",
                conditions=[
                    {"type": "sensor", "esp_id": "ESP_AABB", "gpio": 1, "operator": ">", "value": 5}
                ],
                actions=[{"type": "actuator", "esp_id": "ESP_CCDD", "gpio": 2, "command": "ON"}],
                escalation_policy={"notify": ["sms"]},
            )

    def test_update_patch_is_critical(self):
        update = LogicRuleUpdate(is_critical=True)
        dumped = update.model_dump(exclude_unset=True)
        assert dumped == {"is_critical": True}

    def test_response_includes_degraded_fields(self):
        resp = LogicRuleResponse(
            id=uuid.uuid4(),
            name="Test",
            conditions=[],
            actions=[],
            logic_operator="AND",
            enabled=True,
            priority=50,
            cooldown_seconds=60,
            is_critical=True,
            degraded_since=datetime(2026, 4, 22, tzinfo=timezone.utc),
            degraded_reason="target_esp_offline:ESP_AABB",
        )
        assert resp.is_critical is True
        assert resp.degraded_since is not None
        assert resp.degraded_reason == "target_esp_offline:ESP_AABB"


# =============================================================================
# Engine enter/exit degraded state
# =============================================================================


class TestEngineDegradedState:
    """Test _enter_degraded_state / _exit_degraded_state on LogicEngine."""

    @pytest.fixture
    def engine(self):
        from src.services.logic_engine import LogicEngine

        repo = AsyncMock()
        actuator = AsyncMock()
        ws = AsyncMock()
        return LogicEngine(
            logic_repo=repo,
            actuator_service=actuator,
            websocket_manager=ws,
        )

    @pytest.mark.asyncio
    async def test_enter_degraded_emits_once(self, engine):
        """First call sets degraded_since and broadcasts; second call is a no-op."""
        rule_id = uuid.uuid4()
        rule_mock = MagicMock()
        rule_mock.is_critical = True
        rule_mock.degraded_since = None
        rule_mock.escalation_policy = {"notify": ["websocket"]}

        session = AsyncMock()
        exec_result = MagicMock()
        exec_result.scalar_one_or_none.return_value = rule_mock
        session.execute = AsyncMock(return_value=exec_result)

        await engine._enter_degraded_state(
            rule_id, "TestRule", "target_esp_offline:ESP_AABB", session
        )

        assert rule_mock.degraded_since is not None
        assert rule_mock.degraded_reason == "target_esp_offline:ESP_AABB"
        engine.websocket_manager.broadcast.assert_called_once()
        call_args = engine.websocket_manager.broadcast.call_args
        assert call_args[0][0] == "rule_degraded"
        payload = call_args[0][1]
        assert payload["degraded_reason"] == "target_esp_offline:ESP_AABB"
        assert payload["reason"] == "target_esp_offline:ESP_AABB"

        # Second call: rule already degraded
        engine.websocket_manager.broadcast.reset_mock()
        rule_mock.degraded_since = datetime.now(timezone.utc)
        await engine._enter_degraded_state(
            rule_id, "TestRule", "target_esp_offline:ESP_AABB", session
        )
        engine.websocket_manager.broadcast.assert_not_called()

    @pytest.mark.asyncio
    async def test_enter_degraded_noop_for_non_critical(self, engine):
        """Non-critical rules are silently ignored."""
        rule_id = uuid.uuid4()
        rule_mock = MagicMock()
        rule_mock.is_critical = False

        session = AsyncMock()
        exec_result = MagicMock()
        exec_result.scalar_one_or_none.return_value = rule_mock
        session.execute = AsyncMock(return_value=exec_result)

        await engine._enter_degraded_state(
            rule_id, "NonCritical", "target_esp_offline:ESP_AABB", session
        )
        engine.websocket_manager.broadcast.assert_not_called()

    @pytest.mark.asyncio
    async def test_exit_degraded_clears_and_emits(self, engine):
        """Recovery clears fields and emits rule_recovered."""
        rule_id = uuid.uuid4()
        rule_mock = MagicMock()
        rule_mock.degraded_since = datetime(2026, 4, 22, tzinfo=timezone.utc)
        rule_mock.degraded_reason = "target_esp_offline:ESP_AABB"

        session = AsyncMock()
        exec_result = MagicMock()
        exec_result.scalar_one_or_none.return_value = rule_mock
        session.execute = AsyncMock(return_value=exec_result)

        await engine._exit_degraded_state(rule_id, "TestRule", session)

        assert rule_mock.degraded_since is None
        assert rule_mock.degraded_reason is None
        engine.websocket_manager.broadcast.assert_called_once()
        call_args = engine.websocket_manager.broadcast.call_args
        assert call_args[0][0] == "rule_recovered"

    @pytest.mark.asyncio
    async def test_exit_degraded_noop_when_not_degraded(self, engine):
        """Exit is a no-op when rule is not degraded."""
        rule_id = uuid.uuid4()
        rule_mock = MagicMock()
        rule_mock.degraded_since = None

        session = AsyncMock()
        exec_result = MagicMock()
        exec_result.scalar_one_or_none.return_value = rule_mock
        session.execute = AsyncMock(return_value=exec_result)

        await engine._exit_degraded_state(rule_id, "TestRule", session)
        engine.websocket_manager.broadcast.assert_not_called()
