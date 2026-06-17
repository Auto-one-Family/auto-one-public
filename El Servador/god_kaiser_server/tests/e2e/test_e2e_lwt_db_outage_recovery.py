"""
E2E: LWT/Recovery ordering for deterministic offline->online transitions.

This test targets the incident pattern where devices can remain offline
after restart/reconnect sequences. It verifies that a valid heartbeat after
an offline transition reliably converges state back to online.
"""

import asyncio

import pytest

try:
    from conftest import (
        E2EAPIClient,
        E2EMQTTClient,
        E2EWebSocketClient,
        ESPDeviceTestData,
        generate_unique_mock_id,
    )
except ImportError:
    E2EAPIClient = None
    E2EMQTTClient = None
    E2EWebSocketClient = None
    ESPDeviceTestData = None
    generate_unique_mock_id = None


pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


def _extract_status(payload: dict) -> str | None:
    if not isinstance(payload, dict):
        return None
    if isinstance(payload.get("status"), str):
        return payload["status"]
    data = payload.get("data")
    if isinstance(data, dict) and isinstance(data.get("status"), str):
        return data["status"]
    return None


class TestLWTHeartbeatRecovery:
    """E2E coverage for LWT -> first heartbeat recovery."""

    async def test_lwt_then_heartbeat_converges_to_online(
        self,
        api_client: E2EAPIClient,
        mqtt_client: E2EMQTTClient,
        ws_client: E2EWebSocketClient,
        cleanup_test_devices,
    ):
        esp_id = generate_unique_mock_id("RST")
        cleanup_test_devices(esp_id)

        await ws_client.subscribe({"types": ["esp_health"]})

        esp = ESPDeviceTestData(device_id=esp_id, name="Restart Recovery Device")
        register_result = await api_client.register_esp(esp)
        assert "device_id" in register_result or "id" in register_result

        await mqtt_client.publish_heartbeat(esp_id, uptime=90)
        await asyncio.sleep(1.5)

        # Simulate disconnect close to outage window.
        await mqtt_client.publish_lwt(esp_id, reason="unexpected_disconnect")
        offline_event = await ws_client.wait_for_event(
            "esp_health",
            timeout=8.0,
            match_fn=lambda msg: (
                (msg.get("data") or {}).get("esp_id") == esp_id
                and (msg.get("data") or {}).get("status") == "offline"
            ),
        )
        assert offline_event is not None, "Expected esp_health offline event after LWT"

        # Recovery signal: first valid heartbeat after restart/reconnect.
        await mqtt_client.publish_heartbeat(esp_id, uptime=3)
        online_event = await ws_client.wait_for_event(
            "esp_health",
            timeout=10.0,
            match_fn=lambda msg: (
                (msg.get("data") or {}).get("esp_id") == esp_id
                and (msg.get("data") or {}).get("status") == "online"
            ),
        )
        assert online_event is not None, "Expected esp_health online event after recovery heartbeat"

        # Final DB/API convergence check.
        final_status = None
        for _ in range(10):
            status_payload = await api_client.get_esp_status(esp_id)
            final_status = _extract_status(status_payload)
            if final_status == "online":
                break
            await asyncio.sleep(0.6)

        assert final_status == "online", "Device should converge back to online after recovery heartbeat"
