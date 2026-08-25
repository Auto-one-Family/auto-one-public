"""Unit tests for the esp_health WS-serializer and the AUT-884 offline-metrics fix.

AUT-884: Offline broadcasts (LWT / heartbeat-timeout) previously defaulted
heap_free/wifi_rssi/uptime to 0. Because the frontend resolves these via
``value ?? lastKnown`` (and ``0 ?? x === 0``), a default-0 overwrote the last
shown values ("0/0/0" flash). ``extract_last_known_health_metrics`` lets the
offline call sites carry the last persisted values from ``device_metadata``.
"""

from src.services.event_contract_serializers import (
    extract_last_known_health_metrics,
    serialize_esp_health_event,
)


def test_extract_last_known_health_metrics_none_returns_empty():
    assert extract_last_known_health_metrics(None) == {}


def test_extract_last_known_health_metrics_empty_returns_empty():
    assert extract_last_known_health_metrics({}) == {}


def test_extract_last_known_health_metrics_maps_all_keys():
    metadata = {
        "last_heap_free": 45000,
        "last_wifi_rssi": -45,
        "last_uptime": 3600,
        "last_disconnect": {"reason": "lwt"},
    }
    assert extract_last_known_health_metrics(metadata) == {
        "heap_free": 45000,
        "wifi_rssi": -45,
        "uptime": 3600,
    }


def test_extract_last_known_health_metrics_partial_only_known_keys():
    assert extract_last_known_health_metrics({"last_heap_free": 1000}) == {"heap_free": 1000}


def test_extract_last_known_health_metrics_skips_none_values():
    metadata = {"last_heap_free": None, "last_wifi_rssi": None, "last_uptime": 5}
    assert extract_last_known_health_metrics(metadata) == {"uptime": 5}


def test_serialize_esp_health_offline_without_metrics_defaults_to_zero():
    event = serialize_esp_health_event(
        esp_id="esp-1", status="offline", reason="unexpected_disconnect"
    )
    assert event["heap_free"] == 0
    assert event["wifi_rssi"] == 0
    assert event["uptime"] == 0
    assert event["status"] == "offline"


def test_serialize_esp_health_offline_with_last_known_metrics_keeps_values():
    metadata = {"last_heap_free": 45000, "last_wifi_rssi": -45, "last_uptime": 3600}
    event = serialize_esp_health_event(
        esp_id="esp-1",
        status="offline",
        reason="unexpected_disconnect",
        **extract_last_known_health_metrics(metadata),
    )
    assert event["heap_free"] == 45000
    assert event["wifi_rssi"] == -45
    assert event["uptime"] == 3600
    assert event["status"] == "offline"
    # Offline broadcasts keep the offline message, not the "online (...)" string.
    assert "offline" in event["message"]


def test_serialize_esp_health_online_passes_live_values():
    event = serialize_esp_health_event(
        esp_id="esp-1",
        status="online",
        heap_free=50000,
        wifi_rssi=-50,
        uptime=10,
        sensor_count=2,
        actuator_count=1,
    )
    assert event["heap_free"] == 50000
    assert event["wifi_rssi"] == -50
    assert event["uptime"] == 10
    assert event["status"] == "online"
    assert "online" in event["message"]
