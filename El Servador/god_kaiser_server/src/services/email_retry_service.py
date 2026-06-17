"""
Email Retry Service: Automatic retry of failed email sends (Phase C V1.2)

Retries failed emails (status='failed', retry_count < 3) for:
- Critical alerts (notification_id set): Reconstruct from Notification, call send_critical_alert
- Test emails (template='test_email'): Call send_test_email(to_address)

Digest retries are skipped (no template_context stored). Can be added later via
template_context JSONB column if needed.
"""

from datetime import datetime, timezone
from typing import Optional

from ..core.logging_config import get_logger
from ..db.repositories.email_log_repo import EmailLogRepository
from ..db.repositories.notification_repo import NotificationRepository
from ..db.session import resilient_session
from .email_service import EmailService, get_email_service

logger = get_logger(__name__)

# Template names used in email_log (must match NotificationRouter, DigestService, Test endpoint)
TEMPLATE_CRITICAL_ALERT = "critical_alert"
TEMPLATE_TEST_EMAIL = "test_email"
# Digest: template="digest" — not retried (no template_context)


class EmailRetryService:
    """
    Processes failed email log entries and retries send.

    Uses resilient_session for circuit breaker protection.
    One failure does not abort the rest; each entry is processed independently.
    """

    def __init__(self, email_service: Optional[EmailService] = None):
        self.email_service = email_service or get_email_service()

    async def process_retries(self, limit: int = 50) -> int:
        """
        Process pending email retries.

        Called by CentralScheduler (e.g. every 5 minutes).
        Updates retry_count, status (sent/failed/permanently_failed), sent_at, error_message.

        Returns:
            Number of entries processed
        """
        processed = 0

        try:
            async with resilient_session() as session:
                email_log_repo = EmailLogRepository(session)
                notification_repo = NotificationRepository(session)

                pending = await email_log_repo.get_pending_retries(limit=limit)

                for log in pending:
                    try:
                        success = await self._retry_single(
                            log=log,
                            email_log_repo=email_log_repo,
                            notification_repo=notification_repo,
                        )
                        if success is not None:
                            new_retry_count = log.retry_count + 1
                            if success:
                                await email_log_repo.update(
                                    log.id,
                                    retry_count=new_retry_count,
                                    status="sent",
                                    sent_at=datetime.now(timezone.utc),
                                    error_message=None,
                                )
                                logger.info(
                                    f"Email retry success: id={log.id} to={log.to_address} "
                                    f"template={log.template} retry_count={new_retry_count}"
                                )
                            else:
                                # EmailService returns False without error details
                                err_msg = log.error_message or "Retry failed"
                                if new_retry_count >= 3:
                                    await email_log_repo.update(
                                        log.id,
                                        retry_count=new_retry_count,
                                        status="permanently_failed",
                                        error_message=err_msg,
                                    )
                                    logger.warning(
                                        f"Email permanently failed: id={log.id} to={log.to_address} "
                                        f"retry_count={new_retry_count}"
                                    )
                                else:
                                    await email_log_repo.update(
                                        log.id,
                                        retry_count=new_retry_count,
                                        status="failed",
                                        error_message=err_msg,
                                    )
                                    logger.debug(
                                        f"Email retry failed (will retry again): id={log.id} "
                                        f"retry_count={new_retry_count}"
                                    )
                            processed += 1
                    except Exception as e:
                        logger.error(
                            f"Email retry error for id={log.id}: {e}",
                            exc_info=True,
                        )
                        # Continue with next entry

                await session.commit()

        except Exception as e:
            logger.error(f"Email retry processing failed: {e}", exc_info=True)

        if processed > 0:
            logger.info(f"Email retry processing complete: {processed} entries processed")

        return processed

    async def _retry_single(
        self,
        log,
        email_log_repo: EmailLogRepository,
        notification_repo: NotificationRepository,
    ) -> Optional[bool]:
        """
        Attempt a single retry. Returns True/False on success/failure, None if skipped.
        """
        # Critical alert: notification_id set
        if log.notification_id:
            notification = await notification_repo.get_by_id(log.notification_id)
            if notification is None:
                logger.warning(
                    f"Email retry skipped: notification {log.notification_id} not found "
                    f"(email_log id={log.id})"
                )
                return None

            success = await self.email_service.send_critical_alert(
                to=log.to_address,
                title=notification.title,
                body=notification.body or "",
                severity=notification.severity,
                source=notification.source,
                category=notification.category,
                metadata=notification.extra_data,
            )
            return success

        # Test email: template='test_email'
        if log.template == TEMPLATE_TEST_EMAIL and log.to_address:
            return await self.email_service.send_test_email(log.to_address)

        # Digest or unknown: skip (Digest-Retry would need template_context)
        logger.debug(f"Email retry skipped (unsupported type): id={log.id} template={log.template}")
        return None


# Module-level singleton
_email_retry_service: Optional[EmailRetryService] = None


def get_email_retry_service() -> EmailRetryService:
    """Get or create the EmailRetryService singleton."""
    global _email_retry_service
    if _email_retry_service is None:
        _email_retry_service = EmailRetryService()
    return _email_retry_service
