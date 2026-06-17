from src.services.system_event_contract import (
    CONTRACT_UNKNOWN_CODE,
    canonicalize_diagnostics,
    canonicalize_error_event,
    canonicalize_heartbeat,
    canonicalize_lwt,
)


def test_canonicalize_error_event_maps_string_severity():
    payload = {"error_code": 1023, "severity": "critical", "category": "hw"}
    canonical = canonicalize_error_event(payload)

    assert canonical.is_contract_violation is False
    assert canonical.payload["severity"] == 3
    assert canonical.payload["severity_label"] == "critical"
    assert canonical.payload["category"] == "HARDWARE"


def test_canonicalize_error_event_marks_unknown_fields():
    payload = {"error_code": 1023, "severity": "fatal-plus", "category": "whatever"}
    canonical = canonicalize_error_event(payload)

    assert canonical.is_contract_violation is True
    assert canonical.contract_code == CONTRACT_UNKNOWN_CODE
    assert canonical.payload["contract_violation"] is True


def test_canonicalize_diagnostics_normalizes_state_fields():
    payload = {
        "heap_free": 10000,
        "wifi_rssi": -60,
        "system_state": "operational",
        "mqtt_cb_state": "closed",
        "wdt_mode": "production",
    }
    canonical = canonicalize_diagnostics(payload)

    assert canonical.is_contract_violation is False
    assert canonical.payload["system_state"] == "OPERATIONAL"
    assert canonical.payload["mqtt_cb_state"] == "CLOSED"
    assert canonical.payload["wdt_mode"] == "PRODUCTION"


def test_canonicalize_heartbeat_normalizes_legacy_fields():
    payload = {
        "ts": 1,
        "uptime": 5,
        "free_heap": 4096,
        "wifi_rssi": -45,
        "active_sensors": 2,
        "active_actuators": 1,
    }
    canonical = canonicalize_heartbeat(payload)

    assert canonical.is_contract_violation is False
    assert canonical.payload["heap_free"] == 4096
    assert canonical.payload["sensor_count"] == 2
    assert canonical.payload["actuator_count"] == 1


def test_canonicalize_lwt_unknown_reason_is_visible():
    payload = {"status": "offline", "reason": "alien_disconnect"}
    canonical = canonicalize_lwt(payload)

    assert canonical.is_contract_violation is True
    assert canonical.contract_code == CONTRACT_UNKNOWN_CODE
    assert canonical.payload["reason"] == "unexpected_disconnect"
    assert canonical.raw_fields["raw_reason"] == "alien_disconnect"
