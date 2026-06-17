"""
Integration Tests: Notifications REST API

Phase 4A Test-Suite (STEP 4, Block 2)
Tests: All 9 REST endpoints + 1 Auth test
"""

import uuid

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import patch

from src.core.security import create_access_token, get_password_hash
from src.db.models.notification import Notification
from src.db.models.user import User
from src.main import app

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
async def operator_user(db_session: AsyncSession):
    """Create an operator user for notification tests."""
    user = User(
        username="notif_operator",
        email="notif_op@example.com",
        password_hash=get_password_hash("OperatorP@ss123"),
        full_name="Notification Operator",
        role="operator",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def admin_user(db_session: AsyncSession):
    """Create an admin user for notification tests."""
    user = User(
        username="notif_admin",
        email="notif_admin@example.com",
        password_hash=get_password_hash("AdminP@ss123"),
        full_name="Notification Admin",
        role="admin",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def operator_headers(operator_user: User):
    """Auth headers for operator user."""
    token = create_access_token(
        user_id=operator_user.id, additional_claims={"role": operator_user.role}
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers(admin_user: User):
    """Auth headers for admin user."""
    token = create_access_token(user_id=admin_user.id, additional_claims={"role": admin_user.role})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def user_notification(db_session: AsyncSession, operator_user: User):
    """Create a notification for operator_user."""
    notif = Notification(
        user_id=operator_user.id,
        title="Test Notification",
        body="Sensor data stale for 5 minutes",
        channel="websocket",
        severity="warning",
        category="data_quality",
        source="sensor_threshold",
    )
    db_session.add(notif)
    await db_session.commit()
    await db_session.refresh(notif)
    return notif


@pytest.fixture
async def multiple_notifications(db_session: AsyncSession, operator_user: User):
    """Create multiple notifications for pagination testing."""
    notifications = []
    for i in range(5):
        severity = "critical" if i == 0 else "warning" if i < 3 else "info"
        notif = Notification(
            user_id=operator_user.id,
            title=f"Notification {i}",
            body=f"Test body {i}",
            channel="websocket",
            severity=severity,
            category="data_quality" if i < 3 else "system",
            source="sensor_threshold",
        )
        db_session.add(notif)
        notifications.append(notif)
    await db_session.commit()
    for n in notifications:
        await db_session.refresh(n)
    return notifications


# =============================================================================
# Test 1: GET /v1/notifications — Paginated
# =============================================================================


@pytest.mark.asyncio
async def test_get_notifications_paginated(
    operator_headers,
    multiple_notifications,
):
    """GET /v1/notifications returns paginated list."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/notifications",
            headers=operator_headers,
            params={"page": 1, "page_size": 10},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert "data" in body
    assert "pagination" in body
    assert body["pagination"]["total_items"] >= 5


# =============================================================================
# Test 2: GET /v1/notifications?severity=critical — Filter
# =============================================================================


@pytest.mark.asyncio
async def test_get_notifications_filter_severity(
    operator_headers,
    multiple_notifications,
):
    """GET /v1/notifications?severity=critical filters correctly."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/notifications",
            headers=operator_headers,
            params={"severity": "critical"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    for item in body["data"]:
        assert item["severity"] == "critical"


# =============================================================================
# Test 2a: GET /v1/notifications?status — Lifecycle filter (AUT-196)
# =============================================================================


@pytest.mark.asyncio
async def test_get_notifications_filter_status(
    operator_headers,
    db_session: AsyncSession,
    operator_user: User,
):
    """GET /v1/notifications?status filters on alert lifecycle (server-side)."""
    active_n = Notification(
        user_id=operator_user.id,
        title="Active alert",
        body="",
        channel="websocket",
        severity="warning",
        category="system",
        source="manual",
        status="active",
    )
    ack_n = Notification(
        user_id=operator_user.id,
        title="Ack alert",
        body="",
        channel="websocket",
        severity="warning",
        category="system",
        source="manual",
        status="acknowledged",
    )
    db_session.add_all([active_n, ack_n])
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/notifications",
            headers=operator_headers,
            params={"status": "acknowledged", "page_size": 50},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    ids = {item["id"] for item in body["data"]}
    assert str(ack_n.id) in ids
    assert str(active_n.id) not in ids
    for item in body["data"]:
        if item["id"] == str(ack_n.id):
            assert item["status"] == "acknowledged"


@pytest.mark.asyncio
async def test_get_notifications_filter_source_bucket_system(
    operator_headers,
    db_session: AsyncSession,
    operator_user: User,
):
    """GET /v1/notifications?source_bucket=system matches grouped sources."""
    logic_n = Notification(
        user_id=operator_user.id,
        title="Logic",
        body="",
        channel="websocket",
        severity="info",
        category="system",
        source="logic_engine",
        status="active",
    )
    manual_n = Notification(
        user_id=operator_user.id,
        title="Manual",
        body="",
        channel="websocket",
        severity="info",
        category="system",
        source="manual",
        status="active",
    )
    db_session.add_all([logic_n, manual_n])
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/notifications",
            headers=operator_headers,
            params={"source_bucket": "system"},
        )
    assert response.status_code == 200
    body = response.json()
    ids = {item["id"] for item in body["data"]}
    assert str(manual_n.id) in ids
    assert str(logic_n.id) not in ids


@pytest.mark.asyncio
async def test_get_notifications_invalid_status_returns_422(operator_headers):
    """Invalid ?status= yields 422 (not an empty list)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/notifications",
            headers=operator_headers,
            params={"status": "not_a_status"},
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_notifications_invalid_source_bucket_returns_422(operator_headers):
    """Invalid ?source_bucket= yields 422 (not silently ignored)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/notifications",
            headers=operator_headers,
            params={"source_bucket": "bogus"},
        )
    assert response.status_code == 422


# =============================================================================
# Test 3: GET /v1/notifications?category=system — Filter
# =============================================================================


@pytest.mark.asyncio
async def test_get_notifications_filter_category(
    operator_headers,
    multiple_notifications,
):
    """GET /v1/notifications?category=system filters correctly."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/notifications",
            headers=operator_headers,
            params={"category": "system"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    for item in body["data"]:
        assert item["category"] == "system"


# =============================================================================
# Test 4: GET /v1/notifications/unread-count
# =============================================================================


@pytest.mark.asyncio
async def test_get_unread_count(
    operator_headers,
    multiple_notifications,
):
    """GET /v1/notifications/unread-count returns count and highest severity."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/notifications/unread-count",
            headers=operator_headers,
        )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["unread_count"] >= 5
    assert body["highest_severity"] == "critical"


# =============================================================================
# Test 5: GET /v1/notifications/{id}
# =============================================================================


@pytest.mark.asyncio
async def test_get_notification_by_id(
    operator_headers,
    user_notification,
):
    """GET /v1/notifications/{id} returns single notification."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            f"/api/v1/notifications/{user_notification.id}",
            headers=operator_headers,
        )
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Test Notification"
    assert body["severity"] == "warning"


# =============================================================================
# Test 6: GET /v1/notifications/{invalid_id} → 404
# =============================================================================


@pytest.mark.asyncio
async def test_get_notification_not_found(operator_headers):
    """GET /v1/notifications/{invalid_id} returns 404."""
    fake_id = str(uuid.uuid4())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            f"/api/v1/notifications/{fake_id}",
            headers=operator_headers,
        )
    assert response.status_code == 404


# =============================================================================
# Test 7: PATCH /v1/notifications/{id}/read
# =============================================================================


@pytest.mark.asyncio
async def test_mark_as_read(operator_headers, user_notification):
    """PATCH /v1/notifications/{id}/read marks notification as read."""
    from unittest.mock import AsyncMock

    # Mock WS manager to avoid broadcast errors
    mock_ws = AsyncMock()
    mock_ws.broadcast = AsyncMock()
    with patch(
        "src.websocket.manager.WebSocketManager.get_instance",
        return_value=mock_ws,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.patch(
                f"/api/v1/notifications/{user_notification.id}/read",
                headers=operator_headers,
            )
    assert response.status_code == 200
    body = response.json()
    assert body["is_read"] is True


# =============================================================================
# Test 8: PATCH /v1/notifications/read-all
# =============================================================================


@pytest.mark.asyncio
async def test_mark_all_as_read(operator_headers, multiple_notifications):
    """PATCH /v1/notifications/read-all marks all as read."""
    from unittest.mock import AsyncMock

    mock_ws = AsyncMock()
    mock_ws.broadcast = AsyncMock()
    with patch(
        "src.websocket.manager.WebSocketManager.get_instance",
        return_value=mock_ws,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.patch(
                "/api/v1/notifications/read-all",
                headers=operator_headers,
            )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True

    # Verify unread count is now 0
    with patch(
        "src.websocket.manager.WebSocketManager.get_instance",
        return_value=mock_ws,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            count_response = await client.get(
                "/api/v1/notifications/unread-count",
                headers=operator_headers,
            )
    assert count_response.json()["unread_count"] == 0


# =============================================================================
# Test 9: POST /v1/notifications/send — Admin Only
# =============================================================================


@pytest.mark.asyncio
async def test_send_notification_admin_only(admin_headers, admin_user):
    """POST /v1/notifications/send works for admin user."""
    from unittest.mock import AsyncMock

    mock_ws = AsyncMock()
    mock_ws.broadcast = AsyncMock()
    with patch(
        "src.websocket.manager.WebSocketManager.get_instance",
        return_value=mock_ws,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/notifications/send",
                json={
                    "title": "Admin Test Notification",
                    "body": "Sent by admin",
                    "severity": "info",
                    "category": "system",
                    "source": "manual",
                },
                headers=admin_headers,
            )
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Admin Test Notification"


# =============================================================================
# Test 10: POST /v1/notifications/send — Non-Admin → 403
# =============================================================================


@pytest.mark.asyncio
async def test_send_notification_non_admin_forbidden(operator_headers):
    """POST /v1/notifications/send with operator returns 403."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/notifications/send",
            json={
                "title": "Unauthorized Test",
                "severity": "info",
            },
            headers=operator_headers,
        )
    assert response.status_code == 403
