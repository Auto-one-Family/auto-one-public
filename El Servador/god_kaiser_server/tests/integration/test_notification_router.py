"""
Integration Tests: NotificationRouter

Phase 4A Test-Suite (STEP 4, Block 1)
Tests: Core notification routing — persist, dedup, email, WS broadcast, quiet hours
"""

import pytest
from datetime import datetime, time as dt_time, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from src.db.models.notification import Notification, NotificationPreferences
from src.schemas.notification import NotificationCreate
from src.services.notification_router import NotificationRouter

# =============================================================================
# Helper Fixtures
# =============================================================================


@pytest.fixture
async def preferences_email_enabled(db_session, sample_user):
    """Create preferences with email enabled for critical + warning."""
    prefs = NotificationPreferences(
        user_id=sample_user.id,
        websocket_enabled=True,
        email_enabled=True,
        email_address="test@example.com",
        email_severities=["critical", "warning"],
        quiet_hours_enabled=False,
    )
    db_session.add(prefs)
    await db_session.flush()
    await db_session.refresh(prefs)
    return prefs


@pytest.fixture
async def preferences_quiet_hours(db_session, sample_user):
    """Create preferences with quiet hours 22:00-06:00."""
    prefs = NotificationPreferences(
        user_id=sample_user.id,
        websocket_enabled=True,
        email_enabled=True,
        email_address="test@example.com",
        email_severities=["critical", "warning"],
        quiet_hours_enabled=True,
        quiet_hours_start="22:00",
        quiet_hours_end="06:00",
    )
    db_session.add(prefs)
    await db_session.flush()
    await db_session.refresh(prefs)
    return prefs


# =============================================================================
# Test 1: Normal Flow
# =============================================================================


@pytest.mark.asyncio
async def test_route_normal_flow(db_session, sample_user, mock_ws_manager, mock_email_service):
    """NotificationRouter.route() persists in DB and broadcasts via WS."""
    router = NotificationRouter(session=db_session, email_service=mock_email_service)

    notification = NotificationCreate(
        user_id=sample_user.id,
        title="Test Alert",
        body="Sensor hat Schwellwert ueberschritten",
        severity="warning",
        category="data_quality",
        source="sensor_threshold",
    )

    result = await router.route(notification)

    assert result is not None
    assert result.id is not None
    assert result.title == "Test Alert"
    assert result.severity == "warning"

    # WS broadcasts should include notification_new + unread count refresh
    broadcast_calls = [call.args[0] for call in mock_ws_manager.broadcast.call_args_list]
    assert "notification_new" in broadcast_calls
    assert "notification_unread_count" in broadcast_calls


# =============================================================================
# Test 2: Fingerprint Dedup
# =============================================================================


@pytest.mark.asyncio
async def test_route_fingerprint_dedup(
    db_session, sample_user, mock_ws_manager, mock_email_service
):
    """Second notification with same fingerprint is skipped."""
    router = NotificationRouter(session=db_session, email_service=mock_email_service)

    notification = NotificationCreate(
        user_id=sample_user.id,
        title="Duplicate Alert",
        body="Same alert",
        severity="warning",
        category="system",
        source="grafana",
        fingerprint="abc123def456",
    )

    result1 = await router.route(notification)
    assert result1 is not None
    assert result1.id is not None

    result2 = await router.route(notification)
    assert result2 is None


# =============================================================================
# Test 3: Title Dedup (60s window)
# =============================================================================


@pytest.mark.asyncio
async def test_route_title_dedup_60s(db_session, sample_user, mock_ws_manager, mock_email_service):
    """Same title within 60s is deduplicated."""
    router = NotificationRouter(session=db_session, email_service=mock_email_service)

    notification = NotificationCreate(
        user_id=sample_user.id,
        title="Repeated Warning",
        body="Same warning",
        severity="warning",
        category="data_quality",
        source="sensor_threshold",
    )

    result1 = await router.route(notification)
    assert result1 is not None

    # Second call within 60s — should be deduped
    result2 = await router.route(notification)
    assert result2 is None


# =============================================================================
# Test 4: Critical → Immediate Email
# =============================================================================


@pytest.mark.asyncio
async def test_route_critical_immediate_email(
    db_session, sample_user, preferences_email_enabled, mock_ws_manager, mock_email_service
):
    """Critical severity triggers send_critical_alert()."""
    router = NotificationRouter(session=db_session, email_service=mock_email_service)

    notification = NotificationCreate(
        user_id=sample_user.id,
        title="Critical System Alert",
        body="Database unreachable",
        severity="critical",
        category="infrastructure",
        source="system",
    )

    result = await router.route(notification)
    assert result is not None

    # Email should have been sent
    mock_email_service.send_critical_alert.assert_called_once()


# =============================================================================
# Test 5: Warning — First of Day Email
# =============================================================================


@pytest.mark.asyncio
async def test_route_warning_first_of_day_email(
    db_session, sample_user, preferences_email_enabled, mock_ws_manager, mock_email_service
):
    """Warning: first of day sends immediate email, second goes to digest."""
    router = NotificationRouter(session=db_session, email_service=mock_email_service)

    notification = NotificationCreate(
        user_id=sample_user.id,
        title="Warning Alert",
        body="Temperature rising",
        severity="warning",
        category="data_quality",
        source="sensor_threshold",
    )

    # First warning of the day — should trigger email
    result1 = await router.route(notification)
    assert result1 is not None
    assert mock_email_service.send_critical_alert.call_count == 1

    # Second warning (different title to avoid dedup)
    notification2 = NotificationCreate(
        user_id=sample_user.id,
        title="Warning Alert 2",
        body="Humidity rising",
        severity="warning",
        category="data_quality",
        source="sensor_threshold",
    )
    result2 = await router.route(notification2)
    assert result2 is not None
    # Second warning should NOT trigger another immediate email
    assert mock_email_service.send_critical_alert.call_count == 1


# =============================================================================
# Test 6: Info — No Email
# =============================================================================


@pytest.mark.asyncio
async def test_route_info_no_email(
    db_session, sample_user, preferences_email_enabled, mock_ws_manager, mock_email_service
):
    """Info severity never triggers email regardless of preferences."""
    router = NotificationRouter(session=db_session, email_service=mock_email_service)

    notification = NotificationCreate(
        user_id=sample_user.id,
        title="Info Note",
        body="System restarted successfully",
        severity="info",
        category="system",
        source="system",
    )

    result = await router.route(notification)
    assert result is not None
    mock_email_service.send_critical_alert.assert_not_called()
    mock_email_service.send_email.assert_not_called()


# =============================================================================
# Test 7: Quiet Hours — Critical Passes
# =============================================================================


@pytest.mark.asyncio
async def test_route_quiet_hours_critical_passes(
    db_session, sample_user, preferences_quiet_hours, mock_ws_manager, mock_email_service
):
    """During quiet hours, critical still gets emailed."""
    router = NotificationRouter(session=db_session, email_service=mock_email_service)

    # Mock current time to be within quiet hours (23:00 UTC)
    mock_time = datetime(2026, 3, 2, 23, 0, 0, tzinfo=timezone.utc)
    with patch("src.services.notification_router.datetime") as mock_dt:
        mock_dt.now.return_value = mock_time
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

        notification = NotificationCreate(
            user_id=sample_user.id,
            title="Critical During Quiet Hours",
            body="Server down",
            severity="critical",
            category="infrastructure",
            source="system",
        )

        result = await router.route(notification)
        assert result is not None
        mock_email_service.send_critical_alert.assert_called_once()


# =============================================================================
# Test 8: Quiet Hours — Warning Blocked
# =============================================================================


@pytest.mark.asyncio
async def test_route_quiet_hours_warning_blocked(
    db_session, sample_user, preferences_quiet_hours, mock_ws_manager, mock_email_service
):
    """During quiet hours, warning is NOT emailed."""
    router = NotificationRouter(session=db_session, email_service=mock_email_service)

    # Mock current time to be within quiet hours (23:00 UTC)
    mock_time = datetime(2026, 3, 2, 23, 0, 0, tzinfo=timezone.utc)
    with patch("src.services.notification_router.datetime") as mock_dt:
        mock_dt.now.return_value = mock_time
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

        notification = NotificationCreate(
            user_id=sample_user.id,
            title="Warning During Quiet Hours",
            body="Temperature slightly elevated",
            severity="warning",
            category="data_quality",
            source="sensor_threshold",
        )

        result = await router.route(notification)
        assert result is not None
        mock_email_service.send_critical_alert.assert_not_called()


# =============================================================================
# Test 9: Quiet Hours Overnight Range
# =============================================================================


def test_is_quiet_hours_overnight_range():
    """Quiet hours 22:00-06:00: 23:00 → True, 07:00 → False."""
    router = NotificationRouter.__new__(NotificationRouter)

    prefs = MagicMock()
    prefs.quiet_hours_enabled = True
    prefs.quiet_hours_start = "22:00"
    prefs.quiet_hours_end = "06:00"

    # 23:00 should be in quiet hours
    with patch("src.services.notification_router.datetime") as mock_dt:
        mock_now = datetime(2026, 3, 2, 23, 0, 0, tzinfo=timezone.utc)
        mock_dt.now.return_value = mock_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        assert router._is_quiet_hours(prefs) is True

    # 07:00 should NOT be in quiet hours
    with patch("src.services.notification_router.datetime") as mock_dt:
        mock_now = datetime(2026, 3, 2, 7, 0, 0, tzinfo=timezone.utc)
        mock_dt.now.return_value = mock_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        assert router._is_quiet_hours(prefs) is False


# =============================================================================
# Test 10: WS Broadcast Error Non-Blocking
# =============================================================================


@pytest.mark.asyncio
async def test_broadcast_websocket_error_non_blocking(db_session, sample_user, mock_email_service):
    """WS broadcast failure is logged but does not block route()."""
    with patch(
        "src.websocket.manager.WebSocketManager.get_instance",
        side_effect=Exception("WebSocket connection failed"),
    ):
        router = NotificationRouter(session=db_session, email_service=mock_email_service)

        notification = NotificationCreate(
            user_id=sample_user.id,
            title="WS Error Test",
            body="This should persist despite WS failure",
            severity="info",
            category="system",
            source="system",
        )

        result = await router.route(notification)
        # Notification should still be persisted
        assert result is not None
        assert result.id is not None


# =============================================================================
# Test 11: Persist Suppressed Audit Trail
# =============================================================================


@pytest.mark.asyncio
async def test_persist_suppressed_audit_trail(
    db_session, sample_user, mock_ws_manager, mock_email_service
):
    """persist_suppressed() creates notification with channel='suppressed', is_read=True."""
    router = NotificationRouter(session=db_session, email_service=mock_email_service)

    notification = NotificationCreate(
        user_id=sample_user.id,
        title="Suppressed Alert",
        body="Sensor suppressed during maintenance",
        severity="warning",
        category="data_quality",
        source="sensor_threshold",
    )

    await router.persist_suppressed(notification)
    await db_session.commit()

    # Verify the suppressed notification was persisted
    from sqlalchemy import select

    stmt = select(Notification).where(
        Notification.user_id == sample_user.id,
        Notification.channel == "suppressed",
    )
    result = await db_session.execute(stmt)
    suppressed = result.scalar_one_or_none()

    assert suppressed is not None
    assert suppressed.channel == "suppressed"
    assert suppressed.is_read is True
    assert suppressed.title == "Suppressed Alert"


# =============================================================================
# Test 12: Broadcast Unread Count Correct
# =============================================================================


@pytest.mark.asyncio
async def test_broadcast_unread_count_correct(
    db_session, sample_user, sample_notification, mock_ws_manager, mock_email_service
):
    """broadcast_unread_count() sends correct count and highest_severity."""
    router = NotificationRouter(session=db_session, email_service=mock_email_service)

    await router.broadcast_unread_count(sample_user.id)

    mock_ws_manager.broadcast.assert_called()
    call_args = mock_ws_manager.broadcast.call_args
    assert call_args[0][0] == "notification_unread_count"
    data = call_args[0][1]
    assert data["user_id"] == sample_user.id
    assert data["unread_count"] >= 1
    assert data["highest_severity"] is not None


# =============================================================================
# Test 13: Broadcast propagates fingerprint (Fix-V Block 1)
# =============================================================================


@pytest.mark.asyncio
async def test_broadcast_to_all_propagates_fingerprint(
    db_session, sample_user, mock_ws_manager, mock_email_service
):
    """_broadcast_to_all() must propagate fingerprint to per-user notifications."""
    router = NotificationRouter(session=db_session, email_service=mock_email_service)

    # Broadcast notification (user_id=None) with fingerprint
    notification = NotificationCreate(
        user_id=None,
        title="Grafana Alert: CPU High",
        body="CPU > 90%",
        severity="warning",
        category="infrastructure",
        source="grafana",
        fingerprint="abc123def456",
        correlation_id="grafana_abc123def456",
    )

    result = await router.route(notification)
    assert result is not None

    # Verify the persisted notification has the fingerprint
    from sqlalchemy import select

    stmt = select(Notification).where(
        Notification.user_id == sample_user.id,
        Notification.title == "Grafana Alert: CPU High",
    )
    db_result = await db_session.execute(stmt)
    persisted = db_result.scalar_one_or_none()

    assert persisted is not None
    assert persisted.fingerprint == "abc123def456"


# =============================================================================
# Test 14: Fingerprint dedup blocks broadcast duplicates (Fix-V Block 1)
# =============================================================================


@pytest.mark.asyncio
async def test_broadcast_fingerprint_dedup_blocks_second(
    db_session, sample_user, mock_ws_manager, mock_email_service
):
    """Second broadcast with same fingerprint is deduplicated via per-user fingerprint."""
    router = NotificationRouter(session=db_session, email_service=mock_email_service)

    notification = NotificationCreate(
        user_id=None,
        title="Grafana Alert: Disk Full",
        body="Disk > 95%",
        severity="critical",
        category="infrastructure",
        source="grafana",
        fingerprint="disk_full_fp_001",
        correlation_id="grafana_disk_full_fp_001",
    )

    result1 = await router.route(notification)
    assert result1 is not None

    # Second identical broadcast — should be deduplicated
    result2 = await router.route(notification)
    assert result2 is None

    # Only one notification in DB for this user
    from sqlalchemy import select, func

    stmt = (
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.user_id == sample_user.id,
            Notification.title == "Grafana Alert: Disk Full",
        )
    )
    count_result = await db_session.execute(stmt)
    assert count_result.scalar_one() == 1


# =============================================================================
# Test 15: Correlation dedup refire-cycle protection (Fix-V Block 2)
# =============================================================================


@pytest.mark.asyncio
async def test_correlation_dedup_refire_cycle_protection(
    db_session, sample_user, mock_ws_manager, mock_email_service
):
    """Recently resolved notification with same correlation_id blocks refire."""
    from src.db.repositories.notification_repo import NotificationRepository

    repo = NotificationRepository(db_session)

    # Create and immediately resolve a notification (simulates Grafana resolved webhook)
    notification = Notification(
        user_id=sample_user.id,
        channel="websocket",
        severity="warning",
        category="infrastructure",
        title="Grafana Alert: Memory",
        source="grafana",
        correlation_id="grafana_mem_fp_001",
        status="resolved",
        resolved_at=datetime.now(timezone.utc) - timedelta(minutes=5),
    )
    db_session.add(notification)
    await db_session.flush()

    # Refire within 30 min — should be detected as duplicate
    is_dup = await repo.check_correlation_duplicate("grafana_mem_fp_001")
    assert is_dup is True


# =============================================================================
# Test 16: Correlation dedup allows genuinely new alert after 30+ min
# =============================================================================


@pytest.mark.asyncio
async def test_correlation_dedup_allows_after_30_min(
    db_session, sample_user, mock_ws_manager, mock_email_service
):
    """Alert resolved > 30 min ago should NOT block new firing."""
    from src.db.repositories.notification_repo import NotificationRepository

    repo = NotificationRepository(db_session)

    # Notification resolved 45 minutes ago
    notification = Notification(
        user_id=sample_user.id,
        channel="websocket",
        severity="warning",
        category="infrastructure",
        title="Grafana Alert: Old",
        source="grafana",
        correlation_id="grafana_old_fp_001",
        status="resolved",
        resolved_at=datetime.now(timezone.utc) - timedelta(minutes=45),
    )
    db_session.add(notification)
    await db_session.flush()

    # New firing after 45 min — should be allowed
    is_dup = await repo.check_correlation_duplicate("grafana_old_fp_001")
    assert is_dup is False
