"""
Unit Tests: ZoneRepository CRUD

Phase: 0.3 - Zone as DB Entity
Tests: Create, read, update, delete operations for zones
"""

import uuid

import pytest
import pytest_asyncio

from src.db.models.zone import Zone
from src.db.repositories.zone_repo import ZoneRepository


@pytest_asyncio.fixture
async def zone_repo(test_session):
    """Create ZoneRepository instance."""
    return ZoneRepository(test_session)


@pytest.mark.asyncio
class TestZoneRepositoryCreate:
    """Test ZoneRepository.create()"""

    async def test_create_zone(self, zone_repo: ZoneRepository):
        """Test successful zone creation."""
        zone = await zone_repo.create(
            zone_id="greenhouse_1",
            name="Greenhouse Section 1",
            description="Primary growing area",
        )

        assert zone is not None
        assert isinstance(zone.id, uuid.UUID)
        assert zone.zone_id == "greenhouse_1"
        assert zone.name == "Greenhouse Section 1"
        assert zone.description == "Primary growing area"
        assert zone.created_at is not None
        assert zone.updated_at is not None

    async def test_create_zone_without_description(self, zone_repo: ZoneRepository):
        """Test creation with no description."""
        zone = await zone_repo.create(
            zone_id="office_main",
            name="Main Office",
        )

        assert zone.zone_id == "office_main"
        assert zone.name == "Main Office"
        assert zone.description is None


@pytest.mark.asyncio
class TestZoneRepositoryGet:
    """Test ZoneRepository get methods"""

    async def test_get_by_id(self, zone_repo: ZoneRepository):
        """Test get zone by UUID."""
        zone = await zone_repo.create(zone_id="test_zone", name="Test Zone")
        retrieved = await zone_repo.get_by_id(zone.id)

        assert retrieved is not None
        assert retrieved.id == zone.id
        assert retrieved.zone_id == "test_zone"

    async def test_get_by_id_not_found(self, zone_repo: ZoneRepository):
        """Test get zone by non-existent UUID."""
        result = await zone_repo.get_by_id(uuid.uuid4())
        assert result is None

    async def test_get_by_zone_id(self, zone_repo: ZoneRepository):
        """Test get zone by zone_id string."""
        await zone_repo.create(zone_id="my_zone", name="My Zone")
        retrieved = await zone_repo.get_by_zone_id("my_zone")

        assert retrieved is not None
        assert retrieved.zone_id == "my_zone"
        assert retrieved.name == "My Zone"

    async def test_get_by_zone_id_not_found(self, zone_repo: ZoneRepository):
        """Test get zone by non-existent zone_id."""
        result = await zone_repo.get_by_zone_id("nonexistent")
        assert result is None


@pytest.mark.asyncio
class TestZoneRepositoryListAll:
    """Test ZoneRepository.list_all()"""

    async def test_list_all_empty(self, zone_repo: ZoneRepository):
        """Test listing zones when none exist."""
        zones = await zone_repo.list_all()
        assert zones == []

    async def test_list_all_multiple(self, zone_repo: ZoneRepository):
        """Test listing multiple zones."""
        await zone_repo.create(zone_id="alpha_zone", name="Alpha")
        await zone_repo.create(zone_id="beta_zone", name="Beta")
        await zone_repo.create(zone_id="gamma_zone", name="Gamma")

        zones = await zone_repo.list_all()
        assert len(zones) == 3
        # Should be ordered by zone_id
        zone_ids = [z.zone_id for z in zones]
        assert zone_ids == ["alpha_zone", "beta_zone", "gamma_zone"]


@pytest.mark.asyncio
class TestZoneRepositoryUpdate:
    """Test ZoneRepository.update()"""

    async def test_update_name(self, zone_repo: ZoneRepository):
        """Test updating zone name."""
        zone = await zone_repo.create(zone_id="upd_zone", name="Original")
        updated = await zone_repo.update(zone.id, name="Updated Name")

        assert updated is not None
        assert updated.name == "Updated Name"
        assert updated.zone_id == "upd_zone"  # Unchanged

    async def test_update_description(self, zone_repo: ZoneRepository):
        """Test updating zone description."""
        zone = await zone_repo.create(zone_id="desc_zone", name="Zone")
        updated = await zone_repo.update(zone.id, description="New description")

        assert updated is not None
        assert updated.description == "New description"
        assert updated.name == "Zone"  # Unchanged

    async def test_update_not_found(self, zone_repo: ZoneRepository):
        """Test update with non-existent UUID."""
        result = await zone_repo.update(uuid.uuid4(), name="Nope")
        assert result is None

    async def test_update_no_change_when_none(self, zone_repo: ZoneRepository):
        """Test that None values don't overwrite existing values."""
        zone = await zone_repo.create(
            zone_id="keep_zone", name="Keep Me", description="Keep this too"
        )
        updated = await zone_repo.update(zone.id)

        assert updated.name == "Keep Me"
        assert updated.description == "Keep this too"


@pytest.mark.asyncio
class TestZoneRepositoryDelete:
    """Test ZoneRepository.delete()"""

    async def test_delete_success(self, zone_repo: ZoneRepository):
        """Test successful zone deletion."""
        zone = await zone_repo.create(zone_id="del_zone", name="Delete Me")
        result = await zone_repo.delete(zone.id)

        assert result is True

        # Verify deletion
        retrieved = await zone_repo.get_by_id(zone.id)
        assert retrieved is None

    async def test_delete_not_found(self, zone_repo: ZoneRepository):
        """Test deletion with non-existent UUID."""
        result = await zone_repo.delete(uuid.uuid4())
        assert result is False


@pytest.mark.asyncio
class TestZoneRepositoryCount:
    """Test ZoneRepository.count() and exists_by_zone_id()"""

    async def test_count_empty(self, zone_repo: ZoneRepository):
        """Test count with no zones."""
        count = await zone_repo.count()
        assert count == 0

    async def test_count_multiple(self, zone_repo: ZoneRepository):
        """Test count with multiple zones."""
        await zone_repo.create(zone_id="z1", name="Z1")
        await zone_repo.create(zone_id="z2", name="Z2")

        count = await zone_repo.count()
        assert count == 2

    async def test_exists_by_zone_id_true(self, zone_repo: ZoneRepository):
        """Test exists check for existing zone."""
        await zone_repo.create(zone_id="exists_zone", name="Exists")
        assert await zone_repo.exists_by_zone_id("exists_zone") is True

    async def test_exists_by_zone_id_false(self, zone_repo: ZoneRepository):
        """Test exists check for non-existent zone."""
        assert await zone_repo.exists_by_zone_id("nope") is False
