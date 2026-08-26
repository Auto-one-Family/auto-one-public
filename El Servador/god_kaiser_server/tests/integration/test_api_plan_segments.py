"""
Integration Tests: Plan Segment CRUD API (AUT-1232 Lücke / AUT-1235 precondition)

Tests: POST create + GET filtered list (zone/domain/measure/window).
Muster: test_api_zones_crud.py
"""

from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token, get_password_hash
from src.db.models.user import User
from src.db.models.zone import Zone
from src.main import app


@pytest.fixture
async def operator_user(db_session: AsyncSession):
    user = User(
        username="plan_seg_operator",
        email="plan_seg_op@example.com",
        password_hash=get_password_hash("OperatorP@ss123"),
        full_name="Plan Segment Operator",
        role="operator",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers(operator_user: User):
    token = create_access_token(
        user_id=operator_user.id, additional_claims={"role": operator_user.role}
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def sample_zone(db_session: AsyncSession):
    zone = Zone(zone_id="zelt_plan_api", name="Zelt Plan API")
    db_session.add(zone)
    await db_session.commit()
    await db_session.refresh(zone)
    return zone


class TestCreatePlanSegment:
    """Test POST /api/v1/plan-segments"""

    @pytest.mark.asyncio
    async def test_create_plan_segment_success(
        self, auth_headers: dict, sample_zone: Zone
    ):
        payload = {
            "zone_id": sample_zone.zone_id,
            "domain": "nutrient_solution",
            "measure": "target_ec",
            "value": 1.8,
            "from_ts": "2026-07-01T00:00:00+00:00",
            "to_ts": "2026-07-15T00:00:00+00:00",
            "interp": "step",
            "status": "planned",
        }
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/plan-segments",
                json=payload,
                headers=auth_headers,
            )

        assert response.status_code == 201
        data = response.json()
        assert data["zone_id"] == sample_zone.zone_id
        assert data["domain"] == "nutrient_solution"
        assert data["measure"] == "target_ec"
        assert data["value"] == 1.8
        assert data["interp"] == "step"
        assert data["status"] == "planned"
        assert "id" in data
        assert "created_at" in data
        assert "updated_at" in data


class TestListPlanSegmentsFiltered:
    """Test GET /api/v1/plan-segments with filters"""

    @pytest.mark.asyncio
    async def test_list_filtered_by_zone_domain_measure_and_window(
        self, auth_headers: dict, sample_zone: Zone, db_session: AsyncSession
    ):
        other = Zone(zone_id="other_plan_api", name="Other Plan API")
        db_session.add(other)
        await db_session.commit()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # Matching segment (in window)
            r1 = await client.post(
                "/api/v1/plan-segments",
                json={
                    "zone_id": sample_zone.zone_id,
                    "domain": "nutrient_solution",
                    "measure": "target_ec",
                    "value": 1.8,
                    "from_ts": "2026-07-01T00:00:00+00:00",
                    "to_ts": "2026-07-15T00:00:00+00:00",
                    "interp": "step",
                    "status": "active",
                },
                headers=auth_headers,
            )
            assert r1.status_code == 201
            match_id = r1.json()["id"]

            # Wrong measure — must not appear in filtered list
            r2 = await client.post(
                "/api/v1/plan-segments",
                json={
                    "zone_id": sample_zone.zone_id,
                    "domain": "nutrient_solution",
                    "measure": "target_ph",
                    "value": 6.0,
                    "from_ts": "2026-07-01T00:00:00+00:00",
                    "to_ts": "2026-07-15T00:00:00+00:00",
                    "interp": "step",
                    "status": "planned",
                },
                headers=auth_headers,
            )
            assert r2.status_code == 201

            # Outside window — must not appear
            r3 = await client.post(
                "/api/v1/plan-segments",
                json={
                    "zone_id": sample_zone.zone_id,
                    "domain": "nutrient_solution",
                    "measure": "target_ec",
                    "value": 2.2,
                    "from_ts": "2026-08-01T00:00:00+00:00",
                    "to_ts": "2026-08-15T00:00:00+00:00",
                    "interp": "step",
                    "status": "planned",
                },
                headers=auth_headers,
            )
            assert r3.status_code == 201

            # Other zone — must not appear
            r4 = await client.post(
                "/api/v1/plan-segments",
                json={
                    "zone_id": other.zone_id,
                    "domain": "nutrient_solution",
                    "measure": "target_ec",
                    "value": 1.5,
                    "from_ts": "2026-07-01T00:00:00+00:00",
                    "to_ts": "2026-07-15T00:00:00+00:00",
                    "interp": "step",
                    "status": "planned",
                },
                headers=auth_headers,
            )
            assert r4.status_code == 201

            response = await client.get(
                "/api/v1/plan-segments",
                params={
                    "zone_id": sample_zone.zone_id,
                    "domain": "nutrient_solution",
                    "measure": "target_ec",
                    "from_ts": datetime(2026, 7, 1, tzinfo=timezone.utc).isoformat(),
                    "to_ts": datetime(2026, 7, 20, tzinfo=timezone.utc).isoformat(),
                },
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == match_id
        assert data[0]["value"] == 1.8


class TestClimatePlanSegmentsAut1239:
    """AUT-1239: climate write path + derived VPD band (same table/endpoint)."""

    @pytest.mark.asyncio
    async def test_create_climate_temperature_and_humidity_segments(
        self, auth_headers: dict, sample_zone: Zone
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r_temp = await client.post(
                "/api/v1/plan-segments",
                json={
                    "zone_id": sample_zone.zone_id,
                    "domain": "climate",
                    "measure": "target_temperature",
                    "value": 24.0,
                    "from_ts": "2026-07-01T00:00:00+00:00",
                    "to_ts": "2026-07-15T00:00:00+00:00",
                    "interp": "step",
                    "status": "active",
                },
                headers=auth_headers,
            )
            r_hum = await client.post(
                "/api/v1/plan-segments",
                json={
                    "zone_id": sample_zone.zone_id,
                    "domain": "climate",
                    "measure": "target_humidity",
                    "value": 60.0,
                    "from_ts": "2026-07-01T00:00:00+00:00",
                    "to_ts": "2026-07-15T00:00:00+00:00",
                    "interp": "step",
                    "status": "active",
                },
                headers=auth_headers,
            )

        assert r_temp.status_code == 201
        assert r_hum.status_code == 201
        assert r_temp.json()["domain"] == "climate"
        assert r_temp.json()["measure"] == "target_temperature"
        assert r_hum.json()["measure"] == "target_humidity"
        # No invented defaults — operator values round-trip as sent
        assert r_temp.json()["value"] == 24.0
        assert r_hum.json()["value"] == 60.0

    @pytest.mark.asyncio
    async def test_climate_at_derives_vpd_band_from_planned_targets(
        self, auth_headers: dict, sample_zone: Zone
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post(
                "/api/v1/plan-segments",
                json={
                    "zone_id": sample_zone.zone_id,
                    "domain": "climate",
                    "measure": "target_temperature",
                    "value": 24.0,
                    "from_ts": "2026-07-01T00:00:00+00:00",
                    "to_ts": "2026-07-15T00:00:00+00:00",
                    "interp": "step",
                    "status": "active",
                },
                headers=auth_headers,
            )
            await client.post(
                "/api/v1/plan-segments",
                json={
                    "zone_id": sample_zone.zone_id,
                    "domain": "climate",
                    "measure": "target_humidity",
                    "value": 60.0,
                    "from_ts": "2026-07-01T00:00:00+00:00",
                    "to_ts": "2026-07-15T00:00:00+00:00",
                    "interp": "step",
                    "status": "active",
                },
                headers=auth_headers,
            )

            response = await client.get(
                "/api/v1/plan-segments/climate-at",
                params={
                    "zone_id": sample_zone.zone_id,
                    "at": "2026-07-10T12:00:00+00:00",
                },
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["domain"] == "climate"
        assert data["zone_id"] == sample_zone.zone_id
        by_measure = {t["measure"]: t for t in data["targets"]}
        assert by_measure["target_temperature"]["value"] == 24.0
        assert by_measure["target_humidity"]["value"] == 60.0
        assert data["vpd_band"]["computable"] is True
        assert data["vpd_band"]["source"] == "planned_targets"
        assert data["vpd_band"]["vpd_kpa"] is not None
        assert data["vpd_band"]["vpd_min_kpa"] == data["vpd_band"]["vpd_kpa"]
        assert data["vpd_band"]["vpd_max_kpa"] == data["vpd_band"]["vpd_kpa"]
        # VPD must not appear as a stored measure in targets
        assert "target_vpd" not in by_measure
        assert all(t["measure"] != "vpd" for t in data["targets"])

    @pytest.mark.asyncio
    async def test_climate_at_missing_humidity_not_silent(
        self, auth_headers: dict, sample_zone: Zone
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post(
                "/api/v1/plan-segments",
                json={
                    "zone_id": sample_zone.zone_id,
                    "domain": "climate",
                    "measure": "target_temperature",
                    "value": 24.0,
                    "from_ts": "2026-07-01T00:00:00+00:00",
                    "to_ts": "2026-07-15T00:00:00+00:00",
                    "interp": "step",
                    "status": "active",
                },
                headers=auth_headers,
            )

            response = await client.get(
                "/api/v1/plan-segments/climate-at",
                params={
                    "zone_id": sample_zone.zone_id,
                    "at": "2026-07-10T12:00:00+00:00",
                },
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["vpd_band"]["computable"] is False
        assert data["vpd_band"]["reason"] == "missing_target_humidity"
        assert data["vpd_band"]["vpd_kpa"] is None
