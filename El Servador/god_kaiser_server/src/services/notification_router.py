"""
Notification Router Service: Central Notification Routing

Phase 4A.1: Notification-Stack Backend
Priority: HIGH
Status: IMPLEMENTED

Every notification goes through this service:
1. ALWAYS persist to DB
2. Load user preferences
3. WebSocket broadcast (notification_new)
4. Email based on severity + quiet hours + digest rules
5. Optional webhook

Routing Rules (ISA-18.2):
- Critical → immediate email
- Warning (first of day) → immediate email, then → digest queue
- Info → no email
"""

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logging_config import get_logger
from ..core.metrics import (
    increment_notification_created,
    increment_notification_deduplicated,
    increment_notification_suppressed,
    increment_ws_notification_broadcast,
)
from ..db.models.notification import Notification, NotificationSeverity
from ..db.repositories.email_log_repo import EmailLogRepository
from ..db.repositories.notification_repo import (
    NotificationPreferencesRepository,
    NotificationRepository,
)
from ..db.repositories.user_repo import UserRepository
from ..schemas.notification import NotificationCreate
from ..websocket.manager import WebSocketManager
from .email_service import EmailService, get_email_service

logger = get_logger(__name__)


class NotificationRouter:
    """
    Central notification routing service.

    All notifications flow through route() which handles:
    - DB persistence
    - Deduplication (configurable window per source)
    - Cascade suppression (parent_notification_id)
    - WebSocket broadcast
    - Email delivery (severity-based)
    """

    # Alert-Storm fix: configurable dedup windows per source (seconds).
    # Error sources get longer windows to prevent alert storms.
    # ISA-18.2 target: < 6 alerts/hour/operator.
    DEDUP_WINDOWS: dict[str, int] = {
        "mqtt_handler": 300,  # 5 min — MQTT errors are repetitive
        "sensor_threshold": 120,  # 2 min — threshold alerts
        "device_event": 300,  # 5 min — device errors
        "logic_engine": 120,  # 2 min — rule evaluation
        "system": 300,  # 5 min — system errors
    }
    DEDUP_WINDOW_DEFAULT: int = 60  # 1 min default

    def __init__(
        self,
        session: AsyncSession,
        email_service: Optional[EmailService] = None,
    ):
        self.session = session
        self.notification_repo = NotificationRepository(session)
        self.preferences_repo = NotificationPreferencesRepository(session)
        self.user_repo = UserRepository(session)
        self.email_log_repo = EmailLogRepository(session)
        self.email_service = email_service or get_email_service()

    async def route(self, notification: NotificationCreate) -> Optional[Notification]:
        """
        Route a notification through all channels.

        Args:
            notification: NotificationCreate schema with all details

        Returns:
            Persisted Notification model, or None if deduplicated
        """
        user_id = notification.user_id

        # If no user_id, broadcast to all users
        if user_id is None:
            # Dedup for broadcast: check if active notification with same
            # correlation_id already exists (prevents duplicate Grafana alerts)
            if notification.correlation_id:
                is_duplicate = await self.notification_repo.check_correlation_duplicate(
                    correlation_id=notification.correlation_id,
                )
                if is_duplicate:
                    logger.debug(
                        f"Broadcast deduplicated by correlation_id: " f"'{notification.title}'"
                    )
                    increment_notification_deduplicated()
                    return None
            return await self._broadcast_to_all(notification)

        # Step 0: Title-based deduplication (only when no fingerprint;
        # fingerprint path uses atomic INSERT with ON CONFLICT in Step 1 — FIX-F5)
        if not notification.fingerprint:
            window = self.DEDUP_WINDOWS.get(notification.source, self.DEDUP_WINDOW_DEFAULT)
            is_duplicate = await self.notification_repo.check_duplicate(
                user_id=user_id,
                source=notification.source,
                category=notification.category,
                title=notification.title,
                window_seconds=window,
            )
            if is_duplicate:
                logger.debug(
                    f"Notification deduplicated: '{notification.title}' for user {user_id}"
                )
                increment_notification_deduplicated()
                return None

        # Step 1: ALWAYS persist to DB
        create_kwargs = dict(
            user_id=user_id,
            channel=notification.channel,
            severity=notification.severity,
            category=notification.category,
            title=notification.title,
            body=notification.body,
            extra_data=notification.metadata,
            source=notification.source,
            parent_notification_id=notification.parent_notification_id,
            fingerprint=notification.fingerprint,
        )
        # Phase 4B: Add correlation_id if provided
        if notification.correlation_id:
            create_kwargs["correlation_id"] = notification.correlation_id

        # FIX-F5: Atomic INSERT with ON CONFLICT DO NOTHING for fingerprint notifications.
        # Eliminates Check-then-Act race condition on the partial unique index.
        if create_kwargs.get("fingerprint"):
            db_notification, created = await self.notification_repo.create_with_fingerprint_dedup(
                create_kwargs
            )
            if not created:
                logger.debug(
                    "Notification fingerprint dedup (atomic): %s",
                    create_kwargs["fingerprint"],
                )
                increment_notification_deduplicated()
                # AUT-561: Track occurrence_count for repeated safety/threshold events
                if db_notification is not None:
                    existing_data = db_notification.extra_data or {}
                    db_notification.extra_data = {
                        **existing_data,
                        "occurrence_count": existing_data.get("occurrence_count", 1) + 1,
                    }
                    await self.session.commit()
                return db_notification
        else:
            db_notification = await self.notification_repo.create(**create_kwargs)

        logger.info(
            "Notification created: id=%s severity=%s source=%s title=%s",
            str(db_notification.id),
            notification.severity,
            notification.source,
            notification.title,
            extra={
                "notification_id": str(db_notification.id),
                "alert_status": db_notification.status,
            },
        )
        increment_notification_created(
            severity=notification.severity,
            category=notification.category,
            source=notification.source,
        )

        # Step 2: Load user preferences
        prefs = await self.preferences_repo.get_or_create(user_id)

        # Step 3: WebSocket broadcast
        if prefs.websocket_enabled:
            await self._broadcast_websocket(db_notification)
            await self.broadcast_unread_count(user_id)

        # Step 4: Email routing (based on severity + quiet hours + digest)
        if prefs.email_enabled and self.email_service.is_available:
            await self._route_email(db_notification, prefs)

        # Step 5: Commit the session
        await self.session.commit()

        return db_notification

    async def _broadcast_to_all(self, notification: NotificationCreate) -> Optional[Notification]:
        """Broadcast notification to all users (system-wide alerts)."""
        # Get all active users
        users = await self.user_repo.get_active_users()
        first_notification = None

        for user in users:
            user_notification = NotificationCreate(
                user_id=user.id,
                channel=notification.channel,
                severity=notification.severity,
                category=notification.category,
                title=notification.title,
                body=notification.body,
                metadata=notification.metadata,
                source=notification.source,
                parent_notification_id=notification.parent_notification_id,
                correlation_id=notification.correlation_id,
                fingerprint=notification.fingerprint,
            )
            result = await self.route(user_notification)
            if result and first_notification is None:
                first_notification = result

        return first_notification

    async def _broadcast_websocket(self, notification: Notification) -> None:
        """Broadcast notification via WebSocket."""
        try:
            ws_manager = await WebSocketManager.get_instance()
            data = {
                "id": str(notification.id),
                "user_id": notification.user_id,
                "channel": notification.channel,
                "severity": notification.severity,
                "category": notification.category,
                "title": notification.title,
                "body": notification.body,
                "source": notification.source,
                "metadata": notification.extra_data,
                "is_read": notification.is_read,
                "created_at": (
                    notification.created_at.isoformat() if notification.created_at else None
                ),
                # Phase 4B: Alert lifecycle fields
                "status": notification.status,
                "parent_notification_id": (
                    str(notification.parent_notification_id)
                    if notification.parent_notification_id
                    else None
                ),
                "correlation_id": notification.correlation_id,
            }
            await ws_manager.broadcast("notification_new", data)
            increment_ws_notification_broadcast("notification_new")
            logger.info(
                "WebSocket broadcast notification_new user_id=%s",
                notification.user_id,
                extra={
                    "notification_id": str(notification.id),
                    "alert_status": notification.status,
                    "ws_event_type": "notification_new",
                },
            )
        except Exception as e:
            # WebSocket failure MUST NOT block notification processing
            logger.error(f"WebSocket broadcast failed: {e}")

    async def _route_email(self, notification: Notification, prefs) -> None:
        """
        Route email based on severity + ISA-18.2 rules.

        - Critical → immediate email
        - Warning (first of day for this source) → immediate, rest → digest queue
        - Info → no email
        """
        severity = notification.severity

        # Check if severity is in user's email_severities list
        email_severities = prefs.email_severities or ["critical", "warning"]
        if severity not in email_severities:
            return

        # Check quiet hours
        if self._is_quiet_hours(prefs):
            # During quiet hours, only send critical
            if severity != NotificationSeverity.CRITICAL:
                logger.debug(f"Email suppressed (quiet hours): {notification.title}")
                return

        # Get recipient email
        recipient = await self._get_email_address(notification.user_id, prefs)
        if not recipient:
            return

        # Route by severity
        if severity == NotificationSeverity.CRITICAL:
            # Critical → always immediate email
            await self._send_critical_email(notification, recipient)

        elif severity == NotificationSeverity.WARNING:
            # Warning → first of day immediate, rest → digest queue
            today_count = await self.notification_repo.count_today_warnings(
                user_id=notification.user_id,
                source=notification.source,
            )
            if today_count <= 1:
                # First warning of the day → send immediately
                await self._send_critical_email(notification, recipient)
            # Subsequent warnings → handled by DigestService

    def _is_quiet_hours(self, prefs) -> bool:
        """Check if current time is within quiet hours."""
        if not prefs.quiet_hours_enabled:
            return False

        try:
            now = datetime.now(timezone.utc).time()
            start_parts = prefs.quiet_hours_start.split(":")
            end_parts = prefs.quiet_hours_end.split(":")

            from datetime import time as dt_time

            start = dt_time(int(start_parts[0]), int(start_parts[1]))
            end = dt_time(int(end_parts[0]), int(end_parts[1]))

            if start <= end:
                return start <= now <= end
            else:
                # Overnight range (e.g., 22:00 - 07:00)
                return now >= start or now <= end
        except Exception as e:
            logger.warning(f"Error checking quiet hours: {e}")
            return False

    async def _get_email_address(self, user_id: int, prefs) -> Optional[str]:
        """Get the email address for notifications."""
        if prefs.email_address:
            return prefs.email_address

        user = await self.user_repo.get_by_id(user_id)
        if user and user.email:
            return user.email

        return None

    async def _send_critical_email(self, notification: Notification, recipient: str) -> None:
        """Send an immediate alert email (non-blocking)."""
        provider = self.email_service.provider_name
        error_message = None
        try:
            success = await self.email_service.send_critical_alert(
                to=recipient,
                title=notification.title,
                body=notification.body or "",
                severity=notification.severity,
                source=notification.source,
                category=notification.category,
                metadata=notification.extra_data,
            )
            if success:
                logger.info(f"Alert email sent to {recipient}: {notification.title}")
            else:
                error_message = "Email service returned failure"
                logger.warning(f"Alert email failed for {recipient}: {notification.title}")
        except Exception as e:
            # Email failure MUST NOT block notification processing
            success = False
            error_message = str(e)
            logger.error(f"Email delivery error: {e}")

        # Log email send attempt + update notification metadata (Phase C V1.1)
        try:
            await self.email_log_repo.log_send(
                to_address=recipient,
                subject=f"[{notification.severity.upper()}] {notification.title}",
                provider=provider,
                status="sent" if success else "failed",
                notification_id=notification.id,
                template="critical_alert",
                error_message=error_message,
            )
            # Enrich notification extra_data with email status for frontend display
            extra = dict(notification.extra_data or {})
            extra["email_status"] = "sent" if success else "failed"
            extra["email_provider"] = provider
            notification.extra_data = extra
            await self.broadcast_notification_updated(notification)
        except Exception as e:
            logger.error(f"Failed to log email send: {e}")

    async def suppress_dependent_alerts(
        self,
        root_notification: Notification,
        correlation_prefix: str,
    ) -> int:
        """
        Group dependent alerts under a root-cause notification.

        ISA-18.2 Root-Cause Grouping — reduces alarm fatigue by showing
        dependent alerts as children of the root cause. For example, when
        an ESP goes offline (MQTT disconnect), all subsequent sensor threshold
        alerts for that ESP are grouped under the offline notification.

        Args:
            root_notification: The root-cause notification
            correlation_prefix: Prefix to match dependent alerts' correlation_id
                (e.g., "threshold_AABBCCDD" matches all sensor alerts for that ESP)

        Returns:
            Number of alerts grouped under root
        """
        count = await self.notification_repo.group_under_parent(
            parent_notification_id=root_notification.id,
            correlation_prefix=correlation_prefix,
        )

        if count > 0:
            logger.info(
                f"Root-cause suppression: {count} dependent alert(s) grouped under "
                f"notification {root_notification.id} (prefix={correlation_prefix})"
            )
            increment_notification_suppressed(reason="root_cause_grouping")

        return count

    async def persist_suppressed(self, notification: NotificationCreate) -> None:
        """
        Persist a suppressed alert for ISA-18.2 audit trail.

        Suppressed alerts are stored as is_read=True with channel="suppressed".
        No WebSocket broadcast, no email delivery.
        When user_id is None, creates one record per active user (like _broadcast_to_all).
        """
        user_ids: List[int] = []

        if notification.user_id is not None:
            user_ids = [notification.user_id]
        else:
            users = await self.user_repo.get_active_users()
            user_ids = [u.id for u in users]

        if not user_ids:
            logger.warning("No active users found for suppressed alert persistence")
            return

        for uid in user_ids:
            create_kwargs = dict(
                user_id=uid,
                channel="suppressed",
                severity=notification.severity,
                category=notification.category,
                title=notification.title,
                body=notification.body,
                extra_data=notification.metadata,
                source=notification.source,
                is_read=True,
            )
            # Phase 4B: Preserve correlation_id for audit trail
            if notification.correlation_id:
                create_kwargs["correlation_id"] = notification.correlation_id
            await self.notification_repo.create(**create_kwargs)

        increment_notification_suppressed(
            reason=(
                notification.metadata.get("suppression_reason", "unknown")
                if notification.metadata
                else "unknown"
            )
        )
        logger.debug(
            f"Suppressed alert persisted for {len(user_ids)} user(s): '{notification.title}'"
        )

    async def broadcast_notification_updated(self, notification: Notification) -> None:
        """Broadcast notification_updated event via WebSocket (e.g., after mark-as-read)."""
        try:
            ws_manager = await WebSocketManager.get_instance()
            data = {
                "id": str(notification.id),
                "user_id": notification.user_id,
                "title": notification.title,
                "body": notification.body,
                "source": notification.source,
                "category": notification.category,
                "metadata": notification.extra_data,
                "correlation_id": notification.correlation_id,
                "updated_at": (
                    notification.updated_at.isoformat() if notification.updated_at else None
                ),
                "is_read": notification.is_read,
                "is_archived": notification.is_archived,
                "read_at": notification.read_at.isoformat() if notification.read_at else None,
                # Phase 4B: Alert lifecycle fields
                "status": notification.status,
                "acknowledged_at": (
                    notification.acknowledged_at.isoformat()
                    if notification.acknowledged_at
                    else None
                ),
                "acknowledged_by": notification.acknowledged_by,
                "resolved_at": (
                    notification.resolved_at.isoformat() if notification.resolved_at else None
                ),
            }
            await ws_manager.broadcast("notification_updated", data)
            increment_ws_notification_broadcast("notification_updated")
            logger.info(
                "WebSocket broadcast notification_updated id=%s",
                str(notification.id),
                extra={
                    "notification_id": str(notification.id),
                    "alert_status": notification.status,
                    "ws_event_type": "notification_updated",
                },
            )
        except Exception as e:
            logger.error(f"Failed to broadcast notification_updated: {e}")

    async def broadcast_unread_count(self, user_id: int) -> None:
        """Broadcast updated unread count via WebSocket."""
        try:
            count = await self.notification_repo.get_unread_count(user_id)
            highest = await self.notification_repo.get_highest_unread_severity(user_id)

            ws_manager = await WebSocketManager.get_instance()
            await ws_manager.broadcast(
                "notification_unread_count",
                {
                    "user_id": user_id,
                    "unread_count": count,
                    "highest_severity": highest,
                },
            )
            increment_ws_notification_broadcast("notification_unread_count")
        except Exception as e:
            logger.error(f"Failed to broadcast unread count: {e}")
