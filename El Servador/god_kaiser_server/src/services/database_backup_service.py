"""
Database Backup Service (Phase A V5.1)

Full PostgreSQL backup via pg_dump subprocess.
Runs before cleanup jobs to ensure data safety.

Features:
- Compressed SQL backups (.sql.gz) via pg_dump
- Scheduled via CentralScheduler (default: daily 02:00)
- Configurable retention (default: 7 days, max 20 backups)
- Atomic write (temp file → rename) to prevent corruption
- REST API for manual backup/restore/download
- Prometheus metrics for monitoring

Usage:
    service = DatabaseBackupService(settings.backup)
    info = await service.create_backup()
    backups = await service.list_backups()

Phase: A — Grundsicherung
Priority: HIGH
Status: IMPLEMENTED
"""

import asyncio
import gzip
import os
import shutil
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.config import DatabaseBackupSettings
from ..core.logging_config import get_logger

logger = get_logger(__name__)

# Backup directory relative to god_kaiser_server/
DEFAULT_BACKUP_DIR = "backups/database"


class BackupInfo:
    """Metadata for a single backup file."""

    def __init__(
        self,
        backup_id: str,
        filename: str,
        filepath: Path,
        created_at: datetime,
        size_bytes: int,
        pg_version: Optional[str] = None,
        database: Optional[str] = None,
        duration_seconds: Optional[float] = None,
    ):
        self.backup_id = backup_id
        self.filename = filename
        self.filepath = filepath
        self.created_at = created_at
        self.size_bytes = size_bytes
        self.pg_version = pg_version
        self.database = database
        self.duration_seconds = duration_seconds

    def to_dict(self) -> Dict[str, Any]:
        return {
            "backup_id": self.backup_id,
            "filename": self.filename,
            "created_at": self.created_at.isoformat(),
            "size_bytes": self.size_bytes,
            "size_human": _human_size(self.size_bytes),
            "pg_version": self.pg_version,
            "database": self.database,
            "duration_seconds": self.duration_seconds,
        }


def _human_size(size_bytes: int) -> str:
    """Convert bytes to human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if abs(size_bytes) < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def _parse_backup_filename(filename: str) -> Optional[Dict[str, Any]]:
    """
    Parse backup filename to extract metadata.

    Expected format: backup_YYYYMMDD_HHMMSS.sql.gz
    """
    if not filename.startswith("backup_") or not filename.endswith(".sql.gz"):
        return None

    try:
        # backup_20260303_020000.sql.gz
        date_part = filename[7:-7]  # Remove "backup_" and ".sql.gz"
        dt = datetime.strptime(date_part, "%Y%m%d_%H%M%S")
        dt = dt.replace(tzinfo=timezone.utc)
        return {
            "backup_id": date_part,
            "created_at": dt,
        }
    except (ValueError, IndexError):
        return None


class DatabaseBackupService:
    """
    Service for creating and managing PostgreSQL database backups.

    Uses pg_dump subprocess for full database dumps.
    Backups are stored as compressed .sql.gz files.

    Constructor takes DatabaseBackupSettings (no DB session needed).
    """

    def __init__(self, backup_settings: DatabaseBackupSettings):
        self._settings = backup_settings
        self._restore_lock = asyncio.Lock()
        self._restore_preflight_tokens: Dict[str, Dict[str, Any]] = {}
        self._active_restore_run_id: Optional[str] = None

        # Resolve backup directory relative to god_kaiser_server/
        project_root = Path(__file__).parent.parent.parent  # god_kaiser_server/
        self._backup_dir = project_root / DEFAULT_BACKUP_DIR
        self._backup_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"DatabaseBackupService initialized. "
            f"backup_dir={self._backup_dir}, "
            f"enabled={self._settings.enabled}, "
            f"schedule={self._settings.hour:02d}:{self._settings.minute:02d}"
        )

    @property
    def backup_dir(self) -> Path:
        return self._backup_dir

    async def run_restore_preflight(self, backup_id: str) -> Dict[str, Any]:
        """
        Run mandatory preflight checks and issue one-time restore token.

        A restore operation is only allowed if a valid preflight token
        exists and is consumed by restore_backup().
        """
        backup = await self.get_backup(backup_id)
        if not backup:
            raise ValueError(f"Backup {backup_id} not found")

        if self._restore_lock.locked():
            raise RuntimeError("Another restore is already in progress")

        await self._check_psql()
        uncompressed_bytes = await self._verify_backup_integrity(backup.filepath)

        disk_usage = shutil.disk_usage(self._backup_dir)
        required_free = max(backup.size_bytes * 2, 50 * 1024 * 1024)
        if disk_usage.free < required_free:
            raise RuntimeError(
                "Insufficient free disk space for restore preflight: "
                f"required={required_free} bytes, free={disk_usage.free} bytes"
            )

        preflight_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc)
        expires_at = created_at + timedelta(minutes=5)
        self._restore_preflight_tokens[preflight_id] = {
            "backup_id": backup_id,
            "created_at": created_at,
            "expires_at": expires_at,
            "size_bytes": backup.size_bytes,
            "uncompressed_bytes": uncompressed_bytes,
        }

        return {
            "preflight_id": preflight_id,
            "backup_id": backup_id,
            "filename": backup.filename,
            "size_bytes": backup.size_bytes,
            "size_human": _human_size(backup.size_bytes),
            "uncompressed_bytes": uncompressed_bytes,
            "free_disk_bytes": disk_usage.free,
            "required_free_bytes": required_free,
            "created_at": created_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "status": "ready",
        }

    def get_restore_runtime_state(self) -> Dict[str, Any]:
        """Return current restore runtime state for transparency."""
        now = datetime.now(timezone.utc)
        tokens = 0
        for token_data in self._restore_preflight_tokens.values():
            if token_data["expires_at"] > now:
                tokens += 1

        return {
            "restore_in_progress": self._restore_lock.locked(),
            "active_restore_run_id": self._active_restore_run_id,
            "valid_preflight_tokens": tokens,
        }

    async def create_backup(self) -> BackupInfo:
        """
        Create a full PostgreSQL backup using pg_dump.

        Returns:
            BackupInfo with metadata about the created backup.

        Raises:
            RuntimeError: If pg_dump fails or is not available.
        """
        now = datetime.now(timezone.utc)
        backup_id = now.strftime("%Y%m%d_%H%M%S")
        filename = f"backup_{backup_id}.sql.gz"
        filepath = self._backup_dir / filename
        temp_filepath = self._backup_dir / f".tmp_{filename}"

        start_time = time.monotonic()

        try:
            # Check pg_dump availability
            await self._check_pg_dump()

            # Build pg_dump command
            cmd = [
                "pg_dump",
                f"--host={self._settings.pg_host}",
                f"--port={self._settings.pg_port}",
                f"--username={self._settings.pg_user}",
                f"--dbname={self._settings.pg_database}",
                "--format=plain",
                "--no-password",
                "--verbose",
            ]

            env = self._build_pg_env()

            logger.info(
                f"Starting database backup: {filename} "
                f"(host={self._settings.pg_host}:{self._settings.pg_port}, "
                f"db={self._settings.pg_database})"
            )

            stdout = await self._run_pg_dump_with_retries(cmd=cmd, env=env, max_attempts=3)

            # Compress and write to temp file
            with gzip.open(temp_filepath, "wb", compresslevel=6) as f:
                f.write(stdout)

            # Atomic rename: temp → final (prevents corrupt partial files)
            temp_filepath.rename(filepath)

            duration = time.monotonic() - start_time
            size_bytes = filepath.stat().st_size

            # Get pg_dump version for metadata
            pg_version = await self._get_pg_version()

            info = BackupInfo(
                backup_id=backup_id,
                filename=filename,
                filepath=filepath,
                created_at=now,
                size_bytes=size_bytes,
                pg_version=pg_version,
                database=self._settings.pg_database,
                duration_seconds=round(duration, 2),
            )

            logger.info(
                f"Database backup created successfully: {filename} "
                f"({_human_size(size_bytes)}, {duration:.1f}s)"
            )

            # Update Prometheus metrics
            _update_backup_metrics(success=True, size_bytes=size_bytes)

            return info

        except Exception as e:
            # Cleanup temp file on failure
            if temp_filepath.exists():
                try:
                    temp_filepath.unlink()
                except OSError:
                    pass

            _update_backup_metrics(success=False)
            logger.error(f"Database backup failed: {e}")
            raise

    async def list_backups(self) -> List[BackupInfo]:
        """
        List all available backups sorted by creation date (newest first).

        Returns:
            List of BackupInfo objects.
        """
        backups = []

        for filepath in self._backup_dir.glob("backup_*.sql.gz"):
            parsed = _parse_backup_filename(filepath.name)
            if not parsed:
                continue

            try:
                stat = filepath.stat()
                backups.append(
                    BackupInfo(
                        backup_id=parsed["backup_id"],
                        filename=filepath.name,
                        filepath=filepath,
                        created_at=parsed["created_at"],
                        size_bytes=stat.st_size,
                        database=self._settings.pg_database,
                    )
                )
            except OSError as e:
                logger.warning(f"Failed to stat backup file {filepath}: {e}")

        # Sort newest first
        backups.sort(key=lambda b: b.created_at, reverse=True)
        return backups

    async def get_backup(self, backup_id: str) -> Optional[BackupInfo]:
        """
        Get a specific backup by ID.

        Args:
            backup_id: Backup identifier (format: YYYYMMDD_HHMMSS)

        Returns:
            BackupInfo or None if not found.
        """
        filename = f"backup_{backup_id}.sql.gz"
        filepath = self._backup_dir / filename

        if not filepath.exists():
            return None

        parsed = _parse_backup_filename(filename)
        if not parsed:
            return None

        stat = filepath.stat()
        return BackupInfo(
            backup_id=parsed["backup_id"],
            filename=filename,
            filepath=filepath,
            created_at=parsed["created_at"],
            size_bytes=stat.st_size,
            database=self._settings.pg_database,
        )

    async def delete_backup(self, backup_id: str) -> bool:
        """
        Delete a specific backup.

        Args:
            backup_id: Backup identifier.

        Returns:
            True if deleted, False if not found.
        """
        filename = f"backup_{backup_id}.sql.gz"
        filepath = self._backup_dir / filename

        if not filepath.exists():
            return False

        try:
            filepath.unlink()
            logger.info(f"Backup deleted: {filename}")
            return True
        except OSError as e:
            logger.error(f"Failed to delete backup {filename}: {e}")
            return False

    async def cleanup_old_backups(self) -> Dict[str, Any]:
        """
        Remove backups older than max_age_days and excess backups beyond max_count.

        Returns:
            Cleanup statistics.
        """
        backups = await self.list_backups()
        deleted_age = 0
        deleted_count = 0
        cutoff = datetime.now(timezone.utc) - timedelta(days=self._settings.max_age_days)

        # Phase 1: Delete by age
        remaining = []
        for backup in backups:
            if backup.created_at < cutoff:
                try:
                    backup.filepath.unlink()
                    deleted_age += 1
                    logger.debug(f"Deleted old backup: {backup.filename}")
                except OSError as e:
                    logger.warning(f"Failed to delete old backup {backup.filename}: {e}")
                    remaining.append(backup)
            else:
                remaining.append(backup)

        # Phase 2: Delete by count (keep newest max_count)
        if len(remaining) > self._settings.max_count:
            excess = remaining[self._settings.max_count :]
            for backup in excess:
                try:
                    backup.filepath.unlink()
                    deleted_count += 1
                    logger.debug(f"Deleted excess backup: {backup.filename}")
                except OSError as e:
                    logger.warning(f"Failed to delete excess backup {backup.filename}: {e}")

        total_deleted = deleted_age + deleted_count
        if total_deleted > 0:
            logger.info(
                f"Backup cleanup: {deleted_age} by age, {deleted_count} by count "
                f"(max_age={self._settings.max_age_days}d, max_count={self._settings.max_count})"
            )

        return {
            "deleted_by_age": deleted_age,
            "deleted_by_count": deleted_count,
            "total_deleted": total_deleted,
            "remaining": len(remaining) - deleted_count,
        }

    async def restore_backup(
        self,
        backup_id: str,
        *,
        preflight_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Restore a database from backup using psql.

        WARNING: This replaces all current data!

        Args:
            backup_id: Backup identifier.

        Returns:
            Restore statistics.

        Raises:
            ValueError: If backup not found.
            RuntimeError: If restore fails.
        """
        if not preflight_id:
            raise RuntimeError("Restore preflight is required before restore execution")

        now = datetime.now(timezone.utc)
        token = self._restore_preflight_tokens.get(preflight_id)
        if not token:
            raise RuntimeError("Invalid or already consumed restore preflight token")
        if token["backup_id"] != backup_id:
            raise RuntimeError("Restore preflight token does not match backup_id")
        if token["expires_at"] <= now:
            self._restore_preflight_tokens.pop(preflight_id, None)
            raise RuntimeError("Restore preflight token expired. Run preflight again")
        if self._restore_lock.locked():
            raise RuntimeError("Another restore is already in progress")

        backup = await self.get_backup(backup_id)
        if not backup:
            raise ValueError(f"Backup {backup_id} not found")

        start_time = time.monotonic()
        effective_run_id = run_id or str(uuid.uuid4())

        async with self._restore_lock:
            self._restore_preflight_tokens.pop(preflight_id, None)
            self._active_restore_run_id = effective_run_id
            try:
                logger.warning(
                    f"Starting database restore from backup: {backup.filename} "
                    f"(run_id={effective_run_id})"
                )

                # Decompress backup
                with gzip.open(backup.filepath, "rb") as f:
                    sql_content = f.read()

                # Build psql command
                cmd = [
                    "psql",
                    f"--host={self._settings.pg_host}",
                    f"--port={self._settings.pg_port}",
                    f"--username={self._settings.pg_user}",
                    f"--dbname={self._settings.pg_database}",
                    "--no-password",
                    "--single-transaction",
                ]

                env = self._build_pg_env()

                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                )

                stdout, stderr = await process.communicate(input=sql_content)

                duration = time.monotonic() - start_time

                if process.returncode != 0:
                    error_msg = stderr.decode("utf-8", errors="replace").strip()
                    logger.error(
                        f"Database restore failed (exit {process.returncode}): {error_msg}"
                    )
                    raise RuntimeError(
                        f"psql restore failed (exit {process.returncode}): {error_msg}"
                    )

                logger.info(
                    f"Database restored successfully from {backup.filename} "
                    f"({duration:.1f}s, run_id={effective_run_id})"
                )

                return {
                    "backup_id": backup_id,
                    "filename": backup.filename,
                    "size_bytes": backup.size_bytes,
                    "duration_seconds": round(duration, 2),
                    "status": "restored",
                    "run_id": effective_run_id,
                    "preflight_id": preflight_id,
                }
            finally:
                self._active_restore_run_id = None

    async def _check_pg_dump(self) -> None:
        """Verify pg_dump is available in the container."""
        try:
            process = await asyncio.create_subprocess_exec(
                "pg_dump",
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()
            if process.returncode != 0:
                raise RuntimeError("pg_dump returned non-zero exit code")
            logger.debug(f"pg_dump available: {stdout.decode().strip()}")
        except FileNotFoundError:
            raise RuntimeError(
                "pg_dump not found. Install postgresql-client in the Docker image. "
                "Add 'postgresql-client' to apt-get install in Dockerfile Runtime Stage."
            )

    def _build_pg_env(self) -> Dict[str, str]:
        """
        Build process env for pg_dump/psql.

        Preference order:
        1) DB_BACKUP_PGPASSFILE (Docker secret file)
        2) DB_BACKUP_PG_PASSWORD fallback
        """
        env = os.environ.copy()
        pgpassfile = self._settings.pgpassfile
        if pgpassfile:
            env["PGPASSFILE"] = pgpassfile
            env.pop("PGPASSWORD", None)
        else:
            env["PGPASSWORD"] = self._settings.pg_password
        return env

    @staticmethod
    def _is_auth_error(error_message: str) -> bool:
        lowered = error_message.lower()
        return "password authentication failed" in lowered or "no password supplied" in lowered

    async def _run_pg_dump_with_retries(
        self, *, cmd: List[str], env: Dict[str, str], max_attempts: int
    ) -> bytes:
        """
        Execute pg_dump with bounded retries and exponential backoff.
        """
        for attempt in range(1, max_attempts + 1):
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            stdout, stderr = await process.communicate()
            if process.returncode == 0:
                return stdout

            error_msg = stderr.decode("utf-8", errors="replace").strip()
            if self._is_auth_error(error_msg):
                logger.error(
                    "backup_auth_failure attempt=%s max_attempts=%s host=%s db=%s error=%s",
                    attempt,
                    max_attempts,
                    self._settings.pg_host,
                    self._settings.pg_database,
                    error_msg,
                )
            else:
                logger.warning(
                    "backup_pg_dump_failed attempt=%s max_attempts=%s host=%s db=%s error=%s",
                    attempt,
                    max_attempts,
                    self._settings.pg_host,
                    self._settings.pg_database,
                    error_msg,
                )

            if attempt < max_attempts:
                await asyncio.sleep(2 ** (attempt - 1))
                continue

            raise RuntimeError(f"pg_dump failed (exit {process.returncode}): {error_msg}")

        # Defensive fallback; loop always returns or raises.
        raise RuntimeError("pg_dump failed with unknown retry state")

    async def _get_pg_version(self) -> Optional[str]:
        """Get pg_dump version string."""
        try:
            process = await asyncio.create_subprocess_exec(
                "pg_dump",
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()
            if process.returncode == 0:
                return stdout.decode().strip()
        except Exception:
            pass
        return None

    async def _check_psql(self) -> None:
        """Verify psql is available in the runtime environment."""
        try:
            process = await asyncio.create_subprocess_exec(
                "psql",
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()
            if process.returncode != 0:
                raise RuntimeError("psql returned non-zero exit code")
            logger.debug(f"psql available: {stdout.decode().strip()}")
        except FileNotFoundError:
            raise RuntimeError(
                "psql not found. Install postgresql-client in the Docker image. "
                "Add 'postgresql-client' to apt-get install in Dockerfile Runtime Stage."
            )

    async def _verify_backup_integrity(self, filepath: Path) -> int:
        """
        Validate gzip integrity and return uncompressed byte size.
        """
        if not filepath.exists():
            raise RuntimeError(f"Backup file missing: {filepath}")
        if filepath.stat().st_size <= 0:
            raise RuntimeError(f"Backup file empty: {filepath}")

        uncompressed_bytes = 0
        try:
            with gzip.open(filepath, "rb") as gz_file:
                while True:
                    chunk = gz_file.read(1024 * 1024)
                    if not chunk:
                        break
                    uncompressed_bytes += len(chunk)
        except OSError as exc:
            raise RuntimeError(f"Backup integrity check failed: {exc}") from exc

        if uncompressed_bytes <= 0:
            raise RuntimeError("Backup integrity check failed: empty SQL content")

        return uncompressed_bytes


# =============================================================================
# Prometheus Metrics
# =============================================================================


def _update_backup_metrics(success: bool, size_bytes: int = 0) -> None:
    """Update Prometheus backup metrics."""
    try:
        from ..core.metrics import (
            BACKUP_CREATED_TOTAL,
            BACKUP_FAILED_TOTAL,
            BACKUP_SIZE_BYTES,
            BACKUP_LAST_SUCCESS_TIMESTAMP,
        )

        if success:
            BACKUP_CREATED_TOTAL.inc()
            BACKUP_SIZE_BYTES.set(size_bytes)
            BACKUP_LAST_SUCCESS_TIMESTAMP.set(time.time())
        else:
            BACKUP_FAILED_TOTAL.inc()
    except (ImportError, AttributeError):
        # Metrics not yet defined — will be added below
        pass


# =============================================================================
# Dependency Injection
# =============================================================================

_backup_service: Optional["DatabaseBackupService"] = None


def get_database_backup_service() -> "DatabaseBackupService":
    """
    Get DatabaseBackupService instance (Dependency Injection).

    Returns:
        DatabaseBackupService instance

    Raises:
        RuntimeError: If service not initialized
    """
    global _backup_service
    if _backup_service is None:
        raise RuntimeError(
            "DatabaseBackupService not initialized. " "Call init_database_backup_service() first."
        )
    return _backup_service


def init_database_backup_service(
    backup_settings: DatabaseBackupSettings,
) -> "DatabaseBackupService":
    """
    Initialize DatabaseBackupService.

    Must be called during startup in main.py.

    Args:
        backup_settings: DatabaseBackupSettings from config

    Returns:
        Initialized DatabaseBackupService instance
    """
    global _backup_service

    if _backup_service is not None:
        logger.warning("DatabaseBackupService already initialized")
        return _backup_service

    _backup_service = DatabaseBackupService(backup_settings)
    return _backup_service
