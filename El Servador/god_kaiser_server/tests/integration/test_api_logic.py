"""
Integration Tests: Logic Rules API

Phase: 5 (Week 9-10) - API Layer
Tests: Logic endpoints (rules CRUD, toggle, test, history)
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import sessionmaker

from src.api.deps import get_db
from src.core.security import create_access_token, get_password_hash
from src.db.models.logic import CrossESPLogic
from src.db.models.user import User
from src.main import app


@pytest_asyncio.fixture(scope="function")
async def integration_session(test_engine: AsyncEngine):
    """
    Create a session without auto-managed transaction for integration tests.
    This allows the API to manage its own commits/rollbacks.
    """
    async_session_maker = sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with async_session_maker() as session:
        yield session
        # Rollback any uncommitted changes
        await session.rollback()


@pytest.fixture
def override_db(integration_session: AsyncSession):
    """Override the get_db dependency to use the integration session."""

    async def _override_get_db():
        yield integration_session

    app.dependency_overrides[get_db] = _override_get_db
    yield
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_rule(integration_session: AsyncSession):
    """Create a test logic rule."""
    rule = CrossESPLogic(
        rule_name="Test pH Alert Rule",
        description="Test rule for pH monitoring",
        trigger_conditions={
            "type": "sensor",  # Match API expected type
            "esp_id": "ESP_12AB34CD",
            "gpio": 34,
            "sensor_type": "ph",
            "operator": ">",
            "value": 7.5,
        },
        actions=[
            {
                "type": "actuator",  # Match API expected type
                "esp_id": "ESP_AABBCCDD",
                "gpio": 5,
                "actuator_type": "pump",
                "value": 0.0,
            }
        ],
        enabled=True,
        priority=80,
        cooldown_seconds=300,
    )
    integration_session.add(rule)
    await integration_session.commit()
    await integration_session.refresh(rule)
    return rule


@pytest_asyncio.fixture
async def operator_user(integration_session: AsyncSession):
    """Create an operator user."""
    user = User(
        username="logic_operator",
        email="logic_op@example.com",
        password_hash=get_password_hash("OperatorP@ss123"),
        full_name="Logic Operator",
        role="operator",
        is_active=True,
    )
    integration_session.add(user)
    await integration_session.commit()
    await integration_session.refresh(user)
    return user


@pytest.fixture
def auth_headers(operator_user: User):
    """Get authorization headers."""
    token = create_access_token(
        user_id=operator_user.id, additional_claims={"role": operator_user.role}
    )
    return {"Authorization": f"Bearer {token}"}


class TestListRules:
    """Test rule listing."""

    @pytest.mark.asyncio
    async def test_list_rules(self, override_db, auth_headers: dict, test_rule: CrossESPLogic):
        """Test listing logic rules."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/logic/rules",
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["data"]) >= 1

    @pytest.mark.asyncio
    async def test_list_rules_enabled_filter(
        self, override_db, auth_headers: dict, test_rule: CrossESPLogic
    ):
        """Test listing only enabled rules."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/logic/rules",
                params={"enabled": True},
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert all(r["enabled"] for r in data["data"])


class TestGetRule:
    """Test getting single rule."""

    @pytest.mark.asyncio
    async def test_get_rule(self, override_db, auth_headers: dict, test_rule: CrossESPLogic):
        """Test getting a rule by ID."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/logic/rules/{test_rule.id}",
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test pH Alert Rule"
        assert len(data["conditions"]) == 1
        assert len(data["actions"]) == 1

    @pytest.mark.asyncio
    async def test_get_rule_not_found(self, override_db, auth_headers: dict):
        """Test getting non-existent rule."""
        # Use valid UUID format that doesn't exist in DB
        non_existent_uuid = "00000000-0000-0000-0000-000000000000"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/logic/rules/{non_existent_uuid}",
                headers=auth_headers,
            )

        assert response.status_code == 404


class TestCreateRule:
    """Test rule creation."""

    @pytest.mark.asyncio
    async def test_create_rule(self, override_db, auth_headers: dict):
        """Test creating a logic rule."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/logic/rules",
                json={
                    "name": "New Temperature Rule",
                    "description": "Turn on fan when temperature too high",
                    "conditions": [
                        {
                            "type": "sensor",
                            "esp_id": "ESP_11223344",
                            "gpio": 35,
                            "operator": ">",
                            "value": 30.0,
                        }
                    ],
                    "actions": [
                        {
                            "type": "actuator",
                            "esp_id": "ESP_55667788",
                            "gpio": 4,
                            "command": "ON",
                            "value": 1.0,
                        }
                    ],
                    "logic_operator": "AND",
                    "enabled": True,
                    "priority": 60,
                    "cooldown_seconds": 120,
                },
                headers=auth_headers,
            )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "New Temperature Rule"
        assert data["enabled"] is True


class TestUpdateRule:
    """Test rule update."""

    @pytest.mark.asyncio
    async def test_update_rule(self, override_db, auth_headers: dict, test_rule: CrossESPLogic):
        """Test updating a rule."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.put(
                f"/api/v1/logic/rules/{test_rule.id}",
                json={
                    "name": "Updated Rule Name",
                    "priority": 90,
                },
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Rule Name"
        assert data["priority"] == 90


class TestToggleRule:
    """Test rule toggling."""

    @pytest.mark.asyncio
    async def test_toggle_rule_disable(
        self, override_db, auth_headers: dict, test_rule: CrossESPLogic
    ):
        """Test disabling a rule."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/logic/rules/{test_rule.id}/toggle",
                json={
                    "enabled": False,
                    "reason": "Testing disable",
                },
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is False
        assert data["previous_state"] is True

    @pytest.mark.asyncio
    async def test_toggle_rule_enable(
        self, override_db, auth_headers: dict, integration_session: AsyncSession
    ):
        """Test enabling a disabled rule."""
        # Create disabled rule
        rule = CrossESPLogic(
            rule_name="Disabled Rule",
            trigger_conditions={
                "type": "sensor",
                "esp_id": "ESP_00000000",
                "gpio": 0,
                "operator": ">",
                "value": 0,
            },
            actions=[{"type": "actuator", "esp_id": "ESP_00000000", "gpio": 0, "value": 1.0}],
            enabled=False,
            priority=50,
            cooldown_seconds=60,
        )
        integration_session.add(rule)
        await integration_session.commit()
        await integration_session.refresh(rule)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/logic/rules/{rule.id}/toggle",
                json={"enabled": True},
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is True


class TestTestRule:
    """Test rule simulation."""

    @pytest.mark.asyncio
    async def test_simulate_rule(self, override_db, auth_headers: dict, test_rule: CrossESPLogic):
        """Test simulating rule execution."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/logic/rules/{test_rule.id}/test",
                json={
                    "mock_sensor_values": {
                        "ESP_12AB34CD:34": 7.8,  # Above threshold
                    },
                    "mock_time": "14:00",
                    "dry_run": True,
                },
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert str(data["rule_id"]) == str(test_rule.id)  # Compare as strings (UUID serialization)
        assert data["would_trigger"] is True
        assert data["dry_run"] is True

    @pytest.mark.asyncio
    async def test_simulate_rule_not_trigger(
        self, override_db, auth_headers: dict, test_rule: CrossESPLogic
    ):
        """Test simulating rule that doesn't trigger."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/logic/rules/{test_rule.id}/test",
                json={
                    "mock_sensor_values": {
                        "ESP_12AB34CD:34": 6.5,  # Below threshold
                    },
                    "dry_run": True,
                },
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["would_trigger"] is False


class TestExecutionHistory:
    """Test execution history endpoint."""

    @pytest.mark.asyncio
    async def test_get_execution_history(
        self, override_db, auth_headers: dict, test_rule: CrossESPLogic
    ):
        """Test getting execution history."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/logic/execution_history",
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "entries" in data
        assert "total_count" in data

    @pytest.mark.asyncio
    async def test_get_execution_history_with_filter(
        self, override_db, auth_headers: dict, test_rule: CrossESPLogic
    ):
        """Test getting execution history filtered by rule."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/logic/execution_history",
                params={"rule_id": test_rule.id},
                headers=auth_headers,
            )

        assert response.status_code == 200


class TestDeleteRule:
    """Test rule deletion."""

    @pytest.mark.asyncio
    async def test_delete_rule(self, override_db, auth_headers: dict, test_rule: CrossESPLogic):
        """Test deleting a rule."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.delete(
                f"/api/v1/logic/rules/{test_rule.id}",
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == test_rule.name
