"""
Audit Backup Service

Creates JSON backups of audit logs before deletion operations.
Provides restore capability within a configurable time window.

Features:
- JSON file-based backups (no additional database required)
- Configurable expiration (default: 24 hours)
- Restore capability for accidental deletions
- Automatic cleanup of expired backups
- Audit trail for backup/restore operations
- WebSocket broadcast after restore (for live frontend updates)
- Optional auto-delete backup after restore

Usage:
    backup_service = AuditBackupService(session)

    # Create backup before deletion
    backup_id = await backup_service.create_backup(events, metadata)

    # Restore from backup (with optional auto-delete)
    result = await backup_service.restore_backup(backup_id, delete_after_restore=True)

    # List available backups
    backups = await backup_service.list_backups()

Phase: Cleanup System Consolidation
Priority: HIGH
Status: IMPLEMENTED
"""

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logging_config import get_logger
from ..db.models.audit_log import AuditLog

logger = get_logger(__name__)


def _get_websocket_manager():
    """
    Lazy import of WebSocket manager to avoid circular imports.

    Returns the WebSocket manager instance if available, None otherwise.
    """
    try:
        from ..websocket.manager import WebSocketManager

        # Try to get the singleton instance without await (for sync context)
        return WebSocketManager._instance
    except Exception as e:
        logger.debug(f"WebSocket manager not available: {e}")
        return None


# Default backup configuration
# BACKUP_RETENTION_NEVER = 0 means backups never expire
BACKUP_RETENTION_NEVER = 0
DEFAULT_BACKUP_RETENTION_DAYS = 7  # Default: 7 days
MAX_BACKUP_RETENTION_DAYS = 365  # Maximum: 1 year

DEFAULT_BACKUP_CONFIG = {
    "backup_dir": "backups/audit_logs",
    "retention_days": DEFAULT_BACKUP_RETENTION_DAYS,  # Days until backup expires (0 = never)
    "max_backups": 50,  # Maximum number of backups to keep
}


class AuditBackupService:
    """
    Service for creating and managing audit log backups.

    Backups are stored as JSON files in the configured backup directory.
    Each backup contains:
    - Backup metadata (id, created_at, expires_at, event_count)
    - Operation metadata (user, reason, config used)
    - Full event data for restoration

    Thread-safe for concurrent backup operations.
    """

    def __init__(
        self,
        session: AsyncSession,
        backup_dir: Optional[str] = None,
        retention_days: Optional[int] = None,
    ):
        """
        Initialize AuditBackupService.

        Args:
            session: Async database session
            backup_dir: Directory for backup files (relative to project root)
            retention_days: Days until backup expires (default: 7, 0 = never expire)
        """
        self.session = session
        # Use provided retention_days or default from config
        self.retention_days = (
            retention_days
            if retention_days is not None
            else DEFAULT_BACKUP_CONFIG["retention_days"]
        )

        # Resolve backup directory relative to project root
        project_root = Path(__file__).parent.parent.parent  # god_kaiser_server/
        self.backup_dir = project_root / (backup_dir or DEFAULT_BACKUP_CONFIG["backup_dir"])

        # Ensure backup directory exists
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        logger.debug(
            f"AuditBackupService initialized. Backup dir: {self.backup_dir}, retention_days: {self.retention_days}"
        )

    async def create_backup(
        self,
        events: List[AuditLog],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        Create JSON backup of audit log events.

        Args:
            events: List of AuditLog objects to backup
            metadata: Additional metadata (user_id, operation, config, etc.)

        Returns:
            backup_id: UUID string, or None if backup failed
        """
        if not events:
            logger.debug("No events to backup, skipping backup creation")
            return None

        try:
            backup_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc)
            # retention_days=0 means never expire (expires_at=None)
            if self.retention_days == BACKUP_RETENTION_NEVER:
                expires_at = None
            else:
                expires_at = now + timedelta(days=self.retention_days)

            # Serialize events to JSON-compatible format
            serialized_events = []
            for event in events:
                serialized_events.append(
                    {
                        "id": str(event.id),
                        "created_at": event.created_at.isoformat() if event.created_at else None,
                        "event_type": event.event_type,
                        "severity": event.severity,
                        "source_type": event.source_type,
                        "source_id": event.source_id,
                        "status": event.status,
                        "message": event.message,
                        "details": event.details or {},
                        "error_code": event.error_code,
                        "error_description": event.error_description,
                        "ip_address": event.ip_address,
                        "user_agent": event.user_agent,
                        "correlation_id": event.correlation_id,
                    }
                )

            # Build backup document
            backup_data = {
                "backup_id": backup_id,
                "created_at": now.isoformat(),
                "expires_at": (
                    expires_at.isoformat() if expires_at else None
                ),  # None = never expires
                "event_count": len(events),
                "metadata": metadata or {},
                "events": serialized_events,
            }

            # Write to file
            backup_file = self.backup_dir / f"{backup_id}.json"
            with open(backup_file, "w", encoding="utf-8") as f:
                json.dump(backup_data, f, indent=2, ensure_ascii=False)

            expires_info = expires_at.isoformat() if expires_at else "never"
            logger.info(
                f"Backup created: {backup_id} with {len(events)} events, "
                f"expires: {expires_info}"
            )

            return backup_id

        except Exception as e:
            logger.error(f"Failed to create backup: {e}")
            return None

    async def restore_backup(
        self,
        backup_id: str,
        delete_after_restore: bool = True,
    ) -> Dict[str, Any]:
        """
        Restore audit log events from backup.

        Args:
            backup_id: UUID of backup to restore
            delete_after_restore: If True (default), delete backup after successful restore

        Returns:
            Dict with restore statistics:
            - backup_id: The backup that was restored
            - restored_count: Number of events restored
            - skipped_duplicates: Number of events skipped (already exist)
            - total_in_backup: Total events in backup
            - backup_deleted: Whether backup was deleted after restore
            - restored_event_ids: List of restored event IDs (for frontend highlighting)

        Raises:
            ValueError: If backup not found or expired
        """
        backup_file = self.backup_dir / f"{backup_id}.json"

        if not backup_file.exists():
            raise ValueError(f"Backup {backup_id} not found")

        # Load backup
        with open(backup_file, "r", encoding="utf-8") as f:
            backup_data = json.load(f)

        # Check expiration (None = never expires)
        expires_at_str = backup_data.get("expires_at")
        if expires_at_str is not None:
            expires_at = datetime.fromisoformat(expires_at_str)
            if datetime.now(timezone.utc) > expires_at:
                raise ValueError(f"Backup {backup_id} has expired")

        # Restore events
        restored_count = 0
        skipped_count = 0
        restored_event_ids: List[str] = []

        for event_data in backup_data["events"]:
            try:
                event_id = uuid.UUID(event_data["id"])

                # Check if event already exists
                existing = await self.session.execute(
                    select(AuditLog).where(AuditLog.id == event_id)
                )
                if existing.scalar_one_or_none():
                    skipped_count += 1
                    continue

                # Create new event with original ID
                # Add metadata to mark as restored
                original_details = event_data.get("details", {}) or {}
                restored_details = {
                    **original_details,
                    "_restored_from_backup": backup_id,
                    "_restored_at": datetime.now(timezone.utc).isoformat(),
                }

                event = AuditLog(
                    id=event_id,
                    created_at=(
                        datetime.fromisoformat(event_data["created_at"])
                        if event_data["created_at"]
                        else datetime.now(timezone.utc)
                    ),
                    event_type=event_data["event_type"],
                    severity=event_data["severity"],
                    source_type=event_data["source_type"],
                    source_id=event_data["source_id"],
                    status=event_data.get("status", "success"),
                    message=event_data.get("message"),
                    details=restored_details,
                    error_code=event_data.get("error_code"),
                    error_description=event_data.get("error_description"),
                    ip_address=event_data.get("ip_address"),
                    user_agent=event_data.get("user_agent"),
                    correlation_id=event_data.get("correlation_id"),
                )
                self.session.add(event)
                restored_count += 1
                restored_event_ids.append(str(event_id))

            except Exception as e:
                logger.warning(f"Failed to restore event {event_data.get('id')}: {e}")
                continue

        # Commit all restored events
        if restored_count > 0:
            await self.session.commit()

        # Delete backup after successful restore if requested
        backup_deleted = False
        if delete_after_restore and restored_count > 0:
            try:
                backup_file.unlink()
                backup_deleted = True
                logger.info(
                    f"Backup {backup_id} deleted after restore (cleanup_after_restore=True)"
                )
            except Exception as e:
                logger.warning(f"Failed to delete backup {backup_id} after restore: {e}")

        result = {
            "backup_id": backup_id,
            "restored_count": restored_count,
            "skipped_duplicates": skipped_count,
            "total_in_backup": backup_data["event_count"],
            "backup_deleted": backup_deleted,
            "restored_event_ids": restored_event_ids,
        }

        logger.info(
            f"Backup {backup_id} restored: {restored_count} events restored, "
            f"{skipped_count} skipped (duplicates), backup_deleted={backup_deleted}"
        )

        # Broadcast via WebSocket to notify frontend
        ws_manager = _get_websocket_manager()
        if ws_manager and restored_count > 0:
            try:
                ws_manager.broadcast_threadsafe(
                    message_type="events_restored",
                    data={
                        "backup_id": backup_id,
                        "restored_count": restored_count,
                        "event_ids": restored_event_ids,
                        "message": f"{restored_count} Events wurden wiederhergestellt",
                    },
                )
                logger.debug(f"WebSocket broadcast sent for events_restored (backup {backup_id})")
            except Exception as e:
                logger.warning(f"Failed to broadcast events_restored: {e}")

        return result

    async def list_backups(self, include_expired: bool = False) -> List[Dict[str, Any]]:
        """
        List all available backups.

        Args:
            include_expired: Include expired backups in list

        Returns:
            List of backup metadata dicts, sorted by creation date (newest first)
        """
        backups = []
        now = datetime.now(timezone.utc)

        for backup_file in self.backup_dir.glob("*.json"):
            try:
                with open(backup_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # Handle expires_at (None = never expires)
                expires_at_str = data.get("expires_at")
                if expires_at_str is None:
                    is_expired = False  # Never expires
                else:
                    expires_at = datetime.fromisoformat(expires_at_str)
                    is_expired = now > expires_at

                # Skip expired if not requested
                if is_expired and not include_expired:
                    continue

                backups.append(
                    {
                        "backup_id": data["backup_id"],
                        "created_at": data["created_at"],
                        "expires_at": expires_at_str,  # Can be None (never expires)
                        "expired": is_expired,
                        "event_count": data["event_count"],
                        "metadata": data.get("metadata", {}),
                    }
                )

            except Exception as e:
                logger.warning(f"Failed to read backup {backup_file}: {e}")
                continue

        # Sort by creation date (newest first)
        backups.sort(key=lambda x: x["created_at"], reverse=True)

        return backups

    async def get_backup(self, backup_id: str) -> Optional[Dict[str, Any]]:
        """
        Get backup metadata by ID.

        Args:
            backup_id: UUID of backup

        Returns:
            Backup metadata dict, or None if not found
        """
        backup_file = self.backup_dir / f"{backup_id}.json"

        if not backup_file.exists():
            return None

        try:
            with open(backup_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            now = datetime.now(timezone.utc)
            # Handle expires_at (None = never expires)
            expires_at_str = data.get("expires_at")
            if expires_at_str is None:
                is_expired = False  # Never expires
            else:
                expires_at = datetime.fromisoformat(expires_at_str)
                is_expired = now > expires_at

            return {
                "backup_id": data["backup_id"],
                "created_at": data["created_at"],
                "expires_at": expires_at_str,  # Can be None (never expires)
                "expired": is_expired,
                "event_count": data["event_count"],
                "metadata": data.get("metadata", {}),
            }

        except Exception as e:
            logger.warning(f"Failed to read backup {backup_id}: {e}")
            return None

    async def delete_backup(self, backup_id: str) -> bool:
        """
        Delete a specific backup.

        Args:
            backup_id: UUID of backup to delete

        Returns:
            True if deleted, False if not found
        """
        backup_file = self.backup_dir / f"{backup_id}.json"

        if not backup_file.exists():
            return False

        try:
            backup_file.unlink()
            logger.info(f"Backup {backup_id} deleted")
            return True
        except Exception as e:
            logger.error(f"Failed to delete backup {backup_id}: {e}")
            return False

    async def cleanup_expired_backups(self) -> int:
        """
        Delete all expired backups.

        Returns:
            Number of backups deleted
        """
        deleted_count = 0
        now = datetime.now(timezone.utc)

        for backup_file in self.backup_dir.glob("*.json"):
            try:
                with open(backup_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # Skip backups that never expire (expires_at=None)
                expires_at_str = data.get("expires_at")
                if expires_at_str is None:
                    continue  # Never expires, skip

                expires_at = datetime.fromisoformat(expires_at_str)

                if now > expires_at:
                    backup_file.unlink()
                    deleted_count += 1
                    logger.debug(f"Deleted expired backup: {data['backup_id']}")

            except Exception as e:
                logger.warning(f"Failed to process backup {backup_file}: {e}")
                continue

        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} expired backups")

        return deleted_count

    def set_retention_days(self, retention_days: int) -> None:
        """
        Update backup retention period.

        Args:
            retention_days: Days until backup expires (0 = never expire)

        Raises:
            ValueError: If retention_days is invalid
        """
        if retention_days < BACKUP_RETENTION_NEVER:
            raise ValueError("retention_days must be >= 0")
        if retention_days > MAX_BACKUP_RETENTION_DAYS and retention_days != BACKUP_RETENTION_NEVER:
            raise ValueError(f"retention_days must be <= {MAX_BACKUP_RETENTION_DAYS} or 0 (never)")

        self.retention_days = retention_days
        logger.info(
            f"Backup retention updated to {retention_days} days ({'never expires' if retention_days == 0 else 'auto-expire'})"
        )

    def get_retention_config(self) -> Dict[str, Any]:
        """
        Get current backup retention configuration.

        Returns:
            Dict with retention_days, max_backups, and max_retention_days
        """
        return {
            "retention_days": self.retention_days,
            "max_backups": DEFAULT_BACKUP_CONFIG["max_backups"],
            "max_retention_days": MAX_BACKUP_RETENTION_DAYS,
            "never_expire_value": BACKUP_RETENTION_NEVER,
        }
