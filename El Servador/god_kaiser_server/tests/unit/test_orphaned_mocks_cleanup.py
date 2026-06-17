"""
Unit Tests für OrphanedMocksCleanup (Data-Safe Version)

Tests umfassen:
- WARN-ONLY Mode (Default)
- AUTO-DELETE Mode (optional)
- Running-State-Mismatch Detection
- Old-Stopped-Mocks Detection
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.config import MaintenanceSettings
from src.services.maintenance.jobs.cleanup import OrphanedMocksCleanup


@pytest.fixture
def maintenance_settings():
    """Standard MaintenanceSettings mit Safety-Defaults"""
    return MaintenanceSettings(
        sensor_data_retention_enabled=False,
        sensor_data_retention_days=30,
        sensor_data_cleanup_dry_run=True,
        sensor_data_cleanup_batch_size=1000,
        sensor_data_cleanup_max_batches=100,
        command_history_retention_enabled=False,
        command_history_retention_days=14,
        command_history_cleanup_dry_run=True,
        command_history_cleanup_batch_size=1000,
        command_history_cleanup_max_batches=50,
        orphaned_mock_cleanup_enabled=True,
        orphaned_mock_auto_delete=False,  # ⚠️ Default: WARN ONLY
        orphaned_mock_age_hours=24,
        heartbeat_timeout_seconds=180,
        mqtt_health_check_interval_seconds=30,
        esp_health_check_interval_seconds=60,
        stats_aggregation_enabled=True,
        stats_aggregation_interval_minutes=60,
        cleanup_alert_threshold_percent=10.0,
        cleanup_max_records_per_run=100000,
    )


@pytest.fixture
def mock_session():
    """Mock AsyncSession"""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.delete = AsyncMock()
    return session


@pytest.fixture
def mock_scheduler():
    """Mock CentralScheduler"""
    scheduler = MagicMock()
    scheduler.get_job = MagicMock()
    return scheduler


class TestOrphanedMocksCleanup:
    """Tests für OrphanedMocksCleanup"""

    # ================================================================
    # SAFETY TESTS
    # ================================================================

    @pytest.mark.asyncio
    async def test_disabled_mode(self, mock_session, mock_scheduler, maintenance_settings):
        """Test: DISABLED Mode"""
        settings = maintenance_settings
        settings.orphaned_mock_cleanup_enabled = False

        cleanup = OrphanedMocksCleanup(mock_session, mock_scheduler, settings)
        result = await cleanup.execute()

        assert result["status"] == "disabled"
        assert result["orphaned_found"] == 0
        assert result["deleted"] == 0

    @pytest.mark.asyncio
    async def test_warn_only_mode(self, mock_session, mock_scheduler, maintenance_settings, caplog):
        """
        Test: WARN-ONLY Mode (Default)

        Erwartung:
        - Orphaned Mocks werden gefunden
        - State wird auf "stopped" gesetzt
        - KEINE Deletion
        - Nur Warnings geloggt
        """
        import logging

        caplog.set_level(logging.WARNING)

        settings = maintenance_settings
        assert settings.orphaned_mock_auto_delete is False  # ⚠️ WARN ONLY

        # Mock ESP Repository
        mock_device = MagicMock()
        mock_device.id = 1
        mock_device.device_id = "MOCK_001"
        mock_device.device_metadata = {"simulation_state": "stopped"}
        mock_device.created_at = datetime.now(timezone.utc) - timedelta(hours=25)
        mock_device.updated_at = datetime.now(timezone.utc) - timedelta(hours=25)

        with patch("src.db.repositories.ESPRepository") as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.get_running_mock_devices = AsyncMock(return_value=[])
            mock_repo.get_all_mock_devices = AsyncMock(return_value=[mock_device])

            with patch("src.services.simulation.get_simulation_scheduler") as mock_sim:
                mock_sim.return_value = None

                cleanup = OrphanedMocksCleanup(mock_session, mock_scheduler, settings)
                result = await cleanup.execute()

                # Verify: Nur Warnings, keine Deletion
                assert result["status"] == "success"
                assert result["warned"] == 1
                assert result["deleted"] == 0  # ⚠️ NICHT gelöscht!

                # Warning geloggt
                assert "Old orphaned Mock found" in caplog.text
                assert "MOCK_001" in caplog.text

                # Kein Session.delete aufgerufen
                mock_session.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_auto_delete_mode(self, mock_session, mock_scheduler, maintenance_settings):
        """
        Test: AUTO-DELETE Mode (optional)

        Erwartung:
        - Orphaned Mocks werden gefunden
        - Mocks werden GELÖSCHT
        """
        settings = maintenance_settings
        settings.orphaned_mock_auto_delete = True  # ⚠️ AUTO-DELETE ENABLED

        # Mock old stopped device
        mock_device = MagicMock()
        mock_device.id = 1
        mock_device.device_id = "MOCK_OLD"
        mock_device.device_metadata = {"simulation_state": "stopped"}
        mock_device.created_at = datetime.now(timezone.utc) - timedelta(hours=25)
        mock_device.updated_at = datetime.now(timezone.utc) - timedelta(hours=25)

        with patch("src.db.repositories.ESPRepository") as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.get_running_mock_devices = AsyncMock(return_value=[])
            mock_repo.get_all_mock_devices = AsyncMock(return_value=[mock_device])

            with patch("src.services.simulation.get_simulation_scheduler") as mock_sim:
                mock_sim.return_value = None

                cleanup = OrphanedMocksCleanup(mock_session, mock_scheduler, settings)
                result = await cleanup.execute()

                # Verify: Soft-deletion erfolgt (T02-Fix1)
                assert result["status"] == "success"
                assert result["deleted"] == 1
                assert result["warned"] == 0

                # Device soft-deleted (deleted_at gesetzt, status='deleted')
                assert mock_device.deleted_at is not None
                assert mock_device.deleted_by == "maintenance"
                assert mock_device.status == "deleted"

    # ================================================================
    # ORPHAN DETECTION TESTS
    # ================================================================

    @pytest.mark.asyncio
    async def test_running_state_mismatch_detection(
        self, mock_session, mock_scheduler, maintenance_settings
    ):
        """
        Test: Running-State aber kein Job im Scheduler

        Erwartung:
        - State wird auf "stopped" gesetzt
        - Warning geloggt
        """
        settings = maintenance_settings

        # Mock running device (aber kein Job)
        mock_device = MagicMock()
        mock_device.id = 1
        mock_device.device_id = "MOCK_RUNNING"
        mock_device.device_metadata = {"simulation_state": "running"}  # ⚠️ Running
        mock_device.created_at = datetime.now(timezone.utc)
        mock_device.updated_at = datetime.now(timezone.utc)

        with patch("src.db.repositories.ESPRepository") as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.get_running_mock_devices = AsyncMock(return_value=[mock_device])
            mock_repo.get_all_mock_devices = AsyncMock(return_value=[])
            mock_repo.update_simulation_state = AsyncMock()

            with patch("src.services.simulation.get_simulation_scheduler") as mock_sim:
                # Simulation Scheduler sagt: Mock nicht aktiv
                mock_sim_instance = MagicMock()
                mock_sim_instance.is_mock_active.return_value = False
                mock_sim.return_value = mock_sim_instance

                cleanup = OrphanedMocksCleanup(mock_session, mock_scheduler, settings)
                result = await cleanup.execute()

                # Verify: State wurde auf "stopped" gesetzt
                assert result["orphaned_found"] == 1
                assert result["warned"] == 1

                # update_simulation_state aufgerufen
                mock_repo.update_simulation_state.assert_called_once_with("MOCK_RUNNING", "stopped")

    @pytest.mark.asyncio
    async def test_old_stopped_mock_detection(
        self, mock_session, mock_scheduler, maintenance_settings
    ):
        """
        Test: Alte Stopped Mocks Detection

        Erwartung:
        - Mocks älter als 24h werden gefunden
        - WARN-ONLY Mode: Nur Warning
        """
        settings = maintenance_settings
        settings.orphaned_mock_age_hours = 24

        # Mock old stopped device
        old_device = MagicMock()
        old_device.id = 1
        old_device.device_id = "MOCK_OLD"
        old_device.device_metadata = {"simulation_state": "stopped"}
        old_device.created_at = datetime.now(timezone.utc) - timedelta(hours=48)
        old_device.updated_at = datetime.now(timezone.utc) - timedelta(hours=48)

        with patch("src.db.repositories.ESPRepository") as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.get_running_mock_devices = AsyncMock(return_value=[])
            mock_repo.get_all_mock_devices = AsyncMock(return_value=[old_device])

            with patch("src.services.simulation.get_simulation_scheduler") as mock_sim:
                mock_sim.return_value = None

                cleanup = OrphanedMocksCleanup(mock_session, mock_scheduler, settings)
                result = await cleanup.execute()

                # Verify: Gefunden aber nicht gelöscht (WARN ONLY)
                assert result["orphaned_found"] == 1
                assert result["warned"] == 1
                assert result["deleted"] == 0

    @pytest.mark.asyncio
    async def test_recent_stopped_mock_not_detected(
        self, mock_session, mock_scheduler, maintenance_settings
    ):
        """
        Test: Kürzlich gestoppte Mocks werden NICHT als orphaned erkannt

        Erwartung:
        - Mocks jünger als 24h werden NICHT als orphaned markiert
        """
        settings = maintenance_settings
        settings.orphaned_mock_age_hours = 24

        # Mock recent stopped device (nur 1h alt)
        recent_device = MagicMock()
        recent_device.id = 1
        recent_device.device_id = "MOCK_RECENT"
        recent_device.device_metadata = {"simulation_state": "stopped"}
        recent_device.created_at = datetime.now(timezone.utc) - timedelta(hours=1)
        recent_device.updated_at = datetime.now(timezone.utc) - timedelta(hours=1)

        with patch("src.db.repositories.ESPRepository") as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.get_running_mock_devices = AsyncMock(return_value=[])
            mock_repo.get_all_mock_devices = AsyncMock(return_value=[recent_device])

            with patch("src.services.simulation.get_simulation_scheduler") as mock_sim:
                mock_sim.return_value = None

                cleanup = OrphanedMocksCleanup(mock_session, mock_scheduler, settings)
                result = await cleanup.execute()

                # Verify: NICHT als orphaned erkannt
                assert result["orphaned_found"] == 0
                assert result["warned"] == 0
                assert result["deleted"] == 0
