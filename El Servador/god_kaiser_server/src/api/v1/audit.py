"""
Audit Log API: System Event Monitoring and Retention Management

Provides endpoints for:
- Viewing audit logs with filters
- Managing retention policies
- Running manual cleanup
- Dashboard statistics

Phase: Runtime Config Flow Implementation
Priority: MEDIUM
Status: IMPLEMENTED
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field


from ...core.logging_config import get_logger
from ...db.models.audit_log import AuditEventType, AuditLog, AuditSeverity, AuditSourceType
from ...db.repositories.audit_log_repo import AuditLogRepository
from ...services.audit_retention_service import AuditRetentionService
from ...services.event_aggregator_service import EventAggregatorService, DataSource
from ..deps import ActiveUser, AdminUser, DBSession, OperatorUser

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/audit", tags=["Audit Logs"])


# =============================================================================
# Request/Response Models
# =============================================================================


class AuditLogResponse(BaseModel):
    """Audit log entry response."""

    id: str
    event_type: str
    severity: str
    source_type: str
    source_id: Optional[str]
    status: str
    message: Optional[str]
    details: Dict[str, Any]
    error_code: Optional[str]
    error_description: Optional[str]
    ip_address: Optional[str]
    correlation_id: Optional[str]
    request_id: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AuditLogListResponse(BaseModel):
    """Paginated audit log list response."""

    data: List[AuditLogResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class RetentionConfigResponse(BaseModel):
    """Retention configuration response."""

    enabled: bool
    default_days: int
    severity_days: Dict[str, int]
    max_records: int
    batch_size: int
    preserve_emergency_stops: bool
    last_cleanup: Optional[str]


class RetentionConfigUpdate(BaseModel):
    """Retention configuration update request."""

    enabled: Optional[bool] = None
    default_days: Optional[int] = Field(None, ge=1, le=3650)
    severity_days: Optional[Dict[str, int]] = None
    max_records: Optional[int] = Field(None, ge=0)
    batch_size: Optional[int] = Field(None, ge=100, le=10000)
    preserve_emergency_stops: Optional[bool] = None


class CleanupPreviewEvent(BaseModel):
    """Preview event for cleanup operation."""

    id: str  # UUID as string
    event_type: str
    severity: str
    message: str
    device_id: Optional[str] = None
    created_at: Optional[str] = None


class CleanupResponse(BaseModel):
    """Cleanup operation response."""

    deleted_count: int
    deleted_by_severity: Dict[str, int]
    duration_ms: int
    dry_run: bool
    errors: List[str] = []
    retention_enabled: Optional[bool] = None
    backup_id: Optional[str] = None
    skipped: Optional[bool] = None
    reason: Optional[str] = None
    preview_events: Optional[List[CleanupPreviewEvent]] = None
    preview_limited: Optional[bool] = None


class BackupInfo(BaseModel):
    """Backup information response."""

    backup_id: str
    created_at: str
    expires_at: Optional[str]  # None = never expires
    expired: bool
    event_count: int
    metadata: Dict[str, Any] = {}


class BackupRetentionConfigResponse(BaseModel):
    """Backup retention configuration response."""

    retention_days: int = Field(description="Days until backup expires (0 = never expire)")
    max_backups: int = Field(description="Maximum number of backups to keep")
    max_retention_days: int = Field(description="Maximum allowed retention days")
    never_expire_value: int = Field(description="Value for 'never expire' (0)")


class BackupRetentionConfigUpdate(BaseModel):
    """Backup retention configuration update request."""

    retention_days: int = Field(
        ge=0, le=365, description="Days until backup expires (0 = never expire, max 365)"
    )


class BackupListResponse(BaseModel):
    """Backup list response."""

    backups: List[BackupInfo]
    total: int


class BackupRestoreResponse(BaseModel):
    """Backup restore operation response."""

    backup_id: str
    restored_count: int
    skipped_duplicates: int
    total_in_backup: int
    backup_deleted: bool = False
    restored_event_ids: List[str] = []


class AuditStatisticsResponse(BaseModel):
    """Audit statistics response."""

    total_count: int
    count_by_severity: Dict[str, int]
    count_by_event_type: Dict[str, int]
    oldest_entry: Optional[str]
    newest_entry: Optional[str]
    storage_estimate_mb: float
    pending_cleanup_count: int
    pending_cleanup_by_severity: Dict[str, int]
    retention_config: RetentionConfigResponse


class NextCleanupPreview(BaseModel):
    """Preview of what the next auto-cleanup would delete."""

    would_delete: int
    breakdown: Dict[str, int]


class AutoCleanupStatusResponse(BaseModel):
    """Auto-cleanup system status for UI transparency."""

    enabled: bool
    last_run: Optional[str]
    next_run: Optional[str]
    schedule: str
    config: RetentionConfigResponse
    next_cleanup_preview: NextCleanupPreview


class EventTypeInfo(BaseModel):
    """Event type information."""

    value: str
    description: str
    category: str


class SeverityInfo(BaseModel):
    """Severity level information."""

    value: str
    description: str
    color: str


class UnifiedEventResponse(BaseModel):
    """Unified event from aggregated sources."""

    id: str
    timestamp: str
    source: str
    category: str
    title: str
    message: str
    severity: str
    device_id: Optional[str] = None
    metadata: Dict[str, Any] = {}


class SourceCountsResponse(BaseModel):
    """Count information for a single data source."""

    loaded: int
    available: int


class PaginationInfo(BaseModel):
    """Pagination information for cursor-based pagination."""

    has_more: bool
    oldest_timestamp: Optional[str] = None  # Cursor for next page
    total_available: int


class AggregatedEventsResponse(BaseModel):
    """Response for aggregated events from multiple sources."""

    events: List[UnifiedEventResponse]
    total_loaded: int
    total_available: int
    source_counts: Dict[str, SourceCountsResponse]
    sources: List[str]
    time_range_hours: int
    limit_per_source: int
    pagination: PaginationInfo  # NEW: Pagination info for infinite scroll


# =============================================================================
# Audit Log Viewing Endpoints
# =============================================================================


@router.get(
    "",
    response_model=AuditLogListResponse,
    summary="List audit logs",
    description="Get paginated list of audit logs with optional filters.",
)
async def list_audit_logs(
    db: DBSession,
    current_user: ActiveUser,
    # Filters
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    source_type: Optional[str] = Query(None, description="Filter by source type"),
    source_id: Optional[str] = Query(None, description="Filter by source ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
    error_code: Optional[str] = Query(None, description="Filter by error code"),
    # Time range
    start_time: Optional[datetime] = Query(None, description="Start of time range"),
    end_time: Optional[datetime] = Query(None, description="End of time range"),
    hours: Optional[int] = Query(None, ge=1, le=720, description="Last N hours"),
    # Pagination
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=500, description="Items per page"),
) -> AuditLogListResponse:
    """
    List audit logs with filters.

    Supports filtering by:
    - event_type: Type of event (config_response, emergency_stop, etc.)
    - severity: Event severity (info, warning, error, critical)
    - source_type: Source of event (esp32, user, system, api, mqtt)
    - source_id: Specific source identifier
    - status: Event status (success, failed, pending)
    - error_code: Specific error code
    - Time range: start_time/end_time or last N hours
    """
    # Build filter conditions (sqlalchemy + AuditLog imported at module level — AUT-224 A2)
    conditions = []

    if event_type:
        conditions.append(AuditLog.event_type == event_type)
    if severity:
        conditions.append(AuditLog.severity == severity)
    if source_type:
        conditions.append(AuditLog.source_type == source_type)
    if source_id:
        conditions.append(AuditLog.source_id == source_id)
    if status:
        conditions.append(AuditLog.status == status)
    if error_code:
        conditions.append(AuditLog.error_code == error_code)

    # Time range
    if hours:
        start_time = datetime.now(timezone.utc) - timedelta(hours=hours)
    if start_time:
        conditions.append(AuditLog.created_at >= start_time)
    if end_time:
        conditions.append(AuditLog.created_at <= end_time)

    audit_repo = AuditLogRepository(db)
    logs, total = await audit_repo.get_paginated(
        conditions=conditions,
        page=page,
        page_size=page_size,
    )

    # Convert to response models
    response_data = [
        AuditLogResponse(
            id=str(log.id),
            event_type=log.event_type,
            severity=log.severity,
            source_type=log.source_type,
            source_id=log.source_id,
            status=log.status,
            message=log.message,
            details=log.details or {},
            error_code=log.error_code,
            error_description=log.error_description,
            ip_address=log.ip_address,
            correlation_id=log.correlation_id,
            request_id=log.request_id,
            created_at=log.created_at,
        )
        for log in logs
    ]

    total_pages = (total + page_size - 1) // page_size

    return AuditLogListResponse(
        data=response_data,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/events/aggregated",
    response_model=AggregatedEventsResponse,
    summary="Get aggregated events from multiple sources",
    description="Aggregates events from audit logs, sensor data, ESP health, and actuator history.",
)
async def get_aggregated_events(
    db: DBSession,
    current_user: ActiveUser,
    sources: List[DataSource] = Query(
        default=["audit_log"],
        description="Data sources to aggregate: audit_log, sensor_data, esp_health, actuators",
    ),
    hours: Optional[int] = Query(
        default=None,
        ge=1,
        le=8760,  # Max 1 year (365 days)
        description="Time range in hours (1-8760). None = load ALL events.",
    ),
    limit_per_source: int = Query(
        default=500, ge=1, le=2000, description="Maximum events per source"
    ),
    severity: Optional[List[str]] = Query(
        default=None,
        description="Filter by severity levels: info, warning, error, critical. Only applies to audit_log source.",
    ),
    esp_ids: Optional[List[str]] = Query(
        default=None, description="Filter by ESP device IDs (e.g., MOCK_067EA733, ESP_12AB34CD)"
    ),
    before_timestamp: Optional[str] = Query(
        default=None,
        description="Cursor for pagination: Load events BEFORE this ISO timestamp. "
        "Use the 'oldest_timestamp' from the previous response.",
    ),
) -> AggregatedEventsResponse:
    """
    Aggregates events from multiple data sources into a unified format.

    ## Verwendung

    **Standard (nur Audit-Log):**
    ```
    GET /api/v1/audit/events/aggregated
    ```

    **Mit Sensordaten:**
    ```
    GET /api/v1/audit/events/aggregated?sources=audit_log&sources=sensor_data
    ```

    **Alle Quellen (24 Stunden):**
    ```
    GET /api/v1/audit/events/aggregated?sources=audit_log&sources=sensor_data&sources=esp_health&sources=actuators&hours=24
    ```

    **Alle Events (ohne Zeitbegrenzung):**
    ```
    GET /api/v1/audit/events/aggregated?sources=audit_log&sources=sensor_data&sources=esp_health&sources=actuators
    ```
    (Ohne `hours` Parameter = alle historischen Events)

    ## Data Sources

    - **audit_log**: System events, config responses, errors
    - **sensor_data**: Sensor readings (temperature, pH, etc.)
    - **esp_health**: ESP device heartbeats and status
    - **actuators**: Actuator command history

    ## Response Format

    All events are transformed into a unified format:
    - `id`: Unique ID with source prefix (audit_123, sensor_456)
    - `timestamp`: ISO-8601 timestamp
    - `source`: Data source identifier
    - `category`: Human-readable category (German)
    - `title`: Short description (German)
    - `message`: Details (German)
    - `severity`: info, warning, error, critical
    - `device_id`: ESP device ID if applicable
    - `metadata`: Source-specific additional data

    ## Performance

    - Max 500 events per source (default)
    - Sorted chronologically (newest first)
    - Uses DB indices on timestamp/created_at

    ## Performance Note

    - Loading ALL events (hours=None) can be slow for large databases
    - Recommended to use time range (hours) for normal usage
    - Use limit_per_source to control memory usage
    """
    # Validate severity parameter
    if severity:
        valid_severities = {"info", "warning", "error", "critical"}
        invalid = set(severity) - valid_severities
        if invalid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid severity values: {invalid}. Valid values: {valid_severities}",
            )

    # Validate esp_ids parameter (basic format check)
    if esp_ids:
        for esp_id in esp_ids:
            if not esp_id or len(esp_id) > 100:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid ESP ID: '{esp_id}'. Must be non-empty and max 100 characters.",
                )

    service = EventAggregatorService(db)

    # Calculate cutoff time (None = load all historical events)
    cutoff_time = None
    if hours is not None:
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)

    # Parse before_timestamp for cursor-based pagination
    before_time = None
    if before_timestamp:
        try:
            before_time = datetime.fromisoformat(before_timestamp.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid before_timestamp format: '{before_timestamp}'. Use ISO 8601 format.",
            )

    try:
        result = await service.aggregate_events(
            sources=list(sources),
            after=cutoff_time,
            before=before_time,  # NEW: cursor for pagination
            limit_per_source=limit_per_source,
            severity_filter=severity,
            esp_id_filter=esp_ids,
        )

        events = [UnifiedEventResponse(**event) for event in result["events"]]

        # Calculate pagination info
        oldest_timestamp = None
        if events:
            oldest_timestamp = events[-1].timestamp  # Last event is oldest (sorted newest first)

        has_more = result["total_loaded"] >= limit_per_source * len(sources)
        # More accurate: check if we hit the limit for any source
        for source, counts in result["source_counts"].items():
            if counts["loaded"] >= limit_per_source and counts["loaded"] < counts["available"]:
                has_more = True
                break

        return AggregatedEventsResponse(
            events=events,
            total_loaded=result["total_loaded"],
            total_available=result["total_available"],
            source_counts={
                k: SourceCountsResponse(**v) for k, v in result["source_counts"].items()
            },
            sources=list(sources),
            time_range_hours=hours if hours is not None else 0,  # 0 indicates "all"
            limit_per_source=limit_per_source,
            pagination=PaginationInfo(
                has_more=has_more,
                oldest_timestamp=oldest_timestamp,
                total_available=result["total_available"],
            ),
        )
    except Exception as e:
        logger.error(f"Failed to aggregate events: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to aggregate events: {str(e)}",
        )


@router.get(
    "/events/correlated/{correlation_id}",
    response_model=List[AuditLogResponse],
    summary="Get correlated events",
    description="Returns all audit events with the same correlation_id.",
)
async def get_correlated_events(
    correlation_id: str,
    db: DBSession,
    current_user: ActiveUser,
    limit: int = Query(50, ge=1, le=200, description="Maximum results"),
) -> List[AuditLogResponse]:
    """
    Returns all audit events that share the same correlation_id.

    Enables tracking of related events such as:
    - config_published → config_response
    - actuator_command → actuator_response

    Events are sorted chronologically (oldest first).
    """
    audit_repo = AuditLogRepository(db)
    events = await audit_repo.get_by_correlation_id(correlation_id, limit=limit)

    return [
        AuditLogResponse(
            id=str(log.id),
            event_type=log.event_type,
            severity=log.severity,
            source_type=log.source_type,
            source_id=log.source_id,
            status=log.status,
            message=log.message,
            details=log.details or {},
            error_code=log.error_code,
            error_description=log.error_description,
            ip_address=log.ip_address,
            correlation_id=log.correlation_id,
            request_id=log.request_id,
            created_at=log.created_at,
        )
        for log in events
    ]


@router.get(
    "/errors",
    response_model=List[AuditLogResponse],
    summary="Get recent errors",
    description="Get recent error and critical events.",
)
async def get_recent_errors(
    db: DBSession,
    current_user: ActiveUser,
    hours: int = Query(24, ge=1, le=168, description="Look back hours"),
    limit: int = Query(100, ge=1, le=500, description="Maximum results"),
) -> List[AuditLogResponse]:
    """Get recent error and critical events for quick troubleshooting."""
    audit_repo = AuditLogRepository(db)

    start_time = datetime.now(timezone.utc) - timedelta(hours=hours)
    logs = await audit_repo.get_errors(start_time=start_time, limit=limit)

    return [
        AuditLogResponse(
            id=str(log.id),
            event_type=log.event_type,
            severity=log.severity,
            source_type=log.source_type,
            source_id=log.source_id,
            status=log.status,
            message=log.message,
            details=log.details or {},
            error_code=log.error_code,
            error_description=log.error_description,
            ip_address=log.ip_address,
            correlation_id=log.correlation_id,
            request_id=log.request_id,
            created_at=log.created_at,
        )
        for log in logs
    ]


@router.get(
    "/esp/{esp_id}/config-history",
    response_model=List[AuditLogResponse],
    summary="Get ESP config history",
    description="Get configuration response history for an ESP device.",
)
async def get_esp_config_history(
    esp_id: str,
    db: DBSession,
    current_user: ActiveUser,
    limit: int = Query(50, ge=1, le=200, description="Maximum results"),
) -> List[AuditLogResponse]:
    """Get config response history for specific ESP device."""
    audit_repo = AuditLogRepository(db)

    logs = await audit_repo.get_esp_config_history(esp_id=esp_id, limit=limit)

    return [
        AuditLogResponse(
            id=str(log.id),
            event_type=log.event_type,
            severity=log.severity,
            source_type=log.source_type,
            source_id=log.source_id,
            status=log.status,
            message=log.message,
            details=log.details or {},
            error_code=log.error_code,
            error_description=log.error_description,
            ip_address=log.ip_address,
            correlation_id=log.correlation_id,
            request_id=log.request_id,
            created_at=log.created_at,
        )
        for log in logs
    ]


# =============================================================================
# Statistics Endpoints
# =============================================================================

# Valid time ranges for statistics error count filter
TimeRange = Literal["24h", "7d", "30d", "all"]


def calculate_time_cutoff(time_range: TimeRange) -> Optional[datetime]:
    """Calculate cutoff timestamp based on time range."""
    if time_range == "all":
        return None

    now = datetime.now(timezone.utc)
    ranges = {
        "24h": timedelta(hours=24),
        "7d": timedelta(days=7),
        "30d": timedelta(days=30),
    }
    return now - ranges.get(time_range, timedelta(hours=24))


@router.get(
    "/statistics",
    response_model=AuditStatisticsResponse,
    summary="Get audit statistics",
    description="Get comprehensive audit log statistics for dashboard.",
)
async def get_audit_statistics(
    db: DBSession,
    current_user: ActiveUser,
    time_range: TimeRange = Query(
        "24h", description="Time range for error count filter: 24h, 7d, 30d, or all"
    ),
) -> AuditStatisticsResponse:
    """
    Get audit log statistics including counts, storage, and pending cleanup.

    The `time_range` parameter affects only the error/critical counts in
    `count_by_severity`. Total count and other statistics are always all-time.

    Args:
        time_range: Filter for error counts. Options:
            - "24h": Last 24 hours (default)
            - "7d": Last 7 days
            - "30d": Last 30 days
            - "all": All time (no filter)
    """
    retention_service = AuditRetentionService(db)

    # Calculate cutoff time for filtered error counts
    error_cutoff_time = calculate_time_cutoff(time_range)

    # Get statistics with time-filtered error counts
    stats = await retention_service.get_statistics(error_cutoff_time=error_cutoff_time)

    return AuditStatisticsResponse(
        total_count=stats["total_count"],
        count_by_severity=stats["count_by_severity"],
        count_by_event_type=stats["count_by_event_type"],
        oldest_entry=stats["oldest_entry"],
        newest_entry=stats["newest_entry"],
        storage_estimate_mb=stats["storage_estimate_mb"],
        pending_cleanup_count=stats["pending_cleanup_count"],
        pending_cleanup_by_severity=stats["pending_cleanup_by_severity"],
        retention_config=RetentionConfigResponse(**stats["retention_config"]),
    )


@router.get(
    "/error-rate",
    summary="Get error rate",
    description="Get error rate statistics for the specified period.",
)
async def get_error_rate(
    db: DBSession,
    current_user: ActiveUser,
    hours: int = Query(24, ge=1, le=168, description="Analysis period in hours"),
) -> Dict[str, Any]:
    """Get error rate statistics for monitoring dashboards."""
    audit_repo = AuditLogRepository(db)
    return await audit_repo.get_error_rate(hours=hours)


# =============================================================================
# Retention Management Endpoints (Admin Only)
# =============================================================================


@router.get(
    "/retention/status",
    response_model=AutoCleanupStatusResponse,
    summary="Get auto-cleanup status",
    description="Get auto-cleanup system status including next run time and preview.",
)
async def get_retention_status(
    db: DBSession,
    current_user: ActiveUser,
) -> AutoCleanupStatusResponse:
    """
    Get complete auto-cleanup system status for UI transparency.

    Returns:
        - enabled: Is auto-cleanup activated?
        - last_run: When was the last cleanup?
        - next_run: When is the next cleanup scheduled?
        - schedule: Human-readable schedule description
        - config: Current retention configuration
        - next_cleanup_preview: What would be deleted in next run?
    """
    retention_service = AuditRetentionService(db)
    config = await retention_service.get_config()

    # Get last cleanup time
    last_cleanup = config.get("last_cleanup")

    # Calculate next scheduled cleanup (daily at 03:00 UTC)
    next_run = await retention_service.get_next_scheduled_cleanup_time()

    # Simulate what would be deleted in next auto-cleanup
    dry_run_result = await retention_service.cleanup(dry_run=True)

    return AutoCleanupStatusResponse(
        enabled=config.get("enabled", False),
        last_run=last_cleanup,
        next_run=next_run.isoformat() if next_run else None,
        schedule="Täglich um 03:00 UTC",
        config=RetentionConfigResponse(**config),
        next_cleanup_preview=NextCleanupPreview(
            would_delete=dry_run_result.get("deleted_count", 0),
            breakdown=dry_run_result.get("deleted_by_severity", {}),
        ),
    )


@router.get(
    "/retention/config",
    response_model=RetentionConfigResponse,
    summary="Get retention config",
    description="Get current audit log retention configuration.",
)
async def get_retention_config(
    db: DBSession,
    current_user: ActiveUser,
) -> RetentionConfigResponse:
    """Get current retention policy configuration."""
    retention_service = AuditRetentionService(db)
    config = await retention_service.get_config()
    return RetentionConfigResponse(**config)


@router.put(
    "/retention/config",
    response_model=RetentionConfigResponse,
    summary="Update retention config",
    description="Update audit log retention configuration. Admin only.",
)
async def update_retention_config(
    config: RetentionConfigUpdate,
    db: DBSession,
    current_user: AdminUser,
) -> RetentionConfigResponse:
    """
    Update retention policy configuration.

    Only provided fields are updated. Requires admin privileges.
    """
    retention_service = AuditRetentionService(db)

    try:
        updated = await retention_service.set_config(
            enabled=config.enabled,
            default_days=config.default_days,
            severity_days=config.severity_days,
            max_records=config.max_records,
            batch_size=config.batch_size,
            preserve_emergency_stops=config.preserve_emergency_stops,
        )
        await db.commit()
        return RetentionConfigResponse(**updated)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/retention/cleanup",
    response_model=CleanupResponse,
    summary="Run retention cleanup",
    description="Manually trigger retention cleanup. Dry-run: Admin/Operator. Actual cleanup: Admin only.",
)
async def run_retention_cleanup(
    db: DBSession,
    current_user: OperatorUser,  # TODO replace isViewer with capability check
    dry_run: bool = Query(False, description="Simulate without deleting"),
    create_backup: bool = Query(True, description="Create JSON backup before deletion"),
    include_preview_events: bool = Query(
        False, description="Include event details in preview (for UI display)"
    ),
    preview_limit: int = Query(
        20, ge=1, le=100, description="Maximum number of events to include in preview"
    ),
) -> CleanupResponse:
    """
    Manually trigger audit log cleanup.

    **Permissions:**
    - dry_run=true (Preview): Admin or Operator
    - dry_run=false (Actual deletion): Admin only

    Use dry_run=true to see what would be deleted without actually deleting.
    Use include_preview_events=true to get actual event details for UI preview.

    Note: Manual cleanup works regardless of whether auto-retention is enabled.
    This allows admins to clean up logs even if automatic retention is disabled.
    """
    # Permission check based on operation type
    is_admin = current_user.role == "admin"
    is_operator = current_user.role == "operator"

    if dry_run:
        # Dry-run (preview): Admin or Operator allowed
        if not (is_admin or is_operator):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vorschau erfordert Operator- oder Admin-Rechte",
            )
    else:
        # Actual cleanup: Admin only
        if not is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Nur Administratoren können Events löschen",
            )

    retention_service = AuditRetentionService(db)

    try:
        result = await retention_service.cleanup(
            dry_run=dry_run,
            create_backup=create_backup,
            include_preview_events=include_preview_events,
            preview_limit=preview_limit,
            force=True,  # Manual cleanup always allowed, even if auto-retention disabled
        )
        if not dry_run:
            await db.commit()
        return CleanupResponse(**result)
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Cleanup failed: {str(e)}",
        )


# =============================================================================
# Reference Data Endpoints
# =============================================================================


@router.get(
    "/event-types",
    response_model=List[EventTypeInfo],
    summary="List event types",
    description="Get list of all audit event types with descriptions.",
)
async def list_event_types() -> List[EventTypeInfo]:
    """Get all available event types with descriptions for UI dropdowns."""
    event_types = [
        EventTypeInfo(
            value=AuditEventType.CONFIG_RESPONSE,
            description="Configuration response from ESP32",
            category="Config",
        ),
        EventTypeInfo(
            value=AuditEventType.CONFIG_PUBLISHED,
            description="Configuration published to ESP32",
            category="Config",
        ),
        EventTypeInfo(
            value=AuditEventType.CONFIG_FAILED,
            description="Configuration delivery failed",
            category="Config",
        ),
        EventTypeInfo(
            value=AuditEventType.LOGIN_SUCCESS,
            description="Successful user login",
            category="Auth",
        ),
        EventTypeInfo(
            value=AuditEventType.LOGIN_FAILED,
            description="Failed login attempt",
            category="Auth",
        ),
        EventTypeInfo(
            value=AuditEventType.LOGOUT,
            description="User logout",
            category="Auth",
        ),
        EventTypeInfo(
            value=AuditEventType.TOKEN_REVOKED,
            description="Authentication token revoked",
            category="Auth",
        ),
        EventTypeInfo(
            value=AuditEventType.PERMISSION_DENIED,
            description="Access permission denied",
            category="Security",
        ),
        EventTypeInfo(
            value=AuditEventType.API_KEY_INVALID,
            description="Invalid API key used",
            category="Security",
        ),
        EventTypeInfo(
            value=AuditEventType.RATE_LIMIT_EXCEEDED,
            description="Rate limit exceeded",
            category="Security",
        ),
        EventTypeInfo(
            value=AuditEventType.EMERGENCY_STOP,
            description="Emergency stop triggered",
            category="Operations",
        ),
        EventTypeInfo(
            value=AuditEventType.SERVICE_START,
            description="Service started",
            category="Operations",
        ),
        EventTypeInfo(
            value=AuditEventType.SERVICE_STOP,
            description="Service stopped",
            category="Operations",
        ),
        EventTypeInfo(
            value=AuditEventType.DEVICE_REGISTERED,
            description="New device registered",
            category="Operations",
        ),
        EventTypeInfo(
            value=AuditEventType.DEVICE_OFFLINE,
            description="Device went offline",
            category="Operations",
        ),
        # ESP Lifecycle Events (2026-01-20)
        EventTypeInfo(
            value=AuditEventType.DEVICE_DISCOVERED,
            description="New device discovered via heartbeat",
            category="Device Lifecycle",
        ),
        EventTypeInfo(
            value=AuditEventType.DEVICE_APPROVED,
            description="Device approved by administrator",
            category="Device Lifecycle",
        ),
        EventTypeInfo(
            value=AuditEventType.DEVICE_REJECTED,
            description="Device rejected by administrator",
            category="Device Lifecycle",
        ),
        EventTypeInfo(
            value=AuditEventType.DEVICE_ONLINE,
            description="Device came online after being offline",
            category="Device Lifecycle",
        ),
        EventTypeInfo(
            value=AuditEventType.DEVICE_REDISCOVERED,
            description="Previously rejected device sending heartbeats again",
            category="Device Lifecycle",
        ),
        EventTypeInfo(
            value=AuditEventType.LWT_RECEIVED,
            description="Last Will Testament received (unexpected disconnect)",
            category="Device Lifecycle",
        ),
        EventTypeInfo(
            value=AuditEventType.MQTT_ERROR,
            description="MQTT communication error",
            category="Errors",
        ),
        EventTypeInfo(
            value=AuditEventType.DATABASE_ERROR,
            description="Database operation error",
            category="Errors",
        ),
        EventTypeInfo(
            value=AuditEventType.VALIDATION_ERROR,
            description="Data validation error",
            category="Errors",
        ),
    ]
    return event_types


@router.get(
    "/severities",
    response_model=List[SeverityInfo],
    summary="List severities",
    description="Get list of all severity levels with descriptions.",
)
async def list_severities() -> List[SeverityInfo]:
    """Get all severity levels with descriptions and colors for UI."""
    return [
        SeverityInfo(
            value=AuditSeverity.INFO,
            description="Informational event",
            color="#3b82f6",  # Blue
        ),
        SeverityInfo(
            value=AuditSeverity.WARNING,
            description="Warning condition",
            color="#f59e0b",  # Amber
        ),
        SeverityInfo(
            value=AuditSeverity.ERROR,
            description="Error condition",
            color="#ef4444",  # Red
        ),
        SeverityInfo(
            value=AuditSeverity.CRITICAL,
            description="Critical system event",
            color="#dc2626",  # Dark Red
        ),
    ]


@router.get(
    "/source-types",
    response_model=List[str],
    summary="List source types",
    description="Get list of all source types.",
)
async def list_source_types() -> List[str]:
    """Get all source types for UI dropdowns."""
    return [
        AuditSourceType.ESP32,
        AuditSourceType.USER,
        AuditSourceType.SYSTEM,
        AuditSourceType.API,
        AuditSourceType.MQTT,
        AuditSourceType.SCHEDULER,
    ]


# =============================================================================
# Backup Management Endpoints (Admin Only)
# =============================================================================


@router.get(
    "/backups",
    response_model=BackupListResponse,
    summary="List audit log backups",
    description="Get list of available audit log backups. Admin only.",
)
async def list_backups(
    db: DBSession,
    current_user: AdminUser,
    include_expired: bool = Query(False, description="Include expired backups"),
) -> BackupListResponse:
    """
    List all available audit log backups.

    Backups are created automatically before cleanup operations.
    They can be used to restore accidentally deleted events.
    """
    retention_service = AuditRetentionService(db)
    backups = await retention_service.backup_service.list_backups(include_expired=include_expired)

    return BackupListResponse(
        backups=[BackupInfo(**b) for b in backups],
        total=len(backups),
    )


@router.get(
    "/backups/{backup_id}",
    response_model=BackupInfo,
    summary="Get backup details",
    description="Get details of a specific backup. Admin only.",
)
async def get_backup(
    backup_id: str,
    db: DBSession,
    current_user: AdminUser,
) -> BackupInfo:
    """Get details of a specific backup."""
    retention_service = AuditRetentionService(db)
    backup = await retention_service.backup_service.get_backup(backup_id)

    if not backup:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backup {backup_id} not found",
        )

    return BackupInfo(**backup)


@router.post(
    "/backups/{backup_id}/restore",
    response_model=BackupRestoreResponse,
    summary="Restore from backup",
    description="Restore audit log events from a backup. Admin only.",
)
async def restore_backup(
    backup_id: str,
    db: DBSession,
    current_user: AdminUser,
    delete_after_restore: bool = Query(
        True, description="Delete backup after successful restore (default: True)"
    ),
) -> BackupRestoreResponse:
    """
    Restore audit log events from a backup.

    This will re-create deleted events from the backup.
    Events that already exist will be skipped (no duplicates).

    If delete_after_restore=True (default), the backup file will be
    automatically deleted after successful restoration. This prevents
    accidentally restoring the same events multiple times.

    The restored events will have metadata marking them as restored,
    and the frontend will be notified via WebSocket to reload the event list.
    """
    retention_service = AuditRetentionService(db)

    try:
        result = await retention_service.backup_service.restore_backup(
            backup_id,
            delete_after_restore=delete_after_restore,
        )
        await db.commit()

        # Create audit log entry for restore operation
        from ...db.models.audit_log import AuditLog, AuditSeverity

        restore_audit = AuditLog(
            event_type="backup_restored",
            severity=AuditSeverity.WARNING,
            source_type="user",
            source_id=str(current_user.id),
            status="success",
            message=f"Backup restored: {result['restored_count']} events",
            details={
                "backup_id": backup_id,
                "restored_count": result["restored_count"],
                "skipped_duplicates": result["skipped_duplicates"],
                "backup_deleted": result.get("backup_deleted", False),
            },
        )
        db.add(restore_audit)
        await db.commit()

        return BackupRestoreResponse(**result)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Restore failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Restore failed: {str(e)}",
        )


@router.delete(
    "/backups/{backup_id}",
    summary="Delete backup",
    description="Delete a specific backup. Admin only.",
)
async def delete_backup(
    backup_id: str,
    db: DBSession,
    current_user: AdminUser,
) -> Dict[str, Any]:
    """Delete a specific backup file."""
    retention_service = AuditRetentionService(db)
    deleted = await retention_service.backup_service.delete_backup(backup_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backup {backup_id} not found",
        )

    return {"deleted": True, "backup_id": backup_id}


@router.post(
    "/backups/cleanup",
    summary="Cleanup expired backups",
    description="Delete all expired backups. Admin only.",
)
async def cleanup_expired_backups(
    db: DBSession,
    current_user: AdminUser,
) -> Dict[str, Any]:
    """Delete all expired backup files to free up disk space."""
    retention_service = AuditRetentionService(db)
    deleted_count = await retention_service.backup_service.cleanup_expired_backups()

    return {
        "deleted_count": deleted_count,
        "message": f"Deleted {deleted_count} expired backups",
    }


# =============================================================================
# Backup Retention Configuration Endpoints (Admin Only)
# =============================================================================


@router.get(
    "/backups/retention/config",
    response_model=BackupRetentionConfigResponse,
    summary="Get backup retention config",
    description="Get current backup retention configuration. Admin only.",
)
async def get_backup_retention_config(
    db: DBSession,
    current_user: AdminUser,
) -> BackupRetentionConfigResponse:
    """
    Get current backup retention configuration.

    Returns:
        - retention_days: Days until backup expires (0 = never expire)
        - max_backups: Maximum number of backups to keep
        - max_retention_days: Maximum allowed retention days (365)
        - never_expire_value: Value for 'never expire' (0)
    """
    retention_service = AuditRetentionService(db)
    config = retention_service.backup_service.get_retention_config()
    return BackupRetentionConfigResponse(**config)


@router.put(
    "/backups/retention/config",
    response_model=BackupRetentionConfigResponse,
    summary="Update backup retention config",
    description="Update backup retention configuration. Admin only.",
)
async def update_backup_retention_config(
    config: BackupRetentionConfigUpdate,
    db: DBSession,
    current_user: AdminUser,
) -> BackupRetentionConfigResponse:
    """
    Update backup retention configuration.

    **Options for retention_days:**
    - 0: Never expire (backups are kept forever)
    - 1-365: Backups expire after N days

    Note: This affects only NEW backups. Existing backups keep their original expiration.
    """
    retention_service = AuditRetentionService(db)

    try:
        retention_service.backup_service.set_retention_days(config.retention_days)
        updated_config = retention_service.backup_service.get_retention_config()
        return BackupRetentionConfigResponse(**updated_config)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
