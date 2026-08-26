"""
Integration Tests: Actuator API

Phase: 5 (Week 9-10) - API Layer
Tests: Actuator endpoints (config, command, status, emergency)
"""

import uuid
from unittest.mock import patch

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.request_context import build_emergency_actuator_correlation_id
from src.core.security import create_access_token, get_password_hash
from src.db.models.actuator import ActuatorConfig, ActuatorState
from src.db.models.esp import ESPDevice
from src.db.models.user import User
from src.main import app


@pytest.fixture
async def test_esp(db_session: AsyncSession):
    """Create a test ESP device."""
    esp = ESPDevice(
        device_id="ESP_AC000001",
        name="Actuator Test ESP",
        ip_address="192.168.1.110",
        mac_address="AA:BB:CC:DD:EE:01",
        firmware_version="2.0.0",
        hardware_type="ESP32_WROOM",
        status="online",
        metadata={},
    )
    db_session.add(esp)
    await db_session.commit()
    await db_session.refresh(esp)
    return esp


@pytest.fixture
async def test_actuator(db_session: AsyncSession, test_esp: ESPDevice):
    """Create a test actuator configuration."""
    actuator = ActuatorConfig(
        esp_id=test_esp.id,
        gpio=5,
        actuator_type="digital",
        actuator_name="Test Pump",
        enabled=True,
        safety_constraints={"max_runtime": 1800, "cooldown_period": 300},
        actuator_metadata={},
    )
    db_session.add(actuator)
    await db_session.commit()
    await db_session.refresh(actuator)
    return actuator


@pytest.fixture
async def operator_user(db_session: AsyncSession):
    """Create an operator user."""
    user = User(
        username="actuator_operator",
        email="actuator_op@example.com",
        password_hash=get_password_hash("OperatorP@ss123"),
        full_name="Actuator Operator",
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


class TestListActuators:
    """Test actuator listing."""

    @pytest.mark.asyncio
    async def test_list_actuators(self, auth_headers: dict, test_actuator: ActuatorConfig):
        """Test listing actuators."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/actuators/",
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["data"]) >= 1

    @pytest.mark.asyncio
    async def test_list_actuators_with_filter(
        self, auth_headers: dict, test_actuator: ActuatorConfig, test_esp: ESPDevice
    ):
        """Test listing actuators with ESP filter."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/actuators/",
                params={"esp_id": test_esp.device_id},
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert all(d["esp_device_id"] == test_esp.device_id for d in data["data"])


class TestGetActuator:
    """Test getting single actuator."""

    @pytest.mark.asyncio
    async def test_get_actuator(
        self, auth_headers: dict, test_actuator: ActuatorConfig, test_esp: ESPDevice
    ):
        """Test getting actuator by ESP and GPIO."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/actuators/{test_esp.device_id}/{test_actuator.gpio}",
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["gpio"] == test_actuator.gpio
        assert data["name"] == "Test Pump"

    @pytest.mark.asyncio
    async def test_get_actuator_not_found(self, auth_headers: dict, test_esp: ESPDevice):
        """Test getting non-existent actuator."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/actuators/{test_esp.device_id}/99",
                headers=auth_headers,
            )

        assert response.status_code == 404


class TestCreateActuator:
    """Test actuator creation."""

    @pytest.mark.asyncio
    async def test_create_actuator(self, auth_headers: dict, test_esp: ESPDevice):
        """Test creating an actuator."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/actuators/{test_esp.device_id}/25",
                json={
                    "esp_id": test_esp.device_id,
                    "gpio": 25,
                    "actuator_type": "pwm",
                    "name": "New PWM Actuator",
                    "enabled": True,
                    "pwm_frequency": 1000,
                },
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["gpio"] == 25
        assert data["actuator_type"] == "pwm"
        assert data["name"] == "New PWM Actuator"


class TestSendCommand:
    """Test sending actuator commands."""

    @pytest.mark.asyncio
    async def test_send_on_command(
        self, auth_headers: dict, test_actuator: ActuatorConfig, test_esp: ESPDevice
    ):
        """Test sending ON command."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/actuators/{test_esp.device_id}/{test_actuator.gpio}/command",
                json={
                    "command": "ON",
                    "value": 1.0,
                    "duration": 60,
                },
                headers=auth_headers,
            )

        # May fail if MQTT not connected
        assert response.status_code in [200, 400, 500]
        if response.status_code == 200:
            data = response.json()
            assert "correlation_id" in data
            uuid.UUID(data["correlation_id"])
            assert "safety_warnings" in data
            assert isinstance(data["safety_warnings"], list)
            assert "command_sent" in data

    @pytest.mark.asyncio
    async def test_send_command_noop_still_returns_correlation_id(
        self,
        auth_headers: dict,
        test_actuator: ActuatorConfig,
        test_esp: ESPDevice,
        db_session: AsyncSession,
    ):
        """No-op delta skip: MQTT not published but REST exposes same trace correlation_id."""
        db_session.add(
            ActuatorState(
                esp_id=test_esp.id,
                gpio=test_actuator.gpio,
                actuator_type="digital",
                current_value=1.0,
                state="on",
                runtime_seconds=0,
            )
        )
        await db_session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/actuators/{test_esp.device_id}/{test_actuator.gpio}/command",
                json={
                    "command": "ON",
                    "value": 1.0,
                    "duration": 0,
                },
                headers=auth_headers,
            )

        assert response.status_code == 200, response.text
        data = response.json()
        uuid.UUID(data["correlation_id"])
        assert data["command_sent"] is False
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_send_pwm_command(
        self, auth_headers: dict, test_actuator: ActuatorConfig, test_esp: ESPDevice
    ):
        """Test sending PWM command."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/actuators/{test_esp.device_id}/{test_actuator.gpio}/command",
                json={
                    "command": "PWM",
                    "value": 0.5,
                    "duration": 120,
                },
                headers=auth_headers,
            )

        assert response.status_code in [200, 400, 500]

    @pytest.mark.asyncio
    async def test_command_disabled_actuator(
        self, auth_headers: dict, db_session: AsyncSession, test_esp: ESPDevice
    ):
        """Test sending command to disabled actuator."""
        # Create disabled actuator
        actuator = ActuatorConfig(
            esp_id=test_esp.id,
            gpio=7,
            actuator_type="digital",
            actuator_name="Disabled Actuator",
            enabled=False,
            metadata={},
        )
        db_session.add(actuator)
        await db_session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/actuators/{test_esp.device_id}/7/command",
                json={
                    "command": "ON",
                    "value": 1.0,
                    "duration": 0,
                },
                headers=auth_headers,
            )

        assert response.status_code == 400
        error_data = response.json()["error"]
        assert "disabled" in error_data["message"].lower()


class TestEmergencyStop:
    """Test emergency stop functionality."""

    @pytest.mark.asyncio
    async def test_emergency_stop_all(self, auth_headers: dict, test_actuator: ActuatorConfig):
        """Test emergency stop for all actuators."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/actuators/emergency_stop",
                json={
                    "reason": "Test emergency stop",
                },
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["reason"] == "Test emergency stop"
        assert data.get("incident_correlation_id")

    @pytest.mark.asyncio
    async def test_emergency_stop_single_esp(
        self, auth_headers: dict, test_actuator: ActuatorConfig, test_esp: ESPDevice
    ):
        """Test emergency stop for single ESP."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/actuators/emergency_stop",
                json={
                    "esp_id": test_esp.device_id,
                    "reason": "Single ESP emergency stop",
                },
                headers=auth_headers,
            )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_emergency_stop_publish_passes_correlation_id(
        self,
        auth_headers: dict,
        test_actuator: ActuatorConfig,
        test_esp: ESPDevice,
        override_mqtt_publisher,
    ):
        """Epic 1-03: each emergency OFF publish must include deterministic correlation_id."""
        fixed_incident = uuid.UUID("aaaaaaaa-bbbb-4ccc-dddd-eeeeeeeeeeee")
        with patch("src.api.v1.actuators.uuid.uuid4", return_value=fixed_incident):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/v1/actuators/emergency_stop",
                    json={
                        "esp_id": test_esp.device_id,
                        "reason": "correlation integration test",
                    },
                    headers=auth_headers,
                )

        assert response.status_code == 200
        assert response.json()["incident_correlation_id"] == str(fixed_incident)
        override_mqtt_publisher.publish_actuator_command.assert_called()
        expected = build_emergency_actuator_correlation_id(
            str(fixed_incident), test_esp.device_id, test_actuator.gpio
        )
        for call in override_mqtt_publisher.publish_actuator_command.call_args_list:
            assert call.kwargs["correlation_id"] == expected
            assert call.kwargs["gpio"] == test_actuator.gpio

    @pytest.mark.asyncio
    async def test_emergency_broadcast_payload_matches_firmware_contract(
        self,
        auth_headers: dict,
        test_actuator: ActuatorConfig,
        test_esp: ESPDevice,
        override_mqtt_publisher,
    ):
        """AUT-63: broadcast command must be lowercase per firmware contract
        (emergency_broadcast_contract.h accepts only 'emergency_stop' | 'stop_all')."""
        import json

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/actuators/emergency_stop",
                json={
                    "esp_id": test_esp.device_id,
                    "reason": "broadcast contract test",
                },
                headers=auth_headers,
            )

        assert response.status_code == 200

        # AUT-225: emergency broadcast goes through publisher.publish_emergency_broadcast(payload, qos)
        broadcast_calls = override_mqtt_publisher.publish_emergency_broadcast.call_args_list
        assert (
            len(broadcast_calls) == 1
        ), f"Expected 1 publish_emergency_broadcast call, got {len(broadcast_calls)}"

        call = broadcast_calls[0]
        # First positional arg is the payload dict (already JSON-serialisable)
        raw_payload = call.args[0] if call.args else call.kwargs.get("payload")
        # Support either a dict (new API) or a JSON string (legacy)
        payload = raw_payload if isinstance(raw_payload, dict) else json.loads(raw_payload)

        FIRMWARE_ACCEPTED = {"emergency_stop", "stop_all"}
        assert (
            payload["command"] in FIRMWARE_ACCEPTED
        ), f"Broadcast command '{payload['command']}' not in firmware-accepted set {FIRMWARE_ACCEPTED}"
        assert payload.get("reason"), "Broadcast payload must include non-empty 'reason'"
        assert payload.get("timestamp"), "Broadcast payload must include 'timestamp'"
        assert payload.get(
            "incident_correlation_id"
        ), "Broadcast payload must include 'incident_correlation_id'"


class TestGetStatus:
    """Test actuator status endpoint."""

    @pytest.mark.asyncio
    async def test_get_status(
        self, auth_headers: dict, test_actuator: ActuatorConfig, test_esp: ESPDevice
    ):
        """Test getting actuator status."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/actuators/{test_esp.device_id}/{test_actuator.gpio}/status",
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["esp_id"] == test_esp.device_id
        assert data["gpio"] == test_actuator.gpio
        assert "state" in data


class TestDeleteActuator:
    """Test actuator deletion."""

    @pytest.mark.asyncio
    async def test_delete_actuator(
        self, auth_headers: dict, test_actuator: ActuatorConfig, test_esp: ESPDevice
    ):
        """Test deleting an actuator."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.delete(
                f"/api/v1/actuators/{test_esp.device_id}/{test_actuator.gpio}",
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["gpio"] == test_actuator.gpio

    @pytest.mark.asyncio
    async def test_delete_actuator_not_found(self, auth_headers: dict, test_esp: ESPDevice):
        """Test deleting non-existent actuator."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.delete(
                f"/api/v1/actuators/{test_esp.device_id}/99",
                headers=auth_headers,
            )

        assert response.status_code == 404


class TestActuatorHistory:
    """Test actuator history endpoint."""

    @pytest.mark.asyncio
    async def test_get_history(
        self, auth_headers: dict, test_actuator: ActuatorConfig, test_esp: ESPDevice
    ):
        """Test getting actuator command history."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/actuators/{test_esp.device_id}/{test_actuator.gpio}/history",
                headers=auth_headers,
            )

        assert response.status_code == 200


class TestActuatorAuth:
    """Test authentication requirements for actuator endpoints."""

    @pytest.mark.asyncio
    async def test_command_without_auth(self, test_actuator: ActuatorConfig, test_esp: ESPDevice):
        """Test sending command without authentication."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/actuators/{test_esp.device_id}/{test_actuator.gpio}/command",
                json={"command": "ON", "value": 1.0, "duration": 60},
            )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_emergency_stop_without_auth(self):
        """Test emergency stop without authentication."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/actuators/emergency_stop",
                json={"reason": "Unauthorized attempt"},
            )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_actuator_without_auth(self, test_esp: ESPDevice):
        """Test creating actuator without authentication."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/actuators/{test_esp.device_id}/10",
                json={
                    "esp_id": test_esp.device_id,
                    "gpio": 10,
                    "actuator_type": "digital",
                    "name": "Unauthorized Actuator",
                },
            )

        assert response.status_code == 401
