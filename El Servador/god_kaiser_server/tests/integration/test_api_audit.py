"""
Integration Tests: Audit Log API

Phase: 5 - API Layer
Tests: Audit log listing, statistics, and metadata endpoints
"""

import uuid

import pytest
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token, get_password_hash
from src.db.models.audit_log import AuditLog
from src.db.models.user import User
from src.main import app


@pytest.fixture
async def operator_user(db_session: AsyncSession):
    """Create an operator user."""
    user = User(
        username="audit_operator",
        email="audit_op@example.com",
        password_hash=get_password_hash("OperatorP@ss123"),
        full_name="Audit Operator",
        role="operator",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers(operator_user: User):
    """Get authorization headers."""
    token = create_access_token(
        user_id=operator_user.id, additional_claims={"role": operator_user.role}
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def sample_audit_logs(db_session: AsyncSession):
    """Create sample audit log entries."""
    logs = [
        AuditLog(
            event_type="config_response",
            severity="info",
            source_type="esp32",
            source_id="ESP_AUDIT001",
            status="success",
            message="Config applied successfully",
            details={"gpio": 5},
        ),
        AuditLog(
            event_type="emergency_stop",
            severity="critical",
            source_type="user",
            source_id="admin",
            status="success",
            message="Emergency stop triggered",
            details={"reason": "test"},
        ),
        AuditLog(
            event_type="login_failed",
            severity="warning",
            source_type="api",
            source_id="unknown",
            status="failed",
            message="Invalid credentials",
            details={},
            error_code="AUTH_001",
        ),
    ]
    for log in logs:
        db_session.add(log)
    await db_session.commit()
    return logs


class TestAuditList:
    """Test audit log listing."""

    @pytest.mark.asyncio
    async def test_list_audit_logs(self, auth_headers: dict, sample_audit_logs):
        """Test listing audit logs."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/audit",
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 3
        assert len(data["data"]) >= 3

    @pytest.mark.asyncio
    async def test_list_audit_logs_filter_by_severity(self, auth_headers: dict, sample_audit_logs):
        """Test filtering audit logs by severity."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/audit",
                params={"severity": "critical"},
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert all(log["severity"] == "critical" for log in data["data"])

    @pytest.mark.asyncio
    async def test_list_audit_logs_filter_by_event_type(
        self, auth_headers: dict, sample_audit_logs
    ):
        """Test filtering audit logs by event type."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/audit",
                params={"event_type": "emergency_stop"},
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert all(log["event_type"] == "emergency_stop" for log in data["data"])

    @pytest.mark.asyncio
    async def test_list_audit_logs_pagination(self, auth_headers: dict, sample_audit_logs):
        """Test audit log pagination."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/audit",
                params={"page": 1, "page_size": 2},
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) <= 2
        assert data["page"] == 1
        assert data["page_size"] == 2

    @pytest.mark.asyncio
    async def test_list_audit_logs_no_auth(self):
        """Test audit log listing without authentication."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/audit")

        assert response.status_code == 401


class TestAuditStatistics:
    """Test audit statistics endpoints."""

    @pytest.mark.asyncio
    async def test_get_statistics(self, auth_headers: dict, sample_audit_logs):
        """Test getting audit statistics."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/audit/statistics",
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert "total_count" in data
        assert "count_by_severity" in data
        assert "count_by_event_type" in data

    @pytest.mark.asyncio
    async def test_get_error_rate(self, auth_headers: dict, sample_audit_logs):
        """Test getting error rate."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/audit/error-rate",
                headers=auth_headers,
            )

        assert response.status_code == 200


class TestAuditMetadata:
    """Test audit metadata endpoints."""

    @pytest.mark.asyncio
    async def test_list_event_types(self):
        """Test listing event types (public endpoint)."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/audit/event-types")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        assert "value" in data[0]
        assert "description" in data[0]

    @pytest.mark.asyncio
    async def test_list_severities(self):
        """Test listing severities (public endpoint)."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/audit/severities")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 4  # info, warning, error, critical

    @pytest.mark.asyncio
    async def test_list_source_types(self):
        """Test listing source types (public endpoint)."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/audit/source-types")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert "esp32" in data
        assert "system" in data
