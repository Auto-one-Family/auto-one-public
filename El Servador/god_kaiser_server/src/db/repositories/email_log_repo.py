"""
Email Log Repository: CRUD + Filtered Queries for Email Delivery Tracking

Phase C V1.1: Email-Status-Tracking
Phase C V1.2: Email-Retry (get_pending_retries)
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.email_log import EmailLog
from .base_repo import BaseRepository


class EmailLogRepository(BaseRepository[EmailLog]):
    """Repository for email log CRUD and filtered queries."""

    def __init__(self, session: AsyncSession):
        super().__init__(EmailLog, session)

    async def log_send(
        self,
        to_address: str,
        subject: str,
        provider: str,
        status: str,
        notification_id: Optional[uuid.UUID] = None,
        template: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> EmailLog:
        """
        Log an email send attempt.

        Args:
            to_address: Recipient email
            subject: Email subject
            provider: Provider used (resend, smtp)
            status: Delivery status (sent, failed)
            notification_id: Optional linked notification
            template: Optional template name used
            error_message: Error details if failed
        """
        log = EmailLog(
            to_address=to_address,
            subject=subject,
            provider=provider,
            status=status,
            notification_id=notification_id,
            template=template,
            error_message=error_message,
            sent_at=datetime.now(timezone.utc) if status == "sent" else None,
        )
        self.session.add(log)
        await self.session.flush()
        return log

    async def get_filtered(
        self,
        status: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        template: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Tuple[List[EmailLog], int]:
        """
        Get email logs with filters and pagination.

        Returns:
            Tuple of (email_logs, total_count)
        """
        query = select(EmailLog)
        count_query = select(func.count()).select_from(EmailLog)

        if status:
            query = query.where(EmailLog.status == status)
            count_query = count_query.where(EmailLog.status == status)
        if date_from:
            query = query.where(EmailLog.created_at >= date_from)
            count_query = count_query.where(EmailLog.created_at >= date_from)
        if date_to:
            query = query.where(EmailLog.created_at <= date_to)
            count_query = count_query.where(EmailLog.created_at <= date_to)
        if template and template.strip():
            pattern = f"%{template.strip()}%"
            query = query.where(EmailLog.template.ilike(pattern))
            count_query = count_query.where(EmailLog.template.ilike(pattern))

        total = (await self.session.execute(count_query)).scalar_one()

        query = query.order_by(desc(EmailLog.created_at)).offset(skip).limit(limit)
        result = await self.session.execute(query)

        return list(result.scalars().all()), total

    async def get_stats(self) -> Dict[str, Any]:
        """
        Get email sending statistics.

        Returns summary counts by status, provider, and time ranges.
        """
        # Total counts by status
        status_query = select(EmailLog.status, func.count()).group_by(EmailLog.status)
        status_result = await self.session.execute(status_query)
        by_status = {row[0]: row[1] for row in status_result.all()}

        # Total counts by provider
        provider_query = select(EmailLog.provider, func.count()).group_by(EmailLog.provider)
        provider_result = await self.session.execute(provider_query)
        by_provider = {row[0]: row[1] for row in provider_result.all()}

        total = sum(by_status.values())

        return {
            "total": total,
            "by_status": by_status,
            "by_provider": by_provider,
            "sent": by_status.get("sent", 0),
            "failed": by_status.get("failed", 0),
        }

    async def get_for_notification(
        self,
        notification_id: uuid.UUID,
    ) -> Optional[EmailLog]:
        """Get the most recent email log for a notification."""
        query = (
            select(EmailLog)
            .where(EmailLog.notification_id == notification_id)
            .order_by(desc(EmailLog.created_at))
            .limit(1)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_pending_retries(
        self,
        limit: int = 50,
        min_age_minutes: int = 5,
    ) -> List[EmailLog]:
        """
        Get email log entries eligible for retry (Phase C V1.2).

        Filter: status='failed', retry_count < 3.
        Optional: created_at at least min_age_minutes ago (avoids immediate retry).
        Sorted by created_at ascending (oldest first).

        Returns:
            List of EmailLog entries to retry
        """
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=min_age_minutes)
        query = (
            select(EmailLog)
            .where(EmailLog.status == "failed")
            .where(EmailLog.retry_count < 3)
            .where(EmailLog.created_at <= cutoff)
            .order_by(EmailLog.created_at.asc())
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
