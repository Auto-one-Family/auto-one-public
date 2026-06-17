"""Integration tests for calibration session REST contract."""

import asyncio
from collections import Counter
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token, get_password_hash
from src.db.models.esp import ESPDevice
from src.db.models.sensor import SensorConfig
from src.db.models.user import User
from src.main import app


@pytest.fixture
async def operator_user(db_session: AsyncSession) -> User:
    user = User(
        username="calib_operator",
        email="calib_operator@example.com",
        password_hash=get_password_hash("OperatorP@ss123"),
        full_name="Calibration Operator",
        role="operator",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def viewer_user(db_session: AsyncSession) -> User:
    user = User(
        username="calib_viewer",
        email="calib_viewer@example.com",
        password_hash=get_password_hash("ViewerP@ss123"),
        full_name="Calibration Viewer",
        role="viewer",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def operator_headers(operator_user: User) -> dict[str, str]:
    token = create_access_token(
        user_id=operator_user.id,
        additional_claims={"role": operator_user.role},
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def viewer_headers(viewer_user: User) -> dict[str, str]:
    token = create_access_token(
        user_id=viewer_user.id,
        additional_claims={"role": viewer_user.role},
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def bound_sensor_for_apply(db_session: AsyncSession) -> None:
    esp = ESPDevice(device_id="ESP_TEST_001", hardware_type="ESP32_WROOM", status="online")
    db_session.add(esp)
    await db_session.flush()

    sensor = SensorConfig(
        esp_id=esp.id,
        gpio=10,
        sensor_type="moisture",
        sensor_name="moisture-calib-gpio10",
        enabled=True,
    )
    db_session.add(sensor)
    await db_session.commit()


async def _start_session(
    client: AsyncClient,
    headers: dict[str, str],
    gpio: int,
    esp_id: str = "ESP_TEST_001",
) -> str:
    response = await client.post(
        "/api/v1/calibration/sessions",
        headers=headers,
        json={
            "esp_id": esp_id,
            "gpio": gpio,
            "sensor_type": "moisture",
            "method": "linear_2point",
            "expected_points": 2,
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


@pytest.mark.asyncio
async def test_calibration_session_full_route_flow(
    operator_headers: dict[str, str],
    bound_sensor_for_apply: None,
):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        start_response = await client.post(
            "/api/v1/calibration/sessions",
            headers=operator_headers,
            json={
                "esp_id": "ESP_TEST_001",
                "gpio": 10,
                "sensor_type": "moisture",
                "method": "linear_2point",
                "expected_points": 2,
            },
        )
        assert start_response.status_code == 201
        session_id = start_response.json()["id"]

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


@pytest.mark.asyncio
async def test_calibration_session_overwrite_flow(operator_headers: dict[str, str]):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        start_response = await client.post(
            "/api/v1/calibration/sessions",
            headers=operator_headers,
            json={
                "esp_id": "ESP_TEST_001",
                "gpio": 11,
                "sensor_type": "moisture",
                "method": "linear_2point",
                "expected_points": 2,
            },
        )
        session_id = start_response.json()["id"]

        first_point = await client.post(
            f"/api/v1/calibration/sessions/{session_id}/points",
            headers=operator_headers,
            json={
                "raw_value": 910.0,
                "reference_value": 0.0,
                "point_role": "dry",
            },
        )
        assert first_point.status_code == 200
        point_id_before = first_point.json()["calibration_points"]["points"][0]["id"]

        duplicate_without_overwrite = await client.post(
            f"/api/v1/calibration/sessions/{session_id}/points",
            headers=operator_headers,
            json={
                "raw_value": 905.0,
                "reference_value": 1.0,
                "point_role": "dry",
            },
        )
        assert duplicate_without_overwrite.status_code == 409

        overwrite_response = await client.post(
            f"/api/v1/calibration/sessions/{session_id}/points",
            headers=operator_headers,
            json={
                "raw_value": 905.0,
                "reference_value": 1.0,
                "point_role": "dry",
                "overwrite": True,
            },
        )
        assert overwrite_response.status_code == 200
        points = overwrite_response.json()["calibration_points"]["points"]
        assert len(points) == 1
        assert points[0]["id"] == point_id_before
        assert points[0]["raw"] == 905.0


@pytest.mark.asyncio
async def test_calibration_apply_requires_persisted_sensor_binding(
    operator_headers: dict[str, str],
):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        session_id = await _start_session(
            client, operator_headers, gpio=48, esp_id="ESP_NO_SENSOR_001"
        )

        dry_response = await client.post(
            f"/api/v1/calibration/sessions/{session_id}/points",
            headers=operator_headers,
            json={
                "raw_value": 910.0,
                "reference_value": 0.0,
                "point_role": "dry",
            },
        )
        assert dry_response.status_code == 200

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

        finalize_response = await client.post(
            f"/api/v1/calibration/sessions/{session_id}/finalize",
            headers=operator_headers,
        )
        assert finalize_response.status_code == 200

        apply_response = await client.post(
            f"/api/v1/calibration/sessions/{session_id}/apply",
            headers=operator_headers,
        )
        assert apply_response.status_code == 409
        assert apply_response.json()["detail"]["code"] == "APPLY_PERSISTENCE_REQUIRED"

        session_response = await client.get(
            f"/api/v1/calibration/sessions/{session_id}",
            headers=operator_headers,
        )
        assert session_response.status_code == 200
        assert session_response.json()["status"] == "failed"


@pytest.mark.asyncio
async def test_calibration_session_delete_point_flow(operator_headers: dict[str, str]):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        start_response = await client.post(
            "/api/v1/calibration/sessions",
            headers=operator_headers,
            json={
                "esp_id": "ESP_TEST_001",
                "gpio": 12,
                "sensor_type": "moisture",
                "method": "linear_2point",
                "expected_points": 2,
            },
        )
        session_id = start_response.json()["id"]

        dry_response = await client.post(
            f"/api/v1/calibration/sessions/{session_id}/points",
            headers=operator_headers,
            json={
                "raw_value": 930.0,
                "reference_value": 0.0,
                "point_role": "dry",
            },
        )
        assert dry_response.status_code == 200
        point_id = dry_response.json()["calibration_points"]["points"][0]["id"]

        delete_response = await client.delete(
            f"/api/v1/calibration/sessions/{session_id}/points/{point_id}",
            headers=operator_headers,
        )
        assert delete_response.status_code == 200
        assert delete_response.json()["status"] == "collecting"
        assert delete_response.json()["calibration_points"]["points"] == []


@pytest.mark.asyncio
async def test_calibration_session_requires_operator_role(
    operator_headers: dict[str, str], viewer_headers: dict[str, str]
):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        unauthorized = await client.post(
            "/api/v1/calibration/sessions",
            json={
                "esp_id": "ESP_TEST_001",
                "gpio": 13,
                "sensor_type": "moisture",
                "method": "linear_2point",
                "expected_points": 2,
            },
        )
        assert unauthorized.status_code == 401

        forbidden = await client.post(
            "/api/v1/calibration/sessions",
            headers=viewer_headers,
            json={
                "esp_id": "ESP_TEST_001",
                "gpio": 13,
                "sensor_type": "moisture",
                "method": "linear_2point",
                "expected_points": 2,
            },
        )
        assert forbidden.status_code == 403

        ok = await client.post(
            "/api/v1/calibration/sessions",
            headers=operator_headers,
            json={
                "esp_id": "ESP_TEST_001",
                "gpio": 13,
                "sensor_type": "moisture",
                "method": "linear_2point",
                "expected_points": 2,
            },
        )
        assert ok.status_code == 201


@pytest.mark.asyncio
async def test_calibration_session_points_parallel_same_role_conflict(
    operator_headers: dict[str, str],
):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        repetitions = 30
        distribution = Counter()
        for run in range(repetitions):
            session_id = await _start_session(
                client,
                operator_headers,
                gpio=21,
                esp_id=f"ESP_P7_BASE_{run:02d}",
            )
            payload_a = {
                "raw_value": 880.0,
                "reference_value": 0.0,
                "point_role": "dry",
                "overwrite": False,
            }
            payload_b = {
                "raw_value": 870.0,
                "reference_value": 1.0,
                "point_role": "dry",
                "overwrite": False,
            }

            response_a, response_b = await asyncio.gather(
                client.post(
                    f"/api/v1/calibration/sessions/{session_id}/points",
                    headers=operator_headers,
                    json=payload_a,
                ),
                client.post(
                    f"/api/v1/calibration/sessions/{session_id}/points",
                    headers=operator_headers,
                    json=payload_b,
                ),
            )
            distribution.update([response_a.status_code, response_b.status_code])

            statuses = sorted([response_a.status_code, response_b.status_code])
            assert statuses == [200, 409]

            conflict_response = response_a if response_a.status_code == 409 else response_b
            assert conflict_response.json()["detail"]["code"] == "ROLE_POINT_EXISTS"

            session_response = await client.get(
                f"/api/v1/calibration/sessions/{session_id}",
                headers=operator_headers,
            )
            assert session_response.status_code == 200
            assert session_response.json()["status"] == "collecting"
            points = session_response.json()["calibration_points"]["points"]
            assert len(points) == 1
            assert points[0]["point_role"] == "dry"

        assert distribution[200] == repetitions
        assert distribution[409] == repetitions
        assert distribution[500] == 0


@pytest.mark.asyncio
async def test_calibration_session_points_parallel_with_overwrite(operator_headers: dict[str, str]):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        repetitions = 30
        distribution = Counter()
        for run in range(repetitions):
            session_id = await _start_session(
                client,
                operator_headers,
                gpio=22,
                esp_id=f"ESP_P7_MIX_{run:02d}",
            )

            payload_no_overwrite = {
                "raw_value": 860.0,
                "reference_value": 0.0,
                "point_role": "dry",
                "overwrite": False,
            }
            payload_overwrite = {
                "raw_value": 850.0,
                "reference_value": 2.0,
                "point_role": "dry",
                "overwrite": True,
            }

            no_overwrite_response, overwrite_response = await asyncio.gather(
                client.post(
                    f"/api/v1/calibration/sessions/{session_id}/points",
                    headers=operator_headers,
                    json=payload_no_overwrite,
                ),
                client.post(
                    f"/api/v1/calibration/sessions/{session_id}/points",
                    headers=operator_headers,
                    json=payload_overwrite,
                ),
            )

            distribution.update([no_overwrite_response.status_code, overwrite_response.status_code])
            assert no_overwrite_response.status_code == 409
            assert overwrite_response.status_code == 200
            assert no_overwrite_response.json()["detail"]["code"] == "ROLE_POINT_EXISTS"

            session_response = await client.get(
                f"/api/v1/calibration/sessions/{session_id}",
                headers=operator_headers,
            )
            assert session_response.status_code == 200
            assert session_response.json()["status"] == "collecting"
            points = session_response.json()["calibration_points"]["points"]
            assert len(points) == 1
            assert points[0]["point_role"] == "dry"
            assert points[0]["raw"] == 850.0

        assert distribution[200] == repetitions
        assert distribution[409] == repetitions
        assert distribution[500] == 0


@pytest.mark.asyncio
async def test_calibration_session_points_parallel_both_overwrite_deterministic_contract(
    operator_headers: dict[str, str],
):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        repetitions = 30
        distribution = Counter()
        for run in range(repetitions):
            session_id = await _start_session(
                client,
                operator_headers,
                gpio=23,
                esp_id=f"ESP_P7_OVR_{run:02d}",
            )
            payload_a = {
                "raw_value": 840.0,
                "reference_value": 1.0,
                "point_role": "dry",
                "overwrite": True,
            }
            payload_b = {
                "raw_value": 830.0,
                "reference_value": 2.0,
                "point_role": "dry",
                "overwrite": True,
            }

            response_a, response_b = await asyncio.gather(
                client.post(
                    f"/api/v1/calibration/sessions/{session_id}/points",
                    headers=operator_headers,
                    json=payload_a,
                ),
                client.post(
                    f"/api/v1/calibration/sessions/{session_id}/points",
                    headers=operator_headers,
                    json=payload_b,
                ),
            )
            distribution.update([response_a.status_code, response_b.status_code])
            assert response_a.status_code == 200
            assert response_b.status_code == 200

            session_response = await client.get(
                f"/api/v1/calibration/sessions/{session_id}",
                headers=operator_headers,
            )
            assert session_response.status_code == 200
            assert session_response.json()["status"] == "collecting"
            points = session_response.json()["calibration_points"]["points"]
            assert len(points) == 1
            assert points[0]["point_role"] == "dry"
            assert points[0]["raw"] in {840.0, 830.0}

        assert distribution[200] == repetitions * 2
        assert distribution[409] == 0
        assert distribution[500] == 0


@pytest.mark.asyncio
async def test_calibration_session_points_parallel_dry_wet_independent(
    operator_headers: dict[str, str],
):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        session_id = await _start_session(client, operator_headers, gpio=23)

        dry_payload = {
            "raw_value": 900.0,
            "reference_value": 0.0,
            "point_role": "dry",
        }
        wet_payload = {
            "raw_value": 620.0,
            "reference_value": 100.0,
            "point_role": "wet",
        }

        dry_response, wet_response = await asyncio.gather(
            client.post(
                f"/api/v1/calibration/sessions/{session_id}/points",
                headers=operator_headers,
                json=dry_payload,
            ),
            client.post(
                f"/api/v1/calibration/sessions/{session_id}/points",
                headers=operator_headers,
                json=wet_payload,
            ),
        )

        assert dry_response.status_code == 200
        assert wet_response.status_code == 200

        session_response = await client.get(
            f"/api/v1/calibration/sessions/{session_id}",
            headers=operator_headers,
        )
        assert session_response.status_code == 200
        points = session_response.json()["calibration_points"]["points"]
        assert len(points) == 2
        roles = {point["point_role"] for point in points}
        assert roles == {"dry", "wet"}


@pytest.mark.asyncio
async def test_calibration_session_add_delete_parallel_consistency(
    operator_headers: dict[str, str],
):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        session_id = await _start_session(client, operator_headers, gpio=24)

        dry_response = await client.post(
            f"/api/v1/calibration/sessions/{session_id}/points",
            headers=operator_headers,
            json={
                "raw_value": 910.0,
                "reference_value": 0.0,
                "point_role": "dry",
            },
        )
        assert dry_response.status_code == 200
        dry_point_id = dry_response.json()["calibration_points"]["points"][0]["id"]

        delete_request = client.delete(
            f"/api/v1/calibration/sessions/{session_id}/points/{dry_point_id}",
            headers=operator_headers,
        )
        add_wet_request = client.post(
            f"/api/v1/calibration/sessions/{session_id}/points",
            headers=operator_headers,
            json={
                "raw_value": 640.0,
                "reference_value": 100.0,
                "point_role": "wet",
            },
        )

        delete_response, add_response = await asyncio.gather(delete_request, add_wet_request)
        assert delete_response.status_code == 200
        assert add_response.status_code == 200

        session_response = await client.get(
            f"/api/v1/calibration/sessions/{session_id}",
            headers=operator_headers,
        )
        assert session_response.status_code == 200
        points = session_response.json()["calibration_points"]["points"]
        assert len(points) == 1
        assert points[0]["point_role"] == "wet"


@pytest.mark.asyncio
async def test_calibration_session_points_same_role_short_soak(operator_headers: dict[str, str]):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        session_id = await _start_session(client, operator_headers, gpio=25)

        requests = [
            client.post(
                f"/api/v1/calibration/sessions/{session_id}/points",
                headers=operator_headers,
                json={
                    "raw_value": 820.0 + idx,
                    "reference_value": float(idx),
                    "point_role": "dry",
                    "overwrite": False,
                },
            )
            for idx in range(20)
        ]

        responses = await asyncio.gather(*requests)
        distribution = Counter(response.status_code for response in responses)

        assert distribution[200] == 1
        assert distribution[409] == 19
        assert distribution[500] == 0

        session_response = await client.get(
            f"/api/v1/calibration/sessions/{session_id}",
            headers=operator_headers,
        )
        assert session_response.status_code == 200
        points = session_response.json()["calibration_points"]["points"]
        assert len(points) == 1
        assert points[0]["point_role"] == "dry"
