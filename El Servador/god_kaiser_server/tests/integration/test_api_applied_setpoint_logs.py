"""
Integration Tests: Applied Setpoint Log Read API (AUT-1236 T6 precondition)

GET /api/v1/applied-setpoint-logs — read-only, filtered by zone/domain/measure/window.
Muster: test_api_plan_segments.py
"""

from datetime import datetime, timedelta, timezone
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token, get_password_hash
from src.db.models.applied_setpoint_log import AppliedSetpointLog
from src.db.models.user import User
from src.db.models.zone import Zone
from src.main import app


@pytest.fixture
async def operator_user(db_session: AsyncSession):
    user = User(
        username="asl_operator",
        email="asl_op@example.com",
        password_hash=get_password_hash("OperatorP@ss123"),
        full_name="ASL Operator",
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
    zone = Zone(zone_id="zelt_asl_api", name="Zelt ASL API")
    db_session.add(zone)
    await db_session.commit()
    await db_session.refresh(zone)
    return zone


class TestListAppliedSetpointLogs:
    """Test GET /api/v1/applied-setpoint-logs"""

    @pytest.mark.asyncio
    async def test_list_filtered_by_zone_domain_measure_and_window(
        self, auth_headers: dict, sample_zone: Zone, db_session: AsyncSession
    ):
        other = Zone(zone_id="other_asl_api", name="Other ASL API")
        db_session.add(other)
        await db_session.commit()

        t0 = datetime(2026, 7, 10, 12, 0, 0, tzinfo=timezone.utc)
        matching = AppliedSetpointLog(
            id=uuid.uuid4(),
            zone_id=sample_zone.zone_id,
            domain="nutrient_solution",
            measure="target_ec",
            applied_value=2.0,
            effective_at=t0,
            origin="plan_segment",
        )
        outside_window = AppliedSetpointLog(
            id=uuid.uuid4(),
            zone_id=sample_zone.zone_id,
            domain="nutrient_solution",
            measure="target_ec",
            applied_value=2.5,
            effective_at=t0 + timedelta(days=20),
            origin="static_fallback",
        )
        other_zone = AppliedSetpointLog(
            id=uuid.uuid4(),
            zone_id=other.zone_id,
            domain="nutrient_solution",
            measure="target_ec",
            applied_value=1.5,
            effective_at=t0,
            origin="plan_segment",
        )
        db_session.add_all([matching, outside_window, other_zone])
        await db_session.commit()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(
                "/api/v1/applied-setpoint-logs",
                params={
                    "zone_id": sample_zone.zone_id,
                    "domain": "nutrient_solution",
                    "measure": "target_ec",
                    "from_ts": "2026-07-01T00:00:00+00:00",
                    "to_ts": "2026-07-15T00:00:00+00:00",
                },
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["applied_value"] == 2.0
        assert data[0]["origin"] == "plan_segment"
        assert data[0]["zone_id"] == sample_zone.zone_id

    @pytest.mark.asyncio
    async def test_list_empty_without_rows(self, auth_headers: dict, sample_zone: Zone):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(
                "/api/v1/applied-setpoint-logs",
                params={"zone_id": sample_zone.zone_id},
                headers=auth_headers,
            )

        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_list_requires_auth(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/v1/applied-setpoint-logs")
        assert response.status_code in (401, 403)
