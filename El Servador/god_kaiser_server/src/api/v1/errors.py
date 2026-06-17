"""
Error Management API Endpoints

Provides REST endpoints for querying ESP32 error events:
- GET /esp/{esp_id} - Get error events for a specific ESP device
- GET /summary - Get error statistics across all devices
- GET /codes - Get all known error codes with descriptions

Pattern: Follows sensors.py endpoint structure. DB queries live in
``services/error_service.py`` (AUT-224 A2: Service-Layer-Konsistenz).
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from ...core.esp32_error_mapping import (
    ALL_ESP32_ERROR_MESSAGES,
    get_all_error_codes,
    get_error_info,
)
from ...core.server_error_mapping import (
    SERVER_ERROR_MAPPING,
    get_server_error_info,
)
from ...core.logging_config import get_logger
from ...db.models.audit_log import AuditLog
from ...db.repositories import ESPRepository
from ...schemas.common import PaginationMeta
from ...schemas.error_schemas import (
    ErrorCodeCount,
    ErrorCodeInfoResponse,
    ErrorCodeListResponse,
    ErrorLogListResponse,
    ErrorLogResponse,
    ErrorSummaryResponse,
)
from ...services.ai_service import ErrorAnalysisRequest, ErrorAnalysisFinding, ai_service
from ...services.error_service import ErrorService
from ..deps import ActiveUser, DBSession

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/errors", tags=["errors"])


# =============================================================================
# Helper Functions
# =============================================================================


def _audit_log_to_error_response(log: AuditLog, esp_name: Optional[str] = None) -> ErrorLogResponse:
    """
    Convert AuditLog model to ErrorLogResponse schema.

    Args:
        log: AuditLog model instance
        esp_name: Optional ESP device name

    Returns:
        ErrorLogResponse schema
    """
    details = log.details or {}

    return ErrorLogResponse(
        id=log.id,
        esp_id=log.source_id,
        esp_name=esp_name,
        error_code=details.get("error_code", 0),
        severity=log.severity or "error",
        category=details.get("category"),
        message=log.message or log.error_description or "Unknown error",
        troubleshooting=details.get("troubleshooting", []),
        docs_link=details.get("docs_link"),
        user_action_required=details.get("user_action_required", False),
        recoverable=details.get("recoverable", True),
        context=details.get("context", {}),
        esp_raw_message=details.get("esp_raw_message"),
        timestamp=log.created_at,
    )


# =============================================================================
# ESP Error Events Endpoint
# =============================================================================


@router.get(
    "/esp/{esp_id}",
    response_model=ErrorLogListResponse,
    summary="Get ESP error events",
    description="Get error events for a specific ESP device with pagination and filtering",
)
async def get_esp_errors(
    esp_id: str,
    session: DBSession,
    current_user: ActiveUser,
    severity: Optional[str] = Query(
        None,
        description="Filter by severity (info, warning, error, critical)",
    ),
    category: Optional[str] = Query(
        None,
        description="Filter by category (HARDWARE, CONFIG, etc.)",
    ),
    hours: int = Query(
        24,
        ge=1,
        le=168,
        description="Time range in hours (max 168 = 7 days)",
    ),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
) -> ErrorLogListResponse:
    """
    Get error events for a specific ESP device.

    Retrieves MQTT error events from the audit log for the specified ESP.
    Supports filtering by severity, category, and time range.

    Args:
        esp_id: ESP device ID (e.g., ESP_12AB34CD)
        severity: Optional severity filter
        category: Optional category filter
        hours: Time range in hours (default 24)
        page: Page number (default 1)
        page_size: Items per page (default 20)

    Returns:
        Paginated list of error events
    """
    # Verify ESP exists
    esp_repo = ESPRepository(session)
    esp_device = await esp_repo.get_by_device_id(esp_id)
    if not esp_device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ESP device not found: {esp_id}",
        )

    # Delegate query work to ErrorService (AUT-224 A2)
    service = ErrorService(session)
    logs, total_count, unacknowledged_count = await service.list_esp_errors(
        esp_id=esp_id,
        hours=hours,
        severity=severity,
        page=page,
        page_size=page_size,
    )

    # Convert to response models
    error_responses = [_audit_log_to_error_response(log, esp_device.name) for log in logs]

    # Build pagination metadata
    total_pages = (total_count + page_size - 1) // page_size if page_size > 0 else 0
    pagination = PaginationMeta(
        page=page,
        page_size=page_size,
        total_items=total_count,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1,
    )

    return ErrorLogListResponse(
        success=True,
        errors=error_responses,
        total_count=total_count,
        unacknowledged_count=unacknowledged_count,
        pagination=pagination,
    )


# =============================================================================
# Error Summary Endpoint
# =============================================================================


@router.get(
    "/summary",
    response_model=ErrorSummaryResponse,
    summary="Get error summary",
    description="Get error statistics across all ESP devices",
)
async def get_error_summary(
    session: DBSession,
    current_user: ActiveUser,
    hours: int = Query(
        24,
        ge=1,
        le=168,
        description="Time range in hours (max 168 = 7 days)",
    ),
) -> ErrorSummaryResponse:
    """
    Get error summary statistics across all ESP devices.

    Provides aggregated error counts by severity, category, and ESP device.
    Also includes the most frequent error codes.

    Args:
        hours: Time range in hours (default 24)

    Returns:
        Error summary with statistics
    """
    # Delegate aggregation work to ErrorService (AUT-224 A2)
    service = ErrorService(session)
    summary = await service.get_error_summary(hours=hours)

    error_code_counts: dict[int, int] = summary["error_code_counts"]
    sorted_codes = sorted(error_code_counts.items(), key=lambda x: x[1], reverse=True)[
        :10
    ]  # Top 10

    top_error_codes = []
    all_error_messages = get_all_error_codes()
    for code, count in sorted_codes:
        message = all_error_messages.get(code, f"Unknown error code: {code}")
        top_error_codes.append(
            ErrorCodeCount(
                error_code=code,
                count=count,
                message=message,
            )
        )

    return ErrorSummaryResponse(
        success=True,
        period_hours=hours,
        total_errors=summary["total_errors"],
        errors_by_severity=summary["errors_by_severity"],
        errors_by_category=summary["errors_by_category"],
        errors_by_esp=summary["errors_by_esp"],
        top_error_codes=top_error_codes,
        action_required_count=summary["action_required_count"],
    )


# =============================================================================
# Error Codes Reference Endpoint
# =============================================================================


@router.get(
    "/codes",
    response_model=ErrorCodeListResponse,
    summary="Get error code reference",
    description="Get all known error codes with descriptions and troubleshooting",
)
async def get_error_codes(
    current_user: ActiveUser,
    category: Optional[str] = Query(
        None,
        description="Filter by category (HARDWARE, CONFIG, etc.)",
    ),
) -> ErrorCodeListResponse:
    """
    Get all known error codes (ESP32 + Server) with their descriptions.

    Provides a reference list of error codes for documentation and
    frontend error code lookup.

    Args:
        category: Optional category filter

    Returns:
        List of error codes with descriptions
    """
    error_codes = []

    # ESP32 error codes (1000-4999)
    for code, info in ALL_ESP32_ERROR_MESSAGES.items():
        if category and info.get("category") != category.upper():
            continue

        error_codes.append(
            ErrorCodeInfoResponse(
                error_code=code,
                title=info.get("message_de"),
                category=info.get("category", "UNKNOWN"),
                severity=info.get("severity", "ERROR"),
                message=info.get("message_user_de", f"Error code: {code}"),
                troubleshooting=info.get("troubleshooting_de", []),
                docs_link=info.get("docs_link"),
                recoverable=info.get("recoverable", True),
                user_action_required=info.get("user_action_required", False),
            )
        )

    # Server error codes (5000-5999)
    for code, info in SERVER_ERROR_MAPPING.items():
        if category and info.get("category") != category.upper():
            continue

        error_codes.append(
            ErrorCodeInfoResponse(
                error_code=code,
                title=info.get("message_de"),
                category=info.get("category", "UNKNOWN"),
                severity=info.get("severity", "ERROR"),
                message=info.get("message_user_de", f"Error code: {code}"),
                troubleshooting=info.get("troubleshooting_de", []),
                docs_link=info.get("docs_link"),
                recoverable=info.get("recoverable", True),
                user_action_required=info.get("user_action_required", False),
            )
        )

    return ErrorCodeListResponse(
        success=True,
        error_codes=error_codes,
        total_count=len(error_codes),
    )


# =============================================================================
# Single Error Code Lookup Endpoint
# =============================================================================


@router.get(
    "/codes/{error_code}",
    response_model=ErrorCodeInfoResponse,
    summary="Get error code details",
    description="Get detailed information about a specific error code",
)
async def get_error_code_info(
    error_code: int,
    current_user: ActiveUser,
) -> ErrorCodeInfoResponse:
    """
    Get detailed information about a specific error code.

    Args:
        error_code: Error code to lookup (e.g., 1026)

    Returns:
        Error code information with troubleshooting

    Raises:
        HTTPException: 404 if error code not found
    """
    # Try ESP32 mapping first, then server mapping as fallback
    error_info = get_error_info(error_code) or get_server_error_info(error_code)

    if not error_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Error code not found: {error_code}",
        )

    return ErrorCodeInfoResponse(
        error_code=error_code,
        title=error_info.get("message_de"),
        category=error_info.get("category", "UNKNOWN"),
        severity=error_info.get("severity", "ERROR"),
        message=error_info.get(
            "message_user_de", error_info.get("message", f"Error code: {error_code}")
        ),
        troubleshooting=error_info.get("troubleshooting_de", error_info.get("troubleshooting", [])),
        docs_link=error_info.get("docs_link"),
        recoverable=error_info.get("recoverable", True),
        user_action_required=error_info.get("user_action_required", False),
    )


# =============================================================================
# AI Error Analysis Endpoint
# =============================================================================


@router.get(
    "/codes/{error_code}/analysis",
    response_model=ErrorAnalysisFinding,
    summary="Get AI analysis for error code",
    description="Get AI-powered root cause analysis and recommendations for a specific error code",
)
async def get_error_code_analysis(
    error_code: int,
    current_user: ActiveUser,
    esp_id: Optional[str] = Query(default=None),
    recent_errors: Optional[str] = Query(
        default=None,
        description="Comma-separated list of recent error codes",
    ),
) -> ErrorAnalysisFinding:
    """
    Get AI-powered analysis for a specific error code.

    Uses the AI service to provide root cause analysis, recommended actions,
    and confidence scores for the given error code.

    Args:
        error_code: Error code to analyze (e.g., 1026)
        esp_id: Optional ESP device ID for context
        recent_errors: Optional comma-separated list of recent error codes

    Returns:
        AI analysis finding with root cause and recommendations

    Raises:
        HTTPException: 503 if AI service is not configured
    """
    if not ai_service.is_available():
        raise HTTPException(
            status_code=503,
            detail="AI service not configured (ANTHROPIC_API_KEY missing)",
        )

    recent: list[int] = []
    if recent_errors:
        try:
            recent = [int(x.strip()) for x in recent_errors.split(",") if x.strip()]
        except ValueError:
            pass

    request = ErrorAnalysisRequest(
        error_code=error_code,
        context={"esp_id": esp_id} if esp_id else {},
        recent_errors=recent,
        system_state={},
    )
    return await ai_service.analyze_error(request)
