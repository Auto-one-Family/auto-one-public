"""
Digest Service: Warning Email Batching (ISA-18.2)

Phase 4A.1: Notification-Stack Backend
Priority: HIGH
Status: IMPLEMENTED

Batches warning notifications into periodic digest emails.
- Runs every 60 minutes (configurable) via CentralScheduler
- Collects unsent warning notifications per user
- Sends digest email when threshold met (default: 3 or more)
- Marks notifications as digest_sent=True
- ISA-18.2 target: max 6 alarms/hour per operator
"""

from typing import Optional

from ..core.logging_config import get_logger
from ..core.metrics import increment_digest_processed, observe_digest_batch_size
from ..db.repositories.email_log_repo import EmailLogRepository
from ..db.repositories.notification_repo import (
    NotificationPreferencesRepository,
    NotificationRepository,
)
from ..db.repositories.user_repo import UserRepository
from ..db.session import resilient_session
from .email_service import EmailService, get_email_service

logger = get_logger(__name__)


class DigestService:
    """
    Periodic digest email service.

    Integrates with CentralScheduler via process_digests() method.
    """

    def __init__(
        self,
        email_service: Optional[EmailService] = None,
        digest_min_count: int = 3,
    ):
        self.email_service = email_service or get_email_service()
        self.digest_min_count = digest_min_count

    async def process_digests(self) -> int:
        """
        Process all pending digest emails.

        Called by CentralScheduler at configured interval.
        Uses resilient_session for circuit breaker protection.

        Returns:
            Number of digest emails sent
        """
        digests_sent = 0

        try:
            async with resilient_session() as session:
                prefs_repo = NotificationPreferencesRepository(session)
                notification_repo = NotificationRepository(session)
                user_repo = UserRepository(session)
                email_log_repo = EmailLogRepository(session)

                # Get all users with email enabled
                all_prefs = await prefs_repo.get_all_with_email_enabled()

                for prefs in all_prefs:
                    if prefs.digest_interval_minutes <= 0:
                        continue

                    # Get pending digest notifications
                    pending = await notification_repo.get_pending_digest_notifications(
                        user_id=prefs.user_id,
                        min_count=self.digest_min_count,
                    )

                    if not pending:
                        continue

                    # Get recipient email
                    recipient = prefs.email_address
                    if not recipient:
                        user = await user_repo.get_by_id(prefs.user_id)
                        if user:
                            recipient = user.email

                    if not recipient:
                        logger.warning(
                            f"No email address for user {prefs.user_id}, skipping digest"
                        )
                        continue

                    # Build digest notification list
                    digest_items = [
                        {
                            "title": n.title,
                            "body": n.body or "",
                            "severity": n.severity,
                            "source": n.source,
                            "timestamp": (
                                n.created_at.strftime("%Y-%m-%d %H:%M UTC")
                                if n.created_at
                                else "unknown"
                            ),
                        }
                        for n in pending
                    ]

                    # Calculate digest period string
                    digest_period = f"{prefs.digest_interval_minutes} minutes"
                    if prefs.digest_interval_minutes >= 60:
                        hours = prefs.digest_interval_minutes // 60
                        digest_period = f"{hours} hour{'s' if hours > 1 else ''}"

                    # Send digest email
                    provider = self.email_service.provider_name
                    success = await self.email_service.send_digest(
                        to=recipient,
                        notifications=digest_items,
                        digest_period=digest_period,
                    )

                    # Log email send attempt (Phase C V1.1)
                    try:
                        await email_log_repo.log_send(
                            to_address=recipient,
                            subject=f"AutomationOne Digest ({len(pending)} alerts)",
                            provider=provider,
                            status="sent" if success else "failed",
                            template="digest",
                            error_message=None if success else "Digest send failed",
                        )
                    except Exception as log_err:
                        logger.error(f"Failed to log digest email: {log_err}")

                    if success:
                        # Mark as digest_sent
                        notification_ids = [n.id for n in pending]
                        await notification_repo.mark_digest_sent(notification_ids)
                        digests_sent += 1
                        increment_digest_processed()
                        observe_digest_batch_size(len(pending))
                        logger.info(
                            f"Digest email sent to {recipient}: " f"{len(pending)} notifications"
                        )
                    else:
                        logger.warning(f"Digest email failed for {recipient}")

                await session.commit()

        except Exception as e:
            logger.error(f"Digest processing failed: {e}", exc_info=True)

        if digests_sent > 0:
            logger.info(f"Digest processing complete: {digests_sent} emails sent")

        return digests_sent


# Module-level singleton
_digest_service: Optional[DigestService] = None


def get_digest_service() -> DigestService:
    """Get or create the DigestService singleton."""
    global _digest_service
    if _digest_service is None:
        _digest_service = DigestService()
    return _digest_service
