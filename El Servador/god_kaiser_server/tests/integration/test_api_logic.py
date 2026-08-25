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
from src.db.models.actuator import ActuatorConfig
from src.db.models.esp import ESPDevice
from src.db.models.logic import CrossESPLogic
from src.db.models.user import User
from src.db.repositories import LogicRepository
from src.main import app
from src.services import logic_engine as logic_engine_module
from src.services.logic_service import LogicService


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

class TestRuleMetadataRoundTrip:
    """AUT-1113: rule_metadata set via API -> read back -> identical."""

    @pytest.mark.asyncio
    async def test_create_rule_with_rule_metadata_round_trip(self, override_db, auth_headers: dict):
        dose_config = {
            "target_value": 1.8,
            "volume_l": 50.0,
            "components": [{"concentration": 1.0, "ratio_share": 0.5}],
        }
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            create_response = await client.post(
                "/api/v1/logic/rules",
                json={
                    "name": "EC Raise Rule",
                    "conditions": [
                        {
                            "type": "sensor",
                            "esp_id": "ESP_11223344",
                            "gpio": 35,
                            "operator": "<",
                            "value": 1.5,
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
                    "rule_metadata": {"dose_config": dose_config},
                },
                headers=auth_headers,
            )
            assert create_response.status_code == 201
            created = create_response.json()
            assert created["rule_metadata"] == {"dose_config": dose_config}

            get_response = await client.get(
                f"/api/v1/logic/rules/{created['id']}",
                headers=auth_headers,
            )

        assert get_response.status_code == 200
        assert get_response.json()["rule_metadata"] == {"dose_config": dose_config}

    @pytest.mark.asyncio
    async def test_update_rule_rule_metadata_round_trip(
        self, override_db, auth_headers: dict, test_rule: CrossESPLogic
    ):
        new_metadata = {"category": "ec_raise", "note": "AUT-1113"}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            update_response = await client.put(
                f"/api/v1/logic/rules/{test_rule.id}",
                json={"rule_metadata": new_metadata},
                headers=auth_headers,
            )
            assert update_response.status_code == 200
            assert update_response.json()["rule_metadata"] == new_metadata

            get_response = await client.get(
                f"/api/v1/logic/rules/{test_rule.id}",
                headers=auth_headers,
            )

        assert get_response.status_code == 200
        assert get_response.json()["rule_metadata"] == new_metadata

    @pytest.mark.asyncio
    async def test_create_rule_without_rule_metadata_defaults_to_empty_dict(
        self, override_db, auth_headers: dict
    ):
        """Existing callers that don't send rule_metadata must keep working (default {})."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/logic/rules",
                json={
                    "name": "Plain Rule Without Metadata",
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
                },
                headers=auth_headers,
            )

        assert response.status_code == 201
        assert response.json()["rule_metadata"] == {}


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


# esp_ids must match ^(ESP_[A-F0-9]{6,8}|MOCK_[A-Z0-9]+)$ → hex chars only.
_PUMP_ESP = "ESP_AABBCC01"
_SENSOR_ESP = "ESP_DDEE0034"
_PUMP_GPIO = 5
_RELAY_GPIO = 6


@pytest_asyncio.fixture
async def registered_pump(integration_session: AsyncSession):
    """Register an ESP with a dosing pump (gpio 5) and a non-pump relay (gpio 6)."""
    esp = ESPDevice(
        device_id=_PUMP_ESP,
        name="Dosing ESP",
        ip_address="192.168.1.50",
        mac_address="AA:BB:CC:DD:EE:50",
        firmware_version="1.0.0",
        hardware_type="ESP32_WROOM",
        status="online",
        metadata={},
    )
    integration_session.add(esp)
    await integration_session.commit()
    await integration_session.refresh(esp)

    pump = ActuatorConfig(
        esp_id=esp.id,
        gpio=_PUMP_GPIO,
        actuator_type="digital",
        actuator_name="Dosing Pump",
        hardware_type="pump",
        enabled=True,
        safety_constraints={},
        actuator_metadata={},
    )
    relay = ActuatorConfig(
        esp_id=esp.id,
        gpio=_RELAY_GPIO,
        actuator_type="digital",
        actuator_name="Light Relay",
        hardware_type="relay",
        enabled=True,
        safety_constraints={},
        actuator_metadata={},
    )
    integration_session.add_all([pump, relay])
    await integration_session.commit()
    return esp, pump, relay


def _pump_rule_payload(require_fresh_data: bool | None, gpio: int = _PUMP_GPIO) -> dict:
    """Build a rule payload that switches an actuator when pH is too high.

    require_fresh_data=None omits the flag entirely (schema default False).
    gpio selects the target actuator (pump vs. relay).
    """
    condition: dict = {
        "type": "sensor",
        "esp_id": _SENSOR_ESP,
        "gpio": 34,
        "sensor_type": "ph",
        "operator": ">",
        "value": 6.5,
    }
    if require_fresh_data is not None:
        condition["require_fresh_data"] = require_fresh_data
    return {
        "name": "pH-down dosing",
        "description": "Dose pH-down when pH exceeds 6.5",
        "conditions": [condition],
        "actions": [
            {
                "type": "actuator",
                "esp_id": _PUMP_ESP,
                "gpio": gpio,
                "command": "ON",
                "value": 1.0,
            }
        ],
        "logic_operator": "AND",
        "enabled": True,
        "priority": 70,
        "cooldown_seconds": 300,
    }


class TestPumpFreshnessEnforcement:
    """AUT-994 B1: a rule that doses a pump must set require_fresh_data on every sensor condition."""

    @pytest.mark.asyncio
    async def test_create_pump_rule_without_fresh_data_rejected(
        self, override_db, auth_headers: dict, registered_pump
    ):
        """Pump action + sensor condition missing require_fresh_data → 400 (RULE_VALIDATION_FAILED)."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/logic/rules",
                json=_pump_rule_payload(require_fresh_data=None),
                headers=auth_headers,
            )

        assert response.status_code == 400
        assert "require_fresh_data" in response.text

    @pytest.mark.asyncio
    async def test_create_pump_rule_fresh_data_false_rejected(
        self, override_db, auth_headers: dict, registered_pump
    ):
        """Explicit require_fresh_data=False is still rejected for a pump target → 400."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/logic/rules",
                json=_pump_rule_payload(require_fresh_data=False),
                headers=auth_headers,
            )

        assert response.status_code == 400
        assert "require_fresh_data" in response.text

    @pytest.mark.asyncio
    async def test_create_pump_rule_with_fresh_data_accepted(
        self, override_db, auth_headers: dict, registered_pump
    ):
        """Pump action + require_fresh_data=True on every sensor condition → 201."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/logic/rules",
                json=_pump_rule_payload(require_fresh_data=True),
                headers=auth_headers,
            )

        assert response.status_code == 201, response.text
        assert response.json()["name"] == "pH-down dosing"

    @pytest.mark.asyncio
    async def test_create_non_pump_rule_without_fresh_data_accepted(
        self, override_db, auth_headers: dict, registered_pump
    ):
        """Guard is pump-specific: a relay target without require_fresh_data → 201."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/logic/rules",
                json=_pump_rule_payload(require_fresh_data=None, gpio=_RELAY_GPIO),
                headers=auth_headers,
            )

        assert response.status_code == 201, response.text

    @pytest.mark.asyncio
    async def test_update_pump_rule_removing_fresh_data_rejected(
        self, override_db, auth_headers: dict, registered_pump
    ):
        """update_rule mirrors the guard: dropping require_fresh_data on a pump rule → 400."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            create = await client.post(
                "/api/v1/logic/rules",
                json=_pump_rule_payload(require_fresh_data=True),
                headers=auth_headers,
            )
            assert create.status_code == 201, create.text
            rule_id = create.json()["id"]

            update = await client.put(
                f"/api/v1/logic/rules/{rule_id}",
                json={
                    "conditions": [
                        {
                            "type": "sensor",
                            "esp_id": _SENSOR_ESP,
                            "gpio": 34,
                            "sensor_type": "ph",
                            "operator": ">",
                            "value": 6.5,
                            "require_fresh_data": False,
                        }
                    ]
                },
                headers=auth_headers,
            )

        assert update.status_code == 400
        assert "require_fresh_data" in update.text


class TestRuleGroupDerivation:
    """AUT-1145 (S0): Given/When/Then Ableitung + Nutzer-Override."""

    @pytest.mark.asyncio
    async def test_rule_group_derived_when_null(
        self, override_db, auth_headers: dict, integration_session: AsyncSession
    ):
        """Given a hysteresis+actuator rule with rule_group=NULL, the read route
        returns the derived value 'temperatur' (AUT-1173, Variante C: Messgröße
        als Primärachse) without writing anything to the DB."""
        rule = CrossESPLogic(
            rule_name="Fan Hysteresis Rule",
            trigger_conditions={
                "type": "hysteresis",
                "esp_id": "ESP_11223344",
                "gpio": 4,
                "sensor_type": "temperature",
                "activate_above": 28.0,
                "deactivate_below": 24.0,
            },
            actions=[
                {
                    "type": "actuator",
                    "esp_id": "ESP_55667788",
                    "gpio": 18,
                    "command": "ON",
                    "value": 1.0,
                }
            ],
            enabled=True,
            priority=50,
            cooldown_seconds=60,
        )
        integration_session.add(rule)
        await integration_session.commit()
        await integration_session.refresh(rule)
        assert rule.rule_group is None

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(f"/api/v1/logic/rules/{rule.id}", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["rule_group"] == "temperatur"

        await integration_session.refresh(rule)
        assert rule.rule_group is None, "derivation must be read-time only, never persisted"

    @pytest.mark.asyncio
    async def test_rule_group_explicit_override_wins(
        self, override_db, auth_headers: dict, test_rule: CrossESPLogic
    ):
        """Given the same rule, now with an explicit rule_group override, the read
        route returns the override — the derivation function is not applied."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            update = await client.put(
                f"/api/v1/logic/rules/{test_rule.id}",
                json={"rule_group": "sonstiges"},
                headers=auth_headers,
            )
            assert update.status_code == 200, update.text
            assert update.json()["rule_group"] == "sonstiges"

            get_response = await client.get(
                f"/api/v1/logic/rules/{test_rule.id}", headers=auth_headers
            )

        assert get_response.status_code == 200
        assert get_response.json()["rule_group"] == "sonstiges"

    @pytest.mark.asyncio
    async def test_rule_group_invalid_value_rejected(
        self, override_db, auth_headers: dict, test_rule: CrossESPLogic
    ):
        """Fixed catalog only — an unknown group name must be rejected (422),
        never silently stored."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.put(
                f"/api/v1/logic/rules/{test_rule.id}",
                json={"rule_group": "nicht_im_katalog"},
                headers=auth_headers,
            )
        assert response.status_code == 422


class TestBulkQuickUpdate:
    """AUT-1145 (S0): Bulk quick-field update for the Gruppenkarten-Schnellfeld.

    Fix-Philosophie: the bulk endpoint is a thin loop around the existing
    LogicService.update_rule() — these tests assert on observable outcomes
    (DB state, HTTP response), never on a second/parallel write path.
    """

    @pytest_asyncio.fixture
    async def three_rules(self, integration_session: AsyncSession):
        """Three enabled rules for the bulk An/Aus Given/When/Then."""
        rules = []
        for i in range(3):
            rule = CrossESPLogic(
                rule_name=f"Bulk Quick-Update Rule {i}",
                trigger_conditions={
                    "type": "sensor",
                    "esp_id": "ESP_11223344",
                    "gpio": 34,
                    "operator": ">",
                    "value": 7.0,
                },
                actions=[
                    {
                        "type": "actuator",
                        "esp_id": "ESP_55667788",
                        "gpio": 5,
                        "command": "OFF",
                        "value": 0.0,
                    }
                ],
                enabled=True,
                priority=70,
                cooldown_seconds=120,
            )
            integration_session.add(rule)
            rules.append(rule)
        await integration_session.commit()
        for rule in rules:
            await integration_session.refresh(rule)
        return rules

    @pytest.mark.asyncio
    async def test_bulk_active_off_leaves_priority_and_cooldown_untouched(
        self, override_db, auth_headers: dict, three_rules, integration_session: AsyncSession
    ):
        """Given/When/Then (Bulk-Update An/Aus): three marked rules with
        active=true; bulk {ids: [...], active: false} -> all three active=false
        in the DB, priority and cooldown_seconds UNVERAENDERT."""
        ids = [str(r.id) for r in three_rules]
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/logic/rules/bulk-quick-update",
                json={"ids": ids, "active": False},
                headers=auth_headers,
            )

        assert response.status_code == 200, response.text
        data = response.json()
        assert all(r["success"] for r in data["results"])

        for rule in three_rules:
            await integration_session.refresh(rule)
            assert rule.enabled is False
            assert rule.priority == 70
            assert rule.cooldown_seconds == 120

    @pytest.mark.asyncio
    async def test_bulk_threshold_update_round_trip(
        self, override_db, auth_headers: dict, three_rules, integration_session: AsyncSession
    ):
        """Bulk Schwellwert/Zielwert: new threshold_value lands in every rule's
        sensor_threshold condition, other condition keys untouched."""
        ids = [str(r.id) for r in three_rules]
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/logic/rules/bulk-quick-update",
                json={"ids": ids, "threshold_value": 9.5},
                headers=auth_headers,
            )

        assert response.status_code == 200, response.text
        assert all(r["success"] for r in response.json()["results"])

        for rule in three_rules:
            await integration_session.refresh(rule)
            assert rule.conditions[0]["value"] == 9.5
            assert rule.conditions[0]["esp_id"] == "ESP_11223344"

    @pytest.mark.asyncio
    async def test_bulk_rule_not_found_reports_per_rule_error(
        self, override_db, auth_headers: dict, three_rules
    ):
        """One valid + one non-existent id -> partial success, not a global failure."""
        missing_id = "00000000-0000-0000-0000-000000000000"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/logic/rules/bulk-quick-update",
                json={"ids": [str(three_rules[0].id), missing_id], "active": False},
                headers=auth_headers,
            )

        assert response.status_code == 200
        results = {r["rule_id"]: r for r in response.json()["results"]}
        assert results[str(three_rules[0].id)]["success"] is True
        assert results[missing_id]["success"] is False


class TestBulkQuickUpdateCooldownRegression:
    """AUT-1145 Falle 2 (AUT-1135 regression): a bulk Schwellwert change must
    NOT force-bypass a currently running cooldown/settle window.

    A bulk threshold edit DOES change `conditions`, which would otherwise make
    LogicService._rule_behavior_changed() return True and force-bypass the
    cooldown (exactly the AUT-1135 incident). bulk_quick_update_rules() must
    pass force_reeval=False explicitly to update_rule() to prevent this.

    Verifies the wiring by registering a spy in place of the running
    LogicEngine and capturing the `force` value update_rule() sends it — the
    engine's own cooldown-gate arithmetic is already covered by
    test_logic_engine.py::test_cooldown_not_bypassed_without_force (AUT-1135);
    this test only needs to prove the bulk path reaches it with force=False.
    """

    @pytest.mark.asyncio
    async def test_bulk_threshold_change_passes_force_false_to_engine(
        self, integration_session: AsyncSession, test_rule: CrossESPLogic
    ):
        captured: dict = {}

        class _SpyEngine:
            async def on_rule_updated(self, rule_id, old_trigger_conditions=None, force=False):
                captured["force"] = force
                captured["rule_id"] = rule_id

        original_engine = logic_engine_module.get_logic_engine()
        logic_engine_module.set_logic_engine(_SpyEngine())
        try:
            repo = LogicRepository(integration_session)
            service = LogicService(repo)
            results = await service.bulk_quick_update_rules([test_rule.id], threshold_value=8.2)
        finally:
            logic_engine_module.set_logic_engine(original_engine)

        assert results[0].success is True
        assert captured.get("force") is False, (
            "Bulk threshold change must pass force=False to the engine — "
            "otherwise _rule_behavior_changed()==True would bypass a running "
            "cooldown/settle window (AUT-1145 Falle 2 / AUT-1135)."
        )

        await integration_session.refresh(test_rule)
        assert test_rule.conditions[0]["value"] == 8.2
        assert test_rule.cooldown_seconds == 300  # untouched
        assert test_rule.priority == 80  # untouched
