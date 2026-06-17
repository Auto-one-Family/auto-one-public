"""AUT-69 / AUT-121 unit tests for heartbeat handler."""

import time
from datetime import datetime, timezone
from unittest.mock import patch

from src.mqtt.handlers.heartbeat_handler import HeartbeatHandler
from src.mqtt.handlers.heartbeat_metrics_handler import HeartbeatMetricsHandler
from src.schemas.esp import SessionAnnouncePayload


def test_reject_within_startup_window_increments_startup_counter() -> None:
    handler = HeartbeatHandler()
    esp_id = "ESP_AUT69_STARTUP"
    handler._last_session_connected_ts_by_esp[esp_id] = time.monotonic()
    payload = {
        "handover_contract_reject_count": 1,
        "handover_contract_last_reject": "MISSING_ACTIVE_SESSION_EPOCH",
    }
    metadata: dict = {}

    handler._track_contract_reject_metrics(esp_id, payload, metadata)

    assert metadata["handover_contract_reject_startup"] == 1
    assert metadata["handover_contract_reject_runtime"] == 0
    assert metadata["handover_contract_reject"] == 1


def test_reject_after_startup_window_increments_runtime_counter() -> None:
    handler = HeartbeatHandler()
    esp_id = "ESP_AUT69_RUNTIME"
    handler._last_session_connected_ts_by_esp[esp_id] = time.monotonic() - 1.5
    payload = {
        "handover_contract_reject_count": 2,
        "handover_contract_last_reject": "MISSING_ACTIVE_SESSION_EPOCH",
    }
    metadata = {
        "handover_contract_reject_count_last": 1,
        "handover_contract_reject_startup": 1,
        "handover_contract_reject_runtime": 0,
    }

    handler._track_contract_reject_metrics(esp_id, payload, metadata)

    assert metadata["handover_contract_reject_startup"] == 1
    assert metadata["handover_contract_reject_runtime"] == 1
    assert metadata["handover_contract_reject"] == 2


def test_payload_without_new_fields_keeps_backward_compatibility() -> None:
    handler = HeartbeatHandler()
    metadata = {"stable_key": "stable_value"}
    payload = {"ts": int(datetime.now(timezone.utc).timestamp())}

    handler._track_contract_reject_metrics("ESP_AUT69_COMPAT", payload, metadata)

    assert metadata == {"stable_key": "stable_value"}


def test_alias_mapping_accepts_both_handover_and_session_epoch() -> None:
    from_handover = SessionAnnouncePayload.from_payload(
        {"handover_epoch": 5, "reason": "reconnect", "ts_ms": 1000}
    )
    from_session = SessionAnnouncePayload.from_payload(
        {"session_epoch": 6, "reason": "boot", "ts_ms": 2000}
    )

    assert from_handover.handover_epoch == 5
    assert from_session.handover_epoch == 6


def test_handover_caches_enforce_maxsize() -> None:
    """Injektion über maxsize hinaus evicted ältere Einträge."""
    handler = HeartbeatHandler()

    for i in range(10_500):
        handler._handover_epoch_by_esp[f"test-esp-{i:06d}"] = i

    assert len(handler._handover_epoch_by_esp) <= 10_000


# ── AUT-121: Metrics merge into heartbeat ────────────────────────────


def _make_metrics_handler_with_entry(
    esp_id: str, metrics_payload: dict, receive_ts: float | None = None
) -> HeartbeatMetricsHandler:
    """Helper: create a HeartbeatMetricsHandler with one pre-populated entry."""
    mh = HeartbeatMetricsHandler()
    mh._latest[esp_id] = {
        "payload": metrics_payload,
        "receive_ts": receive_ts if receive_ts is not None else time.time(),
        "esp_ts": metrics_payload.get("ts", 0),
    }
    return mh


def test_merge_metrics_adds_fields_to_heartbeat_payload() -> None:
    """Metrics fields merge into heartbeat payload with freshness tags."""
    esp_id = "ESP_MERGE_001"
    now = time.time()
    metrics_payload = {"heap_min_free": 25000, "loop_time_avg_us": 3500, "ts": int(now) - 5}
    mh = _make_metrics_handler_with_entry(esp_id, metrics_payload, receive_ts=now - 2)

    heartbeat_payload = {
        "esp_id": esp_id,
        "ts": int(now),
        "heap_free": 45000,
        "wifi_rssi": -42,
        "uptime": 1000,
    }

    with patch(
        "src.mqtt.handlers.heartbeat_handler.get_heartbeat_metrics_handler",
        return_value=mh,
    ):
        HeartbeatHandler._merge_metrics_into_payload(esp_id, heartbeat_payload)

    assert heartbeat_payload["heap_min_free"] == 25000
    assert heartbeat_payload["loop_time_avg_us"] == 3500
    assert "metrics_delta_ts" in heartbeat_payload
    assert heartbeat_payload["metrics_delta_ts"] == int(now) - 5
    assert "metrics_freshness_seconds" in heartbeat_payload
    assert heartbeat_payload["metrics_freshness_seconds"] >= 0


def test_merge_metrics_does_not_overwrite_existing_heartbeat_fields() -> None:
    """Heartbeat is authoritative — existing fields must NOT be overwritten."""
    esp_id = "ESP_MERGE_002"
    now = time.time()
    metrics_payload = {"heap_free": 99999, "custom_field": "from_metrics", "ts": int(now)}
    mh = _make_metrics_handler_with_entry(esp_id, metrics_payload, receive_ts=now)

    heartbeat_payload = {
        "esp_id": esp_id,
        "ts": int(now),
        "heap_free": 45000,
    }

    with patch(
        "src.mqtt.handlers.heartbeat_handler.get_heartbeat_metrics_handler",
        return_value=mh,
    ):
        HeartbeatHandler._merge_metrics_into_payload(esp_id, heartbeat_payload)

    assert heartbeat_payload["heap_free"] == 45000
    assert heartbeat_payload["custom_field"] == "from_metrics"


def test_merge_metrics_without_cached_entry_is_noop() -> None:
    """Heartbeat without prior metrics must remain valid (backward compat)."""
    esp_id = "ESP_MERGE_003"
    mh = HeartbeatMetricsHandler()

    heartbeat_payload = {
        "esp_id": esp_id,
        "ts": int(time.time()),
        "heap_free": 45000,
    }
    original = dict(heartbeat_payload)

    with patch(
        "src.mqtt.handlers.heartbeat_handler.get_heartbeat_metrics_handler",
        return_value=mh,
    ):
        HeartbeatHandler._merge_metrics_into_payload(esp_id, heartbeat_payload)

    assert heartbeat_payload == original


def test_merge_metrics_order_metrics_before_heartbeat() -> None:
    """Simulate: metrics arrive before heartbeat — merged values present."""
    esp_id = "ESP_ORDER_001"
    now = time.time()
    metrics_payload = {
        "heap_min_free": 20000,
        "stack_high_water": 1024,
        "ts": int(now) - 3,
    }
    mh = _make_metrics_handler_with_entry(esp_id, metrics_payload, receive_ts=now - 1)

    heartbeat_payload = {
        "esp_id": esp_id,
        "ts": int(now),
        "heap_free": 40000,
        "wifi_rssi": -50,
        "uptime": 600,
    }

    with patch(
        "src.mqtt.handlers.heartbeat_handler.get_heartbeat_metrics_handler",
        return_value=mh,
    ):
        HeartbeatHandler._merge_metrics_into_payload(esp_id, heartbeat_payload)

    assert heartbeat_payload["heap_min_free"] == 20000
    assert heartbeat_payload["stack_high_water"] == 1024
    assert heartbeat_payload["metrics_delta_ts"] == int(now) - 3
    assert heartbeat_payload["heap_free"] == 40000


def test_reject_metrics_still_work_after_merge() -> None:
    """_track_contract_reject_metrics must still function with merged payload."""
    handler = HeartbeatHandler()
    esp_id = "ESP_REJECT_MERGE"
    handler._last_session_connected_ts_by_esp[esp_id] = time.monotonic() - 2.0

    payload = {
        "ts": int(time.time()),
        "handover_contract_reject_count": 3,
        "handover_contract_last_reject": "EPOCH_MISMATCH",
        "heap_min_free": 20000,
        "metrics_delta_ts": 2,
        "metrics_freshness_seconds": 0.5,
    }
    metadata: dict = {}

    handler._track_contract_reject_metrics(esp_id, payload, metadata)

    assert metadata["handover_contract_reject"] == 3
    assert metadata["handover_contract_reject_runtime"] == 3
