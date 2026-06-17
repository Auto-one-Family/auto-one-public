from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.mqtt.handlers.intent_outcome_handler import IntentOutcomeHandler


@pytest.mark.asyncio
async def test_stale_intent_outcome_is_acknowledged_without_audit():
    handler = IntentOutcomeHandler()
    payload = {
        "intent_id": "intent-1",
        "correlation_id": "corr-1",
        "flow": "command",
        "outcome": "applied",
        "ts": 1735818000,
        "generation": 1,
        "seq": 9,
    }

    session = SimpleNamespace(commit=AsyncMock())
    contract_repo = MagicMock()
    contract_repo.upsert_intent = AsyncMock()
    contract_repo.upsert_outcome = AsyncMock(
        return_value=(SimpleNamespace(outcome="applied", correlation_id="corr-1"), True)
    )
    audit_repo = MagicMock()
    audit_repo.log_device_event = AsyncMock()

    @asynccontextmanager
    async def fake_resilient_session():
        yield session

    with (
        patch(
            "src.mqtt.handlers.intent_outcome_handler.TopicBuilder.parse_intent_outcome_topic",
            return_value={"esp_id": "ESP_01"},
        ),
        patch(
            "src.mqtt.handlers.intent_outcome_handler.resilient_session",
            fake_resilient_session,
        ),
        patch(
            "src.mqtt.handlers.intent_outcome_handler.CommandContractRepository",
            return_value=contract_repo,
        ),
        patch(
            "src.mqtt.handlers.intent_outcome_handler.AuditLogRepository",
            return_value=audit_repo,
        ),
    ):
        result = await handler.handle_intent_outcome(
            "kaiser/god/esp/ESP_01/system/intent_outcome",
            payload,
        )

    assert result is True
    contract_repo.upsert_intent.assert_awaited_once()
    contract_repo.upsert_outcome.assert_awaited_once()
    audit_repo.log_device_event.assert_not_called()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_intent_outcome_returns_false_when_persistence_fails():
    handler = IntentOutcomeHandler()
    payload = {
        "intent_id": "intent-2",
        "correlation_id": "corr-2",
        "flow": "command",
        "outcome": "failed",
        "ts": 1735818000,
    }

    session = SimpleNamespace(commit=AsyncMock())
    contract_repo = MagicMock()
    contract_repo.upsert_intent = AsyncMock(side_effect=RuntimeError("db unavailable"))

    @asynccontextmanager
    async def fake_resilient_session():
        yield session

    with (
        patch(
            "src.mqtt.handlers.intent_outcome_handler.TopicBuilder.parse_intent_outcome_topic",
            return_value={"esp_id": "ESP_02"},
        ),
        patch(
            "src.mqtt.handlers.intent_outcome_handler.resilient_session",
            fake_resilient_session,
        ),
        patch(
            "src.mqtt.handlers.intent_outcome_handler.CommandContractRepository",
            return_value=contract_repo,
        ),
    ):
        result = await handler.handle_intent_outcome(
            "kaiser/god/esp/ESP_02/system/intent_outcome",
            payload,
        )

    assert result is False


@pytest.mark.asyncio
async def test_legacy_alias_is_canonicalized_before_persistence():
    handler = IntentOutcomeHandler()
    payload = {
        "intent_id": "intent-legacy",
        "correlation_id": "corr-legacy",
        "flow": "cfg",
        "outcome": "processing",
        "ts": 1735818000,
    }

    session = SimpleNamespace(commit=AsyncMock())
    captured_payloads: list[dict] = []

    contract_repo = MagicMock()
    contract_repo.upsert_intent = AsyncMock(
        side_effect=lambda p, esp_id: captured_payloads.append(dict(p))
    )
    contract_repo.upsert_outcome = AsyncMock(
        return_value=(
            SimpleNamespace(
                outcome="accepted",
                correlation_id="corr-legacy",
                flow="config",
                code="COMMAND_ACCEPTED",
                reason="ok",
                retryable=False,
                generation=1,
                seq=1,
                epoch=1,
                ttl_ms=0,
                ts=1735818000,
                contract_version=2,
                semantic_mode="target",
                legacy_status="processing",
                target_status="accepted",
                is_final=False,
                intent_id="intent-legacy",
                esp_id="ESP_10",
                first_seen_at=None,
                terminal_at=None,
            ),
            False,
        )
    )
    audit_repo = MagicMock()
    audit_repo.log_device_event = AsyncMock()

    @asynccontextmanager
    async def fake_resilient_session():
        yield session

    with (
        patch(
            "src.mqtt.handlers.intent_outcome_handler.TopicBuilder.parse_intent_outcome_topic",
            return_value={"esp_id": "ESP_10"},
        ),
        patch(
            "src.mqtt.handlers.intent_outcome_handler.resilient_session",
            fake_resilient_session,
        ),
        patch(
            "src.mqtt.handlers.intent_outcome_handler.CommandContractRepository",
            return_value=contract_repo,
        ),
        patch(
            "src.mqtt.handlers.intent_outcome_handler.AuditLogRepository",
            return_value=audit_repo,
        ),
        patch(
            "src.mqtt.handlers.intent_outcome_handler.WebSocketManager",
            create=True,
        ),
    ):
        result = await handler.handle_intent_outcome(
            "kaiser/god/esp/ESP_10/system/intent_outcome",
            payload,
        )

    assert result is True
    assert captured_payloads
    assert captured_payloads[0]["flow"] == "config"
    assert captured_payloads[0]["outcome"] == "accepted"


@pytest.mark.asyncio
async def test_unknown_outcome_is_not_dropped_and_mapped_to_contract_violation():
    handler = IntentOutcomeHandler()
    payload = {
        "intent_id": "intent-unknown",
        "correlation_id": "corr-unknown-outcome",
        "flow": "command",
        "outcome": "totally_new_state",
        "ts": 1735818000,
    }

    session = SimpleNamespace(commit=AsyncMock())
    captured_payloads: list[dict] = []

    contract_repo = MagicMock()
    contract_repo.upsert_intent = AsyncMock(
        side_effect=lambda p, esp_id: captured_payloads.append(dict(p))
    )
    contract_repo.upsert_outcome = AsyncMock(
        return_value=(
            SimpleNamespace(
                outcome="failed",
                correlation_id="corr-unknown-outcome",
                flow="command",
                code="CONTRACT_UNKNOWN_CODE",
                reason="contract violation",
                retryable=False,
                generation=1,
                seq=1,
                epoch=1,
                ttl_ms=0,
                ts=1735818000,
                contract_version=2,
                semantic_mode="target",
                legacy_status="failed",
                target_status="failed",
                is_final=True,
                intent_id="intent-unknown",
                esp_id="ESP_11",
                first_seen_at=None,
                terminal_at=None,
            ),
            False,
        )
    )
    audit_repo = MagicMock()
    audit_repo.log_device_event = AsyncMock()

    @asynccontextmanager
    async def fake_resilient_session():
        yield session

    with (
        patch(
            "src.mqtt.handlers.intent_outcome_handler.TopicBuilder.parse_intent_outcome_topic",
            return_value={"esp_id": "ESP_11"},
        ),
        patch(
            "src.mqtt.handlers.intent_outcome_handler.resilient_session",
            fake_resilient_session,
        ),
        patch(
            "src.mqtt.handlers.intent_outcome_handler.CommandContractRepository",
            return_value=contract_repo,
        ),
        patch(
            "src.mqtt.handlers.intent_outcome_handler.AuditLogRepository",
            return_value=audit_repo,
        ),
        patch(
            "src.mqtt.handlers.intent_outcome_handler.WebSocketManager",
            create=True,
        ),
    ):
        result = await handler.handle_intent_outcome(
            "kaiser/god/esp/ESP_11/system/intent_outcome",
            payload,
        )

    assert result is True
    assert captured_payloads
    assert captured_payloads[0]["code"] == "CONTRACT_UNKNOWN_CODE"
    assert captured_payloads[0]["outcome"] == "failed"


@pytest.mark.asyncio
async def test_missing_intent_id_is_normalized_and_persisted():
    handler = IntentOutcomeHandler()
    payload = {
        "correlation_id": "corr-missing-intent",
        "flow": "config",
        "outcome": "accepted",
        "seq": 17,
        "ts": 1735818000,
    }

    session = SimpleNamespace(commit=AsyncMock())
    captured_payloads: list[dict] = []

    contract_repo = MagicMock()
    contract_repo.upsert_intent = AsyncMock(
        side_effect=lambda p, esp_id: captured_payloads.append(dict(p))
    )
    contract_repo.upsert_outcome = AsyncMock(
        return_value=(
            SimpleNamespace(
                outcome="accepted",
                correlation_id="corr-missing-intent",
                flow="config",
                code="CONTRACT_MISSING_INTENT_ID",
                reason="Contract violation: missing intent_id",
                retryable=False,
                generation=0,
                seq=17,
                epoch=0,
                ttl_ms=0,
                ts=1735818000,
                contract_version=2,
                semantic_mode="target",
                legacy_status="processing",
                target_status="accepted",
                is_final=False,
                intent_id="missing-intent:ESP_12:corr-missing-intent:17:1735818000",
                esp_id="ESP_12",
                first_seen_at=None,
                terminal_at=None,
            ),
            False,
        )
    )
    audit_repo = MagicMock()
    audit_repo.log_device_event = AsyncMock()

    @asynccontextmanager
    async def fake_resilient_session():
        yield session

    with (
        patch(
            "src.mqtt.handlers.intent_outcome_handler.TopicBuilder.parse_intent_outcome_topic",
            return_value={"esp_id": "ESP_12"},
        ),
        patch(
            "src.mqtt.handlers.intent_outcome_handler.resilient_session",
            fake_resilient_session,
        ),
        patch(
            "src.mqtt.handlers.intent_outcome_handler.CommandContractRepository",
            return_value=contract_repo,
        ),
        patch(
            "src.mqtt.handlers.intent_outcome_handler.AuditLogRepository",
            return_value=audit_repo,
        ),
        patch(
            "src.mqtt.handlers.intent_outcome_handler.WebSocketManager",
            create=True,
        ),
    ):
        result = await handler.handle_intent_outcome(
            "kaiser/god/esp/ESP_12/system/intent_outcome",
            payload,
        )

    assert result is True
    assert captured_payloads
    assert captured_payloads[0]["intent_id"] == "corr-missing-intent"
    assert captured_payloads[0]["_reconciliation"]["intent_id_source"] == "correlation_id"
    audit_repo.log_device_event.assert_awaited_once()
    call_kwargs = audit_repo.log_device_event.await_args.kwargs
    assert call_kwargs["correlation_id"] == "corr-missing-intent"


@pytest.mark.asyncio
async def test_missing_intent_and_correlation_generates_synthetic_intent_id():
    handler = IntentOutcomeHandler()
    payload = {
        "flow": "config",
        "outcome": "accepted",
        "seq": 23,
        "ts": 1735818000,
    }

    session = SimpleNamespace(commit=AsyncMock())
    captured_payloads: list[dict] = []

    contract_repo = MagicMock()
    contract_repo.upsert_intent = AsyncMock(
        side_effect=lambda p, esp_id: captured_payloads.append(dict(p))
    )
    contract_repo.upsert_outcome = AsyncMock(
        return_value=(
            SimpleNamespace(
                outcome="accepted",
                correlation_id="missing-corr:missing-intent:ESP_13:missing-corr:23:1735818000",
                flow="config",
                code="CONTRACT_MISSING_INTENT_ID",
                reason="Contract violation: missing intent_id",
                retryable=False,
                generation=0,
                seq=23,
                epoch=0,
                ttl_ms=0,
                ts=1735818000,
                contract_version=2,
                semantic_mode="target",
                legacy_status="processing",
                target_status="accepted",
                is_final=False,
                intent_id="missing-intent:ESP_13:missing-corr:23:1735818000",
                esp_id="ESP_13",
                first_seen_at=None,
                terminal_at=None,
            ),
            False,
        )
    )
    audit_repo = MagicMock()
    audit_repo.log_device_event = AsyncMock()

    @asynccontextmanager
    async def fake_resilient_session():
        yield session

    with (
        patch(
            "src.mqtt.handlers.intent_outcome_handler.TopicBuilder.parse_intent_outcome_topic",
            return_value={"esp_id": "ESP_13"},
        ),
        patch(
            "src.mqtt.handlers.intent_outcome_handler.resilient_session",
            fake_resilient_session,
        ),
        patch(
            "src.mqtt.handlers.intent_outcome_handler.CommandContractRepository",
            return_value=contract_repo,
        ),
        patch(
            "src.mqtt.handlers.intent_outcome_handler.AuditLogRepository",
            return_value=audit_repo,
        ),
        patch(
            "src.mqtt.handlers.intent_outcome_handler.WebSocketManager",
            create=True,
        ),
    ):
        result = await handler.handle_intent_outcome(
            "kaiser/god/esp/ESP_13/system/intent_outcome",
            payload,
        )

    assert result is True
    assert captured_payloads[0]["intent_id"].startswith("missing-intent:ESP_13:")
    assert captured_payloads[0]["code"] == "CONTRACT_MISSING_INTENT_ID"
    assert captured_payloads[0]["retryable"] is False


@pytest.mark.asyncio
async def test_duplicate_intent_outcome_is_deduped_and_acked():
    """AUT-56: Verify that duplicate MQTT delivery of the same intent_outcome
    is idempotently ACKed without duplicate audit/WS events."""
    handler = IntentOutcomeHandler()
    payload = {
        "intent_id": "intent-dup-test",
        "correlation_id": "corr-dup-test",
        "flow": "command",
        "outcome": "applied",
        "ts": 1735818000,
        "generation": 3,
        "seq": 10,
    }

    session = SimpleNamespace(commit=AsyncMock())
    contract_repo = MagicMock()
    contract_repo.upsert_intent = AsyncMock()
    contract_repo.upsert_outcome = AsyncMock(
        return_value=(
            SimpleNamespace(
                outcome="applied",
                correlation_id="corr-dup-test",
                flow="command",
                code="COMMAND_ACCEPTED",
                reason="ok",
                retryable=False,
                generation=3,
                seq=10,
                epoch=1,
                ttl_ms=0,
                ts=1735818000,
                contract_version=2,
                semantic_mode="target",
                legacy_status="processing",
                target_status="applied",
                is_final=False,
                intent_id="intent-dup-test",
                esp_id="ESP_DUP",
                first_seen_at=None,
                terminal_at=None,
            ),
            True,  # is_stale=True — this IS the dedup signal
        )
    )
    audit_repo = MagicMock()
    audit_repo.log_device_event = AsyncMock()

    @asynccontextmanager
    async def fake_resilient_session():
        yield session

    with (
        patch(
            "src.mqtt.handlers.intent_outcome_handler.TopicBuilder.parse_intent_outcome_topic",
            return_value={"esp_id": "ESP_DUP"},
        ),
        patch(
            "src.mqtt.handlers.intent_outcome_handler.resilient_session",
            fake_resilient_session,
        ),
        patch(
            "src.mqtt.handlers.intent_outcome_handler.CommandContractRepository",
            return_value=contract_repo,
        ),
        patch(
            "src.mqtt.handlers.intent_outcome_handler.AuditLogRepository",
            return_value=audit_repo,
        ),
    ):
        result = await handler.handle_intent_outcome(
            "kaiser/god/esp/ESP_DUP/system/intent_outcome",
            payload,
        )

    assert result is True, "Duplicate must be ACKed (return True)"
    contract_repo.upsert_outcome.assert_awaited_once()
    audit_repo.log_device_event.assert_not_called(), "Stale duplicate must not create audit entry"
    session.commit.assert_awaited_once(), "Stale duplicate must still commit the transaction"


@pytest.mark.asyncio
async def test_recovered_intent_outcome_increments_metrics():
    """AUT-56: NVS-replayed outcome (recovered=True, retry_count>0)
    must still be persisted and broadcast normally."""
    handler = IntentOutcomeHandler()
    payload = {
        "intent_id": "intent-recovered",
        "correlation_id": "corr-recovered",
        "flow": "command",
        "outcome": "failed",
        "code": "EXECUTE_FAIL",
        "reason": "Actuator command execution failed",
        "ts": 1735818000,
        "generation": 2,
        "seq": 5,
        "retry_count": 3,
        "recovered": True,
        "delivery_mode": "recovered",
        "outcome_drop_count_critical": 1,
    }

    outcome_row = SimpleNamespace(
        outcome="failed",
        correlation_id="corr-recovered",
        flow="command",
        code="EXECUTE_FAIL",
        reason="Actuator command execution failed",
        retryable=False,
        generation=2,
        seq=5,
        epoch=1,
        ttl_ms=0,
        ts=1735818000,
        contract_version=2,
        semantic_mode="target",
        legacy_status="failed",
        target_status="failed",
        is_final=True,
        intent_id="intent-recovered",
        esp_id="ESP_REC",
        first_seen_at=None,
        terminal_at=None,
    )
    session = SimpleNamespace(commit=AsyncMock())
    contract_repo = MagicMock()
    contract_repo.upsert_intent = AsyncMock()
    contract_repo.upsert_outcome = AsyncMock(return_value=(outcome_row, False))
    audit_repo = MagicMock()
    audit_repo.log_device_event = AsyncMock()

    @asynccontextmanager
    async def fake_resilient_session():
        yield session

    with (
        patch(
            "src.mqtt.handlers.intent_outcome_handler.TopicBuilder.parse_intent_outcome_topic",
            return_value={"esp_id": "ESP_REC"},
        ),
        patch(
            "src.mqtt.handlers.intent_outcome_handler.resilient_session",
            fake_resilient_session,
        ),
        patch(
            "src.mqtt.handlers.intent_outcome_handler.CommandContractRepository",
            return_value=contract_repo,
        ),
        patch(
            "src.mqtt.handlers.intent_outcome_handler.AuditLogRepository",
            return_value=audit_repo,
        ),
        patch(
            "src.mqtt.handlers.intent_outcome_handler.WebSocketManager",
            create=True,
        ),
        patch(
            "src.mqtt.handlers.intent_outcome_handler.increment_outcome_retry_count"
        ) as mock_retry_metric,
        patch(
            "src.mqtt.handlers.intent_outcome_handler.increment_outcome_recovered_count"
        ) as mock_recovered_metric,
        patch(
            "src.mqtt.handlers.intent_outcome_handler.set_outcome_drop_count_critical"
        ) as mock_drop_metric,
    ):
        result = await handler.handle_intent_outcome(
            "kaiser/god/esp/ESP_REC/system/intent_outcome",
            payload,
        )

    assert result is True
    audit_repo.log_device_event.assert_awaited_once()
    mock_retry_metric.assert_called_once_with(3)
    mock_recovered_metric.assert_called_once()
    mock_drop_metric.assert_called_once_with("ESP_REC", 1)
