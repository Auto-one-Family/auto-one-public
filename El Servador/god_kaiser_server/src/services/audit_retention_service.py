"""
Audit Log Retention Service

Manages automatic cleanup of old audit logs based on configurable policies.
Designed for industrial-grade systems with flexible retention rules.

Features:
- Configurable retention periods per severity level
- Batch deletion for performance (small and large systems)
- Statistics and reporting
- Frontend-controllable via SystemConfig

Configuration Keys (stored in SystemConfig):
- audit_retention.enabled: bool - Enable/disable auto-cleanup
- audit_retention.default_days: int - Default retention period in days
- audit_retention.severity_days: dict - Per-severity retention {critical: 365, error: 90, ...}
- audit_retention.max_records: int - Maximum records to keep (0 = unlimited)
- audit_retention.batch_size: int - Records to delete per batch operation
- audit_retention.last_cleanup: datetime - Last cleanup timestamp

Phase: Runtime Config Flow Implementation
Priority: MEDIUM
Status: IMPLEMENTED
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logging_config import get_logger
from ..db.models.audit_log import AuditLog, AuditSeverity
from ..db.models.enums import DataSource
from ..db.models.sensor import SensorData
from ..db.models.actuator import ActuatorHistory
from ..db.repositories.system_config_repo import SystemConfigRepository
from .audit_backup_service import AuditBackupService

logger = get_logger(__name__)


# Default retention configuration
DEFAULT_RETENTION_CONFIG = {
    "enabled": False,  # Safety-First: User muss explizit aktivieren
    "default_days": 30,
    "severity_days": {
        AuditSeverity.INFO: 30,
        AuditSeverity.WARNING: 90,
        AuditSeverity.ERROR: 365,
        AuditSeverity.CRITICAL: 0,  # 0 = never delete
    },
    "max_records": 0,  # 0 = unlimited, useful for small systems
    "batch_size": 1000,  # Records per deletion batch
    "preserve_emergency_stops": True,  # Never delete emergency stop events
}


class AuditRetentionService:
    """
    Service for managing audit log retention.

    Provides:
    - Configurable retention policies
    - Batch cleanup operations
    - Statistics and reporting
    - Integration with SystemConfig for frontend control

    Usage:
        service = AuditRetentionService(db)

        # Get current config
        config = await service.get_config()

        # Update config from frontend
        await service.set_config(default_days=60, severity_days={...})

        # Run cleanup
        result = await service.cleanup()

        # Get statistics
        stats = await service.get_statistics()
    """

    CONFIG_KEY_PREFIX = "audit_retention"

    def __init__(self, session: AsyncSession):
        """
        Initialize AuditRetentionService.

        Args:
            session: Async database session
        """
        self.session = session
        self.config_repo = SystemConfigRepository(session)
        self.backup_service = AuditBackupService(session)

    # =========================================================================
    # Configuration Management
    # =========================================================================

    async def get_config(self) -> Dict[str, Any]:
        """
        Get current retention configuration.

        Returns config from SystemConfig, falling back to defaults
        for any missing values.

        Returns:
            Dict with retention configuration
        """
        config = dict(DEFAULT_RETENTION_CONFIG)

        # Load from SystemConfig
        stored_config = await self.config_repo.get_by_key(f"{self.CONFIG_KEY_PREFIX}.config")

        if stored_config and isinstance(stored_config.config_value, dict):
            # Merge stored config with defaults
            stored = stored_config.config_value
            config["enabled"] = stored.get("enabled", config["enabled"])
            config["default_days"] = stored.get("default_days", config["default_days"])
            config["max_records"] = stored.get("max_records", config["max_records"])
            config["batch_size"] = stored.get("batch_size", config["batch_size"])
            config["preserve_emergency_stops"] = stored.get(
                "preserve_emergency_stops", config["preserve_emergency_stops"]
            )

            # Merge severity days
            if "severity_days" in stored:
                config["severity_days"].update(stored["severity_days"])

        # Load last cleanup timestamp
        last_cleanup = await self.config_repo.get_by_key(f"{self.CONFIG_KEY_PREFIX}.last_cleanup")
        if last_cleanup:
            config["last_cleanup"] = last_cleanup.config_value
        else:
            config["last_cleanup"] = None

        return config

    async def set_config(
        self,
        enabled: Optional[bool] = None,
        default_days: Optional[int] = None,
        severity_days: Optional[Dict[str, int]] = None,
        max_records: Optional[int] = None,
        batch_size: Optional[int] = None,
        preserve_emergency_stops: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Update retention configuration.

        Only provided values are updated; others remain unchanged.
        Validates input before saving.

        Args:
            enabled: Enable/disable auto-cleanup
            default_days: Default retention period (days)
            severity_days: Per-severity retention periods
            max_records: Maximum records to keep (0 = unlimited)
            batch_size: Records per deletion batch
            preserve_emergency_stops: Never delete emergency stop events

        Returns:
            Updated configuration dict

        Raises:
            ValueError: If validation fails
        """
        # Load current config
        current = await self.get_config()

        # Apply updates with validation
        if enabled is not None:
            current["enabled"] = bool(enabled)

        if default_days is not None:
            if default_days < 1:
                raise ValueError("default_days must be at least 1")
            if default_days > 3650:  # ~10 years max
                raise ValueError("default_days cannot exceed 3650 (10 years)")
            current["default_days"] = default_days

        if severity_days is not None:
            for sev, days in severity_days.items():
                if days < 0:
                    raise ValueError(
                        f"Retention for {sev} cannot be negative (use 0 for never delete)"
                    )
                if days > 3650:
                    raise ValueError(f"Retention for {sev} cannot exceed 3650 days")
            current["severity_days"].update(severity_days)

        if max_records is not None:
            if max_records < 0:
                raise ValueError("max_records cannot be negative")
            current["max_records"] = max_records

        if batch_size is not None:
            if batch_size < 100:
                raise ValueError("batch_size must be at least 100")
            if batch_size > 10000:
                raise ValueError("batch_size cannot exceed 10000")
            current["batch_size"] = batch_size

        if preserve_emergency_stops is not None:
            current["preserve_emergency_stops"] = bool(preserve_emergency_stops)

        # Save to SystemConfig
        await self.config_repo.set_config(
            config_key=f"{self.CONFIG_KEY_PREFIX}.config",
            config_value={
                "enabled": current["enabled"],
                "default_days": current["default_days"],
                "severity_days": current["severity_days"],
                "max_records": current["max_records"],
                "batch_size": current["batch_size"],
                "preserve_emergency_stops": current["preserve_emergency_stops"],
            },
            config_type="audit",
            description="Audit log retention policy configuration",
            is_secret=False,
        )

        logger.info(f"Audit retention config updated: {current}")
        return current

    # =========================================================================
    # Cleanup Operations
    # =========================================================================

    async def cleanup(
        self,
        dry_run: bool = False,
        create_backup: bool = True,
        user_id: Optional[str] = None,
        include_preview_events: bool = False,
        preview_limit: int = 20,
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        Run cleanup based on retention policy.

        Deletes old audit logs according to configured retention periods.
        Uses batch deletion for performance on large datasets.

        Args:
            dry_run: If True, calculate but don't delete (preview mode)
            create_backup: If True, create JSON backup before deletion
            user_id: Optional user ID for audit trail
            include_preview_events: If True, include event details in response (for UI preview)
            preview_limit: Maximum number of events to include in preview (default: 20)
            force: If True, run cleanup even if auto-retention is disabled (for manual cleanup)

        Returns:
            Dict with cleanup results:
            - deleted_count: Total records deleted (or would be deleted in dry_run)
            - deleted_by_severity: Count per severity level
            - duration_ms: Operation duration
            - dry_run: Whether this was a dry run
            - errors: Any errors encountered
            - retention_enabled: Whether auto-retention is enabled
            - backup_id: Backup ID if backup was created
            - preview_events: List of events (if include_preview_events=True)
            - preview_limited: True if more events exist than shown in preview
        """
        start_time = datetime.now(timezone.utc)
        config = await self.get_config()

        # IMPORTANT: For dry_run, ALWAYS calculate preview counts
        # regardless of enabled status. This allows users to see what
        # WOULD be deleted if they enable retention.
        # Only block ACTUAL deletion when disabled AND not forced (manual cleanup).
        # force=True allows manual cleanup even when auto-retention is disabled.
        if not config["enabled"] and not dry_run and not force:
            return {
                "deleted_count": 0,
                "deleted_by_severity": {},
                "duration_ms": 0,
                "dry_run": dry_run,
                "skipped": True,
                "retention_enabled": False,
                "reason": "Retention cleanup is disabled. Enable in retention settings first.",
            }

        results = {
            "deleted_count": 0,
            "deleted_by_severity": {},
            "duration_ms": 0,
            "dry_run": dry_run,
            "errors": [],
            "retention_enabled": config["enabled"],
            "backup_id": None,
            "preview_events": None,
            "preview_limited": False,
        }

        now = datetime.now(timezone.utc)
        batch_size = config["batch_size"]
        default_days = config["default_days"]

        # =====================================================================
        # PHASE 1: Count and optionally collect events to delete
        # =====================================================================

        # Collect all events that match deletion criteria (for backup)
        all_events_to_delete: List[AuditLog] = []
        # Collect events for preview (limited)
        preview_events: List[AuditLog] = []
        preview_events_needed = preview_limit if (dry_run and include_preview_events) else 0

        # Process each severity level
        # Use min(default_days, severity_days) so that default_days acts as
        # a MAXIMUM retention period. This allows users to set a global cap:
        # - default_days=30, severity_info=14 → use 14 (severity is stricter)
        # - default_days=1, severity_info=14 → use 1 (default is stricter/global cap)
        for severity, severity_retention in config["severity_days"].items():
            # 0 = never delete this severity
            if severity_retention == 0:
                continue
            retention_days = min(default_days, severity_retention)
            cutoff_date = now - timedelta(days=retention_days)

            try:
                # Build delete conditions
                conditions = [
                    AuditLog.severity == severity,
                    AuditLog.created_at < cutoff_date,
                ]

                # Preserve emergency stops if configured
                if config["preserve_emergency_stops"]:
                    conditions.append(AuditLog.event_type != "emergency_stop")

                if dry_run:
                    # Count what would be deleted
                    count_stmt = select(func.count(AuditLog.id)).where(and_(*conditions))
                    result = await self.session.execute(count_stmt)
                    count = result.scalar_one()

                    if count > 0:
                        results["deleted_by_severity"][severity] = count
                        results["deleted_count"] += count

                    # Fetch preview events if requested and we still need more
                    if include_preview_events and len(preview_events) < preview_events_needed:
                        remaining_needed = preview_events_needed - len(preview_events)
                        preview_stmt = (
                            select(AuditLog)
                            .where(and_(*conditions))
                            .order_by(AuditLog.created_at.desc())
                            .limit(remaining_needed)
                        )
                        preview_result = await self.session.execute(preview_stmt)
                        preview_events.extend(list(preview_result.scalars().all()))
                else:
                    # Step 1: Count ALL events to delete (no limit)
                    count_stmt = select(func.count(AuditLog.id)).where(and_(*conditions))
                    count_result = await self.session.execute(count_stmt)
                    count = count_result.scalar_one()

                    if count > 0:
                        results["deleted_by_severity"][severity] = count
                        results["deleted_count"] += count

                    # Step 2: Collect events for backup (with limit - OK for backup)
                    if create_backup and count > 0:
                        max_backup_events = batch_size * 10
                        events_stmt = (
                            select(AuditLog)
                            .where(and_(*conditions))
                            .order_by(AuditLog.created_at.asc())
                            .limit(max_backup_events)
                        )
                        events_result = await self.session.execute(events_stmt)
                        all_events_to_delete.extend(list(events_result.scalars().all()))

                    # Step 3: Delete ALL matching events (NO LIMIT)
                    if count > 0:
                        delete_stmt = delete(AuditLog).where(and_(*conditions))
                        delete_result = await self.session.execute(delete_stmt)
                        await self.session.flush()
                        actual_deleted = delete_result.rowcount
                        # Update with actual count from DB
                        results["deleted_by_severity"][severity] = actual_deleted
                        results["deleted_count"] = results["deleted_count"] - count + actual_deleted

            except Exception as e:
                error_msg = f"Error processing {severity} logs: {str(e)}"
                results["errors"].append(error_msg)
                logger.error(error_msg)

        # =====================================================================
        # PHASE 2: Create backup before deletion (if not dry_run)
        # =====================================================================

        if not dry_run and all_events_to_delete and create_backup:
            try:
                backup_metadata = {
                    "operation": "retention_cleanup",
                    "user_id": user_id,
                    "retention_config": {
                        "default_days": config["default_days"],
                        "severity_days": {str(k): v for k, v in config["severity_days"].items()},
                        "preserve_emergency_stops": config["preserve_emergency_stops"],
                    },
                    "timestamp": now.isoformat(),
                }
                backup_id = await self.backup_service.create_backup(
                    events=all_events_to_delete,
                    metadata=backup_metadata,
                )
                results["backup_id"] = backup_id
                logger.info(f"Backup created before cleanup: {backup_id}")
            except Exception as e:
                error_msg = f"Backup creation failed: {str(e)}"
                results["errors"].append(error_msg)
                logger.error(error_msg)
                # Continue with deletion even if backup fails (user opted for cleanup)

        # Apply max_records limit if configured
        if config["max_records"] > 0 and not dry_run:
            try:
                total_count = await self._get_total_count()

                if total_count > config["max_records"]:
                    excess = total_count - config["max_records"]

                    # Delete oldest records (preserving emergency stops if configured)
                    conditions = []
                    if config["preserve_emergency_stops"]:
                        conditions.append(AuditLog.event_type != "emergency_stop")

                    # Get oldest IDs to delete
                    oldest_stmt = (
                        select(AuditLog.id)
                        .where(and_(*conditions) if conditions else True)
                        .order_by(AuditLog.created_at.asc())
                        .limit(min(excess, batch_size))
                    )
                    oldest_result = await self.session.execute(oldest_stmt)
                    ids_to_delete = [row[0] for row in oldest_result.all()]

                    if ids_to_delete:
                        delete_stmt = delete(AuditLog).where(AuditLog.id.in_(ids_to_delete))
                        await self.session.execute(delete_stmt)
                        await self.session.flush()

                        results["deleted_count"] += len(ids_to_delete)
                        results["deleted_by_max_records"] = len(ids_to_delete)

            except Exception as e:
                error_msg = f"Error applying max_records limit: {str(e)}"
                results["errors"].append(error_msg)
                logger.error(error_msg)

        # Update last cleanup timestamp
        if not dry_run and results["deleted_count"] > 0:
            await self.config_repo.set_config(
                config_key=f"{self.CONFIG_KEY_PREFIX}.last_cleanup",
                config_value=now.isoformat(),
                config_type="audit",
                description="Last audit log cleanup timestamp",
                is_secret=False,
            )

        end_time = datetime.now(timezone.utc)
        results["duration_ms"] = int((end_time - start_time).total_seconds() * 1000)

        # =====================================================================
        # PHASE 4: Create audit trail entry for the cleanup operation
        # =====================================================================

        if not dry_run and results["deleted_count"] > 0:
            try:
                # Create audit log entry for this cleanup operation
                cleanup_audit = AuditLog(
                    event_type="audit_cleanup_executed",
                    severity=AuditSeverity.WARNING,  # Warning because data was deleted
                    source_type="user" if user_id else "system",
                    source_id=user_id or "scheduler",
                    status="success",
                    message=f"Audit log cleanup: {results['deleted_count']} events deleted",
                    details={
                        "deleted_count": results["deleted_count"],
                        "deleted_by_severity": {
                            str(k): v for k, v in results["deleted_by_severity"].items()
                        },
                        "backup_id": results.get("backup_id"),
                        "retention_config": {
                            "default_days": config["default_days"],
                            "severity_days": {
                                str(k): v for k, v in config["severity_days"].items()
                            },
                            "preserve_emergency_stops": config["preserve_emergency_stops"],
                        },
                        "duration_ms": results["duration_ms"],
                    },
                )
                self.session.add(cleanup_audit)
                await self.session.flush()
                logger.debug("Audit trail created for cleanup operation")
            except Exception as e:
                # Non-critical: log but don't fail the cleanup
                logger.warning(f"Failed to create audit trail for cleanup: {e}")

            logger.info(
                f"Audit cleanup completed: {results['deleted_count']} records deleted "
                f"in {results['duration_ms']}ms (backup: {results.get('backup_id')})"
            )

        # =====================================================================
        # PHASE 5: Add preview events to result (if dry_run and requested)
        # =====================================================================

        if dry_run and include_preview_events and preview_events:
            # Sort preview events by timestamp (newest first)
            preview_events.sort(key=lambda e: e.created_at, reverse=True)
            # Limit to preview_limit
            preview_events = preview_events[:preview_limit]

            results["preview_events"] = [
                {
                    "id": str(e.id),  # UUID to string
                    "event_type": e.event_type,
                    "severity": e.severity,
                    "message": e.message or "",
                    "device_id": e.source_id,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                }
                for e in preview_events
            ]
            results["preview_limited"] = results["deleted_count"] > len(preview_events)

        return results

    # =========================================================================
    # Statistics
    # =========================================================================

    async def get_statistics(
        self,
        error_cutoff_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Get audit log statistics for dashboard display.

        Args:
            error_cutoff_time: If provided, count errors/criticals only after this time.
                              Other statistics (total, event_type, etc.) are always all-time.

        Returns:
            Dict with statistics:
            - total_count: Total audit log entries (all-time)
            - count_by_severity: Count per severity level (time-filtered if cutoff provided)
            - count_by_event_type: Count per event type (all-time)
            - oldest_entry: Timestamp of oldest entry
            - newest_entry: Timestamp of newest entry
            - storage_estimate_mb: Estimated storage usage
            - retention_config: Current retention configuration
        """
        stats: Dict[str, Any] = {}

        # Total count (always all-time)
        stats["total_count"] = await self._get_total_count()

        # Count by severity (with optional time filter)
        severity_stmt = select(
            AuditLog.severity,
            func.count(AuditLog.id).label("count"),
        )

        # Apply time filter if provided
        if error_cutoff_time is not None:
            severity_stmt = severity_stmt.where(AuditLog.created_at >= error_cutoff_time)

        severity_stmt = severity_stmt.group_by(AuditLog.severity)
        severity_result = await self.session.execute(severity_stmt)
        stats["count_by_severity"] = {row.severity: row.count for row in severity_result.all()}

        # Count by event type (top 10)
        event_type_stmt = (
            select(
                AuditLog.event_type,
                func.count(AuditLog.id).label("count"),
            )
            .group_by(AuditLog.event_type)
            .order_by(func.count(AuditLog.id).desc())
            .limit(10)
        )
        event_type_result = await self.session.execute(event_type_stmt)
        stats["count_by_event_type"] = {
            row.event_type: row.count for row in event_type_result.all()
        }

        # Oldest and newest entries
        if stats["total_count"] > 0:
            oldest_stmt = select(func.min(AuditLog.created_at))
            oldest_result = await self.session.execute(oldest_stmt)
            oldest = oldest_result.scalar_one_or_none()
            stats["oldest_entry"] = oldest.isoformat() if oldest else None

            newest_stmt = select(func.max(AuditLog.created_at))
            newest_result = await self.session.execute(newest_stmt)
            newest = newest_result.scalar_one_or_none()
            stats["newest_entry"] = newest.isoformat() if newest else None
        else:
            stats["oldest_entry"] = None
            stats["newest_entry"] = None

        # Storage estimate (rough calculation: ~500 bytes per record)
        stats["storage_estimate_mb"] = round(stats["total_count"] * 500 / (1024 * 1024), 2)

        # Current retention config
        stats["retention_config"] = await self.get_config()

        # Calculate what would be deleted
        dry_run_result = await self.cleanup(dry_run=True)
        stats["pending_cleanup_count"] = dry_run_result["deleted_count"]
        stats["pending_cleanup_by_severity"] = dry_run_result.get("deleted_by_severity", {})

        return stats

    async def _get_total_count(self) -> int:
        """Get total audit log count."""
        stmt = select(func.count(AuditLog.id))
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def get_next_scheduled_cleanup_time(self) -> Optional[datetime]:
        """
        Calculate when the next scheduled auto-cleanup will run.

        Auto-cleanup runs daily at 03:00 UTC.

        Returns:
            Next scheduled cleanup time, or None if auto-cleanup is disabled
        """
        config = await self.get_config()

        if not config.get("enabled", False):
            return None

        now = datetime.now(timezone.utc)

        # Next 03:00 UTC
        next_run = now.replace(hour=3, minute=0, second=0, microsecond=0)

        # If today's 03:00 has already passed, schedule for tomorrow
        if next_run <= now:
            next_run += timedelta(days=1)

        return next_run

    # =========================================================================
    # Test Data Cleanup (Phase 6)
    # =========================================================================

    # Retention policies for test data (shorter than production)
    TEST_DATA_RETENTION = {
        DataSource.TEST: timedelta(hours=24),  # 24 hours
        DataSource.MOCK: timedelta(days=7),  # 7 days
        DataSource.SIMULATION: timedelta(days=30),  # 30 days
        DataSource.PRODUCTION: None,  # Never auto-delete
    }

    async def cleanup_test_sensor_data(
        self,
        dry_run: bool = False,
        include_mock: bool = True,
        include_simulation: bool = True,
    ) -> Dict[str, Any]:
        """
        Delete old test/mock/simulation sensor data.

        Cleans up sensor data based on data_source field and retention periods.
        Production data is never deleted.

        Args:
            dry_run: If True, calculate but don't delete
            include_mock: Include mock data in cleanup
            include_simulation: Include simulation data in cleanup

        Returns:
            Dict with cleanup results per data source
        """
        start_time = datetime.now(timezone.utc)
        results = {
            "deleted": {},
            "total_deleted": 0,
            "dry_run": dry_run,
            "errors": [],
        }

        now = datetime.now(timezone.utc)

        for source, retention in self.TEST_DATA_RETENTION.items():
            # Skip production data (never auto-delete)
            if retention is None:
                continue

            # Check if this source should be included
            if source == DataSource.MOCK and not include_mock:
                continue
            if source == DataSource.SIMULATION and not include_simulation:
                continue

            cutoff = now - retention

            try:
                conditions = [
                    SensorData.data_source == source.value,
                    SensorData.timestamp < cutoff,
                ]

                if dry_run:
                    # Count what would be deleted
                    count_stmt = select(func.count(SensorData.id)).where(and_(*conditions))
                    result = await self.session.execute(count_stmt)
                    count = result.scalar_one()
                else:
                    # Delete records
                    delete_stmt = delete(SensorData).where(and_(*conditions))
                    result = await self.session.execute(delete_stmt)
                    count = result.rowcount
                    await self.session.flush()

                if count > 0:
                    results["deleted"][source.value] = count
                    results["total_deleted"] += count

            except Exception as e:
                error_msg = f"Error cleaning up {source.value} sensor data: {str(e)}"
                results["errors"].append(error_msg)
                logger.error(error_msg)

        end_time = datetime.now(timezone.utc)
        results["duration_ms"] = int((end_time - start_time).total_seconds() * 1000)

        if not dry_run and results["total_deleted"] > 0:
            logger.info(
                f"Test sensor data cleanup: {results['total_deleted']} records deleted "
                f"in {results['duration_ms']}ms"
            )

        return results

    async def cleanup_test_actuator_data(
        self,
        dry_run: bool = False,
        include_mock: bool = True,
        include_simulation: bool = True,
    ) -> Dict[str, Any]:
        """
        Delete old test/mock/simulation actuator history.

        Cleans up actuator history based on data_source field and retention periods.
        Production data is never deleted.

        Args:
            dry_run: If True, calculate but don't delete
            include_mock: Include mock data in cleanup
            include_simulation: Include simulation data in cleanup

        Returns:
            Dict with cleanup results per data source
        """
        start_time = datetime.now(timezone.utc)
        results = {
            "deleted": {},
            "total_deleted": 0,
            "dry_run": dry_run,
            "errors": [],
        }

        now = datetime.now(timezone.utc)

        for source, retention in self.TEST_DATA_RETENTION.items():
            # Skip production data (never auto-delete)
            if retention is None:
                continue

            # Check if this source should be included
            if source == DataSource.MOCK and not include_mock:
                continue
            if source == DataSource.SIMULATION and not include_simulation:
                continue

            cutoff = now - retention

            try:
                conditions = [
                    ActuatorHistory.data_source == source.value,
                    ActuatorHistory.timestamp < cutoff,
                ]

                if dry_run:
                    # Count what would be deleted
                    count_stmt = select(func.count(ActuatorHistory.id)).where(and_(*conditions))
                    result = await self.session.execute(count_stmt)
                    count = result.scalar_one()
                else:
                    # Delete records
                    delete_stmt = delete(ActuatorHistory).where(and_(*conditions))
                    result = await self.session.execute(delete_stmt)
                    count = result.rowcount
                    await self.session.flush()

                if count > 0:
                    results["deleted"][source.value] = count
                    results["total_deleted"] += count

            except Exception as e:
                error_msg = f"Error cleaning up {source.value} actuator history: {str(e)}"
                results["errors"].append(error_msg)
                logger.error(error_msg)

        end_time = datetime.now(timezone.utc)
        results["duration_ms"] = int((end_time - start_time).total_seconds() * 1000)

        if not dry_run and results["total_deleted"] > 0:
            logger.info(
                f"Test actuator history cleanup: {results['total_deleted']} records deleted "
                f"in {results['duration_ms']}ms"
            )

        return results

    async def run_full_test_cleanup(
        self,
        dry_run: bool = False,
        include_mock: bool = True,
        include_simulation: bool = True,
    ) -> Dict[str, Any]:
        """
        Run complete test data cleanup (sensor data + actuator history).

        Combines cleanup of sensor data and actuator history in one operation.
        Production data is never affected.

        Args:
            dry_run: If True, calculate but don't delete
            include_mock: Include mock data in cleanup
            include_simulation: Include simulation data in cleanup

        Returns:
            Combined cleanup results
        """
        start_time = datetime.now(timezone.utc)

        sensor_result = await self.cleanup_test_sensor_data(
            dry_run=dry_run,
            include_mock=include_mock,
            include_simulation=include_simulation,
        )

        actuator_result = await self.cleanup_test_actuator_data(
            dry_run=dry_run,
            include_mock=include_mock,
            include_simulation=include_simulation,
        )

        # Commit changes
        if not dry_run:
            await self.session.commit()

        end_time = datetime.now(timezone.utc)

        return {
            "sensor_data": sensor_result,
            "actuator_history": actuator_result,
            "total_deleted": (sensor_result["total_deleted"] + actuator_result["total_deleted"]),
            "dry_run": dry_run,
            "include_mock": include_mock,
            "include_simulation": include_simulation,
            "duration_ms": int((end_time - start_time).total_seconds() * 1000),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
