"""
Unit Tests: DigestService

Phase 4A Test-Suite (STEP 4, Block 7b)
Tests: Digest collection, empty batch, email-enabled only, mark sent, singleton
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# =============================================================================
# Mock Helpers
# =============================================================================


def _make_mock_notification(title="Test Alert", severity="warning", source="sensor_threshold"):
    """Create a mock notification object."""
    mock = MagicMock()
    mock.id = "notif-uuid-001"
    mock.title = title
    mock.body = "Test notification body"
    mock.severity = severity
    mock.source = source
    mock.created_at = MagicMock()
    mock.created_at.strftime.return_value = "2026-03-02 10:00 UTC"
    return mock


def _make_mock_prefs(
    user_id=1, email_enabled=True, digest_interval=60, email_address="user@test.com"
):
    """Create a mock NotificationPreferences object."""
    mock = MagicMock()
    mock.user_id = user_id
    mock.email_enabled = email_enabled
    mock.digest_interval_minutes = digest_interval
    mock.email_address = email_address
    return mock


def _make_mock_session():
    """Create a mock async session compatible with EmailLogRepository.

    Uses MagicMock for sync methods (add) and AsyncMock for async methods (flush, commit)
    to avoid 'coroutine was never awaited' when session.add() is called.
    """
    mock = MagicMock()
    mock.add = MagicMock(return_value=None)  # sync - SQLAlchemy add is not async
    mock.flush = AsyncMock(return_value=None)
    mock.commit = AsyncMock(return_value=None)
    return mock


# =============================================================================
# Test 1: Process Collects Pending Notifications
# =============================================================================


@pytest.mark.asyncio
async def test_process_digests_collects_pending():
    """process_digests() collects pending notifications per user and sends digest."""
    from src.services.digest_service import DigestService

    mock_email = AsyncMock()
    mock_email.send_digest = AsyncMock(return_value=True)

    mock_prefs = _make_mock_prefs()
    mock_notifications = [_make_mock_notification() for _ in range(3)]

    with patch("src.services.digest_service.resilient_session") as mock_ctx:
        mock_session = _make_mock_session()
        mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.services.digest_service.NotificationPreferencesRepository") as MockPrefsRepo,
            patch("src.services.digest_service.NotificationRepository") as MockNotifRepo,
            patch("src.services.digest_service.UserRepository"),
        ):
            mock_prefs_repo = AsyncMock()
            mock_prefs_repo.get_all_with_email_enabled = AsyncMock(return_value=[mock_prefs])
            MockPrefsRepo.return_value = mock_prefs_repo

            mock_notif_repo = AsyncMock()
            mock_notif_repo.get_pending_digest_notifications = AsyncMock(
                return_value=mock_notifications
            )
            mock_notif_repo.mark_digest_sent = AsyncMock()
            MockNotifRepo.return_value = mock_notif_repo

            service = DigestService(email_service=mock_email, digest_min_count=3)
            count = await service.process_digests()

    assert count == 1
    mock_email.send_digest.assert_called_once()
    mock_notif_repo.mark_digest_sent.assert_called_once()


# =============================================================================
# Test 2: Empty Batch — No Email Sent
# =============================================================================


@pytest.mark.asyncio
async def test_process_digests_empty_batch_no_email():
    """No pending notifications → no digest email sent."""
    from src.services.digest_service import DigestService

    mock_email = AsyncMock()
    mock_email.send_digest = AsyncMock(return_value=True)

    mock_prefs = _make_mock_prefs()

    with patch("src.services.digest_service.resilient_session") as mock_ctx:
        mock_session = _make_mock_session()
        mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.services.digest_service.NotificationPreferencesRepository") as MockPrefsRepo,
            patch("src.services.digest_service.NotificationRepository") as MockNotifRepo,
            patch("src.services.digest_service.UserRepository"),
        ):
            mock_prefs_repo = AsyncMock()
            mock_prefs_repo.get_all_with_email_enabled = AsyncMock(return_value=[mock_prefs])
            MockPrefsRepo.return_value = mock_prefs_repo

            mock_notif_repo = AsyncMock()
            mock_notif_repo.get_pending_digest_notifications = AsyncMock(return_value=[])
            MockNotifRepo.return_value = mock_notif_repo

            service = DigestService(email_service=mock_email, digest_min_count=3)
            count = await service.process_digests()

    assert count == 0
    mock_email.send_digest.assert_not_called()


# =============================================================================
# Test 3: Only Email-Enabled Users
# =============================================================================


@pytest.mark.asyncio
async def test_process_digests_only_email_enabled_users():
    """Users with digest_interval_minutes=0 are skipped."""
    from src.services.digest_service import DigestService

    mock_email = AsyncMock()
    mock_email.send_digest = AsyncMock(return_value=True)

    # User with digest disabled (interval=0)
    mock_prefs_disabled = _make_mock_prefs(user_id=1, digest_interval=0)
    # User with digest enabled
    mock_prefs_enabled = _make_mock_prefs(user_id=2, digest_interval=60)
    mock_notifications = [_make_mock_notification() for _ in range(3)]

    with patch("src.services.digest_service.resilient_session") as mock_ctx:
        mock_session = _make_mock_session()
        mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.services.digest_service.NotificationPreferencesRepository") as MockPrefsRepo,
            patch("src.services.digest_service.NotificationRepository") as MockNotifRepo,
            patch("src.services.digest_service.UserRepository"),
        ):
            mock_prefs_repo = AsyncMock()
            mock_prefs_repo.get_all_with_email_enabled = AsyncMock(
                return_value=[mock_prefs_disabled, mock_prefs_enabled]
            )
            MockPrefsRepo.return_value = mock_prefs_repo

            mock_notif_repo = AsyncMock()
            mock_notif_repo.get_pending_digest_notifications = AsyncMock(
                return_value=mock_notifications
            )
            mock_notif_repo.mark_digest_sent = AsyncMock()
            MockNotifRepo.return_value = mock_notif_repo

            service = DigestService(email_service=mock_email, digest_min_count=3)
            count = await service.process_digests()

    # Only 1 email sent (user 2), user 1 skipped
    assert count == 1


# =============================================================================
# Test 4: Mark Digest Sent After Email
# =============================================================================


@pytest.mark.asyncio
async def test_process_digests_marks_sent():
    """After successful email, notifications are marked with digest_sent=True."""
    from src.services.digest_service import DigestService

    mock_email = AsyncMock()
    mock_email.send_digest = AsyncMock(return_value=True)

    mock_prefs = _make_mock_prefs()
    mock_notifications = [_make_mock_notification() for _ in range(5)]
    notification_ids = [n.id for n in mock_notifications]

    with patch("src.services.digest_service.resilient_session") as mock_ctx:
        mock_session = _make_mock_session()
        mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("src.services.digest_service.NotificationPreferencesRepository") as MockPrefsRepo,
            patch("src.services.digest_service.NotificationRepository") as MockNotifRepo,
            patch("src.services.digest_service.UserRepository"),
        ):
            mock_prefs_repo = AsyncMock()
            mock_prefs_repo.get_all_with_email_enabled = AsyncMock(return_value=[mock_prefs])
            MockPrefsRepo.return_value = mock_prefs_repo

            mock_notif_repo = AsyncMock()
            mock_notif_repo.get_pending_digest_notifications = AsyncMock(
                return_value=mock_notifications
            )
            mock_notif_repo.mark_digest_sent = AsyncMock()
            MockNotifRepo.return_value = mock_notif_repo

            service = DigestService(email_service=mock_email, digest_min_count=3)
            await service.process_digests()

    mock_notif_repo.mark_digest_sent.assert_called_once_with(notification_ids)


# =============================================================================
# Test 5: Singleton Pattern
# =============================================================================


def test_digest_service_singleton():
    """get_digest_service() returns the same instance."""
    import src.services.digest_service as module

    # Reset singleton
    module._digest_service = None

    with patch.object(module, "get_email_service", return_value=MagicMock()):
        svc1 = module.get_digest_service()
        svc2 = module.get_digest_service()

    assert svc1 is svc2

    # Cleanup
    module._digest_service = None
