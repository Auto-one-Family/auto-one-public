"""
Integration Tests: Alert Lifecycle (Phase 4B — ISA-18.2)

Tests the complete alert lifecycle:
- Acknowledge (active → acknowledged)
- Resolve (active/acknowledged → resolved)
- Auto-resolve by correlation_id
- Invalid state transitions
- Alert stats (MTTA, MTTR, counts)
- Root-cause grouping (group_under_parent)
- API endpoints for alert lifecycle
"""

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import patch

from src.core.security import create_access_token, get_password_hash
from src.db.models.notification import AlertStatus, Notification
from src.db.models.user import User
from src.db.repositories.notification_repo import NotificationRepository
from src.main import app

# =============================================================================
# Fixtures
# =============================================================================


@pytest_asyncio.fixture
async def alert_user(db_session: AsyncSession):
    """Create a user for alert lifecycle tests."""
    user = User(
        username="alert_operator",
        email="alert_op@example.com",
        password_hash=get_password_hash("AlertP@ss123"),
        full_name="Alert Operator",
        role="operator",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def alert_headers(alert_user: User):
    """Auth headers for alert user."""
    token = create_access_token(user_id=alert_user.id, additional_claims={"role": alert_user.role})
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def active_alert(db_session: AsyncSession, alert_user: User):
    """Create an active alert notification."""
    notif = Notification(
        user_id=alert_user.id,
        title="Threshold exceeded: Temperature",
        body="Sensor DS18B20 on ESP_AABB has value 45°C",
        channel="websocket",
        severity="critical",
        category="data_quality",
        source="sensor_threshold",
        status=AlertStatus.ACTIVE,
        correlation_id="threshold_AABB_temperature",
    )
    db_session.add(notif)
    await db_session.commit()
    await db_session.refresh(notif)
    return notif


@pytest_asyncio.fixture
async def acknowledged_alert(db_session: AsyncSession, alert_user: User):
    """Create an acknowledged alert notification."""
    now = datetime.now(timezone.utc)
    notif = Notification(
        user_id=alert_user.id,
        title="Threshold exceeded: Humidity",
        body="Sensor SHT31 on ESP_CCDD has value 95%",
        channel="websocket",
        severity="warning",
        category="data_quality",
        source="sensor_threshold",
        status=AlertStatus.ACKNOWLEDGED,
        acknowledged_at=now,
        acknowledged_by=alert_user.id,
        correlation_id="threshold_CCDD_humidity",
    )
    db_session.add(notif)
    await db_session.commit()
    await db_session.refresh(notif)
    return notif


@pytest_asyncio.fixture
async def resolved_alert(db_session: AsyncSession, alert_user: User):
    """Create a resolved alert notification."""
    now = datetime.now(timezone.utc)
    notif = Notification(
        user_id=alert_user.id,
        title="Old threshold alert",
        body="This was resolved",
        channel="websocket",
        severity="info",
        category="data_quality",
        source="sensor_threshold",
        status=AlertStatus.RESOLVED,
        resolved_at=now,
    )
    db_session.add(notif)
    await db_session.commit()
    await db_session.refresh(notif)
    return notif


@pytest_asyncio.fixture
async def multiple_alerts(db_session: AsyncSession, alert_user: User):
    """Create multiple alerts with different statuses for stats testing."""
    now = datetime.now(timezone.utc)
    alerts = []

    # 2 active critical alerts
    for i in range(2):
        a = Notification(
            user_id=alert_user.id,
            title=f"Critical Alert {i}",
            body=f"Critical body {i}",
            channel="websocket",
            severity="critical",
            category="data_quality",
            source="sensor_threshold",
            status=AlertStatus.ACTIVE,
            correlation_id=f"threshold_ESP{i}_temp",
        )
        db_session.add(a)
        alerts.append(a)

    # 1 active warning alert
    w = Notification(
        user_id=alert_user.id,
        title="Warning Alert",
        body="Warning body",
        channel="websocket",
        severity="warning",
        category="data_quality",
        source="sensor_threshold",
        status=AlertStatus.ACTIVE,
        correlation_id="threshold_ESP2_humidity",
    )
    db_session.add(w)
    alerts.append(w)

    # 1 acknowledged alert
    ack = Notification(
        user_id=alert_user.id,
        title="Acknowledged Alert",
        body="Ack body",
        channel="websocket",
        severity="warning",
        category="data_quality",
        source="sensor_threshold",
        status=AlertStatus.ACKNOWLEDGED,
        acknowledged_at=now,
        acknowledged_by=alert_user.id,
    )
    db_session.add(ack)
    alerts.append(ack)

    # 1 resolved today alert
    res = Notification(
        user_id=alert_user.id,
        title="Resolved Today",
        body="Resolved body",
        channel="websocket",
        severity="warning",
        category="data_quality",
        source="sensor_threshold",
        status=AlertStatus.RESOLVED,
        acknowledged_at=now,
        resolved_at=now,
    )
    db_session.add(res)
    alerts.append(res)

    await db_session.commit()
    for a in alerts:
        await db_session.refresh(a)
    return alerts


@pytest_asyncio.fixture
async def correlated_alerts(db_session: AsyncSession, alert_user: User):
    """Create alerts with matching correlation_id for auto-resolve testing."""
    alerts = []
    for i in range(3):
        a = Notification(
            user_id=alert_user.id,
            title=f"Grafana Alert {i}",
            body=f"Body {i}",
            channel="websocket",
            severity="warning",
            category="infrastructure",
            source="grafana",
            status=AlertStatus.ACTIVE if i < 2 else AlertStatus.ACKNOWLEDGED,
            correlation_id="grafana_abc123",
        )
        db_session.add(a)
        alerts.append(a)
    await db_session.commit()
    for a in alerts:
        await db_session.refresh(a)
    return alerts


# =============================================================================
# Repository Tests: Acknowledge
# =============================================================================


@pytest.mark.asyncio
async def test_acknowledge_active_alert(db_session, alert_user, active_alert):
    """acknowledge_alert() transitions active → acknowledged."""
    repo = NotificationRepository(db_session)

    result = await repo.acknowledge_alert(
        notification_id=active_alert.id,
        user_id=alert_user.id,
        acknowledging_user_id=alert_user.id,
    )

    assert result is not None
    assert result.status == AlertStatus.ACKNOWLEDGED
    assert result.acknowledged_at is not None
    assert result.acknowledged_by == alert_user.id


@pytest.mark.asyncio
async def test_acknowledge_already_acknowledged(db_session, alert_user, acknowledged_alert):
    """acknowledge_alert() returns unchanged if already acknowledged."""
    repo = NotificationRepository(db_session)
    original_ack_at = acknowledged_alert.acknowledged_at

    result = await repo.acknowledge_alert(
        notification_id=acknowledged_alert.id,
        user_id=alert_user.id,
        acknowledging_user_id=alert_user.id,
    )

    assert result is not None
    assert result.status == AlertStatus.ACKNOWLEDGED
    # acknowledged_at should not change
    assert result.acknowledged_at == original_ack_at


@pytest.mark.asyncio
async def test_acknowledge_resolved_alert(db_session, alert_user, resolved_alert):
    """acknowledge_alert() returns unchanged for resolved alerts (invalid transition)."""
    repo = NotificationRepository(db_session)

    result = await repo.acknowledge_alert(
        notification_id=resolved_alert.id,
        user_id=alert_user.id,
        acknowledging_user_id=alert_user.id,
    )

    assert result is not None
    assert result.status == AlertStatus.RESOLVED


@pytest.mark.asyncio
async def test_acknowledge_nonexistent(db_session, alert_user):
    """acknowledge_alert() returns None for non-existent notification."""
    repo = NotificationRepository(db_session)

    result = await repo.acknowledge_alert(
        notification_id=uuid.uuid4(),
        user_id=alert_user.id,
        acknowledging_user_id=alert_user.id,
    )

    assert result is None


# =============================================================================
# Repository Tests: Resolve
# =============================================================================


@pytest.mark.asyncio
async def test_resolve_active_alert(db_session, alert_user, active_alert):
    """resolve_alert() transitions active → resolved."""
    repo = NotificationRepository(db_session)

    result = await repo.resolve_alert(
        notification_id=active_alert.id,
        user_id=alert_user.id,
    )

    assert result is not None
    assert result.status == AlertStatus.RESOLVED
    assert result.resolved_at is not None
    assert result.is_read is True


@pytest.mark.asyncio
async def test_resolve_acknowledged_alert(db_session, alert_user, acknowledged_alert):
    """resolve_alert() transitions acknowledged → resolved."""
    repo = NotificationRepository(db_session)

    result = await repo.resolve_alert(
        notification_id=acknowledged_alert.id,
        user_id=alert_user.id,
    )

    assert result is not None
    assert result.status == AlertStatus.RESOLVED
    assert result.resolved_at is not None


@pytest.mark.asyncio
async def test_resolve_already_resolved(db_session, alert_user, resolved_alert):
    """resolve_alert() returns unchanged if already resolved (terminal state)."""
    repo = NotificationRepository(db_session)
    original_resolved_at = resolved_alert.resolved_at

    result = await repo.resolve_alert(
        notification_id=resolved_alert.id,
        user_id=alert_user.id,
    )

    assert result is not None
    assert result.status == AlertStatus.RESOLVED
    assert result.resolved_at == original_resolved_at


# =============================================================================
# Repository Tests: Auto-Resolve by Correlation ID
# =============================================================================


@pytest.mark.asyncio
async def test_auto_resolve_by_correlation(db_session, alert_user, correlated_alerts):
    """auto_resolve_by_correlation() resolves all matching active/acknowledged alerts."""
    repo = NotificationRepository(db_session)

    count = await repo.auto_resolve_by_correlation("grafana_abc123")

    assert count == 3  # 2 active + 1 acknowledged


@pytest.mark.asyncio
async def test_auto_resolve_no_match(db_session, alert_user, active_alert):
    """auto_resolve_by_correlation() returns 0 for non-matching correlation."""
    repo = NotificationRepository(db_session)

    count = await repo.auto_resolve_by_correlation("nonexistent_correlation")

    assert count == 0


# =============================================================================
# Repository Tests: Alert Stats
# =============================================================================


@pytest.mark.asyncio
async def test_get_alert_stats(db_session, alert_user, multiple_alerts):
    """get_alert_stats() returns correct counts and metrics."""
    repo = NotificationRepository(db_session)

    stats = await repo.get_alert_stats(user_id=alert_user.id)

    assert stats["active_count"] == 3  # 2 critical + 1 warning
    assert stats["acknowledged_count"] == 1
    assert stats["critical_active"] == 2
    assert stats["warning_active"] == 1
    assert stats["resolved_today_count"] == 1


@pytest.mark.asyncio
async def test_get_alert_stats_empty(db_session, alert_user):
    """get_alert_stats() returns zeroes when no alerts exist."""
    repo = NotificationRepository(db_session)

    stats = await repo.get_alert_stats(user_id=alert_user.id)

    assert stats["active_count"] == 0
    assert stats["acknowledged_count"] == 0
    assert stats["critical_active"] == 0
    assert stats["warning_active"] == 0
    assert stats["resolved_today_count"] == 0
    assert stats["mean_time_to_acknowledge_s"] is None
    assert stats["mean_time_to_resolve_s"] is None


# =============================================================================
# Repository Tests: Alerts by Status
# =============================================================================


@pytest.mark.asyncio
async def test_get_alerts_by_status_active(db_session, alert_user, multiple_alerts):
    """get_alerts_by_status() returns only active alerts sorted by severity."""
    repo = NotificationRepository(db_session)

    alerts, total = await repo.get_alerts_by_status(
        status=AlertStatus.ACTIVE,
        user_id=alert_user.id,
    )

    assert total == 3
    assert len(alerts) == 3
    # Critical should come first (severity sort)
    assert alerts[0].severity == "critical"


@pytest.mark.asyncio
async def test_get_alerts_by_status_acknowledged(db_session, alert_user, multiple_alerts):
    """get_alerts_by_status() returns only acknowledged alerts."""
    repo = NotificationRepository(db_session)

    alerts, total = await repo.get_alerts_by_status(
        status=AlertStatus.ACKNOWLEDGED,
        user_id=alert_user.id,
    )

    assert total == 1
    assert alerts[0].status == AlertStatus.ACKNOWLEDGED


# =============================================================================
# Repository Tests: Active Counts by Severity (Prometheus)
# =============================================================================


@pytest.mark.asyncio
async def test_get_active_counts_by_severity(db_session, alert_user, multiple_alerts):
    """get_active_counts_by_severity() returns counts grouped by severity."""
    repo = NotificationRepository(db_session)

    counts = await repo.get_active_counts_by_severity()

    assert counts["critical"] == 2
    assert counts["warning"] >= 2  # 1 active + 1 acknowledged (both unresolved)


# =============================================================================
# Repository Tests: Root-Cause Grouping
# =============================================================================


@pytest.mark.asyncio
async def test_group_under_parent(db_session, alert_user):
    """group_under_parent() groups dependent alerts under root-cause notification."""
    # Create root-cause alert (device offline)
    root = Notification(
        user_id=alert_user.id,
        title="ESP_AABB offline",
        body="Device disconnected",
        channel="websocket",
        severity="critical",
        category="connectivity",
        source="mqtt_handler",
        status=AlertStatus.ACTIVE,
        correlation_id="device_offline_AABB",
    )
    db_session.add(root)

    # Create dependent sensor alerts for the same ESP
    for i in range(3):
        dep = Notification(
            user_id=alert_user.id,
            title=f"Sensor stale on ESP_AABB ({i})",
            body=f"Sensor data stale {i}",
            channel="websocket",
            severity="warning",
            category="data_quality",
            source="sensor_threshold",
            status=AlertStatus.ACTIVE,
            correlation_id=f"threshold_AABB_sensor{i}",
        )
        db_session.add(dep)

    await db_session.commit()
    await db_session.refresh(root)

    repo = NotificationRepository(db_session)
    count = await repo.group_under_parent(
        parent_notification_id=root.id,
        correlation_prefix="threshold_AABB",
    )

    assert count == 3


@pytest.mark.asyncio
async def test_group_under_parent_no_match(db_session, alert_user, active_alert):
    """group_under_parent() returns 0 when no dependent alerts match."""
    repo = NotificationRepository(db_session)

    count = await repo.group_under_parent(
        parent_notification_id=active_alert.id,
        correlation_prefix="nonexistent_prefix",
    )

    assert count == 0


# =============================================================================
# VALID_TRANSITIONS State Machine Tests
# =============================================================================


def test_valid_transitions_active():
    """Active can transition to acknowledged or resolved."""
    valid = AlertStatus.VALID_TRANSITIONS[AlertStatus.ACTIVE]
    assert AlertStatus.ACKNOWLEDGED in valid
    assert AlertStatus.RESOLVED in valid


def test_valid_transitions_acknowledged():
    """Acknowledged can only transition to resolved."""
    valid = AlertStatus.VALID_TRANSITIONS[AlertStatus.ACKNOWLEDGED]
    assert AlertStatus.RESOLVED in valid
    assert AlertStatus.ACKNOWLEDGED not in valid
    assert AlertStatus.ACTIVE not in valid


def test_valid_transitions_resolved():
    """Resolved is terminal — no valid transitions."""
    valid = AlertStatus.VALID_TRANSITIONS[AlertStatus.RESOLVED]
    assert len(valid) == 0


# =============================================================================
# API Endpoint Tests
# =============================================================================


@pytest.mark.asyncio
async def test_api_acknowledge_alert(
    alert_headers,
    active_alert,
    mock_ws_manager,
):
    """PATCH /v1/notifications/{id}/acknowledge returns acknowledged alert."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(
            f"/api/v1/notifications/{active_alert.id}/acknowledge",
            headers=alert_headers,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "acknowledged"
    assert body["acknowledged_at"] is not None


@pytest.mark.asyncio
async def test_api_acknowledge_resolved_returns_409(
    alert_headers,
    resolved_alert,
    mock_ws_manager,
):
    """PATCH /v1/notifications/{id}/acknowledge returns 409 for resolved alert."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(
            f"/api/v1/notifications/{resolved_alert.id}/acknowledge",
            headers=alert_headers,
        )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_api_resolve_alert(
    alert_headers,
    active_alert,
    mock_ws_manager,
):
    """PATCH /v1/notifications/{id}/resolve returns resolved alert."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(
            f"/api/v1/notifications/{active_alert.id}/resolve",
            headers=alert_headers,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "resolved"
    assert body["resolved_at"] is not None


@pytest.mark.asyncio
async def test_api_resolve_already_resolved_returns_409(
    alert_headers,
    resolved_alert,
    mock_ws_manager,
):
    """PATCH /v1/notifications/{id}/resolve returns 409 for already resolved alert."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(
            f"/api/v1/notifications/{resolved_alert.id}/resolve",
            headers=alert_headers,
        )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_api_acknowledge_nonexistent_returns_404(
    alert_headers,
    mock_ws_manager,
):
    """PATCH /v1/notifications/{id}/acknowledge returns 404 for unknown ID."""
    fake_id = uuid.uuid4()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(
            f"/api/v1/notifications/{fake_id}/acknowledge",
            headers=alert_headers,
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_api_get_active_alerts(
    alert_headers,
    multiple_alerts,
):
    """GET /v1/notifications/alerts/active returns active alerts."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/notifications/alerts/active",
            headers=alert_headers,
            params={"status": "active"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["pagination"]["total_items"] == 3


@pytest.mark.asyncio
async def test_api_get_alert_stats(
    alert_headers,
    multiple_alerts,
):
    """GET /v1/notifications/alerts/stats returns ISA-18.2 metrics."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/notifications/alerts/stats",
            headers=alert_headers,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["active_count"] == 3
    assert body["acknowledged_count"] == 1
    assert body["critical_active"] == 2
    assert body["warning_active"] == 1


@pytest.mark.asyncio
async def test_api_alert_lifecycle_flow(
    alert_headers,
    active_alert,
    mock_ws_manager,
):
    """Full lifecycle: active → acknowledged → resolved via API."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Step 1: Acknowledge
        resp1 = await client.patch(
            f"/api/v1/notifications/{active_alert.id}/acknowledge",
            headers=alert_headers,
        )
        assert resp1.status_code == 200
        assert resp1.json()["status"] == "acknowledged"

        # Step 2: Resolve
        resp2 = await client.patch(
            f"/api/v1/notifications/{active_alert.id}/resolve",
            headers=alert_headers,
        )
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "resolved"

        # Step 3: Cannot acknowledge again (409)
        resp3 = await client.patch(
            f"/api/v1/notifications/{active_alert.id}/acknowledge",
            headers=alert_headers,
        )
        assert resp3.status_code == 409
