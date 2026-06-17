"""Integration Tests: MQTTCommandBridge + ZoneService

Tests ACK-gesteuerte Zone/Subzone-Operationen:
- Zone-Wechsel mit Subzone-Transfer (Happy Path)
- Zone-Wechsel mit ACK-Timeout
- Zone-Wechsel mit Error-ACK
- Heartbeat waehrend pending Assignment
- Mock-ESP ueberspringt Bridge
- Zone-Removal ueber Bridge
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.mqtt_command_bridge import (
    MQTTACKTimeoutError,
    MQTTCommandBridge,
)
from src.services.zone_service import ZoneService


def _make_mock_esp_repo(device_id: str, zone_id: str = None, device_metadata: dict = None):
    """Create a mock ESPRepository with a device."""
    device = MagicMock()
    device.device_id = device_id
    device.zone_id = zone_id
    device.master_zone_id = None
    device.zone_name = None
    device.kaiser_id = "god"
    device.device_metadata = device_metadata or {}
    device.is_zone_master = False

    repo = AsyncMock()
    repo.get_by_device_id = AsyncMock(return_value=device)
    repo.session = AsyncMock()
    repo.session.add = MagicMock()
    repo.session.flush = AsyncMock()
    return repo, device


def _make_mock_zone_repo(zone_id: str = "zone_b", status: str = "active"):
    """Create a mock ZoneRepository returning a valid zone."""
    zone = MagicMock()
    zone.zone_id = zone_id
    zone.name = f"Zone {zone_id}"
    zone.status = status
    return zone


# =============================================================================
# Szenario 1: Zone-Wechsel mit Transfer — Happy Path
# =============================================================================


@pytest.mark.asyncio
async def test_zone_assign_with_transfer_happy_path():
    """Zone-Wechsel mit subzone transfer: Zone-ACK dann Subzone-ACK."""
    mock_client = MagicMock()
    mock_client.publish.return_value = True
    bridge = MQTTCommandBridge(mock_client)

    repo, device = _make_mock_esp_repo("ESP_TEST01", zone_id="zone_a")

    zone_service = ZoneService(repo, command_bridge=bridge)

    async def simulate_acks():
        await asyncio.sleep(0.05)
        # Zone ACK (correlation_id required — no FIFO fallback)
        zc = bridge._esp_pending[("ESP_TEST01", "zone")][0]
        bridge.resolve_ack(
            ack_data={
                "status": "zone_assigned",
                "zone_id": "zone_b",
                "correlation_id": zc,
            },
            esp_id="ESP_TEST01",
            command_type="zone",
        )
        await asyncio.sleep(0.05)
        # Subzone ACKs
        s1 = bridge._esp_pending[("ESP_TEST01", "subzone")][0]
        bridge.resolve_ack(
            ack_data={
                "status": "subzone_assigned",
                "subzone_id": "sz_1",
                "correlation_id": s1,
            },
            esp_id="ESP_TEST01",
            command_type="subzone",
        )
        await asyncio.sleep(0.05)
        s2 = bridge._esp_pending[("ESP_TEST01", "subzone")][0]
        bridge.resolve_ack(
            ack_data={
                "status": "subzone_assigned",
                "subzone_id": "sz_2",
                "correlation_id": s2,
            },
            esp_id="ESP_TEST01",
            command_type="subzone",
        )

    asyncio.create_task(simulate_acks())

    with (
        patch.object(zone_service, "_handle_subzone_strategy") as mock_strategy,
        patch("src.services.zone_service.ZoneRepository") as MockZoneRepo,
        patch.object(zone_service, "_update_mock_esp_zone", new_callable=AsyncMock),
    ):

        mock_zone = _make_mock_zone_repo("zone_b")
        MockZoneRepo.return_value.get_by_zone_id = AsyncMock(return_value=mock_zone)

        mock_strategy.return_value = [
            {
                "subzone_id": "sz_1",
                "subzone_name": "Subzone 1",
                "assigned_gpios": [2, 4],
                "old_parent": "zone_a",
                "new_parent": "zone_b",
                "action": "transferred",
            },
            {
                "subzone_id": "sz_2",
                "subzone_name": "Subzone 2",
                "assigned_gpios": [15, 0],
                "old_parent": "zone_a",
                "new_parent": "zone_b",
                "action": "transferred",
            },
        ]

        result = await zone_service.assign_zone(
            device_id="ESP_TEST01",
            zone_id="zone_b",
            subzone_strategy="transfer",
        )

    assert result.mqtt_sent is True
    assert result.ack_received is True
    assert result.warning is None
    # MQTT should have been called 3 times: 1 zone + 2 subzones
    assert mock_client.publish.call_count == 3

    # Check that GPIO 0 was filtered from subzone payload
    subzone_calls = [call for call in mock_client.publish.call_args_list if "subzone" in call[0][0]]
    for call in subzone_calls:
        payload = json.loads(call[0][1])
        assert 0 not in payload.get("assigned_gpios", [])
        assert payload["parent_zone_id"] == ""  # EMPTY — firmware sets current zone


# =============================================================================
# Szenario 2: Zone-Wechsel — ACK Timeout
# =============================================================================


@pytest.mark.asyncio
async def test_zone_assign_ack_timeout():
    """Zone-Wechsel ohne ACK -> Timeout, mqtt_sent=False, ack_received=False, warning set."""
    mock_client = MagicMock()
    mock_client.publish.return_value = True
    bridge = MQTTCommandBridge(mock_client)

    repo, device = _make_mock_esp_repo("ESP_TEST01", zone_id="zone_a")
    zone_service = ZoneService(repo, command_bridge=bridge)

    with (
        patch("src.services.zone_service.ZoneRepository") as MockZoneRepo,
        patch.object(zone_service, "_handle_subzone_strategy", return_value=[]),
        patch.object(zone_service, "_update_mock_esp_zone", new_callable=AsyncMock),
        patch("src.services.zone_context_service.ZoneContextService") as MockZoneContextService,
    ):

        mock_zone = _make_mock_zone_repo("zone_b")
        MockZoneRepo.return_value.get_by_zone_id = AsyncMock(return_value=mock_zone)
        MockZoneContextService.return_value.sync_zone_name = AsyncMock(return_value=True)

        # Use very short timeout for test speed
        with patch.object(bridge, "DEFAULT_TIMEOUT", 0.1):
            result = await zone_service.assign_zone(
                device_id="ESP_TEST01",
                zone_id="zone_b",
            )

    assert result.mqtt_sent is False
    assert result.ack_received is False
    assert result.warning is not None
    assert "ACK-Timeout" in result.warning
    # DB update still happened (zone_id set on device ORM object)
    assert device.zone_id == "zone_b"
    # pending_zone_assignment should remain in device_metadata
    assert "pending_zone_assignment" in device.device_metadata


# =============================================================================
# Szenario 3: Zone-Wechsel — Error-ACK
# =============================================================================


@pytest.mark.asyncio
async def test_zone_assign_error_ack():
    """Zone-ACK mit status=error -> kein Subzone-MQTT, mqtt_sent=False."""
    mock_client = MagicMock()
    mock_client.publish.return_value = True
    bridge = MQTTCommandBridge(mock_client)

    repo, device = _make_mock_esp_repo("ESP_TEST01", zone_id="zone_a")
    zone_service = ZoneService(repo, command_bridge=bridge)

    async def simulate_error_ack():
        await asyncio.sleep(0.05)
        zc = bridge._esp_pending[("ESP_TEST01", "zone")][0]
        bridge.resolve_ack(
            ack_data={
                "status": "error",
                "message": "NVS write failed",
                "correlation_id": zc,
            },
            esp_id="ESP_TEST01",
            command_type="zone",
        )

    asyncio.create_task(simulate_error_ack())

    with (
        patch("src.services.zone_service.ZoneRepository") as MockZoneRepo,
        patch.object(zone_service, "_handle_subzone_strategy") as mock_strategy,
        patch.object(zone_service, "_update_mock_esp_zone", new_callable=AsyncMock),
    ):

        mock_zone = _make_mock_zone_repo("zone_b")
        MockZoneRepo.return_value.get_by_zone_id = AsyncMock(return_value=mock_zone)
        mock_strategy.return_value = [
            {
                "subzone_id": "sz_1",
                "subzone_name": "SZ1",
                "assigned_gpios": [2],
                "old_parent": "zone_a",
                "new_parent": "zone_b",
                "action": "transferred",
            },
        ]

        result = await zone_service.assign_zone(
            device_id="ESP_TEST01",
            zone_id="zone_b",
            subzone_strategy="transfer",
        )

    assert result.mqtt_sent is False
    # Only 1 MQTT publish (zone/assign) — no subzone/assign because zone ACK was error
    assert mock_client.publish.call_count == 1


# =============================================================================
# Szenario 4: Heartbeat waehrend pending Assignment
# =============================================================================


@pytest.mark.asyncio
async def test_heartbeat_tolerates_pending_assignment():
    """Heartbeat with pending_zone_assignment tolerates zone mismatch."""
    mock_client = MagicMock()
    bridge = MQTTCommandBridge(mock_client)

    # has_pending should be False when nothing is pending
    assert bridge.has_pending("ESP_TEST01") is False


# =============================================================================
# Szenario 5: Mock-ESP ueberspringt Bridge
# =============================================================================


@pytest.mark.asyncio
async def test_mock_esp_skips_bridge():
    """Mock-ESP uses fire-and-forget, not bridge."""
    mock_client = MagicMock()
    mock_client.publish.return_value = True
    bridge = MQTTCommandBridge(mock_client)

    # Mock publisher for fire-and-forget path (post-AUT-225: zone_service uses publish_raw)
    mock_publisher = MagicMock()
    mock_publisher.client = MagicMock()
    mock_publisher.client.publish.return_value = True
    mock_publisher.publish_raw = MagicMock(return_value=True)

    # Use a MOCK device ID
    repo, device = _make_mock_esp_repo("ESP_MOCK_001")
    zone_service = ZoneService(repo, publisher=mock_publisher, command_bridge=bridge)

    with (
        patch("src.services.zone_service.ZoneRepository") as MockZoneRepo,
        patch.object(zone_service, "_handle_subzone_strategy", return_value=[]),
        patch.object(zone_service, "_update_mock_esp_zone", new_callable=AsyncMock),
    ):

        mock_zone = _make_mock_zone_repo("zone_b")
        MockZoneRepo.return_value.get_by_zone_id = AsyncMock(return_value=mock_zone)

        result = await zone_service.assign_zone(
            device_id="ESP_MOCK_001",
            zone_id="zone_b",
        )

    assert result.mqtt_sent is True
    # Should use fire-and-forget via publisher.publish_raw (AUT-225), not bridge
    assert mock_publisher.publish_raw.call_count == 1
    # Bridge mock_client should NOT have been called (skipped for mock ESPs)
    assert mock_client.publish.call_count == 0


# =============================================================================
# Szenario 6: Zone-Removal ueber Bridge
# =============================================================================


@pytest.mark.asyncio
async def test_zone_removal_via_bridge():
    """Zone removal with ACK -> mqtt_sent=True."""
    mock_client = MagicMock()
    mock_client.publish.return_value = True
    bridge = MQTTCommandBridge(mock_client)

    repo, device = _make_mock_esp_repo("ESP_TEST01", zone_id="zone_a")
    zone_service = ZoneService(repo, command_bridge=bridge)

    async def simulate_removal_ack():
        await asyncio.sleep(0.05)
        zc = bridge._esp_pending[("ESP_TEST01", "zone")][0]
        bridge.resolve_ack(
            ack_data={"status": "zone_removed", "correlation_id": zc},
            esp_id="ESP_TEST01",
            command_type="zone",
        )

    asyncio.create_task(simulate_removal_ack())

    with (
        patch.object(zone_service, "_update_mock_esp_zone", new_callable=AsyncMock),
        patch("src.services.zone_service.SubzoneRepository") as MockSubzoneRepo,
    ):

        MockSubzoneRepo.return_value.delete_all_by_esp = AsyncMock(return_value=0)

        result = await zone_service.remove_zone(device_id="ESP_TEST01")

    assert result.mqtt_sent is True
    assert result.success is True
    # zone/assign with empty zone_id
    published_payload = json.loads(mock_client.publish.call_args[0][1])
    assert published_payload["zone_id"] == ""


# =============================================================================
# Szenario 7: Reset-Strategie loescht Subzones aus DB (BUG-3)
# =============================================================================


@pytest.mark.asyncio
async def test_reset_strategy_deletes_subzones_from_db():
    """Reset strategy must call delete_all_by_esp to physically remove subzones."""
    mock_subzone_1 = MagicMock()
    mock_subzone_1.subzone_id = "sz_1"
    mock_subzone_1.parent_zone_id = "zone_a"
    mock_subzone_1.subzone_name = "Subzone 1"
    mock_subzone_1.assigned_gpios = [2, 4]
    mock_subzone_1.safe_mode_active = True

    mock_subzone_2 = MagicMock()
    mock_subzone_2.subzone_id = "sz_2"
    mock_subzone_2.parent_zone_id = "zone_a"
    mock_subzone_2.subzone_name = "Subzone 2"
    mock_subzone_2.assigned_gpios = [15]
    mock_subzone_2.safe_mode_active = False

    subzone_repo = AsyncMock()
    subzone_repo.get_by_esp = AsyncMock(return_value=[mock_subzone_1, mock_subzone_2])
    subzone_repo.delete_all_by_esp = AsyncMock(return_value=2)

    repo, _ = _make_mock_esp_repo("ESP_TEST01", zone_id="zone_a")
    zone_service = ZoneService(repo)

    affected = await zone_service._handle_subzone_strategy(
        device_id="ESP_TEST01",
        old_zone_id="zone_a",
        new_zone_id="zone_b",
        strategy="reset",
        subzone_repo=subzone_repo,
    )

    # Must call delete_all_by_esp
    subzone_repo.delete_all_by_esp.assert_awaited_once_with("ESP_TEST01")

    # Affected list has both subzones with action="deleted"
    assert len(affected) == 2
    assert affected[0]["action"] == "deleted"
    assert affected[1]["action"] == "deleted"
    assert affected[0]["subzone_id"] == "sz_1"
    assert affected[1]["subzone_id"] == "sz_2"


@pytest.mark.asyncio
async def test_reset_strategy_no_subzones():
    """Reset strategy with no subzones returns empty list without errors."""
    subzone_repo = AsyncMock()
    subzone_repo.get_by_esp = AsyncMock(return_value=[])

    repo, _ = _make_mock_esp_repo("ESP_TEST01", zone_id="zone_a")
    zone_service = ZoneService(repo)

    affected = await zone_service._handle_subzone_strategy(
        device_id="ESP_TEST01",
        old_zone_id="zone_a",
        new_zone_id="zone_b",
        strategy="reset",
        subzone_repo=subzone_repo,
    )

    assert affected == []
    subzone_repo.delete_all_by_esp.assert_not_awaited()


# =============================================================================
# Szenario 8: Mock-ESP hat ack_received=None (BUG-4 Schema)
# =============================================================================


@pytest.mark.asyncio
async def test_mock_esp_ack_received_is_none():
    """Mock-ESP uses fire-and-forget, ack_received should be None."""
    mock_publisher = MagicMock()
    mock_publisher.client = MagicMock()
    mock_publisher.client.publish.return_value = True
    mock_publisher.publish_raw = MagicMock(return_value=True)

    repo, device = _make_mock_esp_repo("ESP_MOCK_002")
    mock_client = MagicMock()
    bridge = MQTTCommandBridge(mock_client)
    zone_service = ZoneService(repo, publisher=mock_publisher, command_bridge=bridge)

    with (
        patch("src.services.zone_service.ZoneRepository") as MockZoneRepo,
        patch.object(zone_service, "_handle_subzone_strategy", return_value=[]),
        patch.object(zone_service, "_update_mock_esp_zone", new_callable=AsyncMock),
    ):

        mock_zone = _make_mock_zone_repo("zone_b")
        MockZoneRepo.return_value.get_by_zone_id = AsyncMock(return_value=mock_zone)

        result = await zone_service.assign_zone(
            device_id="ESP_MOCK_002",
            zone_id="zone_b",
        )

    assert result.ack_received is None
    assert result.warning is None
    assert result.mqtt_sent is True


# =============================================================================
# Szenario 9: ACK-Timeout — DB wird trotzdem aktualisiert (BUG-4)
# =============================================================================


@pytest.mark.asyncio
async def test_ack_timeout_db_still_updated():
    """ACK timeout must NOT prevent DB update — zone_id must be set."""
    mock_client = MagicMock()
    mock_client.publish.return_value = True
    bridge = MQTTCommandBridge(mock_client)

    repo, device = _make_mock_esp_repo("ESP_TEST01", zone_id="zone_a")
    zone_service = ZoneService(repo, command_bridge=bridge)

    with (
        patch("src.services.zone_service.ZoneRepository") as MockZoneRepo,
        patch.object(zone_service, "_handle_subzone_strategy", return_value=[]),
        patch.object(zone_service, "_update_mock_esp_zone", new_callable=AsyncMock),
    ):

        mock_zone = _make_mock_zone_repo("zone_b")
        MockZoneRepo.return_value.get_by_zone_id = AsyncMock(return_value=mock_zone)

        with patch.object(bridge, "DEFAULT_TIMEOUT", 0.1):
            result = await zone_service.assign_zone(
                device_id="ESP_TEST01",
                zone_id="zone_b",
                zone_name="Zone B",
            )

    # No exception raised — returns 200-equivalent result
    assert result.success is True
    assert result.ack_received is False
    assert result.message == "Zone assignment saved (ACK timeout)"

    # DB update happened despite timeout
    assert device.zone_id == "zone_b"
    assert device.zone_name == "Zone B"
