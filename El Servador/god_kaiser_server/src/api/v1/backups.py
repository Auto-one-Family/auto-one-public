"""
Database Backup REST API Endpoints (Phase A V5.1)

Provides admin-only endpoints for PostgreSQL backup management:
- POST   /v1/backups/database/create        - Trigger immediate backup
- GET    /v1/backups/database/list           - List all backups
- GET    /v1/backups/database/{id}/download  - Download backup file
- DELETE /v1/backups/database/{id}           - Delete single backup
- POST   /v1/backups/database/{id}/restore   - Restore from backup (confirm required)
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from ...core.logging_config import get_logger
from ...core.scheduler import get_central_scheduler
from ...db.models.audit_log import AuditSeverity, AuditSourceType
from ...db.repositories.audit_log_repo import AuditLogRepository
from ...db.session import dispose_engine, get_session
from ...services.database_backup_service import get_database_backup_service
from ...services.maintenance.service import get_maintenance_service
from ...websocket.manager import WebSocketManager
from ..deps import AdminUser

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/backups", tags=["backups"])


# --- Response Models ---


class BackupInfoResponse(BaseModel):
    backup_id: str
    filename: str
    created_at: str
    size_bytes: int
    size_human: str
    pg_version: Optional[str] = None
    database: Optional[str] = None
    duration_seconds: Optional[float] = None


class BackupListResponse(BaseModel):
    status: str = "success"
    count: int
    backups: List[BackupInfoResponse]


class BackupCreateResponse(BaseModel):
    status: str = "success"
    message: str
    backup: BackupInfoResponse


class BackupDeleteResponse(BaseModel):
    status: str = "success"
    message: str
    backup_id: str


class BackupRestoreResponse(BaseModel):
    status: str = "success"
    message: str
    backup_id: str
    filename: str
    duration_seconds: float
    run_id: str
    preflight_id: str


async def _broadcast_restore_status(
    run_id: str,
    phase: str,
    status: str,
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    """Broadcast restore status via system_event websocket channel."""
    try:
        ws_manager = await WebSocketManager.get_instance()
        await ws_manager.broadcast(
            "system_event",
            {
                "event": "database_restore_status",
                "run_id": run_id,
                "phase": phase,
                "status": status,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "payload": payload or {},
            },
        )
    except Exception as exc:
        logger.warning(f"Failed to broadcast restore status event: {exc}")


async def _write_restore_audit(
    run_id: str,
    event_type: str,
    status: str,
    severity: str,
    username: str,
    details: Optional[Dict[str, Any]] = None,
    message: Optional[str] = None,
    error_description: Optional[str] = None,
) -> None:
    """Persist restore lifecycle evidence to audit log."""
    try:
        async for session in get_session():
            repo = AuditLogRepository(session)
            await repo.create(
                event_type=event_type,
                severity=severity,
                source_type=AuditSourceType.SYSTEM,
                source_id="database_backup_service",
                status=status,
                message=message,
                details={
                    "run_id": run_id,
                    "operator": username,
                    **(details or {}),
                },
                error_description=error_description,
            )
            await session.commit()
            break
    except Exception as exc:
        logger.warning(f"Failed to write restore audit event {event_type}: {exc}")


def _pause_conflict_jobs() -> List[str]:
    """
    Pause scheduler jobs that can conflict with restore writes.
    Returns list of paused job IDs for later resume.
    """
    paused_jobs: List[str] = []
    scheduler = get_central_scheduler()
    for job in scheduler.get_all_jobs():
        job_id = job["id"]
        if scheduler.pause_job(job_id):
            paused_jobs.append(job_id)
    return paused_jobs


def _resume_conflict_jobs(paused_jobs: List[str]) -> Dict[str, int]:
    """Resume previously paused jobs and return resume statistics."""
    resumed = 0
    failed = 0
    scheduler = get_central_scheduler()
    for job_id in paused_jobs:
        if scheduler.resume_job(job_id):
            resumed += 1
        else:
            failed += 1
    return {"resumed": resumed, "failed": failed}


class BackupCleanupResponse(BaseModel):
    status: str = "success"
    deleted_by_age: int
    deleted_by_count: int
    total_deleted: int
    remaining: int


# --- Endpoints ---


@router.post(
    "/database/create",
    response_model=BackupCreateResponse,
    summary="Create database backup",
    description="Trigger an immediate full PostgreSQL backup. Admin only.",
)
async def create_backup(user: AdminUser):
    """Create an immediate database backup via pg_dump."""
    try:
        service = get_database_backup_service()
        info = await service.create_backup()

        logger.info(f"Manual backup triggered by admin {user.username}: {info.filename}")

        return BackupCreateResponse(
            message=f"Backup created: {info.filename} ({info.to_dict()['size_human']})",
            backup=BackupInfoResponse(**info.to_dict()),
        )
    except RuntimeError as e:
        logger.error(f"Backup creation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/database/list",
    response_model=BackupListResponse,
    summary="List database backups",
    description="List all available database backups with metadata. Admin only.",
)
async def list_backups(user: AdminUser):
    """List all database backups sorted by creation date (newest first)."""
    service = get_database_backup_service()
    backups = await service.list_backups()

    return BackupListResponse(
        count=len(backups),
        backups=[BackupInfoResponse(**b.to_dict()) for b in backups],
    )


@router.get(
    "/database/{backup_id}/download",
    summary="Download backup file",
    description="Download a specific backup as .sql.gz file. Admin only.",
)
async def download_backup(backup_id: str, user: AdminUser):
    """Download a backup file."""
    service = get_database_backup_service()
    backup = await service.get_backup(backup_id)

    if not backup:
        raise HTTPException(status_code=404, detail=f"Backup {backup_id} not found")

    return FileResponse(
        path=str(backup.filepath),
        filename=backup.filename,
        media_type="application/gzip",
    )


@router.delete(
    "/database/{backup_id}",
    response_model=BackupDeleteResponse,
    summary="Delete backup",
    description="Delete a specific database backup. Admin only.",
)
async def delete_backup(backup_id: str, user: AdminUser):
    """Delete a specific backup file."""
    service = get_database_backup_service()
    deleted = await service.delete_backup(backup_id)

    if not deleted:
        raise HTTPException(status_code=404, detail=f"Backup {backup_id} not found")

    logger.info(f"Backup {backup_id} deleted by admin {user.username}")

    return BackupDeleteResponse(
        message=f"Backup {backup_id} deleted",
        backup_id=backup_id,
    )


@router.post(
    "/database/{backup_id}/restore",
    response_model=BackupRestoreResponse,
    summary="Restore from backup",
    description=(
        "Restore database from a backup. "
        "WARNING: This replaces ALL current data! "
        "Requires confirm=true query parameter. Admin only."
    ),
)
async def restore_backup(
    backup_id: str,
    user: AdminUser,
    confirm: bool = Query(
        default=False,
        description="Must be true to confirm restore. Safety gate.",
    ),
):
    """Restore database from backup. Requires explicit confirmation."""
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail=(
                "Restore requires confirm=true. "
                "WARNING: This will replace ALL current data in the database!"
            ),
        )

    service = get_database_backup_service()
    run_id = str(uuid.uuid4())
    paused_jobs: List[str] = []
    preflight_id: Optional[str] = None

    try:
        # ------------------------------
        # Phase 1: Preflight
        # ------------------------------
        await _broadcast_restore_status(run_id, "preflight", "started", {"backup_id": backup_id})
        await _write_restore_audit(
            run_id=run_id,
            event_type="database_restore_preflight_started",
            status="pending",
            severity=AuditSeverity.WARNING,
            username=user.username,
            details={"backup_id": backup_id},
            message=f"Restore preflight started for backup {backup_id}",
        )

        scheduler = get_central_scheduler()
        if not scheduler.is_running:
            raise RuntimeError("Preflight failed: central scheduler not running")

        runtime_state = service.get_restore_runtime_state()
        if runtime_state["restore_in_progress"]:
            raise RuntimeError("Preflight failed: another restore is already running")

        preflight = await service.run_restore_preflight(backup_id)
        preflight_id = preflight["preflight_id"]

        await _broadcast_restore_status(run_id, "preflight", "success", preflight)
        await _write_restore_audit(
            run_id=run_id,
            event_type="database_restore_preflight_ok",
            status="success",
            severity=AuditSeverity.INFO,
            username=user.username,
            details=preflight,
            message=f"Restore preflight successful for backup {backup_id}",
        )

        # ------------------------------
        # Phase 2: Quiesce
        # ------------------------------
        await _broadcast_restore_status(run_id, "quiesce", "started", {})
        paused_jobs = _pause_conflict_jobs()
        await _write_restore_audit(
            run_id=run_id,
            event_type="database_restore_quiesce_ok",
            status="success",
            severity=AuditSeverity.INFO,
            username=user.username,
            details={"paused_jobs": len(paused_jobs), "job_ids": paused_jobs},
            message=f"Restore quiesce complete, paused jobs={len(paused_jobs)}",
        )
        await _broadcast_restore_status(
            run_id,
            "quiesce",
            "success",
            {"paused_jobs": len(paused_jobs)},
        )

        # ------------------------------
        # Phase 3: Restore execution
        # ------------------------------
        await _broadcast_restore_status(run_id, "restore", "started", {"backup_id": backup_id})
        result = await service.restore_backup(backup_id, preflight_id=preflight_id, run_id=run_id)

        # ------------------------------
        # Phase 4: Post-restore reconcile
        # ------------------------------
        await _broadcast_restore_status(run_id, "reconcile", "started", {})
        await dispose_engine()

        maintenance_state: Dict[str, Any] = {"reconciled": False}
        try:
            maintenance_service = get_maintenance_service()
            maintenance_state = maintenance_service.reconcile_after_restore()
        except RuntimeError:
            maintenance_state = {"reconciled": False, "reason": "maintenance_service_unavailable"}

        await _broadcast_restore_status(run_id, "reconcile", "success", maintenance_state)

        await _write_restore_audit(
            run_id=run_id,
            event_type="database_restore_completed",
            status="success",
            severity=AuditSeverity.CRITICAL,
            username=user.username,
            details={
                "backup_id": backup_id,
                "filename": result["filename"],
                "duration_seconds": result["duration_seconds"],
                "preflight_id": preflight_id,
                "maintenance_state": maintenance_state,
            },
            message=f"Database restored from backup {backup_id}",
        )

        logger.warning(f"Database restored from backup {backup_id} by admin {user.username}")

        await _broadcast_restore_status(
            run_id,
            "terminal",
            "success",
            {
                "backup_id": backup_id,
                "duration_seconds": result["duration_seconds"],
            },
        )

        return BackupRestoreResponse(
            message=f"Database restored from backup {backup_id}",
            backup_id=result["backup_id"],
            filename=result["filename"],
            duration_seconds=result["duration_seconds"],
            run_id=result["run_id"],
            preflight_id=result["preflight_id"],
        )
    except ValueError as e:
        await _broadcast_restore_status(run_id, "terminal", "failed", {"error": str(e)})
        await _write_restore_audit(
            run_id=run_id,
            event_type="database_restore_failed",
            status="failed",
            severity=AuditSeverity.ERROR,
            username=user.username,
            details={"backup_id": backup_id},
            message=f"Database restore failed for backup {backup_id}",
            error_description=str(e),
        )
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        message = str(e)
        await _broadcast_restore_status(run_id, "terminal", "failed", {"error": message})
        await _write_restore_audit(
            run_id=run_id,
            event_type="database_restore_failed",
            status="failed",
            severity=AuditSeverity.ERROR,
            username=user.username,
            details={"backup_id": backup_id, "preflight_id": preflight_id},
            message=f"Database restore failed for backup {backup_id}",
            error_description=message,
        )
        logger.error(f"Database restore failed: {e}")
        if (
            "Preflight failed" in message
            or "preflight" in message.lower()
            or "already in progress" in message.lower()
            or "Insufficient free disk" in message
        ):
            raise HTTPException(status_code=412, detail=message)
        raise HTTPException(status_code=500, detail=message)
    finally:
        if paused_jobs:
            resume_stats = _resume_conflict_jobs(paused_jobs)
            await _broadcast_restore_status(run_id, "quiesce_resume", "success", resume_stats)
            await _write_restore_audit(
                run_id=run_id,
                event_type="database_restore_quiesce_released",
                status="success",
                severity=AuditSeverity.INFO,
                username=user.username,
                details=resume_stats,
                message="Restore quiesce released",
            )


@router.post(
    "/database/cleanup",
    response_model=BackupCleanupResponse,
    summary="Cleanup old backups",
    description="Remove backups older than max_age_days and excess beyond max_count. Admin only.",
)
async def cleanup_backups(user: AdminUser):
    """Manually trigger backup cleanup."""
    service = get_database_backup_service()
    result = await service.cleanup_old_backups()

    if result["total_deleted"] > 0:
        logger.info(
            f"Backup cleanup triggered by admin {user.username}: "
            f"{result['total_deleted']} deleted"
        )

    return BackupCleanupResponse(**result)
