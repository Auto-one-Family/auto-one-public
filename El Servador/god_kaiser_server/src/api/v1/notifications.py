"""
Notification REST API Endpoints

Phase 4A.1 + 4B + C V1.1: Notification-Stack Backend + Alert Center + Email Log
Priority: HIGH
Status: IMPLEMENTED

Endpoints:
- GET  /v1/notifications                  - List with filters
- GET  /v1/notifications/unread-count     - Badge counter
- GET  /v1/notifications/alerts/active    - Active alerts (Phase 4B)
- GET  /v1/notifications/alerts/stats     - Alert ISA-18.2 metrics (Phase 4B)
- GET  /v1/notifications/email-log        - Email sending log (Phase C V1.1)
- GET  /v1/notifications/email-log/stats  - Email statistics (Phase C V1.1)
- GET  /v1/notifications/{id}            - Single notification
- PATCH /v1/notifications/{id}/read      - Mark as read
- PATCH /v1/notifications/{id}/acknowledge - Acknowledge alert (Phase 4B)
- PATCH /v1/notifications/{id}/resolve    - Resolve alert (Phase 4B)
- PATCH /v1/notifications/resolve-all     - Resolve all unresolved alerts
- PATCH /v1/notifications/read-all       - Mark all as read
- POST /v1/notifications/send            - Admin send notification
- GET  /v1/notifications/preferences     - Get user preferences
- PUT  /v1/notifications/preferences     - Update user preferences
- POST /v1/notifications/test-email      - Test email delivery
"""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query

from ...core.metrics import (
    increment_alert_acknowledged,
    increment_alert_resolved,
    increment_notification_read,
)
from ...core.exceptions import (
    AlertInvalidStateTransition,
    EmailProviderUnavailableException,
    EmailSendException,
    NoEmailRecipientException,
    NotificationNotFoundException,
    NotificationSendFailedException,
)
from ...core.logging_config import get_logger
from ...db.models.notification import AlertStatus
from ...db.repositories.email_log_repo import EmailLogRepository
from ...db.repositories.notification_repo import (
    NotificationPreferencesRepository,
    NotificationRepository,
)
from ...schemas.common import BaseResponse, PaginationMeta
from ...schemas.notification import (
    AlertActiveListResponse,
    AlertBulkResolveResponse,
    AlertStatsResponse,
    EmailLogListResponse,
    EmailLogResponse,
    EmailLogStatsResponse,
    EmailLogStatusFilter,
    NotificationCreate,
    NotificationListResponse,
    NotificationListStatusFilter,
    NotificationPreferencesResponse,
    NotificationPreferencesUpdate,
    NotificationResponse,
    NotificationSendRequest,
    NotificationSourceBucketQuery,
    NotificationUnreadCountResponse,
    TestEmailRequest,
    TestEmailResponse,
)
from ...services.email_service import get_email_service
from ...services.notification_router import NotificationRouter
from ..deps import ActiveUser, AdminUser, DBSession

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/notifications", tags=["notifications"])


# =============================================================================
# GET /v1/notifications — List with filters
# =============================================================================


@router.get(
    "",
    response_model=NotificationListResponse,
    summary="List notifications",
    description="Get paginated notifications for the current user with optional filters.",
)
async def list_notifications(
    db: DBSession,
    user: ActiveUser,
    severity: Optional[str] = Query(None, description="Filter by severity"),
    category: Optional[str] = Query(None, description="Filter by category"),
    source: Optional[str] = Query(None, description="Filter by source"),
    source_bucket: Optional[NotificationSourceBucketQuery] = Query(
        None,
        description='Grouped source filter: "system" = manual|system|device_event|autoops',
    ),
    status: Optional[NotificationListStatusFilter] = Query(
        None,
        description="Alert lifecycle filter: active, acknowledged, resolved",
    ),
    is_read: Optional[bool] = Query(None, description="Filter by read status"),
    show_suppressed: bool = Query(
        False,
        description="When true, include audit notifications with channel=suppressed",
    ),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
):
    repo = NotificationRepository(db)
    skip = (page - 1) * page_size

    notifications, total = await repo.get_for_user(
        user_id=user.id,
        severity=severity,
        category=category,
        source=source,
        source_bucket=source_bucket,
        status=status,
        is_read=is_read,
        show_suppressed=show_suppressed,
        skip=skip,
        limit=page_size,
    )

    return NotificationListResponse(
        success=True,
        data=[NotificationResponse.model_validate(n) for n in notifications],
        pagination=PaginationMeta.from_pagination(
            page=page, page_size=page_size, total_items=total
        ),
    )


# =============================================================================
# GET /v1/notifications/unread-count — Badge counter
# =============================================================================


@router.get(
    "/unread-count",
    response_model=NotificationUnreadCountResponse,
    summary="Get unread count",
    description="Get the number of unread notifications for the badge counter.",
)
async def get_unread_count(
    db: DBSession,
    user: ActiveUser,
):
    repo = NotificationRepository(db)
    count = await repo.get_unread_count(user.id)
    highest = await repo.get_highest_unread_severity(user.id)

    return NotificationUnreadCountResponse(
        success=True,
        unread_count=count,
        highest_severity=highest,
    )


# =============================================================================
# GET /v1/notifications/alerts/active — Active alerts (Phase 4B)
# MUST be declared BEFORE /{notification_id} wildcard to avoid route shadowing
# =============================================================================


@router.get(
    "/alerts/active",
    response_model=AlertActiveListResponse,
    summary="Get active alerts",
    description="Get paginated list of active (unresolved) alerts for the current user.",
)
async def get_active_alerts(
    db: DBSession,
    user: ActiveUser,
    severity: Optional[str] = Query(None, description="Filter by severity"),
    category: Optional[str] = Query(None, description="Filter by category"),
    status: NotificationListStatusFilter = Query(
        "active",
        description="Alert status filter (active, acknowledged, resolved)",
    ),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
):
    repo = NotificationRepository(db)
    skip = (page - 1) * page_size

    alerts, total = await repo.get_alerts_by_status(
        status=status,
        user_id=user.id,
        severity=severity,
        category=category,
        skip=skip,
        limit=page_size,
    )

    return AlertActiveListResponse(
        success=True,
        data=[NotificationResponse.model_validate(a) for a in alerts],
        pagination=PaginationMeta.from_pagination(
            page=page, page_size=page_size, total_items=total
        ),
    )


# =============================================================================
# GET /v1/notifications/alerts/stats — Alert ISA-18.2 metrics (Phase 4B)
# =============================================================================


@router.get(
    "/alerts/stats",
    response_model=AlertStatsResponse,
    summary="Get alert statistics",
    description="Get ISA-18.2 alert lifecycle statistics (MTTA, MTTR, counts).",
)
async def get_alert_stats(
    db: DBSession,
    user: ActiveUser,
):
    repo = NotificationRepository(db)
    stats = await repo.get_alert_stats(user_id=user.id)

    return AlertStatsResponse(success=True, **stats)


# =============================================================================
# GET /v1/notifications/preferences — Get user preferences
# MUST be declared BEFORE /{notification_id} wildcard to avoid route shadowing
# =============================================================================


@router.get(
    "/preferences",
    response_model=NotificationPreferencesResponse,
    summary="Get preferences",
    description="Get notification preferences for the current user.",
)
async def get_preferences(
    db: DBSession,
    user: ActiveUser,
):
    repo = NotificationPreferencesRepository(db)
    prefs = await repo.get_or_create(user.id)
    await db.commit()
    return NotificationPreferencesResponse.model_validate(prefs)


# =============================================================================
# GET /v1/notifications/email-log — Email sending log (Phase C V1.1)
# MUST be declared BEFORE /{notification_id} wildcard to avoid route shadowing
# =============================================================================


@router.get(
    "/email-log",
    response_model=EmailLogListResponse,
    summary="Get email log",
    description="Get paginated email sending log with optional filters.",
)
async def get_email_log(
    db: DBSession,
    user: AdminUser,
    status: Optional[EmailLogStatusFilter] = Query(
        None, description="Filter by status (pending, sent, failed, permanently_failed)"
    ),
    date_from: Optional[datetime] = Query(None, description="Filter from date (ISO 8601)"),
    date_to: Optional[datetime] = Query(None, description="Filter to date (ISO 8601)"),
    template: Optional[str] = Query(None, description="Filter by template (partial match)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
):
    repo = EmailLogRepository(db)
    skip = (page - 1) * page_size

    logs, total = await repo.get_filtered(
        status=status,
        date_from=date_from,
        date_to=date_to,
        template=template,
        skip=skip,
        limit=page_size,
    )

    return EmailLogListResponse(
        success=True,
        data=[EmailLogResponse.model_validate(log) for log in logs],
        pagination=PaginationMeta.from_pagination(
            page=page, page_size=page_size, total_items=total
        ),
    )


# =============================================================================
# GET /v1/notifications/email-log/stats — Email statistics (Phase C V1.1)
# =============================================================================


@router.get(
    "/email-log/stats",
    response_model=EmailLogStatsResponse,
    summary="Get email statistics",
    description="Get email sending statistics (total, sent, failed, by provider).",
)
async def get_email_log_stats(
    db: DBSession,
    user: AdminUser,
):
    repo = EmailLogRepository(db)
    stats = await repo.get_stats()

    return EmailLogStatsResponse(success=True, **stats)


# =============================================================================
# GET /v1/notifications/{id} — Single notification
# =============================================================================


@router.get(
    "/{notification_id}",
    response_model=NotificationResponse,
    summary="Get notification",
    description="Get a single notification by ID.",
)
async def get_notification(
    notification_id: uuid.UUID,
    db: DBSession,
    user: ActiveUser,
):
    repo = NotificationRepository(db)
    notification = await repo.get_by_id(notification_id)

    if not notification or notification.user_id != user.id:
        raise NotificationNotFoundException(str(notification_id))

    return NotificationResponse.model_validate(notification)


# =============================================================================
# PATCH /v1/notifications/{id}/read — Mark as read
# =============================================================================


@router.patch(
    "/{notification_id}/read",
    response_model=NotificationResponse,
    summary="Mark as read",
    description="Mark a single notification as read.",
)
async def mark_notification_read(
    notification_id: uuid.UUID,
    db: DBSession,
    user: ActiveUser,
):
    repo = NotificationRepository(db)
    notification = await repo.mark_as_read(notification_id, user.id)

    if not notification:
        raise NotificationNotFoundException(str(notification_id))

    await db.commit()
    increment_notification_read()

    # Broadcast notification_updated + updated unread count
    router_service = NotificationRouter(db)
    await router_service.broadcast_notification_updated(notification)
    await router_service.broadcast_unread_count(user.id)

    return NotificationResponse.model_validate(notification)


# =============================================================================
# PATCH /v1/notifications/{id}/acknowledge — Acknowledge alert (Phase 4B)
# =============================================================================


@router.patch(
    "/{notification_id}/acknowledge",
    response_model=NotificationResponse,
    summary="Acknowledge alert",
    description="Acknowledge an active alert (ISA-18.2: active → acknowledged).",
)
async def acknowledge_alert(
    notification_id: uuid.UUID,
    db: DBSession,
    user: ActiveUser,
):
    repo = NotificationRepository(db)

    # Pre-check: fetch current state to detect invalid transitions
    existing = await repo.get_by_id(notification_id)
    if not existing or existing.user_id != user.id:
        raise NotificationNotFoundException(str(notification_id))

    valid_targets = AlertStatus.VALID_TRANSITIONS.get(existing.status, set())
    if AlertStatus.ACKNOWLEDGED not in valid_targets:
        raise AlertInvalidStateTransition(
            current_status=existing.status,
            target_status=AlertStatus.ACKNOWLEDGED,
        )

    notification = await repo.acknowledge_alert(
        notification_id=notification_id,
        user_id=user.id,
        acknowledging_user_id=user.id,
    )

    if not notification:
        raise NotificationNotFoundException(str(notification_id))

    await db.commit()
    increment_alert_acknowledged(notification.severity)

    logger.info(
        "Alert acknowledged via REST API",
        extra={
            "notification_id": str(notification.id),
            "alert_status": notification.status,
        },
    )

    # Broadcast updated status via WebSocket
    router_service = NotificationRouter(db)
    await router_service.broadcast_notification_updated(notification)
    await router_service.broadcast_unread_count(user.id)

    return NotificationResponse.model_validate(notification)


# =============================================================================
# PATCH /v1/notifications/{id}/resolve — Resolve alert (Phase 4B)
# =============================================================================


@router.patch(
    "/{notification_id}/resolve",
    response_model=NotificationResponse,
    summary="Resolve alert",
    description="Resolve an alert (ISA-18.2: active/acknowledged → resolved).",
)
async def resolve_alert(
    notification_id: uuid.UUID,
    db: DBSession,
    user: ActiveUser,
):
    repo = NotificationRepository(db)

    # Pre-check: fetch current state to detect invalid transitions
    existing = await repo.get_by_id(notification_id)
    if not existing or existing.user_id != user.id:
        raise NotificationNotFoundException(str(notification_id))

    valid_targets = AlertStatus.VALID_TRANSITIONS.get(existing.status, set())
    if AlertStatus.RESOLVED not in valid_targets:
        raise AlertInvalidStateTransition(
            current_status=existing.status,
            target_status=AlertStatus.RESOLVED,
        )

    notification = await repo.resolve_alert(
        notification_id=notification_id,
        user_id=user.id,
    )

    if not notification:
        raise NotificationNotFoundException(str(notification_id))

    await db.commit()
    increment_alert_resolved(notification.severity, resolution_type="manual")

    logger.info(
        "Alert resolved via REST API",
        extra={
            "notification_id": str(notification.id),
            "alert_status": notification.status,
        },
    )

    # Broadcast updated status via WebSocket
    router_service = NotificationRouter(db)
    await router_service.broadcast_notification_updated(notification)
    await router_service.broadcast_unread_count(user.id)

    return NotificationResponse.model_validate(notification)


# =============================================================================
# PATCH /v1/notifications/resolve-all — Resolve all unresolved alerts
# =============================================================================


@router.patch(
    "/resolve-all",
    response_model=AlertBulkResolveResponse,
    summary="Resolve all unresolved alerts",
    description="Resolve all active/acknowledged alerts for the current user.",
)
async def resolve_all_alerts(
    db: DBSession,
    user: ActiveUser,
):
    repo = NotificationRepository(db)
    resolved_count = await repo.resolve_all_alerts(user.id)
    await db.commit()

    # Broadcast updated unread count (bulk operation; no per-item events).
    router_service = NotificationRouter(db)
    await router_service.broadcast_unread_count(user.id)

    return AlertBulkResolveResponse(
        success=True,
        message=f"Resolved {resolved_count} alerts",
        resolved_count=resolved_count,
    )


# =============================================================================
# PATCH /v1/notifications/read-all — Mark all as read
# =============================================================================


@router.patch(
    "/read-all",
    response_model=BaseResponse,
    summary="Mark all as read",
    description="Mark all unread notifications as read for the current user.",
)
async def mark_all_read(
    db: DBSession,
    user: ActiveUser,
):
    repo = NotificationRepository(db)
    count = await repo.mark_all_as_read(user.id)
    await db.commit()
    increment_notification_read(count)

    # Broadcast updated unread count (notification_updated not sent per-item for bulk)
    router_service = NotificationRouter(db)
    await router_service.broadcast_unread_count(user.id)

    return BaseResponse(
        success=True,
        message=f"Marked {count} notifications as read",
    )


# =============================================================================
# POST /v1/notifications/send — Admin send notification
# =============================================================================


@router.post(
    "/send",
    response_model=NotificationResponse,
    summary="Send notification (Admin)",
    description="Manually send a notification to all users. Admin only.",
)
async def send_notification(
    request: NotificationSendRequest,
    db: DBSession,
    user: AdminUser,
):
    notification_create = NotificationCreate(
        user_id=None,  # Broadcast to all
        channel=request.channel,
        severity=request.severity,
        category=request.category,
        title=request.title,
        body=request.body,
        metadata=request.metadata,
        source=request.source,
    )

    router_service = NotificationRouter(db)
    result = await router_service.route(notification_create)

    if not result:
        raise NotificationSendFailedException("Notification was deduplicated or no users found")

    return NotificationResponse.model_validate(result)


# =============================================================================
# PUT /v1/notifications/preferences — Update user preferences
# =============================================================================


@router.put(
    "/preferences",
    response_model=NotificationPreferencesResponse,
    summary="Update preferences",
    description="Update notification preferences for the current user.",
)
async def update_preferences(
    request: NotificationPreferencesUpdate,
    db: DBSession,
    user: ActiveUser,
):
    repo = NotificationPreferencesRepository(db)

    update_data = request.model_dump(exclude_none=True)
    prefs = await repo.update(user.id, **update_data)
    await db.commit()

    return NotificationPreferencesResponse.model_validate(prefs)


# =============================================================================
# POST /v1/notifications/test-email — Test email delivery
# =============================================================================


@router.post(
    "/test-email",
    response_model=TestEmailResponse,
    summary="Test email",
    description="Send a test email to verify email configuration.",
)
async def test_email(
    request: TestEmailRequest,
    db: DBSession,
    user: ActiveUser,
):
    email_service = get_email_service()

    if not email_service.is_available:
        raise EmailProviderUnavailableException()

    # Determine recipient
    recipient = request.email
    if not recipient:
        # Try user preferences, then user account email
        prefs_repo = NotificationPreferencesRepository(db)
        prefs = await prefs_repo.get_for_user(user.id)
        if prefs and prefs.email_address:
            recipient = prefs.email_address
        else:
            recipient = user.email

    if not recipient:
        raise NoEmailRecipientException()

    provider = email_service.provider_name
    success = await email_service.send_test_email(recipient)

    # Log email send attempt (Phase C V1.1)
    email_log_repo = EmailLogRepository(db)
    await email_log_repo.log_send(
        to_address=recipient,
        subject="AutomationOne Test Email",
        provider=provider,
        status="sent" if success else "failed",
        template="test_email",
        error_message=None if success else "Check server logs for details.",
    )
    await db.commit()

    if not success:
        raise EmailSendException(provider=provider, reason="Check server logs for details.")

    return TestEmailResponse(
        success=True,
        message=f"Test email sent successfully via {provider}",
        provider=provider,
        recipient=recipient,
    )
