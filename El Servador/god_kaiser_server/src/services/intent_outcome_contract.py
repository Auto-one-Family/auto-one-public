"""
Canonical intent/outcome contract utilities.

Single source for:
- ingestion normalization (legacy/alias -> canonical)
- contract violation mapping (unknown values)
- shared API/WS serialization from persisted rows
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

# Aligned with El Trabajante publishIntentOutcome(flow, ...) — extend when firmware adds flows.
CANONICAL_FLOWS = {
    "command",
    "config",
    "publish",
    "zone",
    "subzone_assign",
    "subzone_remove",
    "subzone_safe",
    "offline_rules",
}
FLOW_ALIASES = {
    "cmd": "command",
    "commands": "command",
    "cfg": "config",
    "configuration": "config",
    "pub": "publish",
}

CANONICAL_OUTCOMES = {"accepted", "rejected", "applied", "persisted", "failed", "expired"}
OUTCOME_ALIASES = {
    "processing": "accepted",
    "success": "persisted",
    "ok": "persisted",
    "error": "failed",
    "timeout": "expired",
}

FINAL_OUTCOMES = {"persisted", "rejected", "failed", "expired"}


def merge_intent_outcome_nested_data(payload: dict[str, Any]) -> None:
    """
    Firmware may nest intent metadata under ``data``; merge into top-level keys in-place
    before validation/canonicalization (missing or empty top-level only).
    """
    data = payload.get("data")
    if not isinstance(data, dict):
        return
    for key in (
        "intent_id",
        "correlation_id",
        "generation",
        "seq",
        "epoch",
        "ttl_ms",
        "created_at_ms",
        # ``flow`` / ``outcome`` may be nested under ``data`` by legacy firmware
        # or dropped from the top level when ArduinoJson hits its size budget
        # (Lauf-4 Live-Hartetest / AUT-108, AUT-304).
        "flow",
        "outcome",
        "ts",
    ):
        if key not in data:
            continue
        current = payload.get(key)
        if current is None or (isinstance(current, str) and not current.strip()):
            payload[key] = data[key]


@dataclass(frozen=True)
class CanonicalIntentOutcome:
    flow: str
    outcome: str
    code: str | None
    reason: str | None
    domain: str
    severity: str
    terminality: str
    retry_policy: str
    is_final: bool
    retryable: bool
    is_contract_violation: bool
    raw_flow: str | None
    raw_outcome: str | None


def _to_text(value: Any) -> str | None:
    if value is None:
        return None
    as_text = str(value).strip()
    return as_text or None


def _normalize_flow(raw_flow: str | None) -> tuple[str, bool]:
    if raw_flow is None:
        return "contract", False
    lowered = raw_flow.lower()
    alias = FLOW_ALIASES.get(lowered, lowered)
    if alias in CANONICAL_FLOWS:
        return alias, True
    return "contract", False


def _normalize_outcome(raw_outcome: str | None) -> tuple[str, bool]:
    if raw_outcome is None:
        return "failed", False
    lowered = raw_outcome.lower()
    alias = OUTCOME_ALIASES.get(lowered, lowered)
    if alias in CANONICAL_OUTCOMES:
        return alias, True
    return "failed", False


def canonicalize_intent_outcome(payload: Mapping[str, Any]) -> CanonicalIntentOutcome:
    raw_flow = _to_text(payload.get("flow"))
    raw_outcome = _to_text(payload.get("outcome"))
    raw_reason = _to_text(payload.get("reason"))
    raw_code = _to_text(payload.get("code"))

    flow, flow_is_known = _normalize_flow(raw_flow)
    outcome, outcome_is_known = _normalize_outcome(raw_outcome)

    contract_issues: list[str] = []
    if not flow_is_known:
        contract_issues.append(f"flow={raw_flow or 'missing'}")
    if not outcome_is_known:
        contract_issues.append(f"outcome={raw_outcome or 'missing'}")

    is_contract_violation = len(contract_issues) > 0
    code = raw_code
    reason = raw_reason

    if is_contract_violation:
        # Known firmware flow + unknown outcome: keep diagnostic code (e.g. future outcomes).
        if flow_is_known and not outcome_is_known and raw_code:
            code = raw_code
        else:
            code = "CONTRACT_UNKNOWN_CODE"
        violation_msg = "Contract violation: unknown intent_outcome values"
        detail = ", ".join(contract_issues)
        reason = f"{violation_msg} ({detail})" if detail else violation_msg

    is_final = outcome in FINAL_OUTCOMES
    retryable = bool(payload.get("retryable", False)) and not is_contract_violation
    retry_policy = "allowed" if retryable else "forbidden"

    severity = "error" if is_contract_violation or outcome in {"failed", "expired"} else "warning"
    if outcome in {"accepted", "applied", "persisted"} and not is_contract_violation:
        severity = "info"

    terminality = "terminal_success" if outcome == "persisted" else "non_terminal"
    if outcome in {"rejected", "failed", "expired"}:
        terminality = "terminal_failure"

    domain = flow if flow in CANONICAL_FLOWS else "contract"

    return CanonicalIntentOutcome(
        flow=flow,
        outcome=outcome,
        code=code,
        reason=reason,
        domain=domain,
        severity=severity,
        terminality=terminality,
        retry_policy=retry_policy,
        is_final=is_final,
        retryable=retryable,
        is_contract_violation=is_contract_violation,
        raw_flow=raw_flow,
        raw_outcome=raw_outcome,
    )


def serialize_intent_outcome_row(row: Any) -> dict[str, Any]:
    """Shared canonical projection for REST and WebSocket."""
    return {
        "intent_id": row.intent_id,
        "correlation_id": row.correlation_id,
        "esp_id": row.esp_id,
        "flow": row.flow,
        "outcome": row.outcome,
        "contract_version": row.contract_version,
        "semantic_mode": row.semantic_mode,
        "legacy_status": row.legacy_status,
        "target_status": row.target_status,
        "is_final": bool(row.is_final),
        "code": row.code,
        "reason": row.reason,
        "retryable": bool(row.retryable),
        "generation": row.generation,
        "seq": row.seq,
        "epoch": row.epoch,
        "ttl_ms": row.ttl_ms,
        "ts": row.ts,
        "first_seen_at": (
            row.first_seen_at.isoformat() if getattr(row, "first_seen_at", None) else None
        ),
        "terminal_at": row.terminal_at.isoformat() if getattr(row, "terminal_at", None) else None,
    }
