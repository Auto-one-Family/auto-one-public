from types import SimpleNamespace

from src.services.intent_outcome_contract import (
    canonicalize_intent_outcome,
    merge_intent_outcome_nested_data,
    serialize_intent_outcome_row,
)


def test_canonicalize_legacy_alias_values():
    normalized = canonicalize_intent_outcome(
        {
            "flow": "cfg",
            "outcome": "processing",
            "code": "NONE",
            "reason": "legacy",
            "retryable": True,
        }
    )

    assert normalized.flow == "config"
    assert normalized.outcome == "accepted"
    assert normalized.is_contract_violation is False
    assert normalized.retryable is True
    assert normalized.terminality == "non_terminal"


def test_canonicalize_zone_flow_is_known():
    normalized = canonicalize_intent_outcome(
        {
            "flow": "zone",
            "outcome": "failed",
            "code": "CONFIG_LANE_BUSY",
            "retryable": True,
        }
    )
    assert normalized.flow == "zone"
    assert normalized.is_contract_violation is False


def test_merge_intent_outcome_nested_data_fills_top_level():
    payload = {
        "flow": "config",
        "outcome": "failed",
        "data": {
            "intent_id": "i1",
            "correlation_id": "c1",
            "generation": 2,
        },
    }
    merge_intent_outcome_nested_data(payload)
    assert payload["intent_id"] == "i1"
    assert payload["correlation_id"] == "c1"
    assert payload["generation"] == 2


def test_merge_intent_outcome_nested_data_lifts_flow_from_nested():
    """Legacy firmware may nest ``flow`` under ``data`` (AUT-108, PKG-03)."""
    payload = {
        "outcome": "persisted",
        "data": {
            "intent_id": "i2",
            "flow": "config",
        },
    }
    merge_intent_outcome_nested_data(payload)
    assert payload["flow"] == "config"
    assert payload["intent_id"] == "i2"


def test_merge_intent_outcome_nested_data_preserves_top_level_flow():
    """Top-level ``flow`` wins over nested value when both are present."""
    payload = {
        "flow": "command",
        "outcome": "persisted",
        "data": {
            "flow": "config",
        },
    }
    merge_intent_outcome_nested_data(payload)
    assert payload["flow"] == "command"


def test_canonicalize_unknown_values_to_contract_violation():
    normalized = canonicalize_intent_outcome(
        {
            "flow": "mystery_flow",
            "outcome": "mystery_outcome",
            "code": "X123",
            "retryable": True,
        }
    )

    assert normalized.flow == "contract"
    assert normalized.outcome == "failed"
    assert normalized.code == "CONTRACT_UNKNOWN_CODE"
    assert normalized.is_contract_violation is True
    assert normalized.retryable is False
    assert normalized.terminality == "terminal_failure"
    assert normalized.retry_policy == "forbidden"


def test_serialize_intent_outcome_row_has_stable_contract_fields():
    row = SimpleNamespace(
        intent_id="intent-1",
        correlation_id="corr-1",
        esp_id="ESP_01",
        flow="command",
        outcome="persisted",
        contract_version=2,
        semantic_mode="target",
        legacy_status="success",
        target_status="persisted",
        is_final=True,
        code="COMMAND_ACCEPTED",
        reason="ok",
        retryable=False,
        generation=3,
        seq=9,
        epoch=1,
        ttl_ms=1000,
        ts=1735818000,
        first_seen_at=None,
        terminal_at=None,
    )

    data = serialize_intent_outcome_row(row)
    assert data["intent_id"] == "intent-1"
    assert data["flow"] == "command"
    assert data["outcome"] == "persisted"
    assert data["is_final"] is True
    assert data["code"] == "COMMAND_ACCEPTED"
