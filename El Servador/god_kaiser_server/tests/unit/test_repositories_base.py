"""
Unit Tests: BaseRepository
Tests for generic CRUD operations
"""

import uuid

import pytest
import pytest_asyncio

from src.db.models.esp import ESPDevice
from src.db.repositories.base_repo import BaseRepository


@pytest_asyncio.fixture
async def base_repo(test_session):
    """Create BaseRepository instance for ESPDevice."""
    return BaseRepository(ESPDevice, test_session)


@pytest.mark.asyncio
class TestBaseRepositoryCreate:
    """Test BaseRepository.create()"""

    async def test_create_success(self, base_repo: BaseRepository[ESPDevice]):
        """Test successful creation."""
        device = await base_repo.create(
            device_id="ESP_TEST_001",
            name="Test Device",
            ip_address="192.168.1.100",
            mac_address="AA:BB:CC:DD:EE:FF",
            firmware_version="1.0.0",
            hardware_type="ESP32_WROOM",
            status="online",
        )

        assert device is not None
        assert device.device_id == "ESP_TEST_001"
        assert device.name == "Test Device"
        assert isinstance(device.id, uuid.UUID)

    async def test_create_with_optional_fields(self, base_repo: BaseRepository[ESPDevice]):
        """Test creation with optional fields."""
        device = await base_repo.create(
            device_id="ESP_TEST_002",
            name="Test Device 2",
            ip_address="192.168.1.101",
            mac_address="AA:BB:CC:DD:EE:FE",
            firmware_version="1.0.0",
            hardware_type="XIAO_ESP32_C3",
            status="offline",
            zone_id="zone_1",
            zone_name="Test Zone",
            is_zone_master=True,
        )

        assert device.zone_id == "zone_1"
        assert device.zone_name == "Test Zone"
        assert device.is_zone_master is True


@pytest.mark.asyncio
class TestBaseRepositoryGet:
    """Test BaseRepository.get_by_id()"""

    async def test_get_by_id_success(self, base_repo: BaseRepository[ESPDevice]):
        """Test successful retrieval by ID."""
        # Create device
        device = await base_repo.create(
            device_id="ESP_TEST_003",
            name="Test Device 3",
            ip_address="192.168.1.102",
            mac_address="AA:BB:CC:DD:EE:FD",
            firmware_version="1.0.0",
            hardware_type="ESP32_WROOM",
            status="online",
        )
        device_id = device.id

        # Retrieve device
        retrieved = await base_repo.get_by_id(device_id)

        assert retrieved is not None
        assert retrieved.id == device_id
        assert retrieved.device_id == "ESP_TEST_003"

    async def test_get_by_id_not_found(self, base_repo: BaseRepository[ESPDevice]):
        """Test retrieval with non-existent ID."""
        fake_id = uuid.uuid4()
        result = await base_repo.get_by_id(fake_id)

        assert result is None

    async def test_get_all_with_pagination(self, base_repo: BaseRepository[ESPDevice]):
        """Test get_all() with pagination."""
        # Create multiple devices
        for i in range(5):
            await base_repo.create(
                device_id=f"ESP_TEST_{i:03d}",
                name=f"Test Device {i}",
                ip_address=f"192.168.1.{100 + i}",
                mac_address=f"AA:BB:CC:DD:EE:{i:02X}",
                firmware_version="1.0.0",
                hardware_type="ESP32_WROOM",
                status="online",
            )

        # Get first 3
        devices = await base_repo.get_all(skip=0, limit=3)
        assert len(devices) == 3

        # Get next 2
        devices = await base_repo.get_all(skip=3, limit=3)
        assert len(devices) == 2

    async def test_get_all_empty(self, base_repo: BaseRepository[ESPDevice]):
        """Test get_all() with empty database."""
        devices = await base_repo.get_all()
        assert len(devices) == 0


@pytest.mark.asyncio
class TestBaseRepositoryUpdate:
    """Test BaseRepository.update()"""

    async def test_update_success(self, base_repo: BaseRepository[ESPDevice]):
        """Test successful update."""
        # Create device
        device = await base_repo.create(
            device_id="ESP_TEST_004",
            name="Original Name",
            ip_address="192.168.1.103",
            mac_address="AA:BB:CC:DD:EE:FC",
            firmware_version="1.0.0",
            hardware_type="ESP32_WROOM",
            status="online",
        )
        device_id = device.id

        # Update device
        updated = await base_repo.update(device_id, name="Updated Name", status="offline")

        assert updated is not None
        assert updated.name == "Updated Name"
        assert updated.status == "offline"
        assert updated.device_id == "ESP_TEST_004"  # Unchanged

    async def test_update_not_found(self, base_repo: BaseRepository[ESPDevice]):
        """Test update with non-existent ID."""
        fake_id = uuid.uuid4()
        result = await base_repo.update(fake_id, name="Should Fail")

        assert result is None

    async def test_update_partial(self, base_repo: BaseRepository[ESPDevice]):
        """Test partial update (only some fields)."""
        device = await base_repo.create(
            device_id="ESP_TEST_005",
            name="Original Name",
            ip_address="192.168.1.104",
            mac_address="AA:BB:CC:DD:EE:FB",
            firmware_version="1.0.0",
            hardware_type="ESP32_WROOM",
            status="online",
        )

        updated = await base_repo.update(device.id, status="error")

        assert updated.status == "error"
        assert updated.name == "Original Name"  # Unchanged


@pytest.mark.asyncio
class TestBaseRepositoryDelete:
    """Test BaseRepository.delete()"""

    async def test_delete_success(self, base_repo: BaseRepository[ESPDevice]):
        """Test successful deletion."""
        device = await base_repo.create(
            device_id="ESP_TEST_006",
            name="To Delete",
            ip_address="192.168.1.105",
            mac_address="AA:BB:CC:DD:EE:FA",
            firmware_version="1.0.0",
            hardware_type="ESP32_WROOM",
            status="online",
        )
        device_id = device.id

        # Delete device
        deleted = await base_repo.delete(device_id)

        assert deleted is True

        # Verify deletion
        retrieved = await base_repo.get_by_id(device_id)
        assert retrieved is None

    async def test_delete_not_found(self, base_repo: BaseRepository[ESPDevice]):
        """Test deletion with non-existent ID."""
        fake_id = uuid.uuid4()
        result = await base_repo.delete(fake_id)

        assert result is False


@pytest.mark.asyncio
class TestBaseRepositoryCount:
    """Test BaseRepository.count()"""

    async def test_count_empty(self, base_repo: BaseRepository[ESPDevice]):
        """Test count with empty database."""
        count = await base_repo.count()
        assert count == 0

    async def test_count_multiple(self, base_repo: BaseRepository[ESPDevice]):
        """Test count with multiple records."""
        for i in range(3):
            await base_repo.create(
                device_id=f"ESP_TEST_{i:03d}",
                name=f"Device {i}",
                ip_address=f"192.168.1.{100 + i}",
                mac_address=f"AA:BB:CC:DD:EE:{i:02X}",
                firmware_version="1.0.0",
                hardware_type="ESP32_WROOM",
                status="online",
            )

        count = await base_repo.count()
        assert count == 3


@pytest.mark.asyncio
class TestBaseRepositoryExists:
    """Test BaseRepository.exists()"""

    async def test_exists_true(self, base_repo: BaseRepository[ESPDevice]):
        """Test exists() with existing record."""
        device = await base_repo.create(
            device_id="ESP_TEST_007",
            name="Exists",
            ip_address="192.168.1.106",
            mac_address="AA:BB:CC:DD:EE:F9",
            firmware_version="1.0.0",
            hardware_type="ESP32_WROOM",
            status="online",
        )

        exists = await base_repo.exists(device.id)
        assert exists is True

    async def test_exists_false(self, base_repo: BaseRepository[ESPDevice]):
        """Test exists() with non-existent record."""
        fake_id = uuid.uuid4()
        exists = await base_repo.exists(fake_id)
        assert exists is False
