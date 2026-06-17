"""
Maintenance Cleanup Jobs (Data-Safe Version)

Provides cleanup jobs with comprehensive safety features:
- Dry-Run Mode (default: enabled)
- Batch Processing (prevents DB locks)
- Safety Limits (max records per run)
- Transparency (detailed logging)
- Rollback on errors
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import MaintenanceSettings
from src.core.logging_config import get_logger
from src.db.models.actuator import ActuatorHistory
from src.db.models.esp_heartbeat import ESPHeartbeatLog
from src.db.models.sensor import SensorData

logger = get_logger(__name__)


class SensorDataCleanup:
    """
    Sensor Data Cleanup Job mit Safety-Features

    Features:
    - Dry-Run Mode (zählt nur, löscht nicht)
    - Batch-Processing (verhindert DB-Lock)
    - Safety-Limits (Max Records pro Run)
    - Transparency (loggt was gelöscht wird)
    - Rollback bei Fehlern
    """

    def __init__(self, session: AsyncSession, settings: MaintenanceSettings):
        self.session = session
        self.settings = settings
        self.logger = get_logger(f"{__name__}.SensorDataCleanup")

    async def execute(self) -> Dict[str, Any]:
        """
        Führt Sensor Data Cleanup aus

        Returns:
            dict: {
                "dry_run": bool,
                "records_found": int,
                "records_deleted": int,
                "batches_processed": int,
                "cutoff_date": str,
                "duration_seconds": float,
                "status": str
            }
        """
        # ────────────────────────────────────────────────────
        # SAFETY CHECK 1: Ist Cleanup aktiviert?
        # ────────────────────────────────────────────────────
        if not self.settings.sensor_data_retention_enabled:
            self.logger.info(
                "Sensor data cleanup is DISABLED. "
                "Set SENSOR_DATA_RETENTION_ENABLED=true to activate."
            )
            return {
                "dry_run": False,
                "records_found": 0,
                "records_deleted": 0,
                "batches_processed": 0,
                "cutoff_date": None,
                "duration_seconds": 0,
                "status": "disabled",
            }

        start_time = datetime.now(timezone.utc)
        dry_run = self.settings.sensor_data_cleanup_dry_run
        retention_days = self.settings.sensor_data_retention_days
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)

        # ────────────────────────────────────────────────────
        # PHASE 1: Zähle zu löschende Records
        # ────────────────────────────────────────────────────
        total_records_result = await self.session.execute(select(func.count(SensorData.id)))
        total_records = total_records_result.scalar() or 0

        records_to_delete_result = await self.session.execute(
            select(func.count(SensorData.id)).where(SensorData.timestamp < cutoff_date)
        )
        records_to_delete = records_to_delete_result.scalar() or 0

        if records_to_delete == 0:
            self.logger.info(
                f"No sensor data older than {cutoff_date.date()} found. " "Cleanup not needed."
            )
            return {
                "dry_run": dry_run,
                "records_found": 0,
                "records_deleted": 0,
                "batches_processed": 0,
                "cutoff_date": cutoff_date.isoformat(),
                "duration_seconds": 0,
                "status": "nothing_to_delete",
            }

        # ────────────────────────────────────────────────────
        # SAFETY CHECK 2: Zu viele Records?
        # ────────────────────────────────────────────────────
        deletion_percent = (records_to_delete / total_records * 100) if total_records > 0 else 0

        if deletion_percent > self.settings.cleanup_alert_threshold_percent:
            self.logger.warning(
                f"⚠️  CLEANUP ALERT: {records_to_delete:,} records ({deletion_percent:.1f}%) "
                f"will be deleted! Cutoff: {cutoff_date.date()}"
            )

        if records_to_delete > self.settings.cleanup_max_records_per_run:
            self.logger.error(
                f"❌ CLEANUP ABORTED: {records_to_delete:,} records exceeds "
                f"safety limit ({self.settings.cleanup_max_records_per_run:,}). "
                "Increase CLEANUP_MAX_RECORDS_PER_RUN or reduce RETENTION_DAYS."
            )
            return {
                "dry_run": dry_run,
                "records_found": records_to_delete,
                "records_deleted": 0,
                "batches_processed": 0,
                "cutoff_date": cutoff_date.isoformat(),
                "duration_seconds": 0,
                "status": "aborted_safety_limit",
            }

        # ────────────────────────────────────────────────────
        # PHASE 2: Dry-Run oder echte Deletion?
        # ────────────────────────────────────────────────────
        if dry_run:
            self.logger.warning(
                f"🔍 DRY-RUN MODE: Would delete {records_to_delete:,} records "
                f"older than {cutoff_date.date()}. Set SENSOR_DATA_CLEANUP_DRY_RUN=false "
                "to actually delete."
            )
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            return {
                "dry_run": True,
                "records_found": records_to_delete,
                "records_deleted": 0,
                "batches_processed": 0,
                "cutoff_date": cutoff_date.isoformat(),
                "duration_seconds": duration,
                "status": "dry_run",
            }

        # ────────────────────────────────────────────────────
        # PHASE 3: Batch-Deletion
        # ────────────────────────────────────────────────────
        batch_size = self.settings.sensor_data_cleanup_batch_size
        max_batches = self.settings.sensor_data_cleanup_max_batches

        total_deleted = 0
        batches_processed = 0

        self.logger.info(
            f"Starting sensor data cleanup: {records_to_delete:,} records to delete "
            f"(cutoff: {cutoff_date.date()})"
        )

        while batches_processed < max_batches:
            try:
                # Find IDs to delete (batch)
                stmt = (
                    select(SensorData.id)
                    .where(SensorData.timestamp < cutoff_date)
                    .limit(batch_size)
                )
                result = await self.session.execute(stmt)
                batch_ids = [row[0] for row in result.fetchall()]

                if not batch_ids:
                    break  # Keine Records mehr

                # Delete batch
                delete_stmt = delete(SensorData).where(SensorData.id.in_(batch_ids))
                delete_result = await self.session.execute(delete_stmt)
                deleted_count = delete_result.rowcount
                await self.session.commit()

                total_deleted += deleted_count
                batches_processed += 1

                self.logger.debug(
                    f"Batch {batches_processed}: Deleted {deleted_count} records "
                    f"({total_deleted:,}/{records_to_delete:,})"
                )

                if deleted_count < batch_size:
                    break  # Letzter Batch

            except Exception as e:
                self.logger.error(f"Error in batch {batches_processed}: {e}", exc_info=True)
                await self.session.rollback()
                break

        duration = (datetime.now(timezone.utc) - start_time).total_seconds()

        self.logger.info(
            f"✅ Sensor data cleanup completed: {total_deleted:,} records deleted "
            f"in {batches_processed} batches ({duration:.2f}s)"
        )

        return {
            "dry_run": False,
            "records_found": records_to_delete,
            "records_deleted": total_deleted,
            "batches_processed": batches_processed,
            "cutoff_date": cutoff_date.isoformat(),
            "duration_seconds": duration,
            "status": "success",
        }


class CommandHistoryCleanup:
    """
    Actuator Command History Cleanup Job

    Analog zu SensorDataCleanup mit gleichen Safety-Features
    """

    def __init__(self, session: AsyncSession, settings: MaintenanceSettings):
        self.session = session
        self.settings = settings
        self.logger = get_logger(f"{__name__}.CommandHistoryCleanup")

    async def execute(self) -> Dict[str, Any]:
        """Führt Command History Cleanup aus (analog zu SensorDataCleanup)"""

        if not self.settings.command_history_retention_enabled:
            self.logger.info(
                "Command history cleanup is DISABLED. "
                "Set COMMAND_HISTORY_RETENTION_ENABLED=true to activate."
            )
            return {
                "dry_run": False,
                "records_found": 0,
                "records_deleted": 0,
                "batches_processed": 0,
                "cutoff_date": None,
                "duration_seconds": 0,
                "status": "disabled",
            }

        start_time = datetime.now(timezone.utc)
        dry_run = self.settings.command_history_cleanup_dry_run
        retention_days = self.settings.command_history_retention_days
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)

        # Count total and records to delete
        total_records_result = await self.session.execute(select(func.count(ActuatorHistory.id)))
        total_records = total_records_result.scalar() or 0

        records_to_delete_result = await self.session.execute(
            select(func.count(ActuatorHistory.id)).where(ActuatorHistory.timestamp < cutoff_date)
        )
        records_to_delete = records_to_delete_result.scalar() or 0

        if records_to_delete == 0:
            self.logger.info(
                f"No command history older than {cutoff_date.date()} found. " "Cleanup not needed."
            )
            return {
                "dry_run": dry_run,
                "records_found": 0,
                "records_deleted": 0,
                "batches_processed": 0,
                "cutoff_date": cutoff_date.isoformat(),
                "duration_seconds": 0,
                "status": "nothing_to_delete",
            }

        # Safety checks
        deletion_percent = (records_to_delete / total_records * 100) if total_records > 0 else 0

        if deletion_percent > self.settings.cleanup_alert_threshold_percent:
            self.logger.warning(
                f"⚠️  CLEANUP ALERT: {records_to_delete:,} records ({deletion_percent:.1f}%) "
                f"will be deleted! Cutoff: {cutoff_date.date()}"
            )

        if records_to_delete > self.settings.cleanup_max_records_per_run:
            self.logger.error(
                f"❌ CLEANUP ABORTED: {records_to_delete:,} records exceeds "
                f"safety limit ({self.settings.cleanup_max_records_per_run:,})."
            )
            return {
                "dry_run": dry_run,
                "records_found": records_to_delete,
                "records_deleted": 0,
                "batches_processed": 0,
                "cutoff_date": cutoff_date.isoformat(),
                "duration_seconds": 0,
                "status": "aborted_safety_limit",
            }

        # Dry-Run check
        if dry_run:
            self.logger.warning(
                f"🔍 DRY-RUN MODE: Would delete {records_to_delete:,} records "
                f"older than {cutoff_date.date()}. Set COMMAND_HISTORY_CLEANUP_DRY_RUN=false "
                "to actually delete."
            )
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            return {
                "dry_run": True,
                "records_found": records_to_delete,
                "records_deleted": 0,
                "batches_processed": 0,
                "cutoff_date": cutoff_date.isoformat(),
                "duration_seconds": duration,
                "status": "dry_run",
            }

        # Batch deletion
        batch_size = self.settings.command_history_cleanup_batch_size
        max_batches = self.settings.command_history_cleanup_max_batches

        total_deleted = 0
        batches_processed = 0

        self.logger.info(
            f"Starting command history cleanup: {records_to_delete:,} records to delete "
            f"(cutoff: {cutoff_date.date()})"
        )

        while batches_processed < max_batches:
            try:
                stmt = (
                    select(ActuatorHistory.id)
                    .where(ActuatorHistory.timestamp < cutoff_date)
                    .limit(batch_size)
                )
                result = await self.session.execute(stmt)
                batch_ids = [row[0] for row in result.fetchall()]

                if not batch_ids:
                    break

                delete_stmt = delete(ActuatorHistory).where(ActuatorHistory.id.in_(batch_ids))
                delete_result = await self.session.execute(delete_stmt)
                deleted_count = delete_result.rowcount
                await self.session.commit()

                total_deleted += deleted_count
                batches_processed += 1

                self.logger.debug(
                    f"Batch {batches_processed}: Deleted {deleted_count} records "
                    f"({total_deleted:,}/{records_to_delete:,})"
                )

                if deleted_count < batch_size:
                    break

            except Exception as e:
                self.logger.error(f"Error in batch {batches_processed}: {e}", exc_info=True)
                await self.session.rollback()
                break

        duration = (datetime.now(timezone.utc) - start_time).total_seconds()

        self.logger.info(
            f"✅ Command history cleanup completed: {total_deleted:,} records deleted "
            f"in {batches_processed} batches ({duration:.2f}s)"
        )

        return {
            "dry_run": False,
            "records_found": records_to_delete,
            "records_deleted": total_deleted,
            "batches_processed": batches_processed,
            "cutoff_date": cutoff_date.isoformat(),
            "duration_seconds": duration,
            "status": "success",
        }


class OrphanedMocksCleanup:
    """
    Orphaned Mock ESPs Cleanup

    DEFAULT: Nur Warnings loggen, keine Deletion!
    User muss ORPHANED_MOCK_AUTO_DELETE=true setzen für echte Deletion.
    """

    def __init__(
        self,
        session: AsyncSession,
        scheduler: Any,  # CentralScheduler
        settings: MaintenanceSettings,
    ):
        self.session = session
        self.scheduler = scheduler
        self.settings = settings
        self.logger = get_logger(f"{__name__}.OrphanedMocksCleanup")

    async def execute(self) -> Dict[str, Any]:
        """
        Findet und behandelt orphaned Mocks

        Returns:
            dict: {
                "orphaned_found": int,
                "deleted": int,
                "warned": int,
                "status": str
            }
        """
        if not self.settings.orphaned_mock_cleanup_enabled:
            return {"status": "disabled", "orphaned_found": 0, "deleted": 0, "warned": 0}

        from src.db.repositories import ESPRepository

        orphaned_count = 0
        deleted_count = 0
        warned_count = 0

        esp_repo = ESPRepository(self.session)

        # ────────────────────────────────────────────────────
        # Case 1: Running state aber kein Job im Scheduler
        # ────────────────────────────────────────────────────
        running_mocks = await esp_repo.get_running_mock_devices()

        # Get SimulationScheduler to check active mocks
        try:
            from src.services.simulation import get_simulation_scheduler

            sim_scheduler = get_simulation_scheduler()
        except RuntimeError:
            sim_scheduler = None

        for device in running_mocks:
            # Check if mock is actually active in SimulationScheduler
            is_active = False
            if sim_scheduler:
                is_active = sim_scheduler.is_mock_active(device.device_id)

            if not is_active:
                orphaned_count += 1

                # Setze state auf stopped (kein Datenverlust)
                await esp_repo.update_simulation_state(device.device_id, "stopped")
                await self.session.commit()

                self.logger.warning(
                    f"⚠️  Orphaned Mock detected: {device.device_id} (ID: {device.id}) "
                    f"- State was 'running' but no active simulation found. "
                    "Set to 'stopped'."
                )
                warned_count += 1

        # ────────────────────────────────────────────────────
        # Case 2: Alte stopped Mocks (optional deletion)
        # ────────────────────────────────────────────────────
        cutoff_age = datetime.now(timezone.utc) - timedelta(
            hours=self.settings.orphaned_mock_age_hours
        )

        stopped_mocks = await esp_repo.get_all_mock_devices()
        old_stopped_count = 0

        for device in stopped_mocks:
            sim_state = device.device_metadata.get("simulation_state", "stopped")
            if sim_state == "stopped":
                updated_at = device.updated_at or device.created_at
                if updated_at:
                    # Make timezone-aware if naive (assume UTC for database values)
                    if updated_at.tzinfo is None:
                        updated_at = updated_at.replace(tzinfo=timezone.utc)
                    if updated_at < cutoff_age:
                        old_stopped_count += 1
                        if self.settings.orphaned_mock_auto_delete:
                            # AUTO-SOFT-DELETE AKTIVIERT (T02-Fix1)
                            device.deleted_at = datetime.now(timezone.utc)
                            device.deleted_by = "maintenance"
                            device.status = "deleted"
                            deleted_count += 1

                            self.logger.info(
                                f"🗑️  Soft-deleted old orphaned Mock: {device.device_id} "
                                f"(last updated: {updated_at.date()})"
                            )
                        else:
                            # NUR WARNEN (DEFAULT)
                            self.logger.warning(
                                f"⚠️  Old orphaned Mock found: {device.device_id} "
                                f"(last updated: {updated_at.date()}). "
                                "Set ORPHANED_MOCK_AUTO_DELETE=true to auto-delete."
                            )
                            warned_count += 1

        if deleted_count > 0:
            await self.session.commit()

        return {
            "status": "success",
            "orphaned_found": orphaned_count + old_stopped_count,
            "deleted": deleted_count,
            "warned": warned_count,
        }


class HeartbeatLogCleanup:
    """
    Heartbeat Log Cleanup Job

    NOTE: This cleanup is ENABLED by default (unlike other cleanups)
    because heartbeat logs are voluminous (1440 records/device/day).

    Default retention: 7 days
    Default dry_run: True (safety first)

    Features:
    - Dry-Run Mode (zählt nur, löscht nicht) - Default: True
    - Batch-Processing (verhindert DB-Lock)
    - Safety-Limits (Max Records pro Run)
    - Transparency (loggt was gelöscht wird)
    """

    def __init__(self, session: AsyncSession, settings: MaintenanceSettings):
        self.session = session
        self.settings = settings
        self.logger = get_logger(f"{__name__}.HeartbeatLogCleanup")

    async def execute(self) -> Dict[str, Any]:
        """
        Führt Heartbeat Log Cleanup aus

        Returns:
            dict: {
                "dry_run": bool,
                "records_found": int,
                "records_deleted": int,
                "batches_processed": int,
                "cutoff_date": str,
                "duration_seconds": float,
                "status": str
            }
        """
        # ────────────────────────────────────────────────────
        # SAFETY CHECK 1: Ist Cleanup aktiviert?
        # ────────────────────────────────────────────────────
        if not self.settings.heartbeat_log_retention_enabled:
            self.logger.info(
                "Heartbeat log cleanup is DISABLED. "
                "Set HEARTBEAT_LOG_RETENTION_ENABLED=true to activate."
            )
            return {
                "dry_run": False,
                "records_found": 0,
                "records_deleted": 0,
                "batches_processed": 0,
                "cutoff_date": None,
                "duration_seconds": 0,
                "status": "disabled",
            }

        start_time = datetime.now(timezone.utc)
        dry_run = self.settings.heartbeat_log_cleanup_dry_run
        retention_days = self.settings.heartbeat_log_retention_days
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)

        # ────────────────────────────────────────────────────
        # PHASE 1: Zähle zu löschende Records
        # ────────────────────────────────────────────────────
        total_records_result = await self.session.execute(select(func.count(ESPHeartbeatLog.id)))
        total_records = total_records_result.scalar() or 0

        records_to_delete_result = await self.session.execute(
            select(func.count(ESPHeartbeatLog.id)).where(ESPHeartbeatLog.timestamp < cutoff_date)
        )
        records_to_delete = records_to_delete_result.scalar() or 0

        if records_to_delete == 0:
            self.logger.info(
                f"No heartbeat logs older than {cutoff_date.date()} found. " "Cleanup not needed."
            )
            return {
                "dry_run": dry_run,
                "records_found": 0,
                "records_deleted": 0,
                "batches_processed": 0,
                "cutoff_date": cutoff_date.isoformat(),
                "duration_seconds": 0,
                "status": "nothing_to_delete",
            }

        # ────────────────────────────────────────────────────
        # PHASE 2: Dry-Run oder echte Deletion?
        # ────────────────────────────────────────────────────
        if dry_run:
            self.logger.warning(
                f"🔍 DRY-RUN MODE: Would delete {records_to_delete:,} heartbeat logs "
                f"older than {cutoff_date.date()}. Total records: {total_records:,}. "
                "Set HEARTBEAT_LOG_CLEANUP_DRY_RUN=false to actually delete."
            )
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            return {
                "dry_run": True,
                "records_found": records_to_delete,
                "records_deleted": 0,
                "batches_processed": 0,
                "cutoff_date": cutoff_date.isoformat(),
                "duration_seconds": duration,
                "status": "dry_run",
            }

        # ────────────────────────────────────────────────────
        # PHASE 3: Batch-Deletion
        # ────────────────────────────────────────────────────
        batch_size = self.settings.heartbeat_log_cleanup_batch_size
        max_batches = self.settings.heartbeat_log_cleanup_max_batches

        total_deleted = 0
        batches_processed = 0

        self.logger.info(
            f"Starting heartbeat log cleanup: {records_to_delete:,} records to delete "
            f"(cutoff: {cutoff_date.date()}, retention: {retention_days} days)"
        )

        while batches_processed < max_batches:
            try:
                # Find IDs to delete (batch)
                stmt = (
                    select(ESPHeartbeatLog.id)
                    .where(ESPHeartbeatLog.timestamp < cutoff_date)
                    .limit(batch_size)
                )
                result = await self.session.execute(stmt)
                batch_ids = [row[0] for row in result.fetchall()]

                if not batch_ids:
                    break  # Keine Records mehr

                # Delete batch
                delete_stmt = delete(ESPHeartbeatLog).where(ESPHeartbeatLog.id.in_(batch_ids))
                delete_result = await self.session.execute(delete_stmt)
                deleted_count = delete_result.rowcount
                await self.session.commit()

                total_deleted += deleted_count
                batches_processed += 1

                self.logger.debug(
                    f"Batch {batches_processed}: Deleted {deleted_count} heartbeat logs "
                    f"({total_deleted:,}/{records_to_delete:,})"
                )

                if deleted_count < batch_size:
                    break  # Letzter Batch

            except Exception as e:
                self.logger.error(f"Error in batch {batches_processed}: {e}", exc_info=True)
                await self.session.rollback()
                break

        duration = (datetime.now(timezone.utc) - start_time).total_seconds()

        self.logger.info(
            f"✅ Heartbeat log cleanup completed: {total_deleted:,} records deleted "
            f"in {batches_processed} batches ({duration:.2f}s)"
        )

        return {
            "dry_run": False,
            "records_found": records_to_delete,
            "records_deleted": total_deleted,
            "batches_processed": batches_processed,
            "cutoff_date": cutoff_date.isoformat(),
            "duration_seconds": duration,
            "status": "success",
        }
