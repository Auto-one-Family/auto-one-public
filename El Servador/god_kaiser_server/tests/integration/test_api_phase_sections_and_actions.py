"""Create/read path: phase sections + executed action on a marked range."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token, get_password_hash
from src.db.models.plant import Plant
from src.db.models.user import User
from src.db.models.zone import Zone
from src.db.models.zone_context import ZoneContext
from src.main import app


@pytest.fixture
async def operator_user(db_session: AsyncSession) -> User:
    user = User(
        username="phase_action_op",
        email="phase_action_op@example.com",
        password_hash=get_password_hash("OperatorP@ss123"),
        full_name="Phase Action Operator",
        role="operator",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def operator_headers(operator_user: User) -> dict:
    token = create_access_token(
        user_id=operator_user.id,
        additional_claims={"role": operator_user.role},
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def zoned_plant(db_session: AsyncSession) -> Plant:
    zone = Zone(zone_id="zone_phase_actions", name="Phase Action Zone")
    plant = Plant(
        plant_id=uuid.uuid4(),
        genotype_label="Phase Action Plant",
        planting_date=datetime(2026, 1, 1).date(),
        phase="veg-frueh",
        zone_id=zone.zone_id,
        qr_code=f"PL-{uuid.uuid4().hex[:8].upper()}",
        visibility="tenant_private",
    )
    db_session.add_all([zone, plant])
    await db_session.commit()
    await db_session.refresh(plant)
    return plant


@pytest.mark.asyncio
async def test_phase_change_syncs_zone_context_canonical_key(
    zoned_plant: Plant,
    operator_headers: dict,
    db_session: AsyncSession,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/api/v1/plants/{zoned_plant.plant_id}/lifecycle-event",
            json={"event_type": "phase_changed", "new_phase": "bluete-bulk"},
            headers=operator_headers,
        )
        assert response.status_code == 201

        ctx = await client.get(
            f"/api/v1/zone/context/{zoned_plant.zone_id}",
            headers=operator_headers,
        )
    assert ctx.status_code == 200
    body = ctx.json()
    assert body["growth_phase"] == "bluete-bulk"
    assert body["resolved_growth_phase"] == "bluete-bulk"
    assert body["growth_phase_source"] == "plant"
    assert body["active_plant_id"] == str(zoned_plant.plant_id)


@pytest.mark.asyncio
async def test_zone_context_maps_legacy_string_and_does_not_overwrite_plant(
    zoned_plant: Plant,
    operator_headers: dict,
    db_session: AsyncSession,
) -> None:
    db_session.add(
        ZoneContext(
            zone_id=zoned_plant.zone_id,
            zone_name="Phase Action Zone",
            growth_phase="flower_week_5",
        )
    )
    await db_session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        mapped = await client.put(
            f"/api/v1/zone/context/{zoned_plant.zone_id}",
            json={
                "zone_name": "Phase Action Zone",
                "growth_phase": "flower_week_5",
                "variety": "Wedding Cake",
            },
            headers=operator_headers,
        )
        plant = await client.get(
            f"/api/v1/plants/{zoned_plant.plant_id}",
            headers=operator_headers,
        )
    assert mapped.status_code == 200
    data = mapped.json()
    # Plant remains SSOT (veg-frueh); zone write must not move the plant.
    assert data["resolved_growth_phase"] == "veg-frueh"
    assert data["growth_phase"] == "veg-frueh"
    assert data["variety"] == "Wedding Cake"
    assert plant.json()["phase"] == "veg-frueh"


@pytest.mark.asyncio
async def test_executed_action_persists_on_phase_section(
    zoned_plant: Plant,
    operator_headers: dict,
) -> None:
    start = datetime(2026, 2, 1, 8, 0, tzinfo=timezone.utc)
    end = start + timedelta(hours=6)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        created = await client.post(
            f"/api/v1/plants/{zoned_plant.plant_id}/lifecycle-event",
            json={
                "event_type": "defoliation",
                "note": "Entlaubt unter Veg-Band",
                "event_status": "occurred",
                "event_timestamp": start.isoformat(),
                "linked_sensor_window_start": start.isoformat(),
                "linked_sensor_window_end": end.isoformat(),
            },
            headers=operator_headers,
        )
        assert created.status_code == 201
        event = created.json()
        assert event["event_type"] == "defoliation"
        assert event["event_status"] == "occurred"
        assert event["new_phase"] == "veg-frueh"
        assert event["zone_id"] == zoned_plant.zone_id
        assert event["linked_sensor_window_start"] is not None
        assert event["linked_sensor_window_end"] is not None

        sections = await client.get(
            f"/api/v1/plants/{zoned_plant.plant_id}/phase-sections",
            headers=operator_headers,
        )
    assert sections.status_code == 200
    payload = sections.json()
    assert payload["current_phase"] == "veg-frueh"
    assert payload["zone_id"] == zoned_plant.zone_id
    assert len(payload["sections"]) == 1
    section = payload["sections"][0]
    assert section["phase"] == "veg-frueh"
    assert len(section["actions"]) == 1
    assert section["actions"][0]["event_id"] == event["event_id"]
    assert section["actions"][0]["event_type"] == "defoliation"


@pytest.mark.asyncio
async def test_default_last_hour_window_stamps_current_phase_after_change(
    zoned_plant: Plant,
    operator_headers: dict,
) -> None:
    now = datetime.now(timezone.utc)
    first = now - timedelta(days=20)
    changed = now - timedelta(minutes=20)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        veg = await client.post(
            f"/api/v1/plants/{zoned_plant.plant_id}/lifecycle-event",
            json={
                "event_type": "phase_changed",
                "new_phase": "veg-frueh",
                "event_timestamp": first.isoformat(),
            },
            headers=operator_headers,
        )
        flower = await client.post(
            f"/api/v1/plants/{zoned_plant.plant_id}/lifecycle-event",
            json={
                "event_type": "phase_changed",
                "new_phase": "bluete-bulk",
                "event_timestamp": changed.isoformat(),
            },
            headers=operator_headers,
        )
        assert veg.status_code == 201
        assert flower.status_code == 201

        created = await client.post(
            f"/api/v1/plants/{zoned_plant.plant_id}/lifecycle-event",
            json={
                "event_type": "topping",
                "event_status": "occurred",
                "linked_sensor_window_start": (now - timedelta(hours=1)).isoformat(),
                "linked_sensor_window_end": now.isoformat(),
            },
            headers=operator_headers,
        )
    assert created.status_code == 201
    assert created.json()["new_phase"] == "bluete-bulk"


@pytest.mark.asyncio
async def test_action_window_outside_section_is_rejected(
    zoned_plant: Plant,
    operator_headers: dict,
) -> None:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(hours=2)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/api/v1/plants/{zoned_plant.plant_id}/lifecycle-event",
            json={
                "event_type": "topping",
                "event_status": "occurred",
                "linked_sensor_window_start": start.isoformat(),
                "linked_sensor_window_end": end.isoformat(),
            },
            headers=operator_headers,
        )
    assert response.status_code == 422
    assert "phase section" in response.json()["detail"]
