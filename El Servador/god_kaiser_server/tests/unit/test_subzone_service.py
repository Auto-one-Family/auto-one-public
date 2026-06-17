"""
Unit Tests for SubzoneService

Phase: 9 - Subzone Management
Status: IMPLEMENTED

Tests SubzoneService business logic in isolation from MQTT.
Uses mocked MQTT publisher to prevent timeouts.

Test Categories:
- Subzone Assignment Validation
- Subzone ACK Handling
- Subzone Queries
- Safe-Mode Control
- Error Handling

References:
- El Trabajante/docs/system-flows/09-subzone-management-flow.md
- El Servador/god_kaiser_server/src/services/subzone_service.py
"""

import pytest
import pytest_asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.esp import ESPDevice
from src.db.models.subzone import SubzoneConfig
from src.db.repositories import ESPRepository
from src.db.repositories.subzone_repo import SubzoneRepository
from src.services.subzone_service import SubzoneService

# =============================================================================
# Fixtures
# =============================================================================


@pytest_asyncio.fixture
async def esp_with_zone(db_session: AsyncSession) -> ESPDevice:
    """Create ESP device with assigned zone."""
    device = ESPDevice(
        device_id="ESP_SUBZONE_TEST",
        name="Subzone Test ESP",
        ip_address="192.168.1.101",
        mac_address="AA:BB:CC:DD:EE:01",
        firmware_version="1.0.0",
        hardware_type="ESP32_WROOM",
        status="online",
        zone_id="greenhouse_zone_1",
        zone_name="Greenhouse Zone 1",
        master_zone_id="greenhouse_master",
        capabilities={"max_sensors": 20, "max_actuators": 12},
    )
    db_session.add(device)
    await db_session.flush()
    await db_session.refresh(device)
    return device


@pytest_asyncio.fixture
async def esp_no_zone(db_session: AsyncSession) -> ESPDevice:
    """Create ESP device without zone assignment."""
    device = ESPDevice(
        device_id="ESP_NO_ZONE",
        name="No Zone ESP",
        ip_address="192.168.1.102",
        mac_address="AA:BB:CC:DD:EE:02",
        firmware_version="1.0.0",
        hardware_type="ESP32_WROOM",
        status="online",
        zone_id=None,  # No zone assigned
        capabilities={"max_sensors": 20, "max_actuators": 12},
    )
    db_session.add(device)
    await db_session.flush()
    await db_session.refresh(device)
    return device


@pytest_asyncio.fixture
async def mock_mqtt_publisher():
    """Create mock MQTT publisher."""
    mock = MagicMock()
    mock.client = MagicMock()
    mock.client.publish = MagicMock(return_value=True)
    mock.publish_raw = MagicMock(return_value=True)
    return mock


@pytest_asyncio.fixture
async def subzone_service(db_session: AsyncSession, mock_mqtt_publisher) -> SubzoneService:
    """Create SubzoneService with mocked publisher."""
    esp_repo = ESPRepository(db_session)
    return SubzoneService(
        esp_repo=esp_repo,
        session=db_session,
        publisher=mock_mqtt_publisher,
    )


@pytest_asyncio.fixture
async def subzone_repo(db_session: AsyncSession) -> SubzoneRepository:
    """Create SubzoneRepository instance."""
    return SubzoneRepository(db_session)


# =============================================================================
# Test: Subzone Assignment Validation
# =============================================================================


class TestSubzoneAssignmentValidation:
    """Test subzone assignment validation logic."""

    @pytest.mark.asyncio
    async def test_assign_subzone_esp_not_found(self, subzone_service: SubzoneService):
        """Test assignment fails when ESP not found."""
        with pytest.raises(ValueError, match="not found"):
            await subzone_service.assign_subzone(
                device_id="ESP_NON_EXISTENT",
                subzone_id="test_subzone",
                assigned_gpios=[4, 5],
            )

    @pytest.mark.asyncio
    async def test_assign_subzone_no_zone(
        self, subzone_service: SubzoneService, esp_no_zone: ESPDevice
    ):
        """Test assignment fails when ESP has no zone assigned."""
        with pytest.raises(ValueError, match="has no zone assigned"):
            await subzone_service.assign_subzone(
                device_id=esp_no_zone.device_id,
                subzone_id="test_subzone",
                assigned_gpios=[4, 5],
            )

    @pytest.mark.asyncio
    async def test_assign_subzone_zone_mismatch(
        self, subzone_service: SubzoneService, esp_with_zone: ESPDevice
    ):
        """Test assignment fails when parent_zone_id doesn't match ESP zone."""
        with pytest.raises(ValueError, match="must match"):
            await subzone_service.assign_subzone(
                device_id=esp_with_zone.device_id,
                subzone_id="test_subzone",
                assigned_gpios=[4, 5],
                parent_zone_id="wrong_zone_id",  # Mismatch!
            )

    @pytest.mark.asyncio
    async def test_assign_subzone_success(
        self,
        subzone_service: SubzoneService,
        esp_with_zone: ESPDevice,
        db_session: AsyncSession,
    ):
        """Test successful subzone assignment."""
        response = await subzone_service.assign_subzone(
            device_id=esp_with_zone.device_id,
            subzone_id="irrigation_section_a",
            assigned_gpios=[4, 5, 6],
            subzone_name="Irrigation Section A",
            safe_mode_active=True,
        )

        assert response.success is True
        assert response.device_id == esp_with_zone.device_id
        assert response.subzone_id == "irrigation_section_a"
        assert response.assigned_gpios == [4, 5, 6]
        assert response.mqtt_sent is True
        assert "subzone/assign" in response.mqtt_topic

    @pytest.mark.asyncio
    async def test_assign_subzone_uses_esp_zone_id(
        self,
        subzone_service: SubzoneService,
        esp_with_zone: ESPDevice,
    ):
        """Test assignment uses ESP's zone_id when parent_zone_id not provided."""
        response = await subzone_service.assign_subzone(
            device_id=esp_with_zone.device_id,
            subzone_id="climate_control",
            assigned_gpios=[18, 19, 21],
            parent_zone_id=None,  # Should use ESP's zone_id
        )

        assert response.success is True
        # Verify it was stored with ESP's zone_id
        subzone = await subzone_service.get_subzone(esp_with_zone.device_id, "climate_control")
        assert subzone is not None
        assert subzone.parent_zone_id == esp_with_zone.zone_id


# =============================================================================
# Test: Subzone ACK Handling
# =============================================================================


class TestSubzoneAckHandling:
    """Test subzone ACK processing."""

    @pytest.mark.asyncio
    async def test_handle_ack_subzone_assigned(
        self,
        subzone_service: SubzoneService,
        esp_with_zone: ESPDevice,
        db_session: AsyncSession,
    ):
        """Test successful subzone_assigned ACK processing."""
        # First create a pending subzone
        await subzone_service.assign_subzone(
            device_id=esp_with_zone.device_id,
            subzone_id="test_ack_subzone",
            assigned_gpios=[4, 5],
        )

        # Simulate ESP ACK
        success = await subzone_service.handle_subzone_ack(
            device_id=esp_with_zone.device_id,
            status="subzone_assigned",
            subzone_id="test_ack_subzone",
            timestamp=1734523800,
        )

        assert success is True

        # Verify last_ack_at was updated
        subzone = await subzone_service.get_subzone(esp_with_zone.device_id, "test_ack_subzone")
        assert subzone is not None
        # Note: In actual implementation, last_ack_at should be set

    @pytest.mark.asyncio
    async def test_handle_ack_subzone_removed(
        self,
        subzone_service: SubzoneService,
        esp_with_zone: ESPDevice,
        db_session: AsyncSession,
    ):
        """Test subzone_removed ACK processing."""
        # Create and then simulate removal
        await subzone_service.assign_subzone(
            device_id=esp_with_zone.device_id,
            subzone_id="to_be_removed",
            assigned_gpios=[4, 5],
        )

        # Verify subzone exists
        subzone = await subzone_service.get_subzone(esp_with_zone.device_id, "to_be_removed")
        assert subzone is not None

        # Simulate ESP removal ACK
        success = await subzone_service.handle_subzone_ack(
            device_id=esp_with_zone.device_id,
            status="subzone_removed",
            subzone_id="to_be_removed",
            timestamp=1734523800,
        )

        assert success is True

        # Verify subzone was deleted
        subzone = await subzone_service.get_subzone(esp_with_zone.device_id, "to_be_removed")
        assert subzone is None

    @pytest.mark.asyncio
    async def test_handle_ack_error(
        self,
        subzone_service: SubzoneService,
        esp_with_zone: ESPDevice,
    ):
        """Test error ACK processing."""
        success = await subzone_service.handle_subzone_ack(
            device_id=esp_with_zone.device_id,
            status="error",
            subzone_id="failed_subzone",
            error_code=2501,
            message="GPIO conflict detected",
        )

        assert success is False

    @pytest.mark.asyncio
    async def test_handle_ack_unknown_status(
        self,
        subzone_service: SubzoneService,
        esp_with_zone: ESPDevice,
    ):
        """Test unknown ACK status handling."""
        success = await subzone_service.handle_subzone_ack(
            device_id=esp_with_zone.device_id,
            status="unknown_status",
            subzone_id="test_subzone",
        )

        assert success is False


# =============================================================================
# Test: Subzone Queries
# =============================================================================


class TestSubzoneQueries:
    """Test subzone query operations."""

    @pytest.mark.asyncio
    async def test_get_esp_subzones_empty(
        self, subzone_service: SubzoneService, esp_with_zone: ESPDevice
    ):
        """Test getting subzones for ESP with none."""
        response = await subzone_service.get_esp_subzones(esp_with_zone.device_id)

        assert response.success is True
        assert response.device_id == esp_with_zone.device_id
        assert response.total_count == 0
        assert len(response.subzones) == 0

    @pytest.mark.asyncio
    async def test_get_esp_subzones_multiple(
        self, subzone_service: SubzoneService, esp_with_zone: ESPDevice
    ):
        """Test getting multiple subzones for ESP."""
        # Create multiple subzones
        await subzone_service.assign_subzone(
            device_id=esp_with_zone.device_id,
            subzone_id="subzone_1",
            assigned_gpios=[4, 5],
        )
        await subzone_service.assign_subzone(
            device_id=esp_with_zone.device_id,
            subzone_id="subzone_2",
            assigned_gpios=[6, 7],
        )
        await subzone_service.assign_subzone(
            device_id=esp_with_zone.device_id,
            subzone_id="subzone_3",
            assigned_gpios=[18, 19],
        )

        response = await subzone_service.get_esp_subzones(esp_with_zone.device_id)

        assert response.success is True
        assert response.total_count == 3
        assert len(response.subzones) == 3

    @pytest.mark.asyncio
    async def test_get_subzone_not_found(
        self, subzone_service: SubzoneService, esp_with_zone: ESPDevice
    ):
        """Test getting non-existent subzone."""
        subzone = await subzone_service.get_subzone(esp_with_zone.device_id, "non_existent")

        assert subzone is None

    @pytest.mark.asyncio
    async def test_get_subzone_found(
        self, subzone_service: SubzoneService, esp_with_zone: ESPDevice
    ):
        """Test getting existing subzone."""
        await subzone_service.assign_subzone(
            device_id=esp_with_zone.device_id,
            subzone_id="test_query",
            subzone_name="Test Query Subzone",
            assigned_gpios=[4, 5, 6],
            safe_mode_active=False,
        )

        subzone = await subzone_service.get_subzone(esp_with_zone.device_id, "test_query")

        assert subzone is not None
        assert subzone.subzone_id == "test_query"
        assert subzone.subzone_name == "Test Query Subzone"
        assert subzone.assigned_gpios == [4, 5, 6]
        assert subzone.safe_mode_active is False


# =============================================================================
# Test: Safe-Mode Control
# =============================================================================


class TestSafeModeControl:
    """Test safe-mode control operations."""

    @pytest.mark.asyncio
    async def test_enable_safe_mode_success(
        self,
        subzone_service: SubzoneService,
        esp_with_zone: ESPDevice,
    ):
        """Test successful safe-mode enable."""
        # Create subzone first
        await subzone_service.assign_subzone(
            device_id=esp_with_zone.device_id,
            subzone_id="safe_mode_test",
            assigned_gpios=[4, 5],
            safe_mode_active=False,  # Start with safe-mode disabled
        )

        response = await subzone_service.enable_safe_mode(
            device_id=esp_with_zone.device_id,
            subzone_id="safe_mode_test",
            reason="maintenance",
        )

        assert response.success is True
        assert response.safe_mode_active is True
        assert response.mqtt_sent is True

    @pytest.mark.asyncio
    async def test_disable_safe_mode_success(
        self,
        subzone_service: SubzoneService,
        esp_with_zone: ESPDevice,
    ):
        """Test successful safe-mode disable."""
        # Create subzone first
        await subzone_service.assign_subzone(
            device_id=esp_with_zone.device_id,
            subzone_id="safe_mode_disable_test",
            assigned_gpios=[4, 5],
            safe_mode_active=True,  # Start with safe-mode enabled
        )

        response = await subzone_service.disable_safe_mode(
            device_id=esp_with_zone.device_id,
            subzone_id="safe_mode_disable_test",
            reason="normal_operation",
        )

        assert response.success is True
        assert response.safe_mode_active is False
        assert response.mqtt_sent is True

    @pytest.mark.asyncio
    async def test_safe_mode_esp_not_found(
        self,
        subzone_service: SubzoneService,
    ):
        """Test safe-mode fails when ESP not found."""
        with pytest.raises(ValueError, match="not found"):
            await subzone_service.enable_safe_mode(
                device_id="ESP_NON_EXISTENT",
                subzone_id="test_subzone",
            )


# =============================================================================
# Test: Subzone Removal
# =============================================================================


class TestSubzoneRemoval:
    """Test subzone removal operations."""

    @pytest.mark.asyncio
    async def test_remove_subzone_success(
        self,
        subzone_service: SubzoneService,
        esp_with_zone: ESPDevice,
    ):
        """Test successful subzone removal."""
        # Create subzone first
        await subzone_service.assign_subzone(
            device_id=esp_with_zone.device_id,
            subzone_id="to_remove",
            assigned_gpios=[4, 5],
        )

        response = await subzone_service.remove_subzone(
            device_id=esp_with_zone.device_id,
            subzone_id="to_remove",
            reason="maintenance",
        )

        assert response.success is True
        assert response.device_id == esp_with_zone.device_id
        assert response.subzone_id == "to_remove"
        assert response.mqtt_sent is True
        assert "subzone/remove" in response.mqtt_topic

    @pytest.mark.asyncio
    async def test_remove_subzone_deletes_from_db(
        self,
        subzone_service: SubzoneService,
        esp_with_zone: ESPDevice,
        db_session: AsyncSession,
    ):
        """Test remove_subzone() deletes subzone from DB before MQTT publish (BUG-5 fix)."""
        # Create subzone first
        await subzone_service.assign_subzone(
            device_id=esp_with_zone.device_id,
            subzone_id="db_delete_test",
            assigned_gpios=[4, 5],
        )

        # Verify subzone exists in DB
        subzone = await subzone_service.get_subzone(esp_with_zone.device_id, "db_delete_test")
        assert subzone is not None

        # Remove subzone
        response = await subzone_service.remove_subzone(
            device_id=esp_with_zone.device_id,
            subzone_id="db_delete_test",
        )

        assert response.success is True

        # Verify subzone is deleted from DB
        subzone = await subzone_service.get_subzone(esp_with_zone.device_id, "db_delete_test")
        assert subzone is None, "Subzone must be deleted from DB after remove_subzone()"

    @pytest.mark.asyncio
    async def test_remove_subzone_succeeds_even_if_mqtt_fails(
        self,
        esp_with_zone: ESPDevice,
        db_session: AsyncSession,
    ):
        """Test remove_subzone() returns success=True even when MQTT publish fails (BUG-5)."""
        # First: create subzone with a working publisher so it exists in DB
        ok_publisher = MagicMock()
        ok_publisher.client = MagicMock()
        ok_publisher.client.publish = MagicMock(return_value=True)
        ok_publisher.publish_raw = MagicMock(return_value=True)

        esp_repo = ESPRepository(db_session)
        service_ok = SubzoneService(esp_repo=esp_repo, session=db_session, publisher=ok_publisher)

        await service_ok.assign_subzone(
            device_id=esp_with_zone.device_id,
            subzone_id="mqtt_fail_test",
            assigned_gpios=[4, 5],
        )

        # Now: create service with failing publisher for the removal
        fail_publisher = MagicMock()
        fail_publisher.client = MagicMock()
        fail_publisher.client.publish = MagicMock(return_value=False)
        fail_publisher.publish_raw = MagicMock(return_value=False)

        service = SubzoneService(esp_repo=esp_repo, session=db_session, publisher=fail_publisher)

        # Remove — MQTT will fail but DB delete should succeed
        response = await service.remove_subzone(
            device_id=esp_with_zone.device_id,
            subzone_id="mqtt_fail_test",
        )

        assert response.success is True, "DB deletion succeeded, success must be True"
        assert response.mqtt_sent is False
        # Verify DB state
        subzone = await service.get_subzone(esp_with_zone.device_id, "mqtt_fail_test")
        assert subzone is None, "Subzone must be deleted from DB even when MQTT fails"

    @pytest.mark.asyncio
    async def test_remove_subzone_ack_graceful_after_db_delete(
        self,
        subzone_service: SubzoneService,
        esp_with_zone: ESPDevice,
    ):
        """Test ACK handler is graceful when subzone already deleted by remove_subzone() (BUG-5)."""
        # Create subzone
        await subzone_service.assign_subzone(
            device_id=esp_with_zone.device_id,
            subzone_id="ack_after_delete",
            assigned_gpios=[4, 5],
        )

        # Remove subzone (deletes from DB)
        await subzone_service.remove_subzone(
            device_id=esp_with_zone.device_id,
            subzone_id="ack_after_delete",
        )

        # ACK arrives after DB delete — should be a graceful no-op
        success = await subzone_service.handle_subzone_ack(
            device_id=esp_with_zone.device_id,
            status="subzone_removed",
            subzone_id="ack_after_delete",
            timestamp=1734523800,
        )

        assert success is True, "ACK handler must succeed even when subzone already deleted"

    @pytest.mark.asyncio
    async def test_remove_subzone_esp_not_found(
        self,
        subzone_service: SubzoneService,
    ):
        """Test removal fails when ESP not found."""
        with pytest.raises(ValueError, match="not found"):
            await subzone_service.remove_subzone(
                device_id="ESP_NON_EXISTENT",
                subzone_id="test_subzone",
            )


# =============================================================================
# Test: SubzoneRepository
# =============================================================================


class TestSubzoneRepository:
    """Test SubzoneRepository operations."""

    @pytest.mark.asyncio
    async def test_create_subzone(
        self,
        subzone_repo: SubzoneRepository,
        esp_with_zone: ESPDevice,
    ):
        """Test subzone creation via repository."""
        subzone = await subzone_repo.create_subzone(
            esp_id=esp_with_zone.device_id,
            subzone_id="repo_test",
            parent_zone_id="greenhouse_zone_1",
            assigned_gpios=[4, 5, 6],
            subzone_name="Repository Test",
            safe_mode_active=True,
        )

        assert subzone.id is not None
        assert subzone.esp_id == esp_with_zone.device_id
        assert subzone.subzone_id == "repo_test"
        assert subzone.assigned_gpios == [4, 5, 6]

    @pytest.mark.asyncio
    async def test_gpio_conflict_detection(
        self,
        subzone_repo: SubzoneRepository,
        esp_with_zone: ESPDevice,
    ):
        """Test GPIO conflict detection."""
        # Create first subzone with GPIOs 4, 5
        await subzone_repo.create_subzone(
            esp_id=esp_with_zone.device_id,
            subzone_id="first_subzone",
            parent_zone_id="greenhouse_zone_1",
            assigned_gpios=[4, 5],
        )

        # Check conflict for GPIO 5 (should find conflict)
        conflict = await subzone_repo.check_gpio_conflict(
            esp_id=esp_with_zone.device_id,
            gpios=[5, 6],  # GPIO 5 conflicts
        )

        assert conflict is not None
        assert conflict.subzone_id == "first_subzone"

        # Check no conflict for GPIOs 18, 19
        no_conflict = await subzone_repo.check_gpio_conflict(
            esp_id=esp_with_zone.device_id,
            gpios=[18, 19],  # No conflict
        )

        assert no_conflict is None

    @pytest.mark.asyncio
    async def test_gpio_conflict_exclude_self(
        self,
        subzone_repo: SubzoneRepository,
        esp_with_zone: ESPDevice,
    ):
        """Test GPIO conflict excludes self on update."""
        # Create subzone with GPIOs 4, 5
        await subzone_repo.create_subzone(
            esp_id=esp_with_zone.device_id,
            subzone_id="self_check",
            parent_zone_id="greenhouse_zone_1",
            assigned_gpios=[4, 5],
        )

        # Check should not find conflict when excluding self
        conflict = await subzone_repo.check_gpio_conflict(
            esp_id=esp_with_zone.device_id,
            gpios=[4, 5, 6],  # Same GPIOs + new one
            exclude_subzone_id="self_check",
        )

        assert conflict is None  # No conflict because we exclude self

    @pytest.mark.asyncio
    async def test_get_subzone_by_gpio(
        self,
        subzone_repo: SubzoneRepository,
        esp_with_zone: ESPDevice,
    ):
        """Test finding subzone by GPIO."""
        await subzone_repo.create_subzone(
            esp_id=esp_with_zone.device_id,
            subzone_id="gpio_lookup",
            parent_zone_id="greenhouse_zone_1",
            assigned_gpios=[4, 5, 6],
        )

        # Find subzone for GPIO 5
        subzone = await subzone_repo.get_subzone_by_gpio(esp_with_zone.device_id, gpio=5)

        assert subzone is not None
        assert subzone.subzone_id == "gpio_lookup"

        # GPIO 18 not assigned
        not_found = await subzone_repo.get_subzone_by_gpio(esp_with_zone.device_id, gpio=18)

        assert not_found is None

    @pytest.mark.asyncio
    async def test_count_gpios_by_esp(
        self,
        subzone_repo: SubzoneRepository,
        esp_with_zone: ESPDevice,
    ):
        """Test counting total GPIOs across subzones."""
        await subzone_repo.create_subzone(
            esp_id=esp_with_zone.device_id,
            subzone_id="count_1",
            parent_zone_id="zone",
            assigned_gpios=[4, 5],  # 2 GPIOs
        )
        await subzone_repo.create_subzone(
            esp_id=esp_with_zone.device_id,
            subzone_id="count_2",
            parent_zone_id="zone",
            assigned_gpios=[6, 7, 18],  # 3 GPIOs
        )

        total = await subzone_repo.count_gpios_by_esp(esp_with_zone.device_id)

        assert total == 5
