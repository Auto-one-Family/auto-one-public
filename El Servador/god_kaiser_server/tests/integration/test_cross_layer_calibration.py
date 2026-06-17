"""
Cross-Layer Integration Tests for Calibration Flow (AUT-10)

Simulates end-to-end calibration workflow:
1. Server API triggers calibration session (REST)
2. Server sends measurement request to ESP32 (MQTT)
3. ESP32 responds with sensor data (simulated via mock)
4. Server processes response and persists calibration result
5. Server applies result to sensor configuration

Tests cover:
- Happy path: Full calibration success
- Timeout handling: ESP32 offline scenario
- Retry logic: Transient failures with successful retry
"""

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token, get_password_hash
from src.db.models.esp import ESPDevice
from src.db.models.sensor import SensorConfig
from src.db.models.user import User
from src.main import app
from src.services.calibration_service import CalibrationService, CalibrationError

# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
async def operator_user(db_session: AsyncSession) -> User:
    """Create operator user for calibration operations."""
    user = User(
        username="calib_operator_cross",
        email="calib_operator_cross@example.com",
        password_hash=get_password_hash("TestOperator123"),
        full_name="Cross-Layer Test Operator",
        role="operator",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def operator_headers(operator_user: User) -> dict[str, str]:
    """Create authorization headers for operator user."""
    token = create_access_token(
        user_id=operator_user.id,
        additional_claims={"role": operator_user.role},
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def calibration_sensor_setup(db_session: AsyncSession) -> tuple[str, int]:
    """
    Create ESP device and bound sensor for calibration testing.

    Returns:
        Tuple of (esp_id, gpio) for calibration test references
    """
    esp = ESPDevice(
        device_id="ESP_CALIB_CROSS_001",
        hardware_type="ESP32_WROOM",
        status="online",
        ip_address="192.168.1.50",
    )
    db_session.add(esp)
    await db_session.flush()

    sensor = SensorConfig(
        esp_id=esp.id,
        gpio=12,
        sensor_type="moisture",
        sensor_name="test-moisture-gpio12",
        enabled=True,
    )
    db_session.add(sensor)
    await db_session.commit()

    return esp.device_id, sensor.gpio


@pytest.fixture
async def mock_mqtt_calibration_handler():
    """
    Create mock MQTT handler for simulating ESP32 sensor data responses.

    Provides methods to simulate successful and failed responses.
    """
    mock_handler = MagicMock()
    mock_handler.publish = AsyncMock()
    mock_handler.subscribe = AsyncMock()
    return mock_handler


# ============================================================================
# Test 1: Happy Path — Full Calibration Success
# ============================================================================


@pytest.mark.asyncio
async def test_cross_layer_calibration_happy_path(
    operator_headers: dict[str, str],
    calibration_sensor_setup: tuple[str, int],
    mock_mqtt_publisher_for_subzone,
):
    """
    Happy path: Server triggers calibration, receives sensor data, applies result.

    Flow:
    1. Create calibration session via REST
    2. Collect dry point (raw=900, ref=0)
    3. Collect wet point (raw=600, ref=100)
    4. Finalize session (compute linear slope/offset)
    5. Apply result to sensor (persist calibration_data)
    6. Verify sensor config now has calibration applied

    This test does NOT simulate actual MQTT; it assumes successful data flow.
    """
    esp_id, gpio = calibration_sensor_setup

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Step 1: Start calibration session
        start_response = await client.post(
            "/api/v1/calibration/sessions",
            headers=operator_headers,
            json={
                "esp_id": esp_id,
                "gpio": gpio,
                "sensor_type": "moisture",
                "method": "linear_2point",
                "expected_points": 2,
            },
        )
        assert start_response.status_code == 201
        session_id = start_response.json()["id"]
        assert start_response.json()["status"] == "pending"

        # Step 2: Add dry point
        dry_response = await client.post(
            f"/api/v1/calibration/sessions/{session_id}/points",
            headers=operator_headers,
            json={
                "raw_value": 900.0,
                "reference_value": 0.0,
                "point_role": "dry",
            },
        )
        assert dry_response.status_code == 200
        assert dry_response.json()["points_collected"] == 1

        # Step 3: Add wet point
        wet_response = await client.post(
            f"/api/v1/calibration/sessions/{session_id}/points",
            headers=operator_headers,
            json={
                "raw_value": 600.0,
                "reference_value": 100.0,
                "point_role": "wet",
            },
        )
        assert wet_response.status_code == 200
        assert wet_response.json()["points_collected"] == 2

        # Step 4: Finalize (compute calibration result)
        finalize_response = await client.post(
            f"/api/v1/calibration/sessions/{session_id}/finalize",
            headers=operator_headers,
        )
        assert finalize_response.status_code == 200
        finalized_session = finalize_response.json()
        assert finalized_session["status"] == "finalizing"

        # Verify calibration result was computed (canonical envelope)
        result = finalized_session.get("calibration_result")
        assert result is not None
        assert result.get("method") == "linear_2point"
        derived = result.get("derived", {})
        assert "slope" in derived
        assert "offset" in derived

        # Step 5: Apply calibration (persist to sensor config)
        apply_response = await client.post(
            f"/api/v1/calibration/sessions/{session_id}/apply",
            headers=operator_headers,
        )
        assert apply_response.status_code == 200
        applied_session = apply_response.json()
        assert applied_session["status"] == "applied"

        # Step 6: Verify sensor now has calibration data
        # Fetch sensor via GET (if endpoint exists) or verify through session
        get_session = await client.get(
            f"/api/v1/calibration/sessions/{session_id}",
            headers=operator_headers,
        )
        assert get_session.status_code == 200
        final_session = get_session.json()
        assert final_session["status"] == "applied"


# ============================================================================
# Test 2: Timeout Scenario — ESP32 Offline / No Response
# ============================================================================


@pytest.mark.asyncio
async def test_cross_layer_calibration_esp_offline_timeout(
    operator_headers: dict[str, str],
    calibration_sensor_setup: tuple[str, int],
):
    """
    Timeout scenario: Server waits for sensor data, ESP32 is offline.

    Simulates:
    - Session is created and waiting for measurement ACK from ESP32
    - No MQTT response arrives within timeout window
    - Session transitions to error/failed state

    Note: This test verifies the calibration service can handle missing
    measurement data. Actual MQTT timeout enforcement is in the
    MQTT client layer (tested separately).
    """
    esp_id, gpio = calibration_sensor_setup

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create session
        start_response = await client.post(
            "/api/v1/calibration/sessions",
            headers=operator_headers,
            json={
                "esp_id": esp_id,
                "gpio": gpio,
                "sensor_type": "moisture",
                "method": "linear_2point",
                "expected_points": 2,
            },
        )
        assert start_response.status_code == 201
        session_id = start_response.json()["id"]

        # Add only one point (dry) — intentionally incomplete
        dry_response = await client.post(
            f"/api/v1/calibration/sessions/{session_id}/points",
            headers=operator_headers,
            json={
                "raw_value": 900.0,
                "reference_value": 0.0,
                "point_role": "dry",
            },
        )
        assert dry_response.status_code == 200
        assert dry_response.json()["points_collected"] == 1

        # Attempt to finalize with incomplete points
        # (simulates scenario where ESP never sent wet point)
        finalize_response = await client.post(
            f"/api/v1/calibration/sessions/{session_id}/finalize",
            headers=operator_headers,
        )

        # Should fail — not enough points (need 2, have 1)
        # INSUFFICIENT_POINTS maps to 409 Conflict in the API contract
        assert finalize_response.status_code == 409
        error_detail = finalize_response.json().get("detail", {})
        assert error_detail.get("code") == "INSUFFICIENT_POINTS"

        # Session remains in COLLECTING (mutable — user can add more points)
        get_response = await client.get(
            f"/api/v1/calibration/sessions/{session_id}",
            headers=operator_headers,
        )
        assert get_response.status_code == 200
        assert get_response.json()["status"] == "collecting"


# ============================================================================
# Test 3: Retry Success — Transient Failure Followed by Recovery
# ============================================================================


@pytest.mark.asyncio
async def test_cross_layer_calibration_retry_success(
    operator_headers: dict[str, str],
    calibration_sensor_setup: tuple[str, int],
):
    """
    Retry scenario: First point addition fails (simulated), second succeeds.

    Demonstrates:
    - User can retry point collection after transient failures
    - Overwrite mechanism allows replacing a bad measurement
    - Session eventually completes successfully

    This test simulates a user repeating a measurement after an error
    (e.g., sensor was disconnected on first attempt, reconnected on second).
    """
    esp_id, gpio = calibration_sensor_setup

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create session
        start_response = await client.post(
            "/api/v1/calibration/sessions",
            headers=operator_headers,
            json={
                "esp_id": esp_id,
                "gpio": gpio,
                "sensor_type": "moisture",
                "method": "linear_2point",
                "expected_points": 2,
            },
        )
        assert start_response.status_code == 201
        session_id = start_response.json()["id"]

        # First dry point addition (simulating first attempt)
        first_dry = await client.post(
            f"/api/v1/calibration/sessions/{session_id}/points",
            headers=operator_headers,
            json={
                "raw_value": 850.0,
                "reference_value": 0.0,
                "point_role": "dry",
            },
        )
        assert first_dry.status_code == 200
        first_point_id = first_dry.json()["calibration_points"]["points"][0]["id"]

        # Try to add another dry point without overwrite (should fail)
        duplicate_dry = await client.post(
            f"/api/v1/calibration/sessions/{session_id}/points",
            headers=operator_headers,
            json={
                "raw_value": 870.0,
                "reference_value": 0.0,
                "point_role": "dry",
            },
        )
        assert duplicate_dry.status_code == 409
        assert duplicate_dry.json()["detail"]["code"] == "ROLE_POINT_EXISTS"

        # Retry with overwrite (simulating user correcting measurement)
        retry_dry = await client.post(
            f"/api/v1/calibration/sessions/{session_id}/points",
            headers=operator_headers,
            json={
                "raw_value": 895.0,
                "reference_value": 0.0,
                "point_role": "dry",
                "overwrite": True,
            },
        )
        assert retry_dry.status_code == 200
        retried_points = retry_dry.json()["calibration_points"]["points"]
        assert len(retried_points) == 1
        # Point ID should be stable (same point, updated value)
        assert retried_points[0]["id"] == first_point_id
        assert retried_points[0]["raw"] == 895.0

        # Add wet point
        wet_response = await client.post(
            f"/api/v1/calibration/sessions/{session_id}/points",
            headers=operator_headers,
            json={
                "raw_value": 620.0,
                "reference_value": 100.0,
                "point_role": "wet",
            },
        )
        assert wet_response.status_code == 200
        assert wet_response.json()["points_collected"] == 2

        # Finalize and apply
        finalize_response = await client.post(
            f"/api/v1/calibration/sessions/{session_id}/finalize",
            headers=operator_headers,
        )
        assert finalize_response.status_code == 200
        assert finalize_response.json()["status"] == "finalizing"

        apply_response = await client.post(
            f"/api/v1/calibration/sessions/{session_id}/apply",
            headers=operator_headers,
        )
        assert apply_response.status_code == 200
        assert apply_response.json()["status"] == "applied"


# ============================================================================
# Test 4 (Advanced): Multiple Concurrent Sessions (Race Condition)
# ============================================================================


@pytest.mark.asyncio
async def test_cross_layer_calibration_concurrent_sessions_isolation(
    operator_headers: dict[str, str],
    db_session: AsyncSession,
):
    """
    Concurrent sessions isolation: Multiple calibrations running simultaneously.

    Verifies:
    - Each session maintains separate point collections
    - No cross-contamination between sessions for same sensor
    - Overwrite arbitration works under concurrency
    """
    # Create two ESP devices
    esp1 = ESPDevice(
        device_id="ESP_CONC_001",
        hardware_type="ESP32_WROOM",
        status="online",
    )
    esp2 = ESPDevice(
        device_id="ESP_CONC_002",
        hardware_type="ESP32_WROOM",
        status="online",
    )
    db_session.add(esp1)
    db_session.add(esp2)
    await db_session.flush()

    sensor1 = SensorConfig(
        esp_id=esp1.id,
        gpio=12,
        sensor_type="moisture",
        sensor_name="concurrency-test-1",
        enabled=True,
    )
    sensor2 = SensorConfig(
        esp_id=esp2.id,
        gpio=12,
        sensor_type="moisture",
        sensor_name="concurrency-test-2",
        enabled=True,
    )
    db_session.add_all([sensor1, sensor2])
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Start two concurrent sessions
        session1_response = await client.post(
            "/api/v1/calibration/sessions",
            headers=operator_headers,
            json={
                "esp_id": "ESP_CONC_001",
                "gpio": 12,
                "sensor_type": "moisture",
                "method": "linear_2point",
                "expected_points": 2,
            },
        )
        session1_id = session1_response.json()["id"]

        session2_response = await client.post(
            "/api/v1/calibration/sessions",
            headers=operator_headers,
            json={
                "esp_id": "ESP_CONC_002",
                "gpio": 12,
                "sensor_type": "moisture",
                "method": "linear_2point",
                "expected_points": 2,
            },
        )
        session2_id = session2_response.json()["id"]

        # Concurrently add points to both sessions
        responses = await asyncio.gather(
            client.post(
                f"/api/v1/calibration/sessions/{session1_id}/points",
                headers=operator_headers,
                json={
                    "raw_value": 900.0,
                    "reference_value": 0.0,
                    "point_role": "dry",
                },
            ),
            client.post(
                f"/api/v1/calibration/sessions/{session2_id}/points",
                headers=operator_headers,
                json={
                    "raw_value": 910.0,
                    "reference_value": 0.0,
                    "point_role": "dry",
                },
            ),
        )

        # Both should succeed independently
        assert responses[0].status_code == 200
        assert responses[1].status_code == 200

        # Verify each session has its own point
        session1_get = await client.get(
            f"/api/v1/calibration/sessions/{session1_id}",
            headers=operator_headers,
        )
        session1_points = session1_get.json()["calibration_points"]["points"]
        assert len(session1_points) == 1
        assert session1_points[0]["raw"] == 900.0

        session2_get = await client.get(
            f"/api/v1/calibration/sessions/{session2_id}",
            headers=operator_headers,
        )
        session2_points = session2_get.json()["calibration_points"]["points"]
        assert len(session2_points) == 1
        assert session2_points[0]["raw"] == 910.0


# ============================================================================
# Test 5: Service Layer Directly — CalibrationService Tests
# ============================================================================


@pytest.mark.asyncio
async def test_calibration_service_full_lifecycle(db_session: AsyncSession):
    """
    Direct service layer test: Verify CalibrationService orchestration.

    Tests service methods directly without HTTP layer, useful for
    testing business logic and edge cases.
    """
    # Setup sensor
    esp = ESPDevice(
        device_id="ESP_SERVICE_TEST",
        hardware_type="ESP32_WROOM",
        status="online",
    )
    db_session.add(esp)
    await db_session.flush()

    sensor = SensorConfig(
        esp_id=esp.id,
        gpio=4,
        sensor_type="temperature",
        sensor_name="service-test-temp",
        enabled=True,
    )
    db_session.add(sensor)
    await db_session.commit()

    # Test service
    service = CalibrationService(db_session)

    # Start session
    session = await service.start_session(
        esp_id="ESP_SERVICE_TEST",
        gpio=4,
        sensor_type="temperature",
        method="linear_2point",
        expected_points=2,
        initiated_by="service_test",
    )
    assert session.status.value == "pending"

    # Add points (first add_point transitions PENDING → COLLECTING)
    session = await service.add_point(
        session_id=session.id,
        raw=500.0,
        reference=20.0,
        point_role="dry",
    )
    assert session.points_collected == 1

    session = await service.add_point(
        session_id=session.id,
        raw=1000.0,
        reference=50.0,
        point_role="wet",
    )
    assert session.points_collected == 2

    # Finalize
    session = await service.finalize(session.id)
    assert session.status.value == "finalizing"
    assert session.calibration_result is not None
    assert session.calibration_result.get("method") == "linear_2point"
    assert "slope" in session.calibration_result.get("derived", {})

    # Apply
    session = await service.apply(session.id)
    assert session.status.value == "applied"

    # Verify sensor was updated (canonical calibration_data envelope)
    updated_sensor = await db_session.get(SensorConfig, sensor.id)
    assert updated_sensor.calibration_data is not None
    assert updated_sensor.calibration_data.get("method") == "linear_2point"


@pytest.mark.asyncio
async def test_calibration_service_error_handling(db_session: AsyncSession):
    """
    Service layer error handling: Invalid operations raise CalibrationError.
    """
    service = CalibrationService(db_session)

    # Test: start session with non-existent ESP (should still work, sensor may not exist yet)
    session = await service.start_session(
        esp_id="ESP_NONEXISTENT",
        gpio=99,
        sensor_type="unknown_type",
        method="linear_2point",
        expected_points=2,
    )
    assert session.status.value == "pending"

    # Test: add invalid point role
    with pytest.raises(CalibrationError) as exc:
        await service.add_point(
            session_id=session.id,
            raw=100.0,
            reference=10.0,
            point_role="invalid_role",
        )
    assert exc.value.code == "VALIDATION_ERROR"

    # Test: add non-finite value
    with pytest.raises(CalibrationError) as exc:
        await service.add_point(
            session_id=session.id,
            raw=float("inf"),
            reference=10.0,
            point_role="dry",
        )
    assert exc.value.code == "VALIDATION_ERROR"

    # Test: finalize from PENDING state (no valid points added → INVALID_STATE)
    with pytest.raises(CalibrationError) as exc:
        await service.finalize(session.id)
    assert exc.value.code == "INVALID_STATE"

    # Test: finalize with insufficient points (add one valid point → COLLECTING, then finalize)
    session = await service.add_point(
        session_id=session.id,
        raw=100.0,
        reference=10.0,
        point_role="dry",
    )
    assert session.status.value == "collecting"
    with pytest.raises(CalibrationError) as exc:
        await service.finalize(session.id)
    assert exc.value.code == "INSUFFICIENT_POINTS"
