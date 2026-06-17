"""
Notification Repository: CRUD + Filtered Queries

Phase 4A.1: Notification-Stack Backend
Priority: HIGH
Status: IMPLEMENTED
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional, Tuple

from sqlalchemy import String, and_, case, cast, desc, func, not_, select, text, update
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import CompileError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.notification import (
    AlertStatus,
    Notification,
    NotificationPreferences,
    NotificationSeverity,
)
from .base_repo import BaseRepository


class NotificationRepository(BaseRepository[Notification]):
    """Repository for notification CRUD and filtered queries."""

    def __init__(self, session: AsyncSession):
        super().__init__(Notification, session)

    async def get_for_user(
        self,
        user_id: int,
        severity: Optional[str] = None,
        category: Optional[str] = None,
        source: Optional[str] = None,
        source_bucket: Optional[str] = None,
        status: Optional[str] = None,
        is_read: Optional[bool] = None,
        show_suppressed: bool = False,
        skip: int = 0,
        limit: int = 50,
    ) -> Tuple[List[Notification], int]:
        """
        Get paginated notifications for a user with optional filters.

        Returns:
            Tuple of (notifications, total_count)
        """
        conditions = [Notification.user_id == user_id, Notification.is_archived == False]

        if severity is not None:
            conditions.append(Notification.severity == severity)
        if category is not None:
            conditions.append(Notification.category == category)
        if source_bucket == "system":
            conditions.append(
                Notification.source.in_(["manual", "system", "device_event", "autoops"])
            )
        elif source is not None:
            conditions.append(Notification.source == source)
        if status is not None:
            conditions.append(Notification.status == status)
        if is_read is not None:
            conditions.append(Notification.is_read == is_read)
        if not show_suppressed:
            conditions.append(not_(Notification.channel == "suppressed"))

        where_clause = and_(*conditions)

        # Count
        count_stmt = select(func.count()).select_from(Notification).where(where_clause)
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar_one()

        # Data
        data_stmt = (
            select(Notification)
            .where(where_clause)
            .order_by(desc(Notification.created_at))
            .offset(skip)
            .limit(limit)
        )
        data_result = await self.session.execute(data_stmt)
        notifications = list(data_result.scalars().all())

        return notifications, total

    async def get_unread_count(self, user_id: int) -> int:
        """Get count of unread, non-archived notifications for a user."""
        stmt = (
            select(func.count())
            .select_from(Notification)
            .where(
                and_(
                    Notification.user_id == user_id,
                    Notification.is_read == False,
                    Notification.is_archived == False,
                )
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def get_highest_unread_severity(self, user_id: int) -> Optional[str]:
        """Get the highest severity among unread notifications."""
        severity_order = {
            NotificationSeverity.CRITICAL: 0,
            NotificationSeverity.WARNING: 1,
            NotificationSeverity.INFO: 2,
        }

        stmt = (
            select(Notification.severity)
            .where(
                and_(
                    Notification.user_id == user_id,
                    Notification.is_read == False,
                    Notification.is_archived == False,
                )
            )
            .distinct()
        )
        result = await self.session.execute(stmt)
        severities = [row[0] for row in result.all()]

        if not severities:
            return None

        return min(severities, key=lambda s: severity_order.get(s, 99))

    async def mark_as_read(
        self, notification_id: uuid.UUID, user_id: int
    ) -> Optional[Notification]:
        """Mark a single notification as read."""
        stmt = select(Notification).where(
            and_(
                Notification.id == notification_id,
                Notification.user_id == user_id,
            )
        )
        result = await self.session.execute(stmt)
        notification = result.scalar_one_or_none()

        if notification and not notification.is_read:
            notification.is_read = True
            notification.read_at = datetime.now(timezone.utc)
            await self.session.flush()
            await self.session.refresh(notification)

        return notification

    async def mark_all_as_read(self, user_id: int) -> int:
        """Mark all unread notifications as read for a user. Returns count updated."""
        now = datetime.now(timezone.utc)
        stmt = (
            update(Notification)
            .where(
                and_(
                    Notification.user_id == user_id,
                    Notification.is_read == False,
                    Notification.is_archived == False,
                )
            )
            .values(is_read=True, read_at=now, updated_at=now)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount

    async def get_pending_digest_notifications(
        self,
        user_id: int,
        min_count: int = 3,
    ) -> List[Notification]:
        """Get warning notifications not yet sent in a digest."""
        stmt = (
            select(Notification)
            .where(
                and_(
                    Notification.user_id == user_id,
                    Notification.severity == NotificationSeverity.WARNING,
                    Notification.digest_sent == False,
                    Notification.is_archived == False,
                )
            )
            .order_by(Notification.created_at)
        )
        result = await self.session.execute(stmt)
        notifications = list(result.scalars().all())

        if len(notifications) < min_count:
            return []

        return notifications

    async def mark_digest_sent(self, notification_ids: List[uuid.UUID]) -> int:
        """Mark notifications as included in a digest email."""
        if not notification_ids:
            return 0
        stmt = (
            update(Notification)
            .where(Notification.id.in_(notification_ids))
            .values(digest_sent=True, updated_at=datetime.now(timezone.utc))
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount

    async def check_duplicate(
        self,
        user_id: int,
        source: str,
        category: str,
        title: str,
        window_seconds: int = 60,
    ) -> bool:
        """Check if a similar active notification exists within the dedup window."""
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
        stmt = (
            select(func.count())
            .select_from(Notification)
            .where(
                and_(
                    Notification.user_id == user_id,
                    Notification.source == source,
                    Notification.category == category,
                    Notification.title == title,
                    Notification.created_at >= cutoff,
                    Notification.status.in_([AlertStatus.ACTIVE, AlertStatus.ACKNOWLEDGED]),
                )
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one() > 0

    async def check_fingerprint_duplicate(self, fingerprint: str) -> bool:
        """Check if an active/acknowledged notification with this fingerprint exists."""
        stmt = (
            select(func.count())
            .select_from(Notification)
            .where(
                and_(
                    Notification.fingerprint == fingerprint,
                    Notification.status.in_([AlertStatus.ACTIVE, AlertStatus.ACKNOWLEDGED]),
                )
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one() > 0

    async def create_with_fingerprint_dedup(
        self,
        notification_data: dict,
    ) -> tuple[Optional[Notification], bool]:
        """
        Atomic INSERT with ON CONFLICT DO NOTHING against the partial unique index
        ix_notifications_fingerprint_unique.

        Returns (notification, created):
        - created=True  -> new row inserted
        - created=False -> duplicate detected, existing active/acknowledged row returned

        Only call when fingerprint is set in notification_data.
        Falls back to sequential check-then-insert on non-PostgreSQL dialects (test env).
        """
        try:
            stmt = (
                postgresql.insert(Notification)
                .values(**notification_data)
                .on_conflict_do_nothing(
                    index_elements=["fingerprint"],
                    index_where=text("fingerprint IS NOT NULL"),
                )
                .returning(Notification)
            )
            result = await self.session.execute(stmt)
            row = result.fetchone()

            if row is not None:
                notification = row[0]
                await self.session.refresh(notification)
                return notification, True

            # ON CONFLICT: duplicate — load existing active/acknowledged row
            dup_stmt = (
                select(Notification)
                .where(
                    and_(
                        Notification.fingerprint == notification_data["fingerprint"],
                        Notification.status.in_([AlertStatus.ACTIVE, AlertStatus.ACKNOWLEDGED]),
                    )
                )
                .limit(1)
            )
            dup_result = await self.session.execute(dup_stmt)
            return dup_result.scalar_one_or_none(), False

        except CompileError:
            # Non-PostgreSQL dialect fallback (SQLite in test environment).
            # Sequential check-then-insert — no race-condition protection.
            is_dup = await self.check_fingerprint_duplicate(notification_data["fingerprint"])
            if is_dup:
                dup_stmt = (
                    select(Notification)
                    .where(
                        and_(
                            Notification.fingerprint == notification_data["fingerprint"],
                            Notification.status.in_([AlertStatus.ACTIVE, AlertStatus.ACKNOWLEDGED]),
                        )
                    )
                    .limit(1)
                )
                dup_result = await self.session.execute(dup_stmt)
                return dup_result.scalar_one_or_none(), False
            notification = await self.create(**notification_data)
            return notification, True

    async def check_correlation_duplicate(self, correlation_id: str) -> bool:
        """Check if an active/acknowledged notification with this correlation_id exists.

        Used for broadcast dedup (Grafana alerts) where fingerprint is not
        stored on per-user copies but correlation_id is.

        Also checks for recently resolved notifications (within 30 minutes)
        to prevent refire-cycle duplicates (firing → resolved → firing).
        """
        # Check active/acknowledged notifications
        stmt = (
            select(func.count())
            .select_from(Notification)
            .where(
                and_(
                    Notification.correlation_id == correlation_id,
                    Notification.status.in_([AlertStatus.ACTIVE, AlertStatus.ACKNOWLEDGED]),
                )
            )
        )
        result = await self.session.execute(stmt)
        if result.scalar_one() > 0:
            return True

        # Refire-cycle protection: also check recently resolved notifications.
        # If an alert was resolved < 30 min ago and fires again, it's a
        # refire-cycle artifact, not a genuinely new incident.
        refire_cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
        refire_stmt = (
            select(func.count())
            .select_from(Notification)
            .where(
                and_(
                    Notification.correlation_id == correlation_id,
                    Notification.status == AlertStatus.RESOLVED,
                    Notification.resolved_at >= refire_cutoff,
                )
            )
        )
        refire_result = await self.session.execute(refire_stmt)
        return refire_result.scalar_one() > 0

    async def count_today_warnings(self, user_id: int, source: str) -> int:
        """Count warning notifications sent today for a user+source."""
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        stmt = (
            select(func.count())
            .select_from(Notification)
            .where(
                and_(
                    Notification.user_id == user_id,
                    Notification.source == source,
                    Notification.severity == NotificationSeverity.WARNING,
                    Notification.created_at >= today_start,
                )
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    # =========================================================================
    # Alert Lifecycle Methods (Phase 4B — ISA-18.2)
    # =========================================================================

    async def acknowledge_alert(
        self,
        notification_id: uuid.UUID,
        user_id: int,
        acknowledging_user_id: int,
    ) -> Optional[Notification]:
        """
        Acknowledge an alert (active → acknowledged).

        Args:
            notification_id: Alert UUID
            user_id: Owner user ID (for authorization)
            acknowledging_user_id: User performing the acknowledgement

        Returns:
            Updated notification or None if not found/not owned
        """
        stmt = select(Notification).where(
            and_(
                Notification.id == notification_id,
                Notification.user_id == user_id,
            )
        )
        result = await self.session.execute(stmt)
        notification = result.scalar_one_or_none()

        if not notification:
            return None

        # ISA-18.2 state machine: validate transition via VALID_TRANSITIONS
        valid_targets = AlertStatus.VALID_TRANSITIONS.get(notification.status, set())
        if AlertStatus.ACKNOWLEDGED not in valid_targets:
            return notification  # Invalid transition (already acknowledged or resolved)

        now = datetime.now(timezone.utc)
        notification.status = AlertStatus.ACKNOWLEDGED
        notification.acknowledged_at = now
        notification.acknowledged_by = acknowledging_user_id
        notification.updated_at = now

        await self.session.flush()
        await self.session.refresh(notification)
        return notification

    async def resolve_alert(
        self,
        notification_id: uuid.UUID,
        user_id: int,
    ) -> Optional[Notification]:
        """
        Resolve an alert (active/acknowledged → resolved).

        Args:
            notification_id: Alert UUID
            user_id: Owner user ID (for authorization)

        Returns:
            Updated notification or None if not found/not owned
        """
        stmt = select(Notification).where(
            and_(
                Notification.id == notification_id,
                Notification.user_id == user_id,
            )
        )
        result = await self.session.execute(stmt)
        notification = result.scalar_one_or_none()

        if not notification:
            return None

        # ISA-18.2 state machine: validate transition via VALID_TRANSITIONS
        valid_targets = AlertStatus.VALID_TRANSITIONS.get(notification.status, set())
        if AlertStatus.RESOLVED not in valid_targets:
            return notification  # Terminal state, no valid transition

        now = datetime.now(timezone.utc)
        notification.status = AlertStatus.RESOLVED
        notification.resolved_at = now
        notification.is_read = True
        notification.read_at = notification.read_at or now
        notification.updated_at = now

        await self.session.flush()
        await self.session.refresh(notification)
        return notification

    async def resolve_all_alerts(self, user_id: int) -> int:
        """
        Resolve all unresolved alerts (active + acknowledged) for a user.

        Also marks alerts as read to keep unread counters consistent.

        Returns:
            Number of resolved alerts
        """
        now = datetime.now(timezone.utc)
        stmt = (
            update(Notification)
            .where(
                and_(
                    Notification.user_id == user_id,
                    Notification.status.in_([AlertStatus.ACTIVE, AlertStatus.ACKNOWLEDGED]),
                )
            )
            .values(
                status=AlertStatus.RESOLVED,
                resolved_at=now,
                is_read=True,
                read_at=func.coalesce(Notification.read_at, now),
                updated_at=now,
            )
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount

    async def auto_resolve_by_correlation(self, correlation_id: str) -> int:
        """
        Auto-resolve all active/acknowledged alerts with matching correlation_id.
        Used when Grafana sends a 'resolved' webhook.

        Returns:
            Number of alerts resolved
        """
        now = datetime.now(timezone.utc)
        stmt = (
            update(Notification)
            .where(
                and_(
                    Notification.correlation_id == correlation_id,
                    Notification.status.in_([AlertStatus.ACTIVE, AlertStatus.ACKNOWLEDGED]),
                )
            )
            .values(
                status=AlertStatus.RESOLVED,
                resolved_at=now,
                updated_at=now,
            )
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount

    async def group_under_parent(
        self,
        parent_notification_id: uuid.UUID,
        correlation_prefix: str,
    ) -> int:
        """
        Group active/acknowledged alerts under a root-cause parent notification.

        Finds alerts whose correlation_id starts with the given prefix
        and sets their parent_notification_id. Used for ISA-18.2 root-cause
        grouping (e.g., MQTT offline → dependent sensor-stale alerts).

        Args:
            parent_notification_id: Root-cause notification UUID
            correlation_prefix: Prefix to match (e.g., "threshold_AABBCCDD")

        Returns:
            Number of alerts grouped
        """
        now = datetime.now(timezone.utc)
        stmt = (
            update(Notification)
            .where(
                and_(
                    Notification.correlation_id.like(f"{correlation_prefix}%"),
                    Notification.status.in_([AlertStatus.ACTIVE, AlertStatus.ACKNOWLEDGED]),
                    Notification.id != parent_notification_id,
                    Notification.parent_notification_id.is_(None),
                )
            )
            .values(
                parent_notification_id=parent_notification_id,
                updated_at=now,
            )
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount

    async def get_alerts_by_status(
        self,
        status: str,
        user_id: Optional[int] = None,
        severity: Optional[str] = None,
        category: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Tuple[List[Notification], int]:
        """
        Get paginated alerts filtered by lifecycle status.

        Args:
            status: Alert status filter (active, acknowledged, resolved)
            user_id: Optional user filter
            severity: Optional severity filter
            category: Optional category filter
            skip: Pagination offset
            limit: Pagination limit

        Returns:
            Tuple of (notifications, total_count)
        """
        conditions = [Notification.status == status]

        if user_id is not None:
            conditions.append(Notification.user_id == user_id)
        if severity is not None:
            conditions.append(Notification.severity == severity)
        if category is not None:
            conditions.append(Notification.category == category)

        where_clause = and_(*conditions)

        # Count
        count_stmt = select(func.count()).select_from(Notification).where(where_clause)
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar_one()

        # Data — active/acknowledged sorted by severity (critical first), then created_at
        if status in (AlertStatus.ACTIVE, AlertStatus.ACKNOWLEDGED):
            severity_order = case(
                (Notification.severity == NotificationSeverity.CRITICAL, 0),
                (Notification.severity == NotificationSeverity.WARNING, 1),
                else_=2,
            )
            order_clause = [severity_order, desc(Notification.created_at)]
        else:
            order_clause = [desc(Notification.resolved_at)]

        data_stmt = (
            select(Notification)
            .where(where_clause)
            .order_by(*order_clause)
            .offset(skip)
            .limit(limit)
        )
        data_result = await self.session.execute(data_stmt)
        notifications = list(data_result.scalars().all())

        return notifications, total

    async def get_alert_stats(self, user_id: Optional[int] = None) -> dict:
        """
        Get ISA-18.2 alert metrics (MTTA, MTTR, counts by status).

        Returns:
            Dict with active_count, acknowledged_count, resolved_today_count,
            critical_active, warning_active, mean_time_to_acknowledge_s,
            mean_time_to_resolve_s
        """
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        base_conditions = []
        if user_id is not None:
            base_conditions.append(Notification.user_id == user_id)

        # Active count
        active_conditions = [Notification.status == AlertStatus.ACTIVE] + base_conditions
        active_stmt = select(func.count()).select_from(Notification).where(and_(*active_conditions))
        active_result = await self.session.execute(active_stmt)
        active_count = active_result.scalar_one()

        # Acknowledged count
        ack_conditions = [Notification.status == AlertStatus.ACKNOWLEDGED] + base_conditions
        ack_stmt = select(func.count()).select_from(Notification).where(and_(*ack_conditions))
        ack_result = await self.session.execute(ack_stmt)
        acknowledged_count = ack_result.scalar_one()

        # Resolved today count
        resolved_conditions = [
            Notification.status == AlertStatus.RESOLVED,
            Notification.resolved_at >= today_start,
        ] + base_conditions
        resolved_stmt = (
            select(func.count()).select_from(Notification).where(and_(*resolved_conditions))
        )
        resolved_result = await self.session.execute(resolved_stmt)
        resolved_today_count = resolved_result.scalar_one()

        # Critical active count
        crit_conditions = [
            Notification.status == AlertStatus.ACTIVE,
            Notification.severity == NotificationSeverity.CRITICAL,
        ] + base_conditions
        crit_stmt = select(func.count()).select_from(Notification).where(and_(*crit_conditions))
        crit_result = await self.session.execute(crit_stmt)
        critical_active = crit_result.scalar_one()

        # Warning active count
        warn_conditions = [
            Notification.status == AlertStatus.ACTIVE,
            Notification.severity == NotificationSeverity.WARNING,
        ] + base_conditions
        warn_stmt = select(func.count()).select_from(Notification).where(and_(*warn_conditions))
        warn_result = await self.session.execute(warn_stmt)
        warning_active = warn_result.scalar_one()

        # Mean Time to Acknowledge (MTTA) — average seconds from created_at to acknowledged_at
        mtta_conditions = [Notification.acknowledged_at.isnot(None)] + base_conditions
        mtta_stmt = (
            select(
                func.avg(
                    func.extract("epoch", Notification.acknowledged_at)
                    - func.extract("epoch", Notification.created_at)
                )
            )
            .select_from(Notification)
            .where(and_(*mtta_conditions))
        )
        mtta_result = await self.session.execute(mtta_stmt)
        mean_time_to_acknowledge_s = mtta_result.scalar_one()

        # Mean Time to Resolve (MTTR) — average seconds from created_at to resolved_at
        mttr_conditions = [Notification.resolved_at.isnot(None)] + base_conditions
        mttr_stmt = (
            select(
                func.avg(
                    func.extract("epoch", Notification.resolved_at)
                    - func.extract("epoch", Notification.created_at)
                )
            )
            .select_from(Notification)
            .where(and_(*mttr_conditions))
        )
        mttr_result = await self.session.execute(mttr_stmt)
        mean_time_to_resolve_s = mttr_result.scalar_one()

        return {
            "active_count": active_count,
            "acknowledged_count": acknowledged_count,
            "resolved_today_count": resolved_today_count,
            "critical_active": critical_active,
            "warning_active": warning_active,
            "mean_time_to_acknowledge_s": (
                round(float(mean_time_to_acknowledge_s), 1)
                if mean_time_to_acknowledge_s is not None
                else None
            ),
            "mean_time_to_resolve_s": (
                round(float(mean_time_to_resolve_s), 1)
                if mean_time_to_resolve_s is not None
                else None
            ),
        }

    async def resolve_alerts_for_device(self, esp_id: str) -> int:
        """
        Auto-resolve all active/acknowledged alerts belonging to a deleted device.

        Matches on extra_data->>'esp_id' (PostgreSQL JSON text extraction).
        Called from device soft-delete to prevent zombie alerts.

        Args:
            esp_id: The ESP device ID being deleted

        Returns:
            Number of alerts resolved
        """
        now = datetime.now(timezone.utc)
        stmt = (
            update(Notification)
            .where(
                and_(
                    cast(Notification.extra_data["esp_id"], String) == esp_id,
                    Notification.status.in_([AlertStatus.ACTIVE, AlertStatus.ACKNOWLEDGED]),
                )
            )
            .values(
                status=AlertStatus.RESOLVED,
                resolved_at=now,
                updated_at=now,
            )
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount

    async def get_active_counts_by_severity(self) -> dict[str, int]:
        """
        Get active (non-resolved) alert counts grouped by severity.

        Used by Prometheus metrics cycle — no user_id filter.

        Returns:
            Dict mapping severity to count, e.g. {"critical": 2, "warning": 5, "info": 1}
        """
        stmt = (
            select(
                Notification.severity,
                func.count().label("cnt"),
            )
            .where(Notification.status.in_([AlertStatus.ACTIVE, AlertStatus.ACKNOWLEDGED]))
            .group_by(Notification.severity)
        )
        result = await self.session.execute(stmt)
        rows = result.all()

        # Initialize all severities to 0
        counts: dict[str, int] = {"critical": 0, "warning": 0, "info": 0}
        for severity, cnt in rows:
            counts[severity] = cnt

        return counts


class NotificationPreferencesRepository:
    """Repository for user notification preferences."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_for_user(self, user_id: int) -> Optional[NotificationPreferences]:
        """Get preferences for a user."""
        stmt = select(NotificationPreferences).where(NotificationPreferences.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_create(self, user_id: int) -> NotificationPreferences:
        """Get preferences, creating defaults if they don't exist."""
        prefs = await self.get_for_user(user_id)
        if prefs is None:
            prefs = NotificationPreferences(user_id=user_id)
            self.session.add(prefs)
            await self.session.flush()
            await self.session.refresh(prefs)
        return prefs

    async def update(self, user_id: int, **data: Any) -> NotificationPreferences:
        """Update preferences for a user (creates if not exists)."""
        prefs = await self.get_or_create(user_id)
        for key, value in data.items():
            if value is not None and hasattr(prefs, key):
                setattr(prefs, key, value)
        await self.session.flush()
        await self.session.refresh(prefs)
        return prefs

    async def get_all_with_email_enabled(self) -> List[NotificationPreferences]:
        """Get all users with email notifications enabled."""
        stmt = select(NotificationPreferences).where(NotificationPreferences.email_enabled == True)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
