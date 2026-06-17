"""
Canonical contract layer for device response MQTT ingress.

Scope:
- config_response (kaiser/.../config_response)
- actuator_response (kaiser/.../actuator/{gpio}/response)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from ..core.esp32_error_mapping import ESP32_CONFIG_ERROR_MESSAGES_DE

CONTRACT_UNKNOWN_CODE = "CONTRACT_UNKNOWN_CODE"

_KNOWN_CONFIG_STATUS = {"success", "partial_success", "error"}
_CONFIG_STATUS_ALIASES = {
    "ok": "success",
    "failed": "error",
    "partial": "partial_success",
}
_KNOWN_CONFIG_TYPES = {"sensor", "actuator", "zone", "system"}
_CONFIG_TYPE_ALIASES = {
    "cfg": "system",
    "configuration": "system",
}
_KNOWN_CONFIG_ERROR_CODES = set(ESP32_CONFIG_ERROR_MESSAGES_DE.keys())


@dataclass(frozen=True)
class CanonicalConfigResponse:
    status: str
    config_type: str
    count: int
    failed_count: int
    message: str
    code: str
    reason: str | None
    error_code: str
    failures: list[dict[str, Any]]
    failed_item: dict[str, Any] | None
    correlation_id: str
    domain: str
    severity: str
    terminality: str
    retry_policy: str
    is_final: bool
    is_contract_violation: bool
    raw_status: str | None
    raw_type: str | None
    raw_error_code: str | None


@dataclass(frozen=True)
class CanonicalActuatorResponse:
    esp_id: str
    gpio: int
    command: str
    value: float
    success: bool
    message: str
    ts: int
    correlation_id: str
    code: str
    domain: str
    severity: str
    terminality: str
    retry_policy: str
    is_final: bool
    is_contract_violation: bool
    raw_esp_id: str | None
    raw_gpio: Any
    raw_success: Any


def _to_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_non_negative_int(value: Any, default: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def _to_bool(value: Any) -> tuple[bool, bool]:
    if isinstance(value, bool):
        return value, True
    if isinstance(value, int):
        return value != 0, True
    text = _to_text(value)
    if text is None:
        return False, False
    lowered = text.lower()
    if lowered in {"true", "1", "yes", "y", "on"}:
        return True, True
    if lowered in {"false", "0", "no", "n", "off"}:
        return False, True
    return False, False


def canonicalize_config_response(
    payload: Mapping[str, Any], *, esp_id: str
) -> CanonicalConfigResponse:
    raw_status = _to_text(payload.get("status"))
    raw_type = _to_text(payload.get("type") or payload.get("config_type"))
    raw_error_code = _to_text(payload.get("error_code"))

    status_candidate = _CONFIG_STATUS_ALIASES.get(
        (raw_status or "").lower(), (raw_status or "").lower()
    )
    type_candidate = _CONFIG_TYPE_ALIASES.get((raw_type or "").lower(), (raw_type or "").lower())

    status = status_candidate if status_candidate in _KNOWN_CONFIG_STATUS else "error"
    config_type = type_candidate if type_candidate in _KNOWN_CONFIG_TYPES else "system"

    contract_issues: list[str] = []
    if status_candidate not in _KNOWN_CONFIG_STATUS:
        contract_issues.append(f"status={raw_status or 'missing'}")
    if type_candidate not in _KNOWN_CONFIG_TYPES:
        contract_issues.append(f"type={raw_type or 'missing'}")

    count = _to_non_negative_int(payload.get("count"), default=0)
    failed_count = _to_non_negative_int(payload.get("failed_count"), default=0)
    message = _to_text(payload.get("message")) or ""

    failures_raw = payload.get("failures")
    failures: list[dict[str, Any]] = []
    if isinstance(failures_raw, list):
        failures = [item for item in failures_raw if isinstance(item, dict)]

    failed_item_raw = payload.get("failed_item")
    failed_item = failed_item_raw if isinstance(failed_item_raw, dict) else None
    if not failures and failed_item and status != "success":
        failures = [failed_item]

    correlation_id = _to_text(payload.get("correlation_id"))
    request_id = _to_text(payload.get("request_id"))
    if correlation_id is None and request_id is not None:
        # Recovery path: some firmware builds mirror only request_id in config_response.
        # Reuse it as correlation handle so downstream finalization can still resolve.
        correlation_id = request_id
        contract_issues.append("correlation_id=missing_used_request_id")
    elif correlation_id is None:
        # Build deterministic fallback per response shape to avoid collisions
        # between sensor/actuator/system responses arriving in the same second.
        ts_part = _to_non_negative_int(
            payload.get("ts"), default=int(datetime.now(timezone.utc).timestamp())
        )
        seq_part = _to_non_negative_int(payload.get("seq"), default=-1)
        seq_token = str(seq_part) if seq_part >= 0 else "na"
        correlation_id = f"missing-corr:cfg:{esp_id}:{config_type}:{ts_part}:{seq_token}"
        contract_issues.append("correlation_id=missing")

    if status == "success":
        error_code = "NONE"
    elif raw_error_code:
        upper_code = raw_error_code.upper()
        if upper_code in _KNOWN_CONFIG_ERROR_CODES:
            error_code = upper_code
        else:
            error_code = CONTRACT_UNKNOWN_CODE
            contract_issues.append(f"error_code={raw_error_code}")
    else:
        failure_error = None
        if failures:
            failure_error = _to_text(failures[0].get("error") or failures[0].get("error_code"))
        upper_failure_error = (failure_error or "").upper()
        if upper_failure_error in _KNOWN_CONFIG_ERROR_CODES:
            error_code = upper_failure_error
        else:
            error_code = CONTRACT_UNKNOWN_CODE
            contract_issues.append("error_code=missing")

    is_contract_violation = len(contract_issues) > 0
    if is_contract_violation and not message:
        message = f"Contract violation: {', '.join(contract_issues)}"

    severity = "info"
    if status == "partial_success":
        severity = "warning"
    elif status == "error":
        severity = "error"
    if is_contract_violation:
        severity = "error"

    terminality = "terminal_success" if status == "success" else "terminal_failure"
    retry_policy = "forbidden" if status == "success" else "allowed"

    return CanonicalConfigResponse(
        status=status,
        config_type=config_type,
        count=count,
        failed_count=max(failed_count, len(failures) if status != "success" else 0),
        message=message,
        code=error_code,
        reason=message or None,
        error_code=error_code,
        failures=failures,
        failed_item=failed_item,
        correlation_id=correlation_id,
        domain=f"config.{config_type}" if config_type in _KNOWN_CONFIG_TYPES else "contract",
        severity=severity,
        terminality=terminality,
        retry_policy=retry_policy,
        is_final=True,
        is_contract_violation=is_contract_violation,
        raw_status=raw_status,
        raw_type=raw_type,
        raw_error_code=raw_error_code,
    )


def canonicalize_actuator_response(
    payload: Mapping[str, Any],
    *,
    topic_esp_id: str,
    topic_gpio: int,
) -> CanonicalActuatorResponse:
    now_ts = int(datetime.now(timezone.utc).timestamp())
    contract_issues: list[str] = []

    raw_esp_id = _to_text(payload.get("esp_id"))
    esp_id = topic_esp_id
    if raw_esp_id and raw_esp_id != topic_esp_id:
        contract_issues.append(f"esp_id_mismatch={raw_esp_id}")
    if raw_esp_id is None:
        contract_issues.append("esp_id=missing")

    raw_gpio = payload.get("gpio")
    gpio = topic_gpio
    parsed_gpio = _to_non_negative_int(raw_gpio, default=-1)
    if parsed_gpio < 0:
        contract_issues.append("gpio=missing_or_invalid")
    elif parsed_gpio != topic_gpio:
        contract_issues.append(f"gpio_mismatch={parsed_gpio}")

    command = (_to_text(payload.get("command")) or "").upper()
    if not command:
        command = "UNKNOWN_COMMAND"
        contract_issues.append("command=missing")

    try:
        value = float(payload.get("value", 0.0))
    except (TypeError, ValueError):
        value = 0.0
        contract_issues.append("value=invalid")

    success, success_known = _to_bool(payload.get("success"))
    if not success_known:
        contract_issues.append(f"success={payload.get('success')}")

    ts = _to_non_negative_int(payload.get("ts"), default=now_ts)
    if ts <= 0:
        ts = now_ts
        contract_issues.append("ts=invalid")

    correlation_id = _to_text(payload.get("correlation_id"))
    if correlation_id is None:
        correlation_id = f"missing-corr:act:{topic_esp_id}:{ts}"
        contract_issues.append("correlation_id=missing")

    is_contract_violation = len(contract_issues) > 0
    code = _to_text(payload.get("code"))
    if not code:
        code = "ACTUATOR_COMMAND_APPLIED" if success else "ACTUATOR_COMMAND_FAILED"
    if is_contract_violation:
        code = CONTRACT_UNKNOWN_CODE

    message = _to_text(payload.get("message")) or ""
    if is_contract_violation and not message:
        message = f"Contract violation: {', '.join(contract_issues)}"

    return CanonicalActuatorResponse(
        esp_id=esp_id,
        gpio=gpio,
        command=command,
        value=value,
        success=success,
        message=message,
        ts=ts,
        correlation_id=correlation_id,
        code=code,
        domain="actuator",
        severity="error" if (is_contract_violation or not success) else "info",
        terminality="terminal_success" if success else "terminal_failure",
        retry_policy="forbidden" if success else "allowed",
        is_final=True,
        is_contract_violation=is_contract_violation,
        raw_esp_id=raw_esp_id,
        raw_gpio=raw_gpio,
        raw_success=payload.get("success"),
    )
