"""
Unit Tests für SensorDataCleanup (Data-Safe Version)

Tests umfassen:
- Disabled-Mode (Safety-Test)
- Dry-Run Mode (Safety-Test)
- Safety-Limit Enforcement
- Batch-Processing
- Rollback bei Fehlern
- Nothing-to-Delete Case
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.config import MaintenanceSettings
from src.services.maintenance.jobs.cleanup import SensorDataCleanup


@pytest.fixture
def maintenance_settings():
    """Standard MaintenanceSettings mit Safety-Defaults"""
    return MaintenanceSettings(
        # Sensor Data Cleanup
        sensor_data_retention_enabled=False,  # ⚠️ Default: DISABLED
        sensor_data_retention_days=30,
        sensor_data_cleanup_dry_run=True,  # ⚠️ Default: DRY-RUN
        sensor_data_cleanup_batch_size=1000,
        sensor_data_cleanup_max_batches=100,
        # Command History
        command_history_retention_enabled=False,
        command_history_retention_days=14,
        command_history_cleanup_dry_run=True,
        command_history_cleanup_batch_size=1000,
        command_history_cleanup_max_batches=50,
        # Orphaned Mocks
        orphaned_mock_cleanup_enabled=True,
        orphaned_mock_auto_delete=False,  # ⚠️ Default: WARN ONLY
        orphaned_mock_age_hours=24,
        # Health Checks
        heartbeat_timeout_seconds=180,
        mqtt_health_check_interval_seconds=30,
        esp_health_check_interval_seconds=60,
        # Stats
        stats_aggregation_enabled=True,
        stats_aggregation_interval_minutes=60,
        # Advanced Safety
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


class TestSensorDataCleanup:
    """Tests für SensorDataCleanup"""

    # ================================================================
    # SAFETY TESTS
    # ================================================================

    @pytest.mark.asyncio
    async def test_disabled_mode(self, mock_session, maintenance_settings):
        """
        Test 1: DISABLED Mode (Default)

        Erwartung:
        - Kein Cleanup ausgeführt
        - Status: "disabled"
        - records_deleted: 0
        - Keine DB-Queries
        """
        # Settings: Cleanup DISABLED
        settings = maintenance_settings
        assert settings.sensor_data_retention_enabled is False  # Safety-Check

        cleanup = SensorDataCleanup(mock_session, settings)
        result = await cleanup.execute()

        # Verify
        assert result["status"] == "disabled"
        assert result["records_found"] == 0
        assert result["records_deleted"] == 0
        assert result["dry_run"] is False
        assert result["cutoff_date"] is None

        # Keine DB-Queries durchgeführt
        mock_session.execute.assert_not_called()
        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_dry_run_mode(self, mock_session, maintenance_settings):
        """
        Test 2: DRY-RUN Mode (Default wenn enabled)

        Erwartung:
        - Zählt Records
        - Löscht KEINE Daten
        - Status: "dry_run"
        - records_deleted: 0
        """
        # Settings: Cleanup ENABLED + DRY-RUN
        settings = maintenance_settings
        settings.sensor_data_retention_enabled = True
        settings.sensor_data_cleanup_dry_run = True  # ⚠️ Safety

        # Mock: 15420 Records zu löschen
        total_records_mock = MagicMock()
        total_records_mock.scalar.return_value = 100000

        to_delete_mock = MagicMock()
        to_delete_mock.scalar.return_value = 15420

        mock_session.execute.side_effect = [total_records_mock, to_delete_mock]

        cleanup = SensorDataCleanup(mock_session, settings)
        result = await cleanup.execute()

        # Verify
        assert result["status"] == "dry_run"
        assert result["dry_run"] is True
        assert result["records_found"] == 15420
        assert result["records_deleted"] == 0  # ⚠️ NICHT gelöscht!
        assert result["batches_processed"] == 0

        # Nur COUNT-Queries, keine DELETE
        assert mock_session.execute.call_count == 2  # Total + To Delete
        mock_session.commit.assert_not_called()  # ⚠️ Kein Commit!

    @pytest.mark.asyncio
    async def test_safety_limit_enforcement(self, mock_session, maintenance_settings):
        """
        Test 3: Safety-Limit verhindert zu große Deletions

        Erwartung:
        - Cleanup wird ABORTED
        - Status: "aborted_safety_limit"
        - records_deleted: 0
        """
        # Settings: Cleanup ENABLED, DRY-RUN OFF, Niedriger Safety-Limit
        settings = maintenance_settings
        settings.sensor_data_retention_enabled = True
        settings.sensor_data_cleanup_dry_run = False
        settings.cleanup_max_records_per_run = 10000  # Nur 10k erlaubt

        # Mock: 150.000 Records zu löschen (> Safety-Limit)
        total_records_mock = MagicMock()
        total_records_mock.scalar.return_value = 200000

        to_delete_mock = MagicMock()
        to_delete_mock.scalar.return_value = 150000

        mock_session.execute.side_effect = [total_records_mock, to_delete_mock]

        cleanup = SensorDataCleanup(mock_session, settings)
        result = await cleanup.execute()

        # Verify: ABORTED
        assert result["status"] == "aborted_safety_limit"
        assert result["records_found"] == 150000
        assert result["records_deleted"] == 0  # ⚠️ NICHTS gelöscht!

        # Nur COUNT-Queries, keine DELETE
        assert mock_session.execute.call_count == 2
        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_alert_threshold_warning(self, mock_session, maintenance_settings, caplog):
        """
        Test 4: Alert bei zu hohem Deletion-Prozentsatz

        Erwartung:
        - Warning geloggt
        - Cleanup läuft trotzdem (DRY-RUN)
        """
        import logging

        caplog.set_level(logging.WARNING)

        # Settings: 10% Alert-Threshold
        settings = maintenance_settings
        settings.sensor_data_retention_enabled = True
        settings.sensor_data_cleanup_dry_run = True
        settings.cleanup_alert_threshold_percent = 10.0

        # Mock: 25% der Records sollen gelöscht werden (> 10% Threshold)
        total_records_mock = MagicMock()
        total_records_mock.scalar.return_value = 100000

        to_delete_mock = MagicMock()
        to_delete_mock.scalar.return_value = 25000  # 25%

        mock_session.execute.side_effect = [total_records_mock, to_delete_mock]

        cleanup = SensorDataCleanup(mock_session, settings)
        result = await cleanup.execute()

        # Verify: Warning geloggt
        assert "CLEANUP ALERT" in caplog.text
        # Note: Log uses thousands separator (:,) so "25,000" not "25000"
        assert "25,000 records (25.0%)" in caplog.text

        # DRY-RUN Status
        assert result["status"] == "dry_run"

    # ================================================================
    # BATCH-PROCESSING TESTS
    # ================================================================

    @pytest.mark.asyncio
    async def test_batch_deletion(self, mock_session, maintenance_settings):
        """
        Test 5: Batch-Processing verhindert DB-Locks

        Erwartung:
        - Deletion in Batches (z.B. 100 Records x 5 Batches = 500 Total)
        - Jeder Batch hat eigenes Commit
        """
        # Settings: Cleanup ENABLED, DRY-RUN OFF
        settings = maintenance_settings
        settings.sensor_data_retention_enabled = True
        settings.sensor_data_cleanup_dry_run = False
        settings.sensor_data_cleanup_batch_size = 100

        # Mock: 500 Records zu löschen
        total_records_mock = MagicMock()
        total_records_mock.scalar.return_value = 10000

        to_delete_mock = MagicMock()
        to_delete_mock.scalar.return_value = 500

        # Mock Batches: 5 Batches à 100 Records
        batch1 = MagicMock()
        batch1.fetchall.return_value = [(i,) for i in range(100)]

        batch2 = MagicMock()
        batch2.fetchall.return_value = [(i,) for i in range(100, 200)]

        batch3 = MagicMock()
        batch3.fetchall.return_value = [(i,) for i in range(200, 300)]

        batch4 = MagicMock()
        batch4.fetchall.return_value = [(i,) for i in range(300, 400)]

        batch5 = MagicMock()
        batch5.fetchall.return_value = [(i,) for i in range(400, 500)]

        empty_batch = MagicMock()
        empty_batch.fetchall.return_value = []

        # Mock Delete Results
        delete_result = MagicMock()
        delete_result.rowcount = 100

        mock_session.execute.side_effect = [
            total_records_mock,  # Total count
            to_delete_mock,  # To delete count
            batch1,
            delete_result,  # Batch 1
            batch2,
            delete_result,  # Batch 2
            batch3,
            delete_result,  # Batch 3
            batch4,
            delete_result,  # Batch 4
            batch5,
            delete_result,  # Batch 5
            empty_batch,  # No more records
        ]

        cleanup = SensorDataCleanup(mock_session, settings)
        result = await cleanup.execute()

        # Verify
        assert result["status"] == "success"
        assert result["records_deleted"] == 500
        assert result["batches_processed"] == 5

        # 5 Commits (einer pro Batch)
        assert mock_session.commit.call_count == 5

    @pytest.mark.asyncio
    async def test_rollback_on_error(self, mock_session, maintenance_settings):
        """
        Test 6: Rollback bei Fehler in Batch

        Erwartung:
        - Batch 1 + 2 erfolgreich
        - Batch 3 schlägt fehl
        - Rollback für Batch 3
        - Nur Batch 1 + 2 committed
        """
        # Settings: Cleanup ENABLED, DRY-RUN OFF
        settings = maintenance_settings
        settings.sensor_data_retention_enabled = True
        settings.sensor_data_cleanup_dry_run = False
        settings.sensor_data_cleanup_batch_size = 100

        # Mock: 300 Records zu löschen
        total_records_mock = MagicMock()
        total_records_mock.scalar.return_value = 10000

        to_delete_mock = MagicMock()
        to_delete_mock.scalar.return_value = 300

        batch1 = MagicMock()
        batch1.fetchall.return_value = [(i,) for i in range(100)]

        batch2 = MagicMock()
        batch2.fetchall.return_value = [(i,) for i in range(100, 200)]

        # Batch 3 wirft Exception
        delete_result = MagicMock()
        delete_result.rowcount = 100

        mock_session.execute.side_effect = [
            total_records_mock,  # Total count
            to_delete_mock,  # To delete count
            batch1,
            delete_result,  # Batch 1 OK
            batch2,
            delete_result,  # Batch 2 OK
            Exception("DB-Lock Error"),  # Batch 3 FEHLER
        ]

        cleanup = SensorDataCleanup(mock_session, settings)
        result = await cleanup.execute()

        # Verify: Nur 2 Batches committed
        assert result["status"] == "success"
        assert result["records_deleted"] == 200  # Nur Batch 1 + 2
        assert result["batches_processed"] == 2

        # Rollback wurde aufgerufen
        mock_session.rollback.assert_called_once()

    # ================================================================
    # EDGE CASES
    # ================================================================

    @pytest.mark.asyncio
    async def test_nothing_to_delete(self, mock_session, maintenance_settings):
        """
        Test 7: Nothing to Delete

        Erwartung:
        - Status: "nothing_to_delete"
        - records_deleted: 0
        - Keine DELETE-Query
        """
        # Settings: Cleanup ENABLED
        settings = maintenance_settings
        settings.sensor_data_retention_enabled = True
        settings.sensor_data_cleanup_dry_run = False

        # Mock: 0 Records zu löschen
        total_records_mock = MagicMock()
        total_records_mock.scalar.return_value = 10000

        to_delete_mock = MagicMock()
        to_delete_mock.scalar.return_value = 0

        mock_session.execute.side_effect = [total_records_mock, to_delete_mock]

        cleanup = SensorDataCleanup(mock_session, settings)
        result = await cleanup.execute()

        # Verify
        assert result["status"] == "nothing_to_delete"
        assert result["records_found"] == 0
        assert result["records_deleted"] == 0

        # Nur 2 COUNT-Queries, keine DELETE
        assert mock_session.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_cutoff_date_calculation(self, mock_session, maintenance_settings):
        """
        Test 8: Cutoff-Date korrekt berechnet

        Erwartung:
        - cutoff_date = now() - retention_days
        - Format: ISO-8601
        """
        # Settings: Retention 30 Tage
        settings = maintenance_settings
        settings.sensor_data_retention_enabled = True
        settings.sensor_data_retention_days = 30
        settings.sensor_data_cleanup_dry_run = True

        # Mock: 1000 Records
        total_records_mock = MagicMock()
        total_records_mock.scalar.return_value = 10000

        to_delete_mock = MagicMock()
        to_delete_mock.scalar.return_value = 1000

        mock_session.execute.side_effect = [total_records_mock, to_delete_mock]

        cleanup = SensorDataCleanup(mock_session, settings)
        result = await cleanup.execute()

        # Verify Cutoff-Date
        cutoff_date_str = result["cutoff_date"]
        cutoff_date = datetime.fromisoformat(cutoff_date_str)

        expected_cutoff = datetime.now(timezone.utc) - timedelta(days=30)

        # Toleranz: 1 Sekunde
        assert abs((cutoff_date - expected_cutoff).total_seconds()) < 1


# ================================================================
# INTEGRATION TESTS (Optional)
# ================================================================


class TestSensorDataCleanupIntegration:
    """Integration Tests mit echter DB (optional)"""

    # TODO: Integration-Tests mit echter PostgreSQL-Datenbank
    # - Testdaten einfügen
    # - Cleanup ausführen
    # - Verifikation der gelöschten Daten
    pass
