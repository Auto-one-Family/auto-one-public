"""
Unit Tests for DatabaseBackupService (Phase A V5.1)

Tests backup creation, listing, deletion, cleanup, and filename parsing.
Uses mocked subprocess calls (no actual pg_dump needed).
"""

import asyncio
import gzip
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.config import DatabaseBackupSettings
from src.services.database_backup_service import (
    BackupInfo,
    DatabaseBackupService,
    _human_size,
    _parse_backup_filename,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def backup_settings(tmp_path):
    """Create DatabaseBackupSettings with defaults."""
    return DatabaseBackupSettings(
        DB_BACKUP_ENABLED=True,
        DB_BACKUP_HOUR=2,
        DB_BACKUP_MINUTE=0,
        DB_BACKUP_MAX_AGE_DAYS=7,
        DB_BACKUP_MAX_COUNT=20,
        DB_BACKUP_PG_HOST="postgres",
        DB_BACKUP_PG_PORT=5432,
        DB_BACKUP_PG_DATABASE="god_kaiser_db",
        DB_BACKUP_PG_USER="god_kaiser",
        DB_BACKUP_PG_PASSWORD="testpassword",
    )


@pytest.fixture
def backup_service(backup_settings, tmp_path):
    """Create DatabaseBackupService with temp directory."""
    service = DatabaseBackupService(backup_settings)
    # Override backup dir to use tmp_path
    service._backup_dir = tmp_path / "backups" / "database"
    service._backup_dir.mkdir(parents=True, exist_ok=True)
    return service


def _create_fake_backup(backup_dir: Path, backup_id: str, content: bytes = b"-- SQL dump") -> Path:
    """Helper: create a fake .sql.gz backup file."""
    filename = f"backup_{backup_id}.sql.gz"
    filepath = backup_dir / filename
    with gzip.open(filepath, "wb") as f:
        f.write(content)
    return filepath


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestHumanSize:
    def test_bytes(self):
        assert _human_size(500) == "500.0 B"

    def test_kilobytes(self):
        assert _human_size(1536) == "1.5 KB"

    def test_megabytes(self):
        assert _human_size(5 * 1024 * 1024) == "5.0 MB"

    def test_gigabytes(self):
        assert _human_size(2 * 1024 * 1024 * 1024) == "2.0 GB"


class TestParseBackupFilename:
    def test_valid_filename(self):
        result = _parse_backup_filename("backup_20260303_020000.sql.gz")
        assert result is not None
        assert result["backup_id"] == "20260303_020000"
        assert result["created_at"].year == 2026
        assert result["created_at"].month == 3
        assert result["created_at"].day == 3

    def test_invalid_prefix(self):
        assert _parse_backup_filename("dump_20260303_020000.sql.gz") is None

    def test_invalid_extension(self):
        assert _parse_backup_filename("backup_20260303_020000.tar.gz") is None

    def test_invalid_date(self):
        assert _parse_backup_filename("backup_invalid_date.sql.gz") is None

    def test_empty_string(self):
        assert _parse_backup_filename("") is None


# =============================================================================
# BackupInfo Tests
# =============================================================================


class TestBackupInfo:
    def test_to_dict(self):
        info = BackupInfo(
            backup_id="20260303_020000",
            filename="backup_20260303_020000.sql.gz",
            filepath=Path("/tmp/backup.sql.gz"),
            created_at=datetime(2026, 3, 3, 2, 0, 0, tzinfo=timezone.utc),
            size_bytes=1024 * 1024,  # 1 MB
            pg_version="pg_dump (PostgreSQL) 16.12",
            database="god_kaiser_db",
            duration_seconds=3.5,
        )
        d = info.to_dict()
        assert d["backup_id"] == "20260303_020000"
        assert d["size_bytes"] == 1048576
        assert d["size_human"] == "1.0 MB"
        assert d["pg_version"] == "pg_dump (PostgreSQL) 16.12"
        assert d["duration_seconds"] == 3.5


# =============================================================================
# DatabaseBackupService Tests
# =============================================================================


class TestDatabaseBackupServiceInit:
    def test_initialization(self, backup_service):
        assert backup_service.backup_dir.exists()

    def test_settings_stored(self, backup_service, backup_settings):
        assert backup_service._settings is backup_settings


class TestListBackups:
    @pytest.mark.asyncio
    async def test_empty_directory(self, backup_service):
        backups = await backup_service.list_backups()
        assert backups == []

    @pytest.mark.asyncio
    async def test_list_single_backup(self, backup_service):
        _create_fake_backup(backup_service.backup_dir, "20260303_020000")
        backups = await backup_service.list_backups()
        assert len(backups) == 1
        assert backups[0].backup_id == "20260303_020000"

    @pytest.mark.asyncio
    async def test_list_multiple_backups_sorted(self, backup_service):
        _create_fake_backup(backup_service.backup_dir, "20260301_020000")
        _create_fake_backup(backup_service.backup_dir, "20260303_020000")
        _create_fake_backup(backup_service.backup_dir, "20260302_020000")

        backups = await backup_service.list_backups()
        assert len(backups) == 3
        # Newest first
        assert backups[0].backup_id == "20260303_020000"
        assert backups[1].backup_id == "20260302_020000"
        assert backups[2].backup_id == "20260301_020000"

    @pytest.mark.asyncio
    async def test_ignores_non_backup_files(self, backup_service):
        # Create a non-backup file
        (backup_service.backup_dir / "readme.txt").write_text("not a backup")
        _create_fake_backup(backup_service.backup_dir, "20260303_020000")

        backups = await backup_service.list_backups()
        assert len(backups) == 1


class TestGetBackup:
    @pytest.mark.asyncio
    async def test_existing_backup(self, backup_service):
        _create_fake_backup(backup_service.backup_dir, "20260303_020000")
        backup = await backup_service.get_backup("20260303_020000")
        assert backup is not None
        assert backup.backup_id == "20260303_020000"

    @pytest.mark.asyncio
    async def test_nonexistent_backup(self, backup_service):
        backup = await backup_service.get_backup("99991231_235959")
        assert backup is None


class TestDeleteBackup:
    @pytest.mark.asyncio
    async def test_delete_existing(self, backup_service):
        filepath = _create_fake_backup(backup_service.backup_dir, "20260303_020000")
        assert filepath.exists()

        result = await backup_service.delete_backup("20260303_020000")
        assert result is True
        assert not filepath.exists()

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, backup_service):
        result = await backup_service.delete_backup("99991231_235959")
        assert result is False


class TestCleanupOldBackups:
    @pytest.mark.asyncio
    async def test_cleanup_by_age(self, backup_service):
        # Create backups with old dates
        now = datetime.now(timezone.utc)
        old_date = now - timedelta(days=10)
        old_id = old_date.strftime("%Y%m%d_%H%M%S")
        recent_id = now.strftime("%Y%m%d_%H%M%S")

        _create_fake_backup(backup_service.backup_dir, old_id)
        _create_fake_backup(backup_service.backup_dir, recent_id)

        result = await backup_service.cleanup_old_backups()
        assert result["deleted_by_age"] == 1
        assert result["remaining"] == 1

    @pytest.mark.asyncio
    async def test_cleanup_by_count(self, backup_service):
        # Set max_count to 2
        backup_service._settings.max_count = 2

        now = datetime.now(timezone.utc)
        for i in range(5):
            dt = now - timedelta(hours=i)
            backup_id = dt.strftime("%Y%m%d_%H%M%S")
            _create_fake_backup(backup_service.backup_dir, backup_id)

        result = await backup_service.cleanup_old_backups()
        assert result["deleted_by_count"] == 3
        assert result["remaining"] == 2

    @pytest.mark.asyncio
    async def test_no_cleanup_needed(self, backup_service):
        now = datetime.now(timezone.utc)
        recent_id = now.strftime("%Y%m%d_%H%M%S")
        _create_fake_backup(backup_service.backup_dir, recent_id)

        result = await backup_service.cleanup_old_backups()
        assert result["total_deleted"] == 0
        assert result["remaining"] == 1


class TestCreateBackup:
    @pytest.mark.asyncio
    async def test_create_backup_success(self, backup_service):
        """Test backup creation with mocked subprocess."""
        sql_dump = b"-- PostgreSQL database dump\nCREATE TABLE test (id int);\n"

        mock_process_dump = AsyncMock()
        mock_process_dump.communicate = AsyncMock(return_value=(sql_dump, b""))
        mock_process_dump.returncode = 0

        mock_process_version = AsyncMock()
        mock_process_version.communicate = AsyncMock(
            return_value=(b"pg_dump (PostgreSQL) 16.12\n", b"")
        )
        mock_process_version.returncode = 0

        call_count = 0

        async def mock_create_subprocess(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                # First call: pg_dump --version (check)
                return mock_process_version
            elif call_count == 2:
                # Second call: pg_dump (actual backup)
                return mock_process_dump
            else:
                # Subsequent calls: pg_dump --version (for metadata)
                return mock_process_version

        with patch("asyncio.create_subprocess_exec", side_effect=mock_create_subprocess):
            info = await backup_service.create_backup()

        assert info is not None
        assert info.filename.startswith("backup_")
        assert info.filename.endswith(".sql.gz")
        assert info.size_bytes > 0
        assert info.filepath.exists()

        # Verify content is gzipped correctly
        with gzip.open(info.filepath, "rb") as f:
            content = f.read()
        assert content == sql_dump

    @pytest.mark.asyncio
    async def test_create_backup_pg_dump_failure(self, backup_service):
        """Test backup creation when pg_dump fails."""
        # First call: _check_pg_dump() → version check succeeds
        mock_version_process = AsyncMock()
        mock_version_process.communicate = AsyncMock(
            return_value=(b"pg_dump (PostgreSQL) 16.12\n", b"")
        )
        mock_version_process.returncode = 0

        # Second call: actual pg_dump → fails
        mock_dump_process = AsyncMock()
        mock_dump_process.communicate = AsyncMock(return_value=(b"", b"connection refused"))
        mock_dump_process.returncode = 1

        call_count = 0

        async def mock_create_subprocess(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_version_process
            return mock_dump_process

        with patch("asyncio.create_subprocess_exec", side_effect=mock_create_subprocess):
            with pytest.raises(RuntimeError, match="pg_dump failed"):
                await backup_service.create_backup()

    @pytest.mark.asyncio
    async def test_create_backup_pg_dump_not_found(self, backup_service):
        """Test backup creation when pg_dump binary is missing."""
        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
            with pytest.raises(RuntimeError, match="pg_dump not found"):
                await backup_service.create_backup()


class TestRestoreBackup:
    @pytest.mark.asyncio
    async def test_restore_success(self, backup_service):
        """Test restore with mocked subprocess."""
        sql_dump = b"-- PostgreSQL database dump\nCREATE TABLE test (id int);\n"
        _create_fake_backup(backup_service.backup_dir, "20260303_020000", sql_dump)

        mock_process_psql_version = AsyncMock()
        mock_process_psql_version.communicate = AsyncMock(
            return_value=(b"psql (PostgreSQL) 16.12\n", b"")
        )
        mock_process_psql_version.returncode = 0

        mock_process_restore = AsyncMock()
        mock_process_restore.communicate = AsyncMock(return_value=(b"", b""))
        mock_process_restore.returncode = 0

        call_count = 0

        async def mock_create_subprocess(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_process_psql_version
            return mock_process_restore

        with patch("asyncio.create_subprocess_exec", side_effect=mock_create_subprocess):
            preflight = await backup_service.run_restore_preflight("20260303_020000")
            result = await backup_service.restore_backup(
                "20260303_020000",
                preflight_id=preflight["preflight_id"],
                run_id="test-run",
            )

        assert result["status"] == "restored"
        assert result["backup_id"] == "20260303_020000"
        assert result["run_id"] == "test-run"

    @pytest.mark.asyncio
    async def test_restore_nonexistent(self, backup_service):
        """Test preflight for nonexistent backup."""
        with pytest.raises(ValueError, match="not found"):
            await backup_service.run_restore_preflight("99991231_235959")

    @pytest.mark.asyncio
    async def test_restore_requires_preflight(self, backup_service):
        """Restore must be blocked when no preflight token is supplied."""
        _create_fake_backup(backup_service.backup_dir, "20260303_020000")
        with pytest.raises(RuntimeError, match="preflight"):
            await backup_service.restore_backup("20260303_020000")

    @pytest.mark.asyncio
    async def test_restore_failure(self, backup_service):
        """Test restore when psql fails."""
        _create_fake_backup(backup_service.backup_dir, "20260303_020000")

        mock_process_psql_version = AsyncMock()
        mock_process_psql_version.communicate = AsyncMock(
            return_value=(b"psql (PostgreSQL) 16.12\n", b"")
        )
        mock_process_psql_version.returncode = 0

        mock_process_restore = AsyncMock()
        mock_process_restore.communicate = AsyncMock(return_value=(b"", b"ERROR: relation exists"))
        mock_process_restore.returncode = 1

        call_count = 0

        async def mock_create_subprocess(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_process_psql_version
            return mock_process_restore

        with patch("asyncio.create_subprocess_exec", side_effect=mock_create_subprocess):
            preflight = await backup_service.run_restore_preflight("20260303_020000")
            with pytest.raises(RuntimeError, match="psql restore failed"):
                await backup_service.restore_backup(
                    "20260303_020000",
                    preflight_id=preflight["preflight_id"],
                )
