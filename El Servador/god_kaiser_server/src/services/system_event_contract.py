"""
Canonical contract utilities for non-intent system events.

This module enforces a canonical-first ingestion path for:
- system/error
- system/diagnostics
- system/heartbeat
- system/will
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

CONTRACT_UNKNOWN_CODE = "CONTRACT_UNKNOWN_CODE"

_KNOWN_SYSTEM_STATES = {
    "BOOT",
    "WIFI_SETUP",
    "WIFI_CONNECTED",
    "MQTT_CONNECTING",
    "MQTT_CONNECTED",
    "AWAITING_USER_CONFIG",
    "ZONE_CONFIGURED",
    "SENSORS_CONFIGURED",
    "CONFIG_PENDING_AFTER_RESET",
    "OPERATIONAL",
    "PENDING_APPROVAL",
    "LIBRARY_DOWNLOADING",
    "SAFE_MODE",
    "SAFE_MODE_PROVISIONING",
    "ERROR",
    "UNKNOWN",
}
_SYSTEM_STATE_ALIASES = {
    "booting": "BOOT",
    "pending": "PENDING_APPROVAL",
    "running": "OPERATIONAL",
}

_KNOWN_MQTT_CB_STATES = {"CLOSED", "OPEN", "HALF_OPEN"}
_KNOWN_WDT_MODES = {"DISABLED", "PROVISIONING", "PRODUCTION", "SAFE_MODE"}

_SEVERITY_TO_LEVEL = {"info": 0, "warning": 1, "error": 2, "critical": 3}
_LEVEL_TO_SEVERITY = {value: key for key, value in _SEVERITY_TO_LEVEL.items()}

_KNOWN_ERROR_CATEGORIES = {
    "HARDWARE",
    "SERVICE",
    "COMMUNICATION",
    "APPLICATION",
    "SYSTEM",
    "SAFETY",
}
_ERROR_CATEGORY_ALIASES = {
    "hw": "HARDWARE",
    "comm": "COMMUNICATION",
}

_KNOWN_LWT_REASONS = {
    "unexpected_disconnect",
    "network_failure",
    "power_loss",
    "broker_timeout",
    "watchdog_reset",
    "crash",
}
_LWT_REASON_ALIASES = {
    "unexpected": "unexpected_disconnect",
    "disconnect": "unexpected_disconnect",
    "timeout": "broker_timeout",
    "wdt_reset": "watchdog_reset",
}


@dataclass(frozen=True)
class CanonicalSystemEvent:
    payload: dict[str, Any]
    is_contract_violation: bool
    contract_code: str | None
    contract_reason: str | None
    raw_fields: dict[str, Any]


def _to_text(value: Any) -> str | None:
    if value is None:
        return None
    parsed = str(value).strip()
    return parsed or None


def _to_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def canonicalize_error_event(payload: Mapping[str, Any]) -> CanonicalSystemEvent:
    canonical = dict(payload)
    issues: list[str] = []

    raw_severity = payload.get("severity")
    severity_level = _to_int(raw_severity)
    severity_label = None
    if severity_level is not None:
        severity_label = _LEVEL_TO_SEVERITY.get(severity_level)
    else:
        severity_text = _to_text(raw_severity)
        severity_label = _LEVEL_TO_SEVERITY.get(
            _SEVERITY_TO_LEVEL.get((severity_text or "").lower(), -1)
        )
        if severity_label is not None:
            severity_level = _SEVERITY_TO_LEVEL[severity_label]
    if severity_label is None or severity_level not in (0, 1, 2, 3):
        issues.append(f"severity={raw_severity!r}")
        severity_level = 2
        severity_label = "error"

    raw_category = _to_text(payload.get("category"))
    category_key = (raw_category or "").lower()
    category = _ERROR_CATEGORY_ALIASES.get(category_key, (raw_category or "").upper() or None)
    if category and category not in _KNOWN_ERROR_CATEGORIES:
        issues.append(f"category={raw_category!r}")
        category = "SYSTEM"

    canonical["severity"] = severity_level
    canonical["severity_label"] = severity_label
    canonical["category"] = category

    is_violation = bool(issues)
    contract_reason = None
    contract_code = None
    if is_violation:
        contract_code = CONTRACT_UNKNOWN_CODE
        contract_reason = (
            "Contract violation: unknown system/error values (" + ", ".join(issues) + ")"
        )
        canonical["message"] = contract_reason
        canonical["contract_violation"] = True

    return CanonicalSystemEvent(
        payload=canonical,
        is_contract_violation=is_violation,
        contract_code=contract_code,
        contract_reason=contract_reason,
        raw_fields={"raw_severity": raw_severity, "raw_category": raw_category},
    )


def _normalize_state_field(
    value: Any,
    *,
    field_name: str,
    allowed: set[str],
    aliases: Mapping[str, str] | None = None,
    fallback: str = "UNKNOWN",
) -> tuple[str | None, str | None]:
    aliases = aliases or {}
    raw_text = _to_text(value)
    if raw_text is None:
        return None, None
    normalized = aliases.get(raw_text.lower(), raw_text.upper())
    if normalized in allowed:
        return normalized, None
    return fallback, f"{field_name}={raw_text!r}"


def canonicalize_diagnostics(payload: Mapping[str, Any]) -> CanonicalSystemEvent:
    canonical = dict(payload)
    issues: list[str] = []

    if "free_heap" in payload and "heap_free" not in payload:
        canonical["heap_free"] = payload.get("free_heap")

    state, state_issue = _normalize_state_field(
        payload.get("system_state"),
        field_name="system_state",
        allowed=_KNOWN_SYSTEM_STATES,
        aliases=_SYSTEM_STATE_ALIASES,
    )
    if state is not None:
        canonical["system_state"] = state
    if state_issue:
        issues.append(state_issue)

    cb_state, cb_issue = _normalize_state_field(
        payload.get("mqtt_cb_state"),
        field_name="mqtt_cb_state",
        allowed=_KNOWN_MQTT_CB_STATES,
    )
    if cb_state is not None:
        canonical["mqtt_cb_state"] = cb_state
    if cb_issue:
        issues.append(cb_issue)

    wdt_mode, wdt_issue = _normalize_state_field(
        payload.get("wdt_mode"),
        field_name="wdt_mode",
        allowed=_KNOWN_WDT_MODES,
    )
    if wdt_mode is not None:
        canonical["wdt_mode"] = wdt_mode
    if wdt_issue:
        issues.append(wdt_issue)

    schema_version = payload.get("metrics_schema_version")
    if isinstance(schema_version, str) and schema_version.strip().isdigit():
        canonical["metrics_schema_version"] = int(schema_version.strip())

    is_violation = bool(issues)
    contract_reason = None
    contract_code = None
    if is_violation:
        contract_code = CONTRACT_UNKNOWN_CODE
        contract_reason = (
            "Contract violation: unknown system/diagnostics values (" + ", ".join(issues) + ")"
        )
        canonical["contract_violation"] = True

    return CanonicalSystemEvent(
        payload=canonical,
        is_contract_violation=is_violation,
        contract_code=contract_code,
        contract_reason=contract_reason,
        raw_fields={"raw_system_state": _to_text(payload.get("system_state"))},
    )


def canonicalize_heartbeat(payload: Mapping[str, Any]) -> CanonicalSystemEvent:
    """
    Normalize heartbeat fields we enforce (system_state, metrics_schema_version, heap aliases).

    Additional firmware keys (e.g. persistence_degraded, critical_outcome_drop_count,
    mqtt_circuit_breaker_open) are passed through unchanged — they are optional telemetry and
    must not break ingestion for older clients missing those fields.
    """
    canonical = dict(payload)
    issues: list[str] = []

    if "free_heap" in payload and "heap_free" not in payload:
        canonical["heap_free"] = payload.get("free_heap")
    if "active_sensors" in payload and "sensor_count" not in payload:
        canonical["sensor_count"] = payload.get("active_sensors")
    if "active_actuators" in payload and "actuator_count" not in payload:
        canonical["actuator_count"] = payload.get("active_actuators")

    state, state_issue = _normalize_state_field(
        payload.get("system_state"),
        field_name="system_state",
        allowed=_KNOWN_SYSTEM_STATES,
        aliases=_SYSTEM_STATE_ALIASES,
    )
    if state is not None:
        canonical["system_state"] = state
    if state_issue:
        issues.append(state_issue)

    schema_version = payload.get("metrics_schema_version")
    if isinstance(schema_version, str) and schema_version.strip().isdigit():
        canonical["metrics_schema_version"] = int(schema_version.strip())

    is_violation = bool(issues)
    contract_reason = None
    contract_code = None
    if is_violation:
        contract_code = CONTRACT_UNKNOWN_CODE
        contract_reason = (
            "Contract violation: unknown system/heartbeat values (" + ", ".join(issues) + ")"
        )
        canonical["contract_violation"] = True

    return CanonicalSystemEvent(
        payload=canonical,
        is_contract_violation=is_violation,
        contract_code=contract_code,
        contract_reason=contract_reason,
        raw_fields={"raw_system_state": _to_text(payload.get("system_state"))},
    )


def canonicalize_lwt(payload: Mapping[str, Any]) -> CanonicalSystemEvent:
    canonical = dict(payload)
    issues: list[str] = []

    raw_status = _to_text(payload.get("status"))
    normalized_status = (raw_status or "offline").lower()
    if normalized_status in {"offline", "disconnected", "down"}:
        canonical["status"] = "offline"
    else:
        canonical["status"] = "offline"
        issues.append(f"status={raw_status!r}")

    raw_reason = _to_text(payload.get("reason"))
    reason_key = (raw_reason or "unexpected_disconnect").lower()
    canonical_reason = _LWT_REASON_ALIASES.get(reason_key, reason_key)
    if canonical_reason not in _KNOWN_LWT_REASONS:
        issues.append(f"reason={raw_reason!r}")
        canonical_reason = "unexpected_disconnect"
    canonical["reason"] = canonical_reason

    is_violation = bool(issues)
    contract_reason = None
    contract_code = None
    if is_violation:
        contract_code = CONTRACT_UNKNOWN_CODE
        contract_reason = (
            "Contract violation: unknown system/will values (" + ", ".join(issues) + ")"
        )
        canonical["contract_violation"] = True

    return CanonicalSystemEvent(
        payload=canonical,
        is_contract_violation=is_violation,
        contract_code=contract_code,
        contract_reason=contract_reason,
        raw_fields={"raw_status": raw_status, "raw_reason": raw_reason},
    )
