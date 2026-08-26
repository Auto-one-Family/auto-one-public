"""
Admin API — Google Sheets Export Management (AUT-446 / S3).

Provides admin-only endpoints for managing the Sheets-Export pipeline cursors:

  POST /api/v1/admin/sheets-export/reset-cursor
      Resets one of the three export progress cursors so the next scheduled
      export job re-exports data from the beginning.
      Auth: get_current_admin_user (AdminUser)

All mutating operations are audit-logged via AuditLogRepository.

Reference: docs/plans/BELEG-sheets-export-baseline-2026-05-23.md
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.logging_config import get_logger
from ...db.models.audit_log import AuditEventType, AuditSeverity, AuditSourceType
from ...db.repositories.audit_log_repo import AuditLogRepository
from ...db.repositories.system_config_repo import ALLOWED_SHEETS_CURSOR_NAMES
from ...integrations.sheets.cursor import SheetsCursorService
from ..deps import AdminUser, get_db

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/admin/sheets-export", tags=["admin", "sheets-export"])

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class ResetCursorRequest(BaseModel):
    """Body for POST /reset-cursor."""

    model_config = ConfigDict(str_strip_whitespace=True)

    cursor_name: str

    @field_validator("cursor_name")
    @classmethod
    def cursor_name_must_be_allowed(cls, v: str) -> str:
        if v not in ALLOWED_SHEETS_CURSOR_NAMES:
            allowed = sorted(ALLOWED_SHEETS_CURSOR_NAMES)
            raise ValueError(
                f"Unknown cursor_name {v!r}. Allowed: {allowed}"
            )
        return v


class ResetCursorResponse(BaseModel):
    """Response for POST /reset-cursor."""

    status: str = "success"
    cursor_name: str
    deleted: bool
    message: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/reset-cursor",
    response_model=ResetCursorResponse,
    summary="Reset a Sheets-Export cursor",
    description=(
        "Deletes the persisted cursor value for the specified Sheets-Export stream "
        "so that the next scheduled export job re-exports all data from the beginning. "
        "Requires admin role."
    ),
    status_code=status.HTTP_200_OK,
)
async def reset_sheets_export_cursor(
    body: ResetCursorRequest,
    current_user: AdminUser,
    db: AsyncSession = Depends(get_db),
) -> ResetCursorResponse:
    """
    Reset a Sheets-Export progress cursor.

    Allowed cursor names:
    - sheets_export_sensor_cursor
    - sheets_export_history_cursor
    - sheets_export_logic_cursor
    """
    cursor_svc = SheetsCursorService(db)
    audit_repo = AuditLogRepository(db)

    try:
        deleted = await cursor_svc.reset(body.cursor_name)
    except ValueError as exc:
        # Defensive: validator already catches this, but guard the service layer too
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error(
            "Failed to reset Sheets-Export cursor %r: %s",
            body.cursor_name,
            exc,
            exc_info=True,
        )
        await audit_repo.create(
            event_type=AuditEventType.API_ERROR,
            severity=AuditSeverity.ERROR,
            source_type=AuditSourceType.API,
            source_id=f"admin:{current_user.username}",
            status="error",
            message=f"sheets-export cursor reset failed: {body.cursor_name}",
            details={
                "cursor_name": body.cursor_name,
                "admin_user": current_user.username,
                "error": str(exc),
            },
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reset cursor.",
        ) from exc

    message = (
        f"Cursor '{body.cursor_name}' deleted; next export run starts from the beginning."
        if deleted
        else f"Cursor '{body.cursor_name}' was not set; nothing to reset."
    )

    # Audit log — always write, whether deleted or not
    await audit_repo.create(
        event_type=AuditEventType.CONFIG_PUBLISHED,
        severity=AuditSeverity.INFO,
        source_type=AuditSourceType.API,
        source_id=f"admin:{current_user.username}",
        status="success",
        message=message,
        details={
            "action": "sheets_export_cursor_reset",
            "cursor_name": body.cursor_name,
            "deleted": deleted,
            "admin_user": current_user.username,
            "admin_user_id": current_user.id,
        },
    )
    await db.commit()

    logger.info(
        "Admin %s reset Sheets-Export cursor %r (deleted=%s)",
        current_user.username,
        body.cursor_name,
        deleted,
    )

    return ResetCursorResponse(
        cursor_name=body.cursor_name,
        deleted=deleted,
        message=message,
    )
