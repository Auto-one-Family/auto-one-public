"""
Integration Tests: Sensor API

Phase: 5 (Week 9-10) - API Layer
Tests: Sensor endpoints (config CRUD, data query)
"""

import csv

import pytest
from datetime import datetime, timedelta, timezone
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token, get_password_hash
from src.db.models.sensor import SensorConfig, SensorData
from src.db.models.esp import ESPDevice
from src.db.models.subzone import SubzoneConfig
from src.db.models.user import User
from src.db.models.zone import Zone
from src.db.repositories.subzone_repo import SubzoneRepository
from src.main import app


@pytest.fixture
async def test_esp(db_session: AsyncSession):
    """Create a test ESP device."""
    esp = ESPDevice(
        device_id="ESP_12345678",  # Must match pattern ^ESP_[A-F0-9]{8}$
        name="Sensor Test ESP",
        ip_address="192.168.1.120",
        mac_address="AA:BB:CC:DD:EE:02",
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
async def test_sensor(db_session: AsyncSession, test_esp: ESPDevice):
    """Create a test sensor configuration."""
    sensor = SensorConfig(
        esp_id=test_esp.id,
        gpio=34,
        sensor_type="ph",
        sensor_name="Test pH Sensor",
        interface_type="ANALOG",
        enabled=True,
        sample_interval_ms=30000,
        pi_enhanced=True,
        calibration_data={"slope": -3.5, "offset": 21.34},
        thresholds={"min": 0.0, "max": 14.0, "warning_min": 5.5, "warning_max": 7.5},
        sensor_metadata={},  # Model field is sensor_metadata, not metadata
    )
    db_session.add(sensor)
    await db_session.commit()
    await db_session.refresh(sensor)
    return sensor


@pytest.fixture
async def operator_user(db_session: AsyncSession):
    """Create an operator user."""
    user = User(
        username="sensor_operator",
        email="sensor_op@example.com",
        password_hash=get_password_hash("OperatorP@ss123"),
        full_name="Sensor Operator",
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


class TestListSensors:
    """Test sensor listing."""

    @pytest.mark.asyncio
    async def test_list_sensors(self, auth_headers: dict, test_sensor: SensorConfig):
        """Test listing sensors."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/sensors/",
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["data"]) >= 1

    @pytest.mark.asyncio
    async def test_list_sensors_with_type_filter(
        self, auth_headers: dict, test_sensor: SensorConfig
    ):
        """Test listing sensors filtered by type."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/sensors/",
                params={"sensor_type": "ph"},
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert all(d["sensor_type"] == "ph" for d in data["data"])


class TestGetSensor:
    """Test getting single sensor."""

    @pytest.mark.asyncio
    async def test_get_sensor(
        self, auth_headers: dict, test_sensor: SensorConfig, test_esp: ESPDevice
    ):
        """Test getting sensor by ESP and GPIO."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/sensors/{test_esp.device_id}/{test_sensor.gpio}",
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["gpio"] == test_sensor.gpio
        assert data["sensor_type"] == "ph"
        assert data["name"] == "Test pH Sensor"

    @pytest.mark.asyncio
    async def test_get_sensor_not_found(self, auth_headers: dict, test_esp: ESPDevice):
        """Test getting non-existent sensor."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/sensors/{test_esp.device_id}/99",
                headers=auth_headers,
            )

        assert response.status_code == 404


class TestCreateSensor:
    """Test sensor creation."""

    @pytest.mark.asyncio
    async def test_create_sensor(self, auth_headers: dict, test_esp: ESPDevice):
        """Test creating a sensor."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/sensors/{test_esp.device_id}/35",
                json={
                    "esp_id": test_esp.device_id,
                    "gpio": 35,
                    "sensor_type": "temperature",
                    "name": "New Temperature Sensor",
                    "enabled": True,
                    "interval_ms": 60000,
                    "processing_mode": "pi_enhanced",
                },
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["gpio"] == 35
        assert data["sensor_type"] == "temperature"


class TestDeleteSensor:
    """Test sensor deletion."""

    @pytest.mark.asyncio
    async def test_delete_sensor(
        self, auth_headers: dict, test_sensor: SensorConfig, test_esp: ESPDevice
    ):
        """Test deleting a sensor by config_id (UUID)."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.delete(
                f"/api/v1/sensors/{test_esp.device_id}/{test_sensor.id}",
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["gpio"] == test_sensor.gpio

    @pytest.mark.asyncio
    async def test_delete_sensor_removes_gpio_from_subzones(
        self,
        auth_headers: dict,
        test_sensor: SensorConfig,
        test_esp: ESPDevice,
        db_session: AsyncSession,
    ):
        """Test that deleting a sensor removes its GPIO from all subzones (Phase 3, S23)."""
        esp_id = test_esp.device_id
        gpio = test_sensor.gpio

        # Ensure ESP has zone for subzone
        test_esp.zone_id = "zone_1"
        test_esp.zone_name = "Zone 1"
        await db_session.flush()

        # Create subzone with sensor's GPIO
        subzone = SubzoneConfig(
            esp_id=esp_id,
            subzone_id="test_subzone",
            parent_zone_id="zone_1",
            assigned_gpios=[gpio, 35],  # Sensor GPIO + another
            subzone_name="Test Subzone",
        )
        db_session.add(subzone)
        await db_session.commit()
        await db_session.refresh(subzone)

        # Verify GPIO is in subzone
        subzone_repo = SubzoneRepository(db_session)
        before = await subzone_repo.get_by_esp(esp_id)
        assert len(before) == 1
        assert gpio in before[0].assigned_gpios
        assert 35 in before[0].assigned_gpios

        # Delete sensor via API (by config_id UUID)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.delete(
                f"/api/v1/sensors/{esp_id}/{test_sensor.id}",
                headers=auth_headers,
            )

        assert response.status_code == 200

        # Verify GPIO removed from subzone, other GPIOs unchanged
        db_session.expire_all()  # Refresh from DB
        after = await subzone_repo.get_by_esp(esp_id)
        assert len(after) == 1
        assert gpio not in after[0].assigned_gpios
        assert 35 in after[0].assigned_gpios


class TestQueryData:
    """Test sensor data query."""

    @pytest.mark.asyncio
    async def test_query_sensor_data(
        self, auth_headers: dict, test_sensor: SensorConfig, test_esp: ESPDevice
    ):
        """Test querying sensor data."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/sensors/data",
                params={
                    "esp_id": test_esp.device_id,
                    "gpio": test_sensor.gpio,
                },
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "readings" in data
        assert "count" in data

    @pytest.mark.asyncio
    async def test_query_sensor_data_omits_warming_up_zero(
        self,
        auth_headers: dict,
        db_session: AsyncSession,
        test_sensor: SensorConfig,
        test_esp: ESPDevice,
    ):
        """AUT-723 E3: persisted warming_up (raw=0) must not appear as pH 0.00."""
        now = datetime.now(timezone.utc)
        db_session.add(
            SensorData(
                esp_id=test_esp.id,
                gpio=test_sensor.gpio,
                sensor_type="ph",
                raw_value=0.0,
                processed_value=None,
                unit="pH",
                processing_mode="raw",
                quality="warming_up",
                timestamp=now,
            )
        )
        db_session.add(
            SensorData(
                esp_id=test_esp.id,
                gpio=test_sensor.gpio,
                sensor_type="ph",
                raw_value=2150.0,
                processed_value=6.8,
                unit="pH",
                processing_mode="pi_enhanced",
                quality="good",
                timestamp=now.replace(microsecond=0) - timedelta(minutes=1),
            )
        )
        await db_session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/sensors/data",
                params={
                    "esp_id": test_esp.device_id,
                    "gpio": test_sensor.gpio,
                    "sensor_type": "ph",
                    "resolution": "raw",
                },
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        qualities = [r.get("quality") for r in data["readings"]]
        assert "warming_up" not in qualities
        assert all(r.get("raw_value") != 0.0 or r.get("processed_value") is not None for r in data["readings"])
        assert any(r.get("processed_value") == 6.8 for r in data["readings"])

    @pytest.mark.asyncio
    async def test_query_sensor_data_explicit_warming_up_filter(
        self,
        auth_headers: dict,
        db_session: AsyncSession,
        test_sensor: SensorConfig,
        test_esp: ESPDevice,
    ):
        """Explicit ?quality=warming_up still returns those rows (diagnostics)."""
        db_session.add(
            SensorData(
                esp_id=test_esp.id,
                gpio=test_sensor.gpio,
                sensor_type="ph",
                raw_value=0.0,
                processed_value=None,
                unit="pH",
                processing_mode="raw",
                quality="warming_up",
                timestamp=datetime.now(timezone.utc),
            )
        )
        await db_session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/sensors/data",
                params={
                    "esp_id": test_esp.device_id,
                    "gpio": test_sensor.gpio,
                    "quality": "warming_up",
                    "resolution": "raw",
                },
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        # Mapping still omits warming_up from chart series (no numeric Y).
        assert data["count"] == 0
        assert data["readings"] == []


class TestSensorStats:
    """Test sensor statistics."""

    @pytest.mark.asyncio
    async def test_get_sensor_stats(
        self, auth_headers: dict, test_sensor: SensorConfig, test_esp: ESPDevice
    ):
        """Test getting sensor statistics."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/sensors/{test_esp.device_id}/{test_sensor.gpio}/stats",
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "stats" in data


class TestSensorDataBySource:
    """Test sensor data query by source."""

    @pytest.mark.asyncio
    async def test_query_by_source(self, auth_headers: dict, test_sensor: SensorConfig):
        """Test querying sensor data by source."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/sensors/data/by-source/production",
                headers=auth_headers,
            )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_query_data_stats_by_source(self, auth_headers: dict):
        """Test getting data stats by source."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/sensors/data/stats/by-source",
                headers=auth_headers,
            )

        assert response.status_code == 200


class TestSensorAuth:
    """Test authentication requirements for sensor endpoints."""

    @pytest.mark.asyncio
    async def test_create_sensor_without_auth(self, test_esp: ESPDevice):
        """Test creating sensor without authentication."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/sensors/{test_esp.device_id}/36",
                json={
                    "esp_id": test_esp.device_id,
                    "gpio": 36,
                    "sensor_type": "temperature",
                    "name": "Unauthorized Sensor",
                },
            )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_sensor_without_auth(self, test_sensor: SensorConfig, test_esp: ESPDevice):
        """Test deleting sensor without authentication."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.delete(
                f"/api/v1/sensors/{test_esp.device_id}/{test_sensor.id}",
            )

        assert response.status_code == 401


class TestSensorValidation:
    """Test sensor input validation."""

    @pytest.mark.asyncio
    async def test_create_duplicate_sensor(
        self, auth_headers: dict, test_sensor: SensorConfig, test_esp: ESPDevice
    ):
        """Test creating sensor on already-used GPIO."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/sensors/{test_esp.device_id}/{test_sensor.gpio}",
                json={
                    "esp_id": test_esp.device_id,
                    "gpio": test_sensor.gpio,
                    "sensor_type": "temperature",
                    "name": "Duplicate Sensor",
                },
                headers=auth_headers,
            )

        # Should reject duplicate GPIO
        assert response.status_code in [400, 409]


class TestMeasurementRole:
    """Test measurement_role domain contract."""

    @pytest.mark.asyncio
    async def test_create_sensor_with_measurement_role(
        self, auth_headers: dict, test_esp: ESPDevice
    ):
        """Test creating sensor with measurement_role."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/sensors/{test_esp.device_id}/36",
                json={
                    "esp_id": test_esp.device_id,
                    "gpio": 36,
                    "sensor_type": "flow",
                    "name": "Inflow Meter",
                    "enabled": True,
                    "interval_ms": 30000,
                    "processing_mode": "pi_enhanced",
                    "measurement_role": "inflow",
                },
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["measurement_role"] == "inflow"
        assert data["gpio"] == 36

    @pytest.mark.asyncio
    async def test_create_sensor_with_runoff_role(self, auth_headers: dict, test_esp: ESPDevice):
        """Test creating sensor with runoff measurement role."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/sensors/{test_esp.device_id}/37",
                json={
                    "esp_id": test_esp.device_id,
                    "gpio": 37,
                    "sensor_type": "flow",
                    "name": "Runoff Meter",
                    "enabled": True,
                    "interval_ms": 30000,
                    "processing_mode": "pi_enhanced",
                    "measurement_role": "runoff",
                },
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["measurement_role"] == "runoff"
        assert data["gpio"] == 37

    @pytest.mark.asyncio
    async def test_create_sensor_without_measurement_role(
        self, auth_headers: dict, test_esp: ESPDevice
    ):
        """Test creating sensor without measurement_role (defaults to None)."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/sensors/{test_esp.device_id}/38",
                json={
                    "esp_id": test_esp.device_id,
                    "gpio": 38,
                    "sensor_type": "temperature",
                    "name": "Ambient Temp",
                    "enabled": True,
                    "interval_ms": 30000,
                    "processing_mode": "pi_enhanced",
                },
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["measurement_role"] is None

    @pytest.mark.asyncio
    async def test_update_sensor_measurement_role(
        self, auth_headers: dict, test_sensor: SensorConfig, test_esp: ESPDevice
    ):
        """Test updating sensor with new measurement_role."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/sensors/{test_esp.device_id}/{test_sensor.gpio}",
                json={
                    "esp_id": test_esp.device_id,
                    "gpio": test_sensor.gpio,
                    "sensor_type": "ph",
                    "name": "Test pH Sensor",
                    "enabled": True,
                    "interval_ms": 30000,
                    "processing_mode": "pi_enhanced",
                    "measurement_role": "inflow",
                },
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["measurement_role"] == "inflow"

    @pytest.mark.asyncio
    async def test_invalid_measurement_role(self, auth_headers: dict, test_esp: ESPDevice):
        """Test that invalid measurement_role is rejected."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/sensors/{test_esp.device_id}/39",
                json={
                    "esp_id": test_esp.device_id,
                    "gpio": 39,
                    "sensor_type": "flow",
                    "name": "Invalid Role Sensor",
                    "enabled": True,
                    "interval_ms": 30000,
                    "processing_mode": "pi_enhanced",
                    "measurement_role": "invalid_role",
                },
                headers=auth_headers,
            )

        # Should reject invalid measurement_role
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_measurement_role_persisted_in_metadata(
        self, auth_headers: dict, test_esp: ESPDevice, db_session: AsyncSession
    ):
        """Test that measurement_role is correctly persisted in sensor_metadata."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/sensors/{test_esp.device_id}/32",
                json={
                    "esp_id": test_esp.device_id,
                    "gpio": 32,
                    "sensor_type": "flow",
                    "name": "Test Flow Sensor",
                    "enabled": True,
                    "interval_ms": 30000,
                    "processing_mode": "pi_enhanced",
                    "measurement_role": "inflow",
                },
                headers=auth_headers,
            )

        assert response.status_code == 200
        sensor_id = response.json()["id"]

        # Verify in database directly
        import uuid as _uuid
        from src.db.repositories import SensorRepository

        sensor_repo = SensorRepository(db_session)
        sensor = await sensor_repo.get_by_id(_uuid.UUID(sensor_id))
        assert sensor is not None
        assert sensor.sensor_metadata.get("measurement_role") == "inflow"


class TestMountGeometry:
    """AUT-1555: mount_* first-class columns on existing sensor_configs write."""

    @pytest.mark.asyncio
    async def test_create_sensor_with_mount_fields(
        self, auth_headers: dict, test_esp: ESPDevice, db_session: AsyncSession
    ):
        """Create persists mount columns and does not write them into sensor_metadata."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/sensors/{test_esp.device_id}/33",
                json={
                    "esp_id": test_esp.device_id,
                    "gpio": 33,
                    "sensor_type": "temperature",
                    "name": "Canopy Temp",
                    "enabled": True,
                    "interval_ms": 30000,
                    "processing_mode": "pi_enhanced",
                    "mount_height_cm": 120.5,
                    "mount_medium": "canopy",
                    "mount_angle_deg": 45.0,
                },
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["mount_height_cm"] == 120.5
        assert data["mount_medium"] == "canopy"
        assert data["mount_angle_deg"] == 45.0

        import uuid as _uuid
        from src.db.repositories import SensorRepository

        sensor = await SensorRepository(db_session).get_by_id(_uuid.UUID(data["id"]))
        assert sensor is not None
        assert sensor.mount_height_cm == 120.5
        assert sensor.mount_medium == "canopy"
        assert sensor.mount_angle_deg == 45.0
        assert "mount_height_cm" not in (sensor.sensor_metadata or {})
        assert "mount_medium" not in (sensor.sensor_metadata or {})
        assert "mount_angle_deg" not in (sensor.sensor_metadata or {})

    @pytest.mark.asyncio
    async def test_create_sensor_without_mount_fields_stays_null(
        self, auth_headers: dict, test_sensor: SensorConfig, test_esp: ESPDevice
    ):
        """Old / omitted rows stay valid: mount fields are null."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/sensors/{test_esp.device_id}/{test_sensor.gpio}",
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["mount_height_cm"] is None
        assert data["mount_medium"] is None
        assert data["mount_angle_deg"] is None

    @pytest.mark.asyncio
    async def test_update_sensor_mount_fields(
        self, auth_headers: dict, test_sensor: SensorConfig, test_esp: ESPDevice
    ):
        """Existing create/update POST stores mount fields on the same row."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/sensors/{test_esp.device_id}/{test_sensor.gpio}",
                json={
                    "esp_id": test_esp.device_id,
                    "gpio": test_sensor.gpio,
                    "sensor_type": "ph",
                    "name": "Test pH Sensor",
                    "enabled": True,
                    "interval_ms": 30000,
                    "processing_mode": "pi_enhanced",
                    "mount_height_cm": 15.0,
                    "mount_medium": "solution",
                    "mount_angle_deg": 0.0,
                },
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["mount_height_cm"] == 15.0
        assert data["mount_medium"] == "solution"
        assert data["mount_angle_deg"] == 0.0

    @pytest.mark.asyncio
    async def test_update_without_mount_fields_does_not_clobber(
        self, auth_headers: dict, test_esp: ESPDevice
    ):
        """Omitting mount fields on a later POST must not wipe stored values."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            created = await client.post(
                f"/api/v1/sensors/{test_esp.device_id}/33",
                json={
                    "esp_id": test_esp.device_id,
                    "gpio": 33,
                    "sensor_type": "humidity",
                    "name": "Air Humidity",
                    "enabled": True,
                    "interval_ms": 30000,
                    "processing_mode": "pi_enhanced",
                    "mount_height_cm": 80.0,
                    "mount_medium": "air",
                    "mount_angle_deg": 90.0,
                },
                headers=auth_headers,
            )
            assert created.status_code == 200

            updated = await client.post(
                f"/api/v1/sensors/{test_esp.device_id}/33",
                json={
                    "esp_id": test_esp.device_id,
                    "gpio": 33,
                    "sensor_type": "humidity",
                    "name": "Air Humidity",
                    "enabled": True,
                    "interval_ms": 30000,
                    "processing_mode": "pi_enhanced",
                },
                headers=auth_headers,
            )

        assert updated.status_code == 200
        data = updated.json()
        assert data["mount_height_cm"] == 80.0
        assert data["mount_medium"] == "air"
        assert data["mount_angle_deg"] == 90.0

    @pytest.mark.asyncio
    async def test_invalid_mount_medium_rejected(self, auth_headers: dict, test_esp: ESPDevice):
        """Medium catalog is exactly air|canopy|substrate|solution."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/sensors/{test_esp.device_id}/33",
                json={
                    "esp_id": test_esp.device_id,
                    "gpio": 33,
                    "sensor_type": "moisture",
                    "name": "Soil Probe",
                    "enabled": True,
                    "interval_ms": 30000,
                    "processing_mode": "pi_enhanced",
                    "mount_medium": "soil",
                },
                headers=auth_headers,
            )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_then_get_reads_back_mount_fields(
        self, auth_headers: dict, test_esp: ESPDevice
    ):
        """Create with all three fields, then GET the same GPIO returns them."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            created = await client.post(
                f"/api/v1/sensors/{test_esp.device_id}/33",
                json={
                    "esp_id": test_esp.device_id,
                    "gpio": 33,
                    "sensor_type": "moisture",
                    "name": "Substrate Probe",
                    "enabled": True,
                    "interval_ms": 30000,
                    "processing_mode": "pi_enhanced",
                    "mount_height_cm": 30.0,
                    "mount_medium": "substrate",
                    "mount_angle_deg": 0.0,
                },
                headers=auth_headers,
            )
            assert created.status_code == 200

            response = await client.get(
                f"/api/v1/sensors/{test_esp.device_id}/33",
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["mount_height_cm"] == 30.0
        assert data["mount_medium"] == "substrate"
        assert data["mount_angle_deg"] == 0.0

    @pytest.mark.asyncio
    async def test_update_one_mount_field_leaves_others(
        self, auth_headers: dict, test_esp: ESPDevice
    ):
        """Updating only height must leave stored medium and angle."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            created = await client.post(
                f"/api/v1/sensors/{test_esp.device_id}/33",
                json={
                    "esp_id": test_esp.device_id,
                    "gpio": 33,
                    "sensor_type": "temperature",
                    "name": "Canopy Temp",
                    "enabled": True,
                    "interval_ms": 30000,
                    "processing_mode": "pi_enhanced",
                    "mount_height_cm": 120.0,
                    "mount_medium": "canopy",
                    "mount_angle_deg": 45.0,
                },
                headers=auth_headers,
            )
            assert created.status_code == 200

            updated = await client.post(
                f"/api/v1/sensors/{test_esp.device_id}/33",
                json={
                    "esp_id": test_esp.device_id,
                    "gpio": 33,
                    "sensor_type": "temperature",
                    "name": "Canopy Temp",
                    "enabled": True,
                    "interval_ms": 30000,
                    "processing_mode": "pi_enhanced",
                    "mount_height_cm": 90.0,
                },
                headers=auth_headers,
            )

        assert updated.status_code == 200
        data = updated.json()
        assert data["mount_height_cm"] == 90.0
        assert data["mount_medium"] == "canopy"
        assert data["mount_angle_deg"] == 45.0

    @pytest.mark.asyncio
    async def test_explicit_null_on_update_does_not_clobber(
        self, auth_headers: dict, test_esp: ESPDevice
    ):
        """Explicit JSON null is indistinguishable from omit — stored mount stays."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            created = await client.post(
                f"/api/v1/sensors/{test_esp.device_id}/33",
                json={
                    "esp_id": test_esp.device_id,
                    "gpio": 33,
                    "sensor_type": "humidity",
                    "name": "Air Humidity",
                    "enabled": True,
                    "interval_ms": 30000,
                    "processing_mode": "pi_enhanced",
                    "mount_height_cm": 80.0,
                    "mount_medium": "air",
                    "mount_angle_deg": 90.0,
                },
                headers=auth_headers,
            )
            assert created.status_code == 200

            updated = await client.post(
                f"/api/v1/sensors/{test_esp.device_id}/33",
                json={
                    "esp_id": test_esp.device_id,
                    "gpio": 33,
                    "sensor_type": "humidity",
                    "name": "Air Humidity",
                    "enabled": True,
                    "interval_ms": 30000,
                    "processing_mode": "pi_enhanced",
                    "mount_height_cm": None,
                    "mount_medium": None,
                    "mount_angle_deg": None,
                },
                headers=auth_headers,
            )

        assert updated.status_code == 200
        data = updated.json()
        assert data["mount_height_cm"] == 80.0
        assert data["mount_medium"] == "air"
        assert data["mount_angle_deg"] == 90.0

    @pytest.mark.asyncio
    async def test_export_default_header_includes_schema_columns(
        self, auth_headers: dict, test_esp: ESPDevice
    ):
        """GET /sensors/export default header is the honest AUT-1577 schema head."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/sensors/export",
                params={"esp_id": test_esp.device_id},
                headers=auth_headers,
            )

        assert response.status_code == 200
        header = (response.text.splitlines()[0] if response.text else "").lstrip("\ufeff")
        assert header == (
            "timestamp,processed_value,unit,quality,sensor_type,timezone,"
            "esp_id,zone_id,subzone_id,sample_interval_ms,mount_height_cm,"
            "mount_medium,mount_angle_deg,calibrated_at,site_id"
        )


class TestExportSchemaHead:
    """AUT-1577: honest CSV head on the existing export endpoint."""

    @pytest.mark.asyncio
    async def test_export_two_zones_canopy_and_empty_calibrated_at(
        self,
        auth_headers: dict,
        db_session: AsyncSession,
    ):
        """Two sensors / two zones; canopy medium present; missing cal stays empty cell."""
        zone_a = Zone(zone_id="haus_a", name="Haus A")
        zone_b = Zone(zone_id="haus_b", name="Haus B")
        db_session.add_all([zone_a, zone_b])
        await db_session.flush()

        esp_a = ESPDevice(
            device_id="ESP_A1577001",
            name="Export ESP A",
            ip_address="192.168.1.201",
            mac_address="AA:BB:CC:DD:EE:A1",
            firmware_version="2.0.0",
            hardware_type="ESP32_WROOM",
            status="online",
            zone_id="haus_a",
            metadata={},
        )
        esp_b = ESPDevice(
            device_id="ESP_B1577002",
            name="Export ESP B",
            ip_address="192.168.1.202",
            mac_address="AA:BB:CC:DD:EE:B2",
            firmware_version="2.0.0",
            hardware_type="ESP32_WROOM",
            status="online",
            zone_id="haus_b",
            metadata={},
        )
        db_session.add_all([esp_a, esp_b])
        await db_session.flush()

        sensor_a = SensorConfig(
            esp_id=esp_a.id,
            gpio=34,
            sensor_type="temperature",
            sensor_name="Canopy A",
            interface_type="ANALOG",
            enabled=True,
            sample_interval_ms=15000,
            pi_enhanced=True,
            mount_height_cm=120.0,
            mount_medium="canopy",
            mount_angle_deg=45.0,
            calibration_data={"derived": {"calibrated_at": "2026-08-01T12:00:00+00:00"}},
            sensor_metadata={},
        )
        sensor_b = SensorConfig(
            esp_id=esp_b.id,
            gpio=35,
            sensor_type="temperature",
            sensor_name="Air B",
            interface_type="ANALOG",
            enabled=True,
            sample_interval_ms=30000,
            pi_enhanced=True,
            mount_medium="air",
            calibration_data={},
            sensor_metadata={},
        )
        db_session.add_all([sensor_a, sensor_b])

        ts_a = datetime(2026, 8, 26, 14, 0, tzinfo=timezone.utc)
        ts_b = datetime(2026, 8, 26, 14, 1, tzinfo=timezone.utc)
        db_session.add_all(
            [
                SensorData(
                    esp_id=esp_a.id,
                    gpio=34,
                    sensor_type="temperature",
                    raw_value=2100.0,
                    processed_value=26.5,
                    unit="°C",
                    processing_mode="pi_enhanced",
                    quality="good",
                    timestamp=ts_a,
                    zone_id="haus_a",
                    subzone_id="canopy_1",
                ),
                SensorData(
                    esp_id=esp_b.id,
                    gpio=35,
                    sensor_type="temperature",
                    raw_value=2048.0,
                    processed_value=24.0,
                    unit="°C",
                    processing_mode="pi_enhanced",
                    quality="good",
                    timestamp=ts_b,
                    zone_id="haus_b",
                    subzone_id="room",
                ),
            ]
        )
        await db_session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response_a = await client.get(
                "/api/v1/sensors/export",
                params={"esp_id": esp_a.device_id},
                headers=auth_headers,
            )
            response_b = await client.get(
                "/api/v1/sensors/export",
                params={"esp_id": esp_b.device_id},
                headers=auth_headers,
            )

        assert response_a.status_code == 200
        assert response_b.status_code == 200

        header_a = response_a.text.splitlines()[0].lstrip("\ufeff")
        header_b = response_b.text.splitlines()[0].lstrip("\ufeff")
        expected = (
            "timestamp,processed_value,unit,quality,sensor_type,timezone,"
            "esp_id,zone_id,subzone_id,sample_interval_ms,mount_height_cm,"
            "mount_medium,mount_angle_deg,calibrated_at,site_id"
        )
        assert header_a == expected
        assert header_b == expected

        cols = expected.split(",")
        row_a = dict(zip(cols, next(csv.reader([response_a.text.splitlines()[1]])), strict=True))
        row_b = dict(zip(cols, next(csv.reader([response_b.text.splitlines()[1]])), strict=True))

        assert row_a["unit"] == "°C"
        assert row_a["timezone"] == "UTC"
        assert row_a["zone_id"] == "haus_a"
        assert row_a["mount_medium"] == "canopy"
        assert row_a["esp_id"] == "ESP_A1577001"
        assert row_a["calibrated_at"] == "2026-08-01T12:00:00+00:00"
        assert row_a["site_id"] == ""
        assert row_a["sample_interval_ms"] == "15000"

        assert row_b["unit"] == "°C"
        assert row_b["timezone"] == "UTC"
        assert row_b["zone_id"] == "haus_b"
        assert row_b["mount_medium"] == "air"
        assert row_b["esp_id"] == "ESP_B1577002"
        assert row_b["calibrated_at"] == ""
        assert row_b["site_id"] == ""
        assert "calibrated_at" in header_b

    @pytest.mark.asyncio
    async def test_export_old_five_columns_query_still_has_schema_head(
        self, auth_headers: dict, test_esp: ESPDevice
    ):
        """columns= AUT-1546 five still yields the AUT-1577 Pflicht-Spalten."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/sensors/export",
                params={
                    "esp_id": test_esp.device_id,
                    "columns": "timestamp,processed_value,unit,quality,sensor_type",
                },
                headers=auth_headers,
            )

        assert response.status_code == 200
        header = response.text.splitlines()[0].lstrip("\ufeff")
        assert header == (
            "timestamp,processed_value,unit,quality,sensor_type,timezone,"
            "esp_id,zone_id,subzone_id,sample_interval_ms,mount_height_cm,"
            "mount_medium,mount_angle_deg,calibrated_at,site_id"
        )
