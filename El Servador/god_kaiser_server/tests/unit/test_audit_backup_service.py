"""
Unit tests for AuditBackupService (AUT-229 F3).

Covers:
- create_backup: Happy path, empty source, retention=0 (never)
- list_backups / get_backup metadata round-trip
- restore_backup: round-trip into clean DB
- delete_backup
- cleanup_expired_backups
- set_retention_days validation

Tests use a temporary backup directory (tmp_path) so they don't pollute
production backup files.

Refs: AUT-229 F3.
"""

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.audit_log import AuditLog
from src.services.audit_backup_service import (
    BACKUP_RETENTION_NEVER,
    DEFAULT_BACKUP_RETENTION_DAYS,
    MAX_BACKUP_RETENTION_DAYS,
    AuditBackupService,
)


pytestmark = [pytest.mark.asyncio]


async def _make_audit_event(
    db_session: AsyncSession,
    *,
    event_type: str = "test_event",
    severity: str = "info",
    source_type: str = "test",
    message: str = "test message",
) -> AuditLog:
    """Create and persist a minimal AuditLog record."""
    event = AuditLog(
        event_type=event_type,
        severity=severity,
        source_type=source_type,
        source_id="test-source",
        status="success",
        message=message,
        details={"foo": "bar"},
    )
    db_session.add(event)
    await db_session.commit()
    await db_session.refresh(event)
    return event


@pytest_asyncio.fixture
async def backup_service(db_session: AsyncSession, tmp_path):
    """AuditBackupService with isolated temp backup_dir."""
    return AuditBackupService(
        session=db_session,
        backup_dir=str(tmp_path),
        retention_days=DEFAULT_BACKUP_RETENTION_DAYS,
    )


class TestCreateBackup:
    async def test_create_backup_happy_path(
        self,
        db_session: AsyncSession,
        backup_service: AuditBackupService,
    ):
        """create_backup returns UUID and writes JSON file."""
        event = await _make_audit_event(db_session)

        backup_id = await backup_service.create_backup(
            [event],
            metadata={"reason": "unit-test"},
        )

        assert backup_id is not None
        assert isinstance(backup_id, str)
        assert len(backup_id) == 36

        backup_file = backup_service.backup_dir / f"{backup_id}.json"
        assert backup_file.exists()

    async def test_create_backup_empty_events_returns_none(
        self,
        backup_service: AuditBackupService,
    ):
        """create_backup with empty events list returns None (skip)."""
        result = await backup_service.create_backup([], metadata={"reason": "empty"})
        assert result is None

    async def test_create_backup_retention_never_no_expiry(
        self,
        db_session: AsyncSession,
        tmp_path,
    ):
        """retention_days=0 (never) -> expires_at is None and backup is non-expired."""
        service = AuditBackupService(
            session=db_session,
            backup_dir=str(tmp_path),
            retention_days=BACKUP_RETENTION_NEVER,
        )
        event = await _make_audit_event(db_session)

        backup_id = await service.create_backup([event])
        assert backup_id is not None

        meta = await service.get_backup(backup_id)
        assert meta is not None
        assert meta["expires_at"] is None
        assert meta["expired"] is False


class TestListBackups:
    async def test_list_backups_empty(self, backup_service: AuditBackupService):
        """list_backups returns empty list for empty backup_dir."""
        result = await backup_service.list_backups()
        assert result == []

    async def test_list_backups_after_create(
        self,
        db_session: AsyncSession,
        backup_service: AuditBackupService,
    ):
        """list_backups contains entries after create_backup."""
        event = await _make_audit_event(db_session)
        backup_id = await backup_service.create_backup(
            [event],
            metadata={"reason": "list-test"},
        )

        result = await backup_service.list_backups()
        assert len(result) == 1
        assert result[0]["backup_id"] == backup_id
        assert result[0]["event_count"] == 1
        assert result[0]["metadata"]["reason"] == "list-test"

    async def test_get_backup_unknown_returns_none(
        self,
        backup_service: AuditBackupService,
    ):
        """get_backup returns None for unknown backup_id."""
        result = await backup_service.get_backup("non-existent-id")
        assert result is None


class TestRestoreBackup:
    async def test_restore_backup_round_trip(
        self,
        db_session: AsyncSession,
        backup_service: AuditBackupService,
    ):
        """restore_backup re-creates events that were removed from DB."""
        event = await _make_audit_event(db_session, message="will-be-restored")
        backup_id = await backup_service.create_backup([event])
        assert backup_id is not None

        await db_session.delete(event)
        await db_session.commit()

        result = await backup_service.restore_backup(
            backup_id, delete_after_restore=False
        )

        assert result["backup_id"] == backup_id
        assert result["restored_count"] == 1
        assert result["skipped_duplicates"] == 0
        assert result["total_in_backup"] == 1
        assert result["backup_deleted"] is False
        assert len(result["restored_event_ids"]) == 1

    async def test_restore_backup_unknown_raises(
        self,
        backup_service: AuditBackupService,
    ):
        """restore_backup raises ValueError for unknown backup_id."""
        with pytest.raises(ValueError, match="not found"):
            await backup_service.restore_backup("non-existent-id")


class TestDeleteBackup:
    async def test_delete_backup_happy_path(
        self,
        db_session: AsyncSession,
        backup_service: AuditBackupService,
    ):
        """delete_backup returns True after creating + deleting."""
        event = await _make_audit_event(db_session)
        backup_id = await backup_service.create_backup([event])
        assert backup_id is not None

        deleted = await backup_service.delete_backup(backup_id)
        assert deleted is True

        again = await backup_service.delete_backup(backup_id)
        assert again is False

    async def test_delete_backup_unknown_returns_false(
        self,
        backup_service: AuditBackupService,
    ):
        """delete_backup returns False for unknown backup_id."""
        result = await backup_service.delete_backup("non-existent-id")
        assert result is False

    async def test_cleanup_expired_skips_never_expire(
        self,
        db_session: AsyncSession,
        tmp_path,
    ):
        """cleanup_expired_backups does not touch retention=0 (never) backups."""
        service = AuditBackupService(
            session=db_session,
            backup_dir=str(tmp_path),
            retention_days=BACKUP_RETENTION_NEVER,
        )
        event = await _make_audit_event(db_session)
        backup_id = await service.create_backup([event])
        assert backup_id is not None

        deleted = await service.cleanup_expired_backups()
        assert deleted == 0

        meta = await service.get_backup(backup_id)
        assert meta is not None


class TestRetentionConfig:
    """Methods are sync but kept async so the async backup_service fixture
    can be cleanly requested under module-level pytestmark."""

    async def test_set_retention_days_valid(self, backup_service: AuditBackupService):
        backup_service.set_retention_days(30)
        assert backup_service.retention_days == 30

    async def test_set_retention_days_never(self, backup_service: AuditBackupService):
        """retention_days=0 (never) is allowed."""
        backup_service.set_retention_days(BACKUP_RETENTION_NEVER)
        assert backup_service.retention_days == BACKUP_RETENTION_NEVER

    async def test_set_retention_days_negative_rejected(
        self,
        backup_service: AuditBackupService,
    ):
        with pytest.raises(ValueError, match=">= 0"):
            backup_service.set_retention_days(-1)

    async def test_set_retention_days_too_large_rejected(
        self,
        backup_service: AuditBackupService,
    ):
        with pytest.raises(ValueError):
            backup_service.set_retention_days(MAX_BACKUP_RETENTION_DAYS + 1)

    async def test_get_retention_config(self, backup_service: AuditBackupService):
        cfg = backup_service.get_retention_config()
        assert cfg["retention_days"] == DEFAULT_BACKUP_RETENTION_DAYS
        assert cfg["max_retention_days"] == MAX_BACKUP_RETENTION_DAYS
        assert cfg["never_expire_value"] == BACKUP_RETENTION_NEVER
        assert "max_backups" in cfg
