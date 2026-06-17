"""
Global Exception Handlers für FastAPI

Paket X: Code Consolidation & Industrial Quality
Standardisiertes Error-Handling für alle API-Endpoints.
"""

from fastapi import Request
from fastapi.responses import JSONResponse

from .exceptions import GodKaiserException
from .logging_config import get_logger
from .metrics import increment_api_error_code
from .request_context import get_request_id

logger = get_logger(__name__)


def _map_status_to_severity(status_code: int) -> str:
    """Map HTTP status code to log severity level."""
    if status_code >= 500:
        return "critical"
    if status_code == 429:
        return "warning"
    if status_code >= 400:
        return "error"
    return "info"


async def _log_to_audit(
    request: Request,
    exc: GodKaiserException,
    request_id: str,
) -> None:
    """
    Fire-and-forget AuditLog entry for API errors with numeric_code.

    Uses a standalone DB session to avoid interfering with the
    request's session. Failures are silently logged — AuditLog
    errors must never block the API response.
    """
    try:
        from ..db.session import get_session_maker
        from ..db.repositories.audit_log_repo import AuditLogRepository

        session_maker = get_session_maker()
        async with session_maker() as session:
            audit_repo = AuditLogRepository(session)
            await audit_repo.log_api_error(
                error_code=exc.error_code,
                numeric_code=exc.numeric_code,
                severity=_map_status_to_severity(exc.status_code),
                message=exc.message,
                source_id=request.url.path,
                method=request.method,
                details={
                    "string_code": exc.error_code,
                    "numeric_code": exc.numeric_code,
                    "status_code": exc.status_code,
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                },
            )
            await session.commit()
    except Exception as e:
        logger.debug(f"AuditLog write failed (non-critical): {e}")


async def automation_one_exception_handler(
    request: Request,
    exc: GodKaiserException,
) -> JSONResponse:
    """
    Global exception handler für GodKaiserException.

    Konvertiert Exceptions in standardisiertes API Response Format:
    {
        "success": false,
        "error": {
            "code": "ERROR_CODE",
            "numeric_code": 5001,
            "message": "Error message",
            "details": {...},
            "request_id": "uuid"
        }
    }
    """
    request_id = get_request_id()

    logger.warning(
        f"API error: {exc.error_code} - {exc.message}",
        extra={
            "error_code": exc.error_code,
            "numeric_code": exc.numeric_code,
            "severity": _map_status_to_severity(exc.status_code),
            "path": request.url.path,
            "method": request.method,
            "request_id": request_id,
            "details": exc.details,
        },
    )

    # Prometheus per-code counter + AuditLog integration
    if exc.numeric_code:
        increment_api_error_code(exc.numeric_code)
        await _log_to_audit(request, exc, request_id)

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": exc.error_code,
                "numeric_code": exc.numeric_code,
                "message": exc.message,
                "details": exc.details,
                "request_id": request_id,
            },
        },
    )


async def general_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """
    Fallback exception handler für unerwartete Exceptions.

    Sollte nie aufgerufen werden in Production, aber als Safety-Net vorhanden.
    """
    logger.error(
        f"Unhandled exception: {type(exc).__name__} - {str(exc)}",
        exc_info=True,
        extra={
            "path": request.url.path,
            "method": request.method,
        },
    )

    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred",
                "details": {},
            },
        },
    )
