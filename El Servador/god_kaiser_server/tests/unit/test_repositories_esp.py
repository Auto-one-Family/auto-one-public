"""
Unit Tests: ESPRepository
Tests for ESP device-specific queries
"""

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio

from src.db.repositories.esp_repo import ESPRepository


@pytest.mark.asyncio
class TestESPRepositoryGetByDeviceID:
    """Test ESPRepository.get_by_device_id()"""

    async def test_get_by_device_id_success(self, esp_repo: ESPRepository):
        """Test successful retrieval by device_id."""
        device = await esp_repo.create(
            device_id="ESP_TEST_001",
            name="Test Device",
            ip_address="192.168.1.100",
            mac_address="AA:BB:CC:DD:EE:FF",
            firmware_version="1.0.0",
            hardware_type="ESP32_WROOM",
            status="online",
        )

        retrieved = await esp_repo.get_by_device_id("ESP_TEST_001")

        assert retrieved is not None
        assert retrieved.device_id == "ESP_TEST_001"
        assert retrieved.id == device.id

    async def test_get_by_device_id_not_found(self, esp_repo: ESPRepository):
        """Test retrieval with non-existent device_id."""
        result = await esp_repo.get_by_device_id("ESP_NONEXISTENT")
        assert result is None


@pytest.mark.asyncio
class TestESPRepositoryGetByZone:
    """Test ESPRepository.get_by_zone()"""

    async def test_get_by_zone_success(self, esp_repo: ESPRepository):
        """Test retrieval by zone_id."""
        # Create devices in different zones
        device1 = await esp_repo.create(
            device_id="ESP_ZONE1_001",
            name="Zone 1 Device 1",
            ip_address="192.168.1.100",
            mac_address="AA:BB:CC:DD:EE:01",
            firmware_version="1.0.0",
            hardware_type="ESP32_WROOM",
            status="online",
            zone_id="zone_1",
            zone_name="Zone 1",
        )

        device2 = await esp_repo.create(
            device_id="ESP_ZONE1_002",
            name="Zone 1 Device 2",
            ip_address="192.168.1.101",
            mac_address="AA:BB:CC:DD:EE:02",
            firmware_version="1.0.0",
            hardware_type="ESP32_WROOM",
            status="online",
            zone_id="zone_1",
            zone_name="Zone 1",
        )

        await esp_repo.create(
            device_id="ESP_ZONE2_001",
            name="Zone 2 Device",
            ip_address="192.168.1.102",
            mac_address="AA:BB:CC:DD:EE:03",
            firmware_version="1.0.0",
            hardware_type="ESP32_WROOM",
            status="online",
            zone_id="zone_2",
            zone_name="Zone 2",
        )

        # Get devices in zone_1
        zone_devices = await esp_repo.get_by_zone("zone_1")

        assert len(zone_devices) == 2
        device_ids = {d.device_id for d in zone_devices}
        assert device_ids == {"ESP_ZONE1_001", "ESP_ZONE1_002"}

    async def test_get_by_zone_empty(self, esp_repo: ESPRepository):
        """Test retrieval with empty zone."""
        devices = await esp_repo.get_by_zone("nonexistent_zone")
        assert len(devices) == 0


@pytest.mark.asyncio
class TestESPRepositoryGetZoneMasters:
    """Test ESPRepository.get_zone_masters()"""

    async def test_get_zone_masters_all(self, esp_repo: ESPRepository):
        """Test retrieval of all zone masters."""
        # Create zone masters
        await esp_repo.create(
            device_id="ESP_MASTER_001",
            name="Master 1",
            ip_address="192.168.1.100",
            mac_address="AA:BB:CC:DD:EE:01",
            firmware_version="1.0.0",
            hardware_type="ESP32_WROOM",
            status="online",
            zone_id="zone_1",
            zone_name="Zone 1",
            is_zone_master=True,
        )

        await esp_repo.create(
            device_id="ESP_MASTER_002",
            name="Master 2",
            ip_address="192.168.1.101",
            mac_address="AA:BB:CC:DD:EE:02",
            firmware_version="1.0.0",
            hardware_type="ESP32_WROOM",
            status="online",
            zone_id="zone_2",
            zone_name="Zone 2",
            is_zone_master=True,
        )

        # Create non-master device
        await esp_repo.create(
            device_id="ESP_SLAVE_001",
            name="Slave 1",
            ip_address="192.168.1.102",
            mac_address="AA:BB:CC:DD:EE:03",
            firmware_version="1.0.0",
            hardware_type="ESP32_WROOM",
            status="online",
            zone_id="zone_1",
            zone_name="Zone 1",
            is_zone_master=False,
        )

        masters = await esp_repo.get_zone_masters()

        assert len(masters) == 2
        device_ids = {d.device_id for d in masters}
        assert device_ids == {"ESP_MASTER_001", "ESP_MASTER_002"}

    async def test_get_zone_masters_filtered(self, esp_repo: ESPRepository):
        """Test retrieval of zone masters filtered by zone_id."""
        await esp_repo.create(
            device_id="ESP_MASTER_Z1",
            name="Zone 1 Master",
            ip_address="192.168.1.100",
            mac_address="AA:BB:CC:DD:EE:01",
            firmware_version="1.0.0",
            hardware_type="ESP32_WROOM",
            status="online",
            zone_id="zone_1",
            zone_name="Zone 1",
            is_zone_master=True,
        )

        await esp_repo.create(
            device_id="ESP_MASTER_Z2",
            name="Zone 2 Master",
            ip_address="192.168.1.101",
            mac_address="AA:BB:CC:DD:EE:02",
            firmware_version="1.0.0",
            hardware_type="ESP32_WROOM",
            status="online",
            zone_id="zone_2",
            zone_name="Zone 2",
            is_zone_master=True,
        )

        masters = await esp_repo.get_zone_masters(zone_id="zone_1")

        assert len(masters) == 1
        assert masters[0].device_id == "ESP_MASTER_Z1"


@pytest.mark.asyncio
class TestESPRepositoryGetOnline:
    """Test ESPRepository.get_online()"""

    async def test_get_online_devices(self, esp_repo: ESPRepository):
        """Test retrieval of online devices."""
        await esp_repo.create(
            device_id="ESP_ONLINE_001",
            name="Online Device",
            ip_address="192.168.1.100",
            mac_address="AA:BB:CC:DD:EE:01",
            firmware_version="1.0.0",
            hardware_type="ESP32_WROOM",
            status="online",
        )

        await esp_repo.create(
            device_id="ESP_OFFLINE_001",
            name="Offline Device",
            ip_address="192.168.1.101",
            mac_address="AA:BB:CC:DD:EE:02",
            firmware_version="1.0.0",
            hardware_type="ESP32_WROOM",
            status="offline",
        )

        online_devices = await esp_repo.get_online()

        assert len(online_devices) == 1
        assert online_devices[0].device_id == "ESP_ONLINE_001"


@pytest.mark.asyncio
class TestESPRepositoryGetByStatus:
    """Test ESPRepository.get_by_status()"""

    async def test_get_by_status_success(self, esp_repo: ESPRepository):
        """Test retrieval by status."""
        await esp_repo.create(
            device_id="ESP_ERROR_001",
            name="Error Device",
            ip_address="192.168.1.100",
            mac_address="AA:BB:CC:DD:EE:01",
            firmware_version="1.0.0",
            hardware_type="ESP32_WROOM",
            status="error",
        )

        await esp_repo.create(
            device_id="ESP_ONLINE_001",
            name="Online Device",
            ip_address="192.168.1.101",
            mac_address="AA:BB:CC:DD:EE:02",
            firmware_version="1.0.0",
            hardware_type="ESP32_WROOM",
            status="online",
        )

        error_devices = await esp_repo.get_by_status("error")

        assert len(error_devices) == 1
        assert error_devices[0].device_id == "ESP_ERROR_001"


@pytest.mark.asyncio
class TestESPRepositoryGetByHardwareType:
    """Test ESPRepository.get_by_hardware_type()"""

    async def test_get_by_hardware_type_success(self, esp_repo: ESPRepository):
        """Test retrieval by hardware type."""
        await esp_repo.create(
            device_id="ESP_WROOM_001",
            name="WROOM Device",
            ip_address="192.168.1.100",
            mac_address="AA:BB:CC:DD:EE:01",
            firmware_version="1.0.0",
            hardware_type="ESP32_WROOM",
            status="online",
        )

        await esp_repo.create(
            device_id="ESP_XIAO_001",
            name="XIAO Device",
            ip_address="192.168.1.101",
            mac_address="AA:BB:CC:DD:EE:02",
            firmware_version="1.0.0",
            hardware_type="XIAO_ESP32_C3",
            status="online",
        )

        wroom_devices = await esp_repo.get_by_hardware_type("ESP32_WROOM")

        assert len(wroom_devices) == 1
        assert wroom_devices[0].device_id == "ESP_WROOM_001"


@pytest.mark.asyncio
class TestESPRepositoryUpdateStatus:
    """Test ESPRepository.update_status()"""

    async def test_update_status_success(self, esp_repo: ESPRepository):
        """Test successful status update."""
        device = await esp_repo.create(
            device_id="ESP_STATUS_TEST",
            name="Status Test Device",
            ip_address="192.168.1.100",
            mac_address="AA:BB:CC:DD:EE:FF",
            firmware_version="1.0.0",
            hardware_type="ESP32_WROOM",
            status="online",
        )

        updated = await esp_repo.update_status("ESP_STATUS_TEST", "offline")

        assert updated is not None
        assert updated.status == "offline"
        assert updated.device_id == "ESP_STATUS_TEST"

    async def test_update_status_with_timestamp(self, esp_repo: ESPRepository):
        """Test status update with custom timestamp."""
        device = await esp_repo.create(
            device_id="ESP_TIMESTAMP_TEST",
            name="Timestamp Test Device",
            ip_address="192.168.1.100",
            mac_address="AA:BB:CC:DD:EE:FE",
            firmware_version="1.0.0",
            hardware_type="ESP32_WROOM",
            status="online",
        )

        custom_timestamp = datetime(2024, 1, 1, 12, 0, 0)
        updated = await esp_repo.update_status(
            "ESP_TIMESTAMP_TEST", "online", last_seen=custom_timestamp
        )

        assert updated is not None
        assert updated.last_seen == custom_timestamp

    async def test_update_status_offline_preserves_last_seen_without_timestamp(
        self, esp_repo: ESPRepository
    ):
        """Offline transition must not overwrite heartbeat-derived last_seen."""
        await esp_repo.create(
            device_id="ESP_LASTSEEN_POLICY",
            name="LastSeen Policy Device",
            ip_address="192.168.1.120",
            mac_address="AA:BB:CC:DD:EE:FA",
            firmware_version="1.0.0",
            hardware_type="ESP32_WROOM",
            status="online",
        )
        heartbeat_ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        await esp_repo.update_status("ESP_LASTSEEN_POLICY", "online", last_seen=heartbeat_ts)

        updated = await esp_repo.update_status("ESP_LASTSEEN_POLICY", "offline")

        assert updated is not None
        assert updated.status == "offline"
        # SQLite returns timezone-naive datetimes; PostgreSQL (production) preserves tzinfo
        assert updated.last_seen == heartbeat_ts.replace(tzinfo=None)

    async def test_update_status_not_found(self, esp_repo: ESPRepository):
        """Test status update with non-existent device."""
        result = await esp_repo.update_status("ESP_NONEXISTENT", "online")
        assert result is None


@pytest.mark.asyncio
class TestESPRepositoryUpdateCapabilities:
    """Test ESPRepository.update_capabilities()"""

    async def test_update_capabilities_success(self, esp_repo: ESPRepository):
        """Test successful capabilities update."""
        device = await esp_repo.create(
            device_id="ESP_CAPS_TEST",
            name="Capabilities Test Device",
            ip_address="192.168.1.100",
            mac_address="AA:BB:CC:DD:EE:FD",
            firmware_version="1.0.0",
            hardware_type="ESP32_WROOM",
            status="online",
            capabilities={"max_sensors": 10},
        )

        new_capabilities = {"max_sensors": 20, "max_actuators": 12}
        updated = await esp_repo.update_capabilities("ESP_CAPS_TEST", new_capabilities)

        assert updated is not None
        assert updated.capabilities == new_capabilities

    async def test_update_capabilities_not_found(self, esp_repo: ESPRepository):
        """Test capabilities update with non-existent device."""
        result = await esp_repo.update_capabilities("ESP_NONEXISTENT", {})
        assert result is None


@pytest.mark.asyncio
class TestESPRepositoryAssignZone:
    """Test ESPRepository.assign_zone()"""

    async def test_assign_zone_success(self, esp_repo: ESPRepository):
        """Test successful zone assignment."""
        device = await esp_repo.create(
            device_id="ESP_ZONE_ASSIGN",
            name="Zone Assign Test",
            ip_address="192.168.1.100",
            mac_address="AA:BB:CC:DD:EE:FC",
            firmware_version="1.0.0",
            hardware_type="ESP32_WROOM",
            status="online",
        )

        updated = await esp_repo.assign_zone(
            "ESP_ZONE_ASSIGN", "zone_1", "Test Zone", is_zone_master=True
        )

        assert updated is not None
        assert updated.zone_id == "zone_1"
        assert updated.zone_name == "Test Zone"
        assert updated.is_zone_master is True

    async def test_assign_zone_not_found(self, esp_repo: ESPRepository):
        """Test zone assignment with non-existent device."""
        result = await esp_repo.assign_zone("ESP_NONEXISTENT", "zone_1", "Zone 1")
        assert result is None
