"""
Unit Tests für CommandHistoryCleanup (Data-Safe Version)

Analog zu SensorDataCleanup mit gleichen Safety-Features.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from src.core.config import MaintenanceSettings
from src.services.maintenance.jobs.cleanup import CommandHistoryCleanup


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
        orphaned_mock_auto_delete=False,
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
    session.rollback = AsyncMock()
    return session


class TestCommandHistoryCleanup:
    """Tests für CommandHistoryCleanup (analog zu SensorDataCleanup)"""

    @pytest.mark.asyncio
    async def test_disabled_mode(self, mock_session, maintenance_settings):
        """Test: DISABLED Mode (Default)"""
        settings = maintenance_settings
        assert settings.command_history_retention_enabled is False

        cleanup = CommandHistoryCleanup(mock_session, settings)
        result = await cleanup.execute()

        assert result["status"] == "disabled"
        assert result["records_deleted"] == 0
        mock_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_dry_run_mode(self, mock_session, maintenance_settings):
        """Test: DRY-RUN Mode (Default wenn enabled)"""
        settings = maintenance_settings
        settings.command_history_retention_enabled = True
        settings.command_history_cleanup_dry_run = True

        # Mock: 5000 Records zu löschen
        total_records_mock = MagicMock()
        total_records_mock.scalar.return_value = 50000

        to_delete_mock = MagicMock()
        to_delete_mock.scalar.return_value = 5000

        mock_session.execute.side_effect = [total_records_mock, to_delete_mock]

        cleanup = CommandHistoryCleanup(mock_session, settings)
        result = await cleanup.execute()

        assert result["status"] == "dry_run"
        assert result["dry_run"] is True
        assert result["records_found"] == 5000
        assert result["records_deleted"] == 0  # ⚠️ NICHT gelöscht!
        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_safety_limit_enforcement(self, mock_session, maintenance_settings):
        """Test: Safety-Limit verhindert zu große Deletions"""
        settings = maintenance_settings
        settings.command_history_retention_enabled = True
        settings.command_history_cleanup_dry_run = False
        settings.cleanup_max_records_per_run = 1000  # Niedriger Limit

        # Mock: 50.000 Records zu löschen (> Safety-Limit)
        total_records_mock = MagicMock()
        total_records_mock.scalar.return_value = 100000

        to_delete_mock = MagicMock()
        to_delete_mock.scalar.return_value = 50000

        mock_session.execute.side_effect = [total_records_mock, to_delete_mock]

        cleanup = CommandHistoryCleanup(mock_session, settings)
        result = await cleanup.execute()

        assert result["status"] == "aborted_safety_limit"
        assert result["records_deleted"] == 0
        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_batch_deletion(self, mock_session, maintenance_settings):
        """Test: Batch-Processing verhindert DB-Locks"""
        settings = maintenance_settings
        settings.command_history_retention_enabled = True
        settings.command_history_cleanup_dry_run = False
        settings.command_history_cleanup_batch_size = 50

        # Mock: 200 Records in 4 Batches à 50
        total_records_mock = MagicMock()
        total_records_mock.scalar.return_value = 5000

        to_delete_mock = MagicMock()
        to_delete_mock.scalar.return_value = 200

        batch = MagicMock()
        batch.fetchall.return_value = [(i,) for i in range(50)]

        empty_batch = MagicMock()
        empty_batch.fetchall.return_value = []

        delete_result = MagicMock()
        delete_result.rowcount = 50

        mock_session.execute.side_effect = [
            total_records_mock,
            to_delete_mock,
            batch,
            delete_result,
            batch,
            delete_result,
            batch,
            delete_result,
            batch,
            delete_result,
            empty_batch,
        ]

        cleanup = CommandHistoryCleanup(mock_session, settings)
        result = await cleanup.execute()

        assert result["status"] == "success"
        assert result["records_deleted"] == 200
        assert result["batches_processed"] == 4
        assert mock_session.commit.call_count == 4

    @pytest.mark.asyncio
    async def test_nothing_to_delete(self, mock_session, maintenance_settings):
        """Test: Nothing to Delete"""
        settings = maintenance_settings
        settings.command_history_retention_enabled = True
        settings.command_history_cleanup_dry_run = False

        # Mock: 0 Records zu löschen
        total_records_mock = MagicMock()
        total_records_mock.scalar.return_value = 5000

        to_delete_mock = MagicMock()
        to_delete_mock.scalar.return_value = 0

        mock_session.execute.side_effect = [total_records_mock, to_delete_mock]

        cleanup = CommandHistoryCleanup(mock_session, settings)
        result = await cleanup.execute()

        assert result["status"] == "nothing_to_delete"
        assert result["records_deleted"] == 0
        assert mock_session.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_cutoff_date_calculation(self, mock_session, maintenance_settings):
        """Test: Cutoff-Date korrekt berechnet (14 Tage)"""
        settings = maintenance_settings
        settings.command_history_retention_enabled = True
        settings.command_history_retention_days = 14
        settings.command_history_cleanup_dry_run = True

        total_records_mock = MagicMock()
        total_records_mock.scalar.return_value = 5000

        to_delete_mock = MagicMock()
        to_delete_mock.scalar.return_value = 500

        mock_session.execute.side_effect = [total_records_mock, to_delete_mock]

        cleanup = CommandHistoryCleanup(mock_session, settings)
        result = await cleanup.execute()

        cutoff_date = datetime.fromisoformat(result["cutoff_date"])
        expected_cutoff = datetime.now(timezone.utc) - timedelta(days=14)

        assert abs((cutoff_date - expected_cutoff).total_seconds()) < 1
