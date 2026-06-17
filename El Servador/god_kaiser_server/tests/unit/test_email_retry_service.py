"""
Unit Tests: EmailRetryService (Phase C V1.2)

Tests: process_retries for critical alerts, test emails, skip digest,
permanently_failed after 3 attempts, singleton.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.db.models.email_log import EmailLog
from src.db.models.notification import Notification


def _make_mock_email_log(
    log_id=None,
    status="failed",
    retry_count=0,
    notification_id=None,
    template="critical_alert",
    to_address="user@test.com",
    created_at=None,
):
    """Create a mock EmailLog object."""
    mock = MagicMock(spec=EmailLog)
    mock.id = log_id or uuid.uuid4()
    mock.status = status
    mock.retry_count = retry_count
    mock.notification_id = notification_id
    mock.template = template
    mock.to_address = to_address
    mock.subject = "Test"
    mock.error_message = "Previous error"
    mock.created_at = created_at or (datetime.now(timezone.utc) - timedelta(minutes=10))
    return mock


def _make_mock_notification():
    """Create a mock Notification object."""
    mock = MagicMock(spec=Notification)
    mock.id = uuid.uuid4()
    mock.title = "Critical Alert"
    mock.body = "Test body"
    mock.severity = "critical"
    mock.source = "logic_engine"
    mock.category = "infrastructure"
    mock.extra_data = {}
    return mock


@pytest.mark.asyncio
async def test_process_retries_critical_alert_success():
    """process_retries() retries critical alert (notification_id set), success → status=sent."""
    mock_email = AsyncMock()
    mock_email.send_critical_alert = AsyncMock(return_value=True)

    mock_log = _make_mock_email_log(notification_id=uuid.uuid4(), template="critical_alert")
    mock_notification = _make_mock_notification()
    mock_notification.id = mock_log.notification_id

    with patch("src.services.email_retry_service.resilient_session") as mock_ctx:
        mock_session = AsyncMock()
        mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.services.email_retry_service.EmailLogRepository") as MockEmailRepo,
            patch("src.services.email_retry_service.NotificationRepository") as MockNotifRepo,
        ):
            mock_email_repo = AsyncMock()
            mock_email_repo.get_pending_retries = AsyncMock(return_value=[mock_log])
            mock_email_repo.update = AsyncMock()
            MockEmailRepo.return_value = mock_email_repo

            mock_notif_repo = AsyncMock()
            mock_notif_repo.get_by_id = AsyncMock(return_value=mock_notification)
            MockNotifRepo.return_value = mock_notif_repo

            from src.services.email_retry_service import EmailRetryService

            service = EmailRetryService(email_service=mock_email)
            count = await service.process_retries(limit=50)

    assert count == 1
    mock_email.send_critical_alert.assert_called_once()
    mock_email_repo.update.assert_called_once()
    call_kwargs = mock_email_repo.update.call_args[1]
    assert call_kwargs["status"] == "sent"
    assert call_kwargs["retry_count"] == 1
    assert call_kwargs["error_message"] is None


@pytest.mark.asyncio
async def test_process_retries_test_email_success():
    """process_retries() retries test email (template=test_email), success."""
    mock_email = AsyncMock()
    mock_email.send_test_email = AsyncMock(return_value=True)

    mock_log = _make_mock_email_log(
        notification_id=None,
        template="test_email",
        to_address="test@example.com",
    )

    with patch("src.services.email_retry_service.resilient_session") as mock_ctx:
        mock_session = AsyncMock()
        mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.services.email_retry_service.EmailLogRepository") as MockEmailRepo,
            patch("src.services.email_retry_service.NotificationRepository") as MockNotifRepo,
        ):
            mock_email_repo = AsyncMock()
            mock_email_repo.get_pending_retries = AsyncMock(return_value=[mock_log])
            mock_email_repo.update = AsyncMock()
            MockEmailRepo.return_value = mock_email_repo

            mock_notif_repo = AsyncMock()
            MockNotifRepo.return_value = mock_notif_repo

            from src.services.email_retry_service import EmailRetryService

            service = EmailRetryService(email_service=mock_email)
            count = await service.process_retries(limit=50)

    assert count == 1
    mock_email.send_test_email.assert_called_once_with("test@example.com")
    mock_email_repo.update.assert_called_once()
    call_kwargs = mock_email_repo.update.call_args[1]
    assert call_kwargs["status"] == "sent"


@pytest.mark.asyncio
async def test_process_retries_permanently_failed_after_third_attempt():
    """After 3rd failed attempt → status=permanently_failed."""
    mock_email = AsyncMock()
    mock_email.send_critical_alert = AsyncMock(return_value=False)

    mock_log = _make_mock_email_log(
        notification_id=uuid.uuid4(),
        retry_count=2,  # 3rd attempt
    )
    mock_notification = _make_mock_notification()
    mock_notification.id = mock_log.notification_id

    with patch("src.services.email_retry_service.resilient_session") as mock_ctx:
        mock_session = AsyncMock()
        mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.services.email_retry_service.EmailLogRepository") as MockEmailRepo,
            patch("src.services.email_retry_service.NotificationRepository") as MockNotifRepo,
        ):
            mock_email_repo = AsyncMock()
            mock_email_repo.get_pending_retries = AsyncMock(return_value=[mock_log])
            mock_email_repo.update = AsyncMock()
            MockEmailRepo.return_value = mock_email_repo

            mock_notif_repo = AsyncMock()
            mock_notif_repo.get_by_id = AsyncMock(return_value=mock_notification)
            MockNotifRepo.return_value = mock_notif_repo

            from src.services.email_retry_service import EmailRetryService

            service = EmailRetryService(email_service=mock_email)
            count = await service.process_retries(limit=50)

    assert count == 1
    mock_email_repo.update.assert_called_once()
    call_kwargs = mock_email_repo.update.call_args[1]
    assert call_kwargs["status"] == "permanently_failed"
    assert call_kwargs["retry_count"] == 3


@pytest.mark.asyncio
async def test_process_retries_skips_digest():
    """Digest entries (template=digest, no notification_id) are skipped."""
    mock_email = AsyncMock()

    mock_log = _make_mock_email_log(
        notification_id=None,
        template="digest",
    )

    with patch("src.services.email_retry_service.resilient_session") as mock_ctx:
        mock_session = AsyncMock()
        mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.services.email_retry_service.EmailLogRepository") as MockEmailRepo,
            patch("src.services.email_retry_service.NotificationRepository") as MockNotifRepo,
        ):
            mock_email_repo = AsyncMock()
            mock_email_repo.get_pending_retries = AsyncMock(return_value=[mock_log])
            mock_email_repo.update = AsyncMock()
            MockEmailRepo.return_value = mock_email_repo

            mock_notif_repo = AsyncMock()
            MockNotifRepo.return_value = mock_notif_repo

            from src.services.email_retry_service import EmailRetryService

            service = EmailRetryService(email_service=mock_email)
            count = await service.process_retries(limit=50)

    assert count == 0
    mock_email.send_critical_alert.assert_not_called()
    mock_email.send_test_email.assert_not_called()
    mock_email_repo.update.assert_not_called()


@pytest.mark.asyncio
async def test_process_retries_empty_pending():
    """No pending retries → 0 processed."""
    mock_email = AsyncMock()

    with patch("src.services.email_retry_service.resilient_session") as mock_ctx:
        mock_session = AsyncMock()
        mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.services.email_retry_service.EmailLogRepository") as MockEmailRepo,
            patch("src.services.email_retry_service.NotificationRepository"),
        ):
            mock_email_repo = AsyncMock()
            mock_email_repo.get_pending_retries = AsyncMock(return_value=[])
            MockEmailRepo.return_value = mock_email_repo

            from src.services.email_retry_service import EmailRetryService

            service = EmailRetryService(email_service=mock_email)
            count = await service.process_retries(limit=50)

    assert count == 0


@pytest.mark.asyncio
async def test_process_retries_notification_not_found_skipped():
    """Notification deleted → entry skipped, no update."""
    mock_email = AsyncMock()

    mock_log = _make_mock_email_log(notification_id=uuid.uuid4())

    with patch("src.services.email_retry_service.resilient_session") as mock_ctx:
        mock_session = AsyncMock()
        mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.services.email_retry_service.EmailLogRepository") as MockEmailRepo,
            patch("src.services.email_retry_service.NotificationRepository") as MockNotifRepo,
        ):
            mock_email_repo = AsyncMock()
            mock_email_repo.get_pending_retries = AsyncMock(return_value=[mock_log])
            mock_email_repo.update = AsyncMock()
            MockEmailRepo.return_value = mock_email_repo

            mock_notif_repo = AsyncMock()
            mock_notif_repo.get_by_id = AsyncMock(return_value=None)  # Not found
            MockNotifRepo.return_value = mock_notif_repo

            from src.services.email_retry_service import EmailRetryService

            service = EmailRetryService(email_service=mock_email)
            count = await service.process_retries(limit=50)

    assert count == 0
    mock_email.send_critical_alert.assert_not_called()
    mock_email_repo.update.assert_not_called()


def test_email_retry_service_singleton():
    """get_email_retry_service() returns the same instance."""
    import src.services.email_retry_service as module

    module._email_retry_service = None

    with patch.object(module, "get_email_service", return_value=MagicMock()):
        svc1 = module.get_email_retry_service()
        svc2 = module.get_email_retry_service()

    assert svc1 is svc2

    module._email_retry_service = None
