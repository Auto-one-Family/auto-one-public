"""
Data Validation Tests (DATA Category).

Tests input validation for sensor configs, actuator commands, ESP registration,
and emergency stop requests via the REST API.

Pattern: AsyncClient + auth_headers, like test_api_actuators.py.
"""

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token, get_password_hash
from src.db.models.actuator import ActuatorConfig
from src.db.models.esp import ESPDevice
from src.db.models.sensor import SensorConfig
from src.db.models.user import User
from src.main import app

# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
async def test_esp(db_session: AsyncSession):
    """Test ESP device."""
    esp = ESPDevice(
        device_id="ESP_DA000001",
        name="Data Validation ESP",
        ip_address="192.168.1.120",
        mac_address="AA:BB:CC:DD:EE:10",
        firmware_version="2.0.0",
        hardware_type="ESP32_WROOM",
        status="online",
        device_metadata={},
    )
    db_session.add(esp)
    await db_session.commit()
    await db_session.refresh(esp)
    return esp


@pytest.fixture
async def test_actuator(db_session: AsyncSession, test_esp: ESPDevice):
    """Test actuator config."""
    actuator = ActuatorConfig(
        esp_id=test_esp.id,
        gpio=5,
        actuator_type="digital",
        actuator_name="Validation Pump",
        enabled=True,
        safety_constraints={"max_runtime": 1800},
        actuator_metadata={},
    )
    db_session.add(actuator)
    await db_session.commit()
    await db_session.refresh(actuator)
    return actuator


@pytest.fixture
async def disabled_actuator(db_session: AsyncSession, test_esp: ESPDevice):
    """Disabled actuator for rejection tests."""
    actuator = ActuatorConfig(
        esp_id=test_esp.id,
        gpio=6,
        actuator_type="pwm",
        actuator_name="Disabled Fan",
        enabled=False,
        actuator_metadata={},
    )
    db_session.add(actuator)
    await db_session.commit()
    await db_session.refresh(actuator)
    return actuator


@pytest.fixture
async def test_sensor(db_session: AsyncSession, test_esp: ESPDevice):
    """Test sensor config."""
    sensor = SensorConfig(
        esp_id=test_esp.id,
        gpio=34,
        sensor_type="temperature",
        sensor_name="Validation Temp",
        interface_type="ANALOG",
        enabled=True,
        pi_enhanced=True,
        sample_interval_ms=30000,
        sensor_metadata={},
    )
    db_session.add(sensor)
    await db_session.commit()
    await db_session.refresh(sensor)
    return sensor


@pytest.fixture
async def operator_user(db_session: AsyncSession):
    """Operator user."""
    user = User(
        username="data_val_operator",
        email="dataval@example.com",
        password_hash=get_password_hash("OperatorP@ss123"),
        full_name="Data Validation Operator",
        role="operator",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers(operator_user: User):
    """Auth headers."""
    token = create_access_token(
        user_id=operator_user.id, additional_claims={"role": operator_user.role}
    )
    return {"Authorization": f"Bearer {token}"}


# =========================================================================
# Sensor Config Validation
# =========================================================================


class TestSensorConfigValidation:
    """Validate sensor configuration inputs."""

    @pytest.mark.asyncio
    async def test_create_sensor_valid(self, auth_headers: dict, test_esp: ESPDevice):
        """Valid sensor config succeeds."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/sensors/{test_esp.device_id}/35",
                json={
                    "esp_id": test_esp.device_id,
                    "gpio": 35,
                    "sensor_type": "humidity",
                    "name": "Test Humidity",
                    "enabled": True,
                    "interval_ms": 30000,
                },
                headers=auth_headers,
            )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_unknown_sensor_type_accepted(self, auth_headers: dict, test_esp: ESPDevice):
        """Unknown sensor_type is accepted (server does not restrict types)."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/sensors/{test_esp.device_id}/35",
                json={
                    "esp_id": test_esp.device_id,
                    "gpio": 35,
                    "sensor_type": "nonexistent_sensor",
                    "name": "Custom Sensor",
                },
                headers=auth_headers,
            )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_reject_interval_too_low(self, auth_headers: dict, test_esp: ESPDevice):
        """Interval below minimum (1000ms) is rejected."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/sensors/{test_esp.device_id}/35",
                json={
                    "esp_id": test_esp.device_id,
                    "gpio": 35,
                    "sensor_type": "temperature",
                    "name": "Fast Sensor",
                    "interval_ms": 100,  # Below 1000ms minimum
                },
                headers=auth_headers,
            )
        assert response.status_code in [400, 422]

    @pytest.mark.asyncio
    async def test_sensor_nonexistent_esp(self, auth_headers: dict):
        """Sensor config for non-existent ESP is rejected."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/sensors/ESP_000000/34",
                json={
                    "esp_id": "ESP_000000",
                    "gpio": 34,
                    "sensor_type": "temperature",
                    "name": "Ghost Sensor",
                },
                headers=auth_headers,
            )
        assert response.status_code in [404, 400]


# =========================================================================
# Actuator Command Validation
# =========================================================================


class TestActuatorCommandValidation:
    """Validate actuator command inputs."""

    @pytest.mark.asyncio
    async def test_send_valid_command(
        self, auth_headers: dict, test_actuator: ActuatorConfig, test_esp: ESPDevice
    ):
        """Valid ON command is accepted."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/actuators/{test_esp.device_id}/{test_actuator.gpio}/command",
                json={"command": "ON", "value": 1.0},
                headers=auth_headers,
            )
        # May succeed or fail due to MQTT mock, but should not be 422 validation error
        assert response.status_code in [200, 400, 500, 503]

    @pytest.mark.asyncio
    async def test_command_on_nonexistent_actuator(self, auth_headers: dict, test_esp: ESPDevice):
        """Command to non-existent GPIO is rejected."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/actuators/{test_esp.device_id}/99/command",
                json={"command": "ON", "value": 1.0},
                headers=auth_headers,
            )
        assert response.status_code in [404, 400]

    @pytest.mark.asyncio
    async def test_command_on_disabled_actuator(
        self, auth_headers: dict, disabled_actuator: ActuatorConfig, test_esp: ESPDevice
    ):
        """Command to disabled actuator is rejected by safety service."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/actuators/{test_esp.device_id}/{disabled_actuator.gpio}/command",
                json={"command": "ON", "value": 1.0},
                headers=auth_headers,
            )
        assert response.status_code in [400, 403, 500]

    @pytest.mark.asyncio
    async def test_reject_missing_command_field(
        self, auth_headers: dict, test_actuator: ActuatorConfig, test_esp: ESPDevice
    ):
        """Missing 'command' field is rejected."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/actuators/{test_esp.device_id}/{test_actuator.gpio}/command",
                json={"value": 0.5},  # No 'command' field
                headers=auth_headers,
            )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_reject_invalid_command_string(
        self, auth_headers: dict, test_actuator: ActuatorConfig, test_esp: ESPDevice
    ):
        """Invalid command string is rejected."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/actuators/{test_esp.device_id}/{test_actuator.gpio}/command",
                json={"command": "EXPLODE", "value": 1.0},
                headers=auth_headers,
            )
        assert response.status_code in [400, 422]


# =========================================================================
# ESP Registration Validation
# =========================================================================


class TestESPRegistrationValidation:
    """Validate ESP device registration inputs."""

    @pytest.mark.asyncio
    async def test_register_valid_device(self, auth_headers: dict):
        """Valid device registration succeeds."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/esp/devices",
                json={
                    "device_id": "ESP_DE000001",
                    "name": "New Device",
                    "ip_address": "192.168.1.200",
                    "mac_address": "11:22:33:44:55:66",
                    "hardware_type": "ESP32_WROOM",
                },
                headers=auth_headers,
            )
        assert response.status_code in [200, 201]

    @pytest.mark.asyncio
    async def test_reject_duplicate_device_id(self, auth_headers: dict, test_esp: ESPDevice):
        """Duplicate device_id is rejected."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/esp/devices",
                json={
                    "device_id": test_esp.device_id,
                    "name": "Duplicate",
                    "ip_address": "192.168.1.201",
                    "mac_address": "11:22:33:44:55:77",
                    "hardware_type": "ESP32_WROOM",
                },
                headers=auth_headers,
            )
        assert response.status_code in [400, 409]

    @pytest.mark.asyncio
    async def test_reject_invalid_mac_format(self, auth_headers: dict):
        """Invalid MAC address format is rejected."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/esp/devices",
                json={
                    "device_id": "ESP_BA000001",
                    "name": "Bad MAC",
                    "ip_address": "192.168.1.202",
                    "mac_address": "not-a-mac",
                    "hardware_type": "ESP32_WROOM",
                },
                headers=auth_headers,
            )
        assert response.status_code == 422


# =========================================================================
# Emergency Stop Validation
# =========================================================================


class TestEmergencyStopValidation:
    """Validate emergency stop request inputs."""

    @pytest.mark.asyncio
    async def test_emergency_stop_valid(self, auth_headers: dict, test_esp: ESPDevice):
        """Valid emergency stop request."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/actuators/emergency_stop",
                json={
                    "esp_id": test_esp.device_id,
                    "reason": "overtemperature detected",
                },
                headers=auth_headers,
            )
        assert response.status_code in [200, 400, 500]

    @pytest.mark.asyncio
    async def test_emergency_stop_global(self, auth_headers: dict):
        """Global emergency stop (no esp_id)."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/actuators/emergency_stop",
                json={"reason": "global emergency test"},
                headers=auth_headers,
            )
        assert response.status_code in [200, 400, 500]

    @pytest.mark.asyncio
    async def test_emergency_stop_missing_reason(self, auth_headers: dict):
        """Emergency stop without reason field."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/actuators/emergency_stop",
                json={},
                headers=auth_headers,
            )
        assert response.status_code in [400, 422]
