"""
Integration Tests: Health API

Phase: 5 (Week 9-10) - API Layer
Tests: Health endpoints (basic, detailed, esp, metrics)
"""

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token, get_password_hash
from src.db.models.user import User
from src.main import app


@pytest.fixture
async def test_user(db_session: AsyncSession):
    """Create a test user."""
    user = User(
        username="health_user",
        email="health@example.com",
        password_hash=get_password_hash("HealthP@ss123"),
        full_name="Health User",
        role="viewer",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers(test_user: User):
    """Get authorization headers."""
    token = create_access_token(user_id=test_user.id, additional_claims={"role": test_user.role})
    return {"Authorization": f"Bearer {token}"}


class TestBasicHealth:
    """Test basic health endpoint."""

    @pytest.mark.asyncio
    async def test_health_check(self):
        """Test basic health check (no auth required)."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/health/")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "status" in data
        assert data["status"] in ["healthy", "degraded", "unhealthy"]
        assert "version" in data
        assert "uptime_seconds" in data

    @pytest.mark.asyncio
    async def test_root_health(self):
        """Test root endpoint health."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "God-Kaiser Server"
        assert data["status"] == "online"


class TestDetailedHealth:
    """Test detailed health endpoint."""

    @pytest.mark.asyncio
    async def test_detailed_health(self, auth_headers: dict):
        """Test detailed health check (requires auth)."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/health/detailed",
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "database" in data
        assert "mqtt" in data
        assert "websocket" in data
        assert "system" in data

    @pytest.mark.asyncio
    async def test_detailed_health_no_auth(self):
        """Test detailed health without auth fails."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/health/detailed")

        assert response.status_code == 401


class TestESPHealth:
    """Test ESP health summary endpoint."""

    @pytest.mark.asyncio
    async def test_esp_health_summary(self, auth_headers: dict):
        """Test ESP health summary."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/health/esp",
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "total_devices" in data
        assert "online_count" in data
        assert "offline_count" in data
        assert "devices" in data


class TestPrometheusMetrics:
    """Test Prometheus metrics endpoint."""

    @pytest.mark.asyncio
    async def test_prometheus_metrics(self):
        pytest.importorskip("prometheus_client", reason="prometheus_client not installed")
        """Test Prometheus metrics export."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/health/metrics")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/plain")
        # Check for Prometheus format markers
        content = response.text
        assert "# HELP" in content
        assert "# TYPE" in content
        # Check for standard process/python metrics (always present)
        assert "python_gc" in content or "god_kaiser" in content


class TestKubernetesProbes:
    """Test Kubernetes probe endpoints."""

    @pytest.mark.asyncio
    async def test_liveness_probe(self):
        """Test liveness probe."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/health/live")

        assert response.status_code == 200
        data = response.json()
        assert data["alive"] is True

    @pytest.mark.asyncio
    async def test_readiness_probe(self):
        """Test readiness probe."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/health/ready")

        assert response.status_code == 200
        data = response.json()
        assert "ready" in data
        assert "checks" in data
        assert "runtime_mode" in data
