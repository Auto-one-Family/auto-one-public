"""
Shared serializers for MQTT event projections.

Single source of truth for REST + WebSocket event payload contracts.
"""

from __future__ import annotations

from typing import Any, Mapping


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _uptime_suffix(uptime_seconds: Any) -> str:
    uptime = _to_int(uptime_seconds, 0)
    if uptime <= 0:
        return ""
    hours = uptime // 3600
    minutes = (uptime % 3600) // 60
    if hours > 0:
        return f" | Uptime: {hours}h {minutes}m"
    if minutes > 0:
        return f" | Uptime: {minutes}m"
    return ""


def build_esp_health_message(esp_id: str, heap_free: Any, wifi_rssi: Any, uptime: Any) -> str:
    heap_free_int = _to_int(heap_free, 0)
    heap_kb = heap_free_int // 1024 if heap_free_int > 0 else 0
    wifi_rssi_int = _to_int(wifi_rssi, 0)
    return f"{esp_id} online ({heap_kb}KB frei, RSSI: {wifi_rssi_int}dBm){_uptime_suffix(uptime)}"


def serialize_actuator_response_event(
    *,
    esp_id: str,
    gpio: Any,
    command: Any,
    value: Any,
    success: Any,
    message: Any,
    timestamp: Any,
    correlation_id: str | None = None,
    issued_by: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "esp_id": esp_id,
        "gpio": _to_int(gpio),
        "command": str(command) if command is not None else "UNKNOWN",
        "value": _to_float(value),
        "success": bool(success),
        "message": str(message) if message is not None else "",
        "timestamp": _to_int(timestamp),
    }
    if correlation_id:
        payload["correlation_id"] = correlation_id
    if issued_by:
        payload["issued_by"] = issued_by
    return payload


def serialize_config_response_event(
    *,
    esp_id: str,
    config_type: Any,
    status: Any,
    count: Any,
    failed_count: Any,
    message: Any,
    timestamp: Any,
    correlation_id: str | None = None,
    error_code: Any = None,
    error_description: Any = None,
    severity: Any = None,
    troubleshooting: list[Any] | None = None,
    recoverable: Any = None,
    user_action_required: Any = None,
    failures: list[Mapping[str, Any]] | None = None,
    failed_item: Mapping[str, Any] | None = None,
    request_id: Any = None,
    reason_code: Any = None,
    generation: Any = None,
    config_fingerprint: Any = None,
    trigger_source: Any = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "esp_id": esp_id,
        "config_type": str(config_type) if config_type is not None else "unknown",
        "status": str(status) if status is not None else "error",
        "count": _to_int(count),
        "failed_count": _to_int(failed_count),
        "message": str(message) if message is not None else "",
        "timestamp": _to_int(timestamp),
        "correlation_id": correlation_id,
    }
    if error_code is not None:
        payload["error_code"] = error_code
    if error_description is not None:
        payload["error_description"] = error_description
    if severity is not None:
        payload["severity"] = severity
    if troubleshooting is not None:
        payload["troubleshooting"] = troubleshooting
    if recoverable is not None:
        payload["recoverable"] = bool(recoverable)
    if user_action_required is not None:
        payload["user_action_required"] = bool(user_action_required)
    if failures:
        payload["failures"] = [dict(item) for item in failures]
    elif failed_item:
        payload["failed_item"] = dict(failed_item)
    if request_id is not None:
        payload["request_id"] = str(request_id)
    if reason_code is not None:
        payload["reason_code"] = str(reason_code)
    if generation is not None:
        payload["generation"] = _to_int(generation)
    if config_fingerprint is not None:
        payload["config_fingerprint"] = str(config_fingerprint)
    if trigger_source is not None:
        payload["trigger_source"] = str(trigger_source)
    return payload


def serialize_error_event(
    *,
    esp_id: str,
    esp_name: Any,
    error_log_id: Any,
    error_code: Any,
    severity: Any,
    category: Any,
    title: Any,
    message: Any,
    troubleshooting: list[Any] | None,
    user_action_required: Any,
    recoverable: Any,
    docs_link: Any,
    context: Mapping[str, Any] | None,
    timestamp: Any,
) -> dict[str, Any]:
    return {
        "esp_id": esp_id,
        "esp_name": str(esp_name) if esp_name is not None else esp_id,
        "error_log_id": str(error_log_id) if error_log_id is not None else None,
        "error_code": error_code,
        "severity": severity,
        "category": category,
        "title": title,
        "message": message,
        "troubleshooting": troubleshooting or [],
        "user_action_required": bool(user_action_required),
        "recoverable": bool(recoverable),
        "docs_link": docs_link,
        "context": dict(context) if isinstance(context, Mapping) else {},
        "timestamp": _to_int(timestamp),
    }


def serialize_diagnostics_event(
    *,
    esp_id: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "esp_id": esp_id,
        "heap_free": payload.get("heap_free"),
        "heap_min_free": payload.get("heap_min_free"),
        "heap_fragmentation": payload.get("heap_fragmentation"),
        "uptime_seconds": payload.get("uptime_seconds"),
        "error_count": payload.get("error_count", 0),
        "wifi_rssi": payload.get("wifi_rssi"),
        "system_state": payload.get("system_state"),
        "boot_reason": payload.get("boot_reason"),
        "mqtt_cb_state": payload.get("mqtt_cb_state"),
        "wdt_mode": payload.get("wdt_mode"),
        "wdt_timeouts_24h": payload.get("wdt_timeouts_24h"),
        "boot_sequence_id": payload.get("boot_sequence_id"),
        "reset_reason": payload.get("reset_reason"),
        "segment_start_ts": payload.get("segment_start_ts"),
        "metrics_schema_version": payload.get("metrics_schema_version"),
        "timestamp": _to_int(payload.get("ts", 0)),
    }


def serialize_esp_health_event(
    *,
    esp_id: str,
    status: str,
    heap_free: Any = 0,
    wifi_rssi: Any = 0,
    uptime: Any = 0,
    sensor_count: Any = 0,
    actuator_count: Any = 0,
    timestamp: Any = 0,
    gpio_status: list[Mapping[str, Any]] | None = None,
    gpio_reserved_count: Any = 0,
    reason: str | None = None,
    source: str | None = None,
    timeout_seconds: Any = None,
    actuator_states_reset: Any = None,
    runtime_telemetry: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_status = str(status)
    base_message = build_esp_health_message(esp_id, heap_free, wifi_rssi, uptime)
    if normalized_status != "online":
        base_message = f"{esp_id} {normalized_status}"
        if reason:
            base_message = f"{base_message} ({reason})"

    payload: dict[str, Any] = {
        "esp_id": esp_id,
        "status": normalized_status,
        "message": base_message,
        "heap_free": _to_int(heap_free),
        "wifi_rssi": _to_int(wifi_rssi),
        "uptime": _to_int(uptime),
        "sensor_count": _to_int(sensor_count),
        "actuator_count": _to_int(actuator_count),
        "timestamp": _to_int(timestamp),
        "gpio_status": [dict(item) for item in (gpio_status or [])],
        "gpio_reserved_count": _to_int(gpio_reserved_count),
    }
    if reason is not None:
        payload["reason"] = reason
    if source is not None:
        payload["source"] = source
    if timeout_seconds is not None:
        payload["timeout_seconds"] = _to_int(timeout_seconds)
    if actuator_states_reset is not None:
        payload["actuator_states_reset"] = _to_int(actuator_states_reset)
    if runtime_telemetry:
        for key, value in runtime_telemetry.items():
            payload[key] = value
    return payload
