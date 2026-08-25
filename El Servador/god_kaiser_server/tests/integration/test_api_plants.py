"""
Integration Tests: Plant Lifecycle Events API (AUT-1098) and Zone Summary
(AUT-1194 - two-axis phase histogram).

Covers:
- GET /v1/plants/{plant_id}/lifecycle-events (Stufe 1)
  - ActiveUser can list events
  - Events are sorted ASC by event_timestamp (oldest first)
  - 401 for unauthenticated requests
  - 404 for unknown plant_id
  - Soft-deleted plants: audit trail still accessible

- POST /v1/plants/{plant_id}/lifecycle-event (Stufe 2 role guard)
  - Viewer (role=viewer) can post note_added -> 201
  - Viewer posting phase_changed -> 403
  - Viewer posting any other event type -> 403
  - Operator can post any event type (phase_changed, transplanted) -> 201

- AUT-1183: Two independent phase axes (nutrient_phase_changed event)

- AUT-1205: Current plant phase follows event chronology, not insert order
  - Backdated phase_changed / nutrient_phase_changed is stored but does not
    overwrite a chronologically newer current state
  - Forward (newest) transitions still update Plant.phase / nutrient_phase

- GET /v1/plants/zone-summary/{zone_id} (AUT-1194)
  - Response carries both light/growth axis (``phases``) and nutrient axis
    (``nutrient_phase_histogram``) - axis identity visible from field name.
  - Empty zone returns zero counts and empty histograms.
  - Plants with nutrient_phase=NULL are excluded from nutrient histogram.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token, get_password_hash
from src.db.models.plant import Plant, PlantLifecycleEvent
from src.db.models.subzone import SubzoneConfig
from src.db.models.user import User
from src.db.models.zone import Zone
from src.main import app

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
async def operator_user(db_session: AsyncSession) -> User:
    """Operator user for auth (can post all event types)."""
    user = User(
        username="plants_operator",
        email="plants_op@example.com",
        password_hash=get_password_hash("OperatorP@ss123"),
        full_name="Plants Operator",
        role="operator",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def viewer_user(db_session: AsyncSession) -> User:
    """Viewer user for auth (can only post note_added)."""
    user = User(
        username="plants_viewer",
        email="plants_viewer@example.com",
        password_hash=get_password_hash("ViewerP@ss123"),
        full_name="Plants Viewer",
        role="viewer",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def operator_headers(operator_user: User) -> dict:
    """Authorization headers for operator."""
    token = create_access_token(
        user_id=operator_user.id,
        additional_claims={"role": operator_user.role},
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def viewer_headers(viewer_user: User) -> dict:
    """Authorization headers for viewer."""
    token = create_access_token(
        user_id=viewer_user.id,
        additional_claims={"role": viewer_user.role},
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def sample_plant(db_session: AsyncSession) -> Plant:
    """A basic active plant with a valid phase from PLANT_PHASES."""
    plant = Plant(
        plant_id=uuid.uuid4(),
        genotype_label="Test Genotype",
        planting_date=datetime(2026, 1, 1).date(),
        phase="veg-frueh",
        qr_code=f"PL-{uuid.uuid4().hex[:8].upper()}",
        visibility="tenant_private",
    )
    db_session.add(plant)
    await db_session.commit()
    await db_session.refresh(plant)
    return plant


@pytest.fixture
async def plant_with_events(
    db_session: AsyncSession,
    sample_plant: Plant,
    operator_user: User,
) -> Plant:
    """Plant with 3 lifecycle events in defined chronological order."""
    now = datetime.now(timezone.utc)

    events = [
        PlantLifecycleEvent(
            plant_id=sample_plant.plant_id,
            event_type="transplanted",
            event_timestamp=now.replace(microsecond=0),
            created_by_user=operator_user.id,
            created_at=now,
        ),
        PlantLifecycleEvent(
            plant_id=sample_plant.plant_id,
            event_type="phase_changed",
            event_timestamp=now.replace(microsecond=1000),
            previous_phase="veg-frueh",
            new_phase="bluete-bulk",
            created_by_user=operator_user.id,
            created_at=now,
        ),
        PlantLifecycleEvent(
            plant_id=sample_plant.plant_id,
            event_type="note_added",
            event_timestamp=now.replace(microsecond=2000),
            notes="Looking healthy",
            created_by_user=operator_user.id,
            created_at=now,
        ),
    ]
    for event in events:
        db_session.add(event)
    await db_session.commit()
    return sample_plant


# =============================================================================
# AUT-1252: Plant location fields
# =============================================================================


class TestPlantLocationResponse:
    """Plant response resolves human-readable subzone and zone location fields."""

    @pytest.fixture
    async def plant_with_subzone_and_zone(self, db_session: AsyncSession) -> Plant:
        zone = Zone(zone_id="zone_location", name="Location Zone")
        subzone = SubzoneConfig(
            id=uuid.uuid4(),
            esp_id="ESP_PLANT_LOCATION",
            subzone_id="subzone_location",
            subzone_name="Propagation Bench",
            parent_zone_id=zone.zone_id,
            assigned_gpios=[],
            assigned_sensor_config_ids=[],
            is_active=True,
        )
        plant = Plant(
            plant_id=uuid.uuid4(),
            genotype_label="Location Plant",
            planting_date=datetime(2026, 1, 1).date(),
            phase="veg-frueh",
            subzone_id=subzone.id,
            qr_code=f"PL-{uuid.uuid4().hex[:8].upper()}",
            visibility="tenant_private",
        )
        db_session.add_all([zone, subzone, plant])
        await db_session.commit()
        return plant

    @pytest.fixture
    async def plant_with_zoneless_subzone(self, db_session: AsyncSession) -> Plant:
        subzone = SubzoneConfig(
            id=uuid.uuid4(),
            esp_id="ESP_PLANT_ZONELESS",
            subzone_id="subzone_zoneless",
            subzone_name="Staging Bench",
            parent_zone_id=None,
            assigned_gpios=[],
            assigned_sensor_config_ids=[],
            is_active=True,
        )
        plant = Plant(
            plant_id=uuid.uuid4(),
            genotype_label="Zoneless Plant",
            planting_date=datetime(2026, 1, 1).date(),
            phase="veg-frueh",
            subzone_id=subzone.id,
            qr_code=f"PL-{uuid.uuid4().hex[:8].upper()}",
            visibility="tenant_private",
        )
        db_session.add_all([subzone, plant])
        await db_session.commit()
        return plant

    @pytest.mark.asyncio
    async def test_list_and_get_plant_include_resolved_location(
        self,
        plant_with_subzone_and_zone: Plant,
        operator_headers: dict,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            list_response = await client.get(
                "/api/v1/plants",
                headers=operator_headers,
            )
            get_response = await client.get(
                f"/api/v1/plants/{plant_with_subzone_and_zone.plant_id}",
                headers=operator_headers,
            )

        assert list_response.status_code == 200
        list_plant = next(
            plant
            for plant in list_response.json()["plants"]
            if plant["plant_id"] == str(plant_with_subzone_and_zone.plant_id)
        )
        assert list_plant["subzone_name"] == "Propagation Bench"
        assert list_plant["parent_zone_id"] == "zone_location"
        assert list_plant["zone_name"] == "Location Zone"

        assert get_response.status_code == 200
        assert get_response.json()["subzone_name"] == "Propagation Bench"
        assert get_response.json()["parent_zone_id"] == "zone_location"
        assert get_response.json()["zone_name"] == "Location Zone"

    @pytest.mark.asyncio
    async def test_plant_without_subzone_returns_null_location_fields(
        self,
        sample_plant: Plant,
        operator_headers: dict,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/plants/{sample_plant.plant_id}",
                headers=operator_headers,
            )

        assert response.status_code == 200
        assert response.json()["subzone_name"] is None
        assert response.json()["parent_zone_id"] is None
        assert response.json()["zone_name"] is None

    @pytest.mark.asyncio
    async def test_plant_with_zoneless_subzone_returns_partial_location(
        self,
        plant_with_zoneless_subzone: Plant,
        operator_headers: dict,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/plants/{plant_with_zoneless_subzone.plant_id}",
                headers=operator_headers,
            )

        assert response.status_code == 200
        assert response.json()["subzone_name"] == "Staging Bench"
        assert response.json()["parent_zone_id"] is None
        assert response.json()["zone_name"] is None
        assert response.json()["zone_id"] is None

    @pytest.mark.asyncio
    async def test_list_and_get_plant_exposes_derived_parent_zone(
        self,
        plant_with_subzone_and_zone: Plant,
        operator_headers: dict,
    ):
        """AUT-1073: parent_zone_id is effective; zone_id is stored direct (null here)."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/plants/{plant_with_subzone_and_zone.plant_id}",
                headers=operator_headers,
            )

        assert response.status_code == 200
        body = response.json()
        assert body["parent_zone_id"] == "zone_location"
        assert body["zone_id"] is None
        assert body["subzone_name"] == "Propagation Bench"


# =============================================================================
# Stufe 1: GET /v1/plants/{plant_id}/lifecycle-events
# =============================================================================


class TestListLifecycleEvents:
    """Tests for GET /api/v1/plants/{plant_id}/lifecycle-events."""

    @pytest.mark.asyncio
    async def test_active_user_can_list_events(
        self,
        plant_with_events: Plant,
        operator_headers: dict,
    ):
        """ActiveUser (operator) can fetch lifecycle events and receives 200."""
        plant_id = plant_with_events.plant_id
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/plants/{plant_id}/lifecycle-events",
                headers=operator_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["plant_id"] == str(plant_id)
        assert data["total"] == 3
        assert len(data["events"]) == 3

    @pytest.mark.asyncio
    async def test_viewer_can_list_events(
        self,
        plant_with_events: Plant,
        viewer_headers: dict,
    ):
        """Viewer role (ActiveUser) can also fetch lifecycle events."""
        plant_id = plant_with_events.plant_id
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/plants/{plant_id}/lifecycle-events",
                headers=viewer_headers,
            )

        assert response.status_code == 200
        assert response.json()["total"] == 3

    @pytest.mark.asyncio
    async def test_events_sorted_chronologically_asc(
        self,
        plant_with_events: Plant,
        operator_headers: dict,
    ):
        """Events are returned oldest-first (event_timestamp ASC)."""
        plant_id = plant_with_events.plant_id
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/plants/{plant_id}/lifecycle-events",
                headers=operator_headers,
            )

        events = response.json()["events"]
        assert events[0]["event_type"] == "transplanted"
        assert events[1]["event_type"] == "phase_changed"
        assert events[2]["event_type"] == "note_added"

        # Verify ascending timestamp order
        timestamps = [e["event_timestamp"] for e in events]
        assert timestamps == sorted(timestamps)

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, sample_plant: Plant):
        """Request without token is rejected with 401."""
        plant_id = sample_plant.plant_id
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(f"/api/v1/plants/{plant_id}/lifecycle-events")

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_unknown_plant_returns_404(self, operator_headers: dict):
        """Unknown plant_id returns 404."""
        unknown_id = uuid.uuid4()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/plants/{unknown_id}/lifecycle-events",
                headers=operator_headers,
            )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_empty_list_for_plant_without_events(
        self,
        sample_plant: Plant,
        operator_headers: dict,
    ):
        """Plant with no events returns empty list with total=0."""
        plant_id = sample_plant.plant_id
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/plants/{plant_id}/lifecycle-events",
                headers=operator_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["events"] == []

    @pytest.mark.asyncio
    async def test_soft_deleted_plant_events_still_accessible(
        self,
        db_session: AsyncSession,
        plant_with_events: Plant,
        operator_headers: dict,
    ):
        """Soft-deleted plant audit trail remains accessible."""
        plant = plant_with_events
        plant.deleted_at = datetime.now(timezone.utc)
        plant.deleted_by = 1
        await db_session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/plants/{plant.plant_id}/lifecycle-events",
                headers=operator_headers,
            )

        assert response.status_code == 200
        assert response.json()["total"] == 3


# =============================================================================
# Stufe 2: POST role guard — viewer only note_added
# =============================================================================


class TestAddLifecycleEventRoleGuard:
    """Tests for POST /api/v1/plants/{plant_id}/lifecycle-event role guard."""

    @pytest.mark.asyncio
    async def test_viewer_can_post_note_added(
        self,
        sample_plant: Plant,
        viewer_headers: dict,
    ):
        """Viewer can post note_added event -> 201."""
        plant_id = sample_plant.plant_id
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/plants/{plant_id}/lifecycle-event",
                json={"event_type": "note_added", "note": "Sieht gut aus"},
                headers=viewer_headers,
            )

        assert response.status_code == 201
        data = response.json()
        assert data["event_type"] == "note_added"
        assert data["plant_id"] == str(plant_id)

    @pytest.mark.asyncio
    async def test_viewer_cannot_post_phase_changed(
        self,
        sample_plant: Plant,
        viewer_headers: dict,
    ):
        """Viewer posting phase_changed is rejected with 403."""
        plant_id = sample_plant.plant_id
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/plants/{plant_id}/lifecycle-event",
                json={"event_type": "phase_changed", "new_phase": "bluete-bulk"},
                headers=viewer_headers,
            )

        assert response.status_code == 403
        assert "operator or admin role" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_viewer_cannot_post_transplanted(
        self,
        sample_plant: Plant,
        viewer_headers: dict,
    ):
        """Viewer posting transplanted (structural event) is rejected with 403."""
        plant_id = sample_plant.plant_id
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/plants/{plant_id}/lifecycle-event",
                json={"event_type": "transplanted"},
                headers=viewer_headers,
            )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_operator_can_post_phase_changed(
        self,
        sample_plant: Plant,
        operator_headers: dict,
        operator_user: User,
    ):
        """Operator can post phase_changed -> 201 and plant phase is updated."""
        plant_id = sample_plant.plant_id
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/plants/{plant_id}/lifecycle-event",
                json={
                    "event_type": "phase_changed",
                    "new_phase": "bluete-bulk",
                },
                headers=operator_headers,
            )

        assert response.status_code == 201
        data = response.json()
        assert data["event_type"] == "phase_changed"
        assert data["new_phase"] == "bluete-bulk"
        assert data["previous_phase"] == "veg-frueh"

    @pytest.mark.asyncio
    async def test_operator_can_post_all_event_types(
        self,
        sample_plant: Plant,
        operator_headers: dict,
    ):
        """Operator can post any event type in LIFECYCLE_EVENT_TYPES."""
        plant_id = sample_plant.plant_id
        # Test a representative non-phase event (no phase semantics)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/plants/{plant_id}/lifecycle-event",
                json={"event_type": "defoliation", "note": "Light defoliation"},
                headers=operator_headers,
            )

        assert response.status_code == 201
        assert response.json()["event_type"] == "defoliation"

    @pytest.mark.asyncio
    async def test_unauthenticated_post_returns_401(self, sample_plant: Plant):
        """Unauthenticated POST is rejected with 401."""
        plant_id = sample_plant.plant_id
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/plants/{plant_id}/lifecycle-event",
                json={"event_type": "note_added", "note": "no auth"},
            )

        assert response.status_code == 401


# =============================================================================
# AUT-1183: Two independent phase axes (nutrient_phase_changed event)
# =============================================================================


class TestNutrientPhaseAxis:
    """
    AUT-1183: Tests for the second independent phase axis.

    Validates that light/growth phase (``phase_changed``) and
    nutrient/fertilizer phase (``nutrient_phase_changed``) are fully
    independent — two events on the same day must not overwrite each other.
    """

    @pytest.mark.asyncio
    async def test_nutrient_phase_changed_sets_nutrient_phase(
        self,
        sample_plant: Plant,
        operator_headers: dict,
        db_session: AsyncSession,
    ):
        """
        ``nutrient_phase_changed`` event updates plants.nutrient_phase
        and leaves plants.phase untouched.
        """
        plant_id = sample_plant.plant_id
        original_phase = sample_plant.phase  # "veg-frueh"

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/plants/{plant_id}/lifecycle-event",
                json={
                    "event_type": "nutrient_phase_changed",
                    "new_phase": "bluete-stretch",
                },
                headers=operator_headers,
            )

        assert response.status_code == 201
        data = response.json()
        assert data["event_type"] == "nutrient_phase_changed"
        assert data["new_phase"] == "bluete-stretch"
        # previous_phase should be None (nutrient axis was unset before)
        assert data["previous_phase"] is None

        # Verify via GET that nutrient_phase was set but phase is unchanged
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            plant_response = await client.get(
                f"/api/v1/plants/{plant_id}",
                headers=operator_headers,
            )

        plant_data = plant_response.json()
        assert plant_data["nutrient_phase"] == "bluete-stretch"
        assert (
            plant_data["phase"] == original_phase
        ), "light/growth phase must not change when nutrient_phase_changed is posted"

    @pytest.mark.asyncio
    async def test_two_axis_events_same_day_do_not_overwrite(
        self,
        sample_plant: Plant,
        operator_headers: dict,
    ):
        """
        A ``phase_changed`` and a ``nutrient_phase_changed`` event posted
        on the same day each land in their own column without overwriting
        each other — the core AUT-1183 requirement.
        """
        plant_id = sample_plant.plant_id

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Event 1: change light/growth phase
            r1 = await client.post(
                f"/api/v1/plants/{plant_id}/lifecycle-event",
                json={"event_type": "phase_changed", "new_phase": "bluete-bulk"},
                headers=operator_headers,
            )
            assert r1.status_code == 201

            # Event 2: change nutrient phase independently
            r2 = await client.post(
                f"/api/v1/plants/{plant_id}/lifecycle-event",
                json={
                    "event_type": "nutrient_phase_changed",
                    "new_phase": "veg-spaet",
                },
                headers=operator_headers,
            )
            assert r2.status_code == 201

            # Verify both axes are set correctly
            plant_response = await client.get(
                f"/api/v1/plants/{plant_id}",
                headers=operator_headers,
            )

        plant_data = plant_response.json()
        assert (
            plant_data["phase"] == "bluete-bulk"
        ), "light/growth phase must reflect phase_changed event"
        assert (
            plant_data["nutrient_phase"] == "veg-spaet"
        ), "nutrient phase must reflect nutrient_phase_changed event independently"

    @pytest.mark.asyncio
    async def test_nutrient_phase_changed_without_new_phase_returns_400(
        self,
        sample_plant: Plant,
        operator_headers: dict,
    ):
        """``nutrient_phase_changed`` without ``new_phase`` is rejected with 400."""
        plant_id = sample_plant.plant_id
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/plants/{plant_id}/lifecycle-event",
                json={"event_type": "nutrient_phase_changed"},
                headers=operator_headers,
            )

        assert response.status_code == 400
        assert "nutrient_phase_changed requires 'new_phase'" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_plant_with_nutrient_phase(
        self,
        operator_headers: dict,
    ):
        """Plant can be created with both axes set from the start."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/plants",
                json={
                    "genotype_label": "NutrientAxisTest",
                    "planting_date": "2026-01-15",
                    "phase": "veg-frueh",
                    "nutrient_phase": "clone",
                },
                headers=operator_headers,
            )

        assert response.status_code == 201
        data = response.json()
        assert data["phase"] == "veg-frueh"
        assert data["nutrient_phase"] == "clone"

    @pytest.mark.asyncio
    async def test_nutrient_phase_defaults_to_null_on_create(
        self,
        operator_headers: dict,
    ):
        """Plants created without nutrient_phase have nutrient_phase=None."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/plants",
                json={
                    "genotype_label": "NoNutrientPhase",
                    "planting_date": "2026-01-15",
                    "phase": "clone",
                },
                headers=operator_headers,
            )

        assert response.status_code == 201
        assert response.json()["nutrient_phase"] is None

    @pytest.mark.asyncio
    async def test_nutrient_phase_records_previous_phase_correctly(
        self,
        sample_plant: Plant,
        operator_headers: dict,
        db_session: AsyncSession,
    ):
        """
        Second ``nutrient_phase_changed`` event captures the prior nutrient
        phase in ``previous_phase`` on the event row.
        """
        plant_id = sample_plant.plant_id

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # First nutrient phase transition
            await client.post(
                f"/api/v1/plants/{plant_id}/lifecycle-event",
                json={"event_type": "nutrient_phase_changed", "new_phase": "veg-frueh"},
                headers=operator_headers,
            )
            # Second nutrient phase transition — previous_phase should be "veg-frueh"
            r2 = await client.post(
                f"/api/v1/plants/{plant_id}/lifecycle-event",
                json={
                    "event_type": "nutrient_phase_changed",
                    "new_phase": "bluete-stretch",
                },
                headers=operator_headers,
            )

        assert r2.status_code == 201
        data = r2.json()
        assert data["previous_phase"] == "veg-frueh"
        assert data["new_phase"] == "bluete-stretch"

    @pytest.mark.asyncio
    async def test_viewer_cannot_post_nutrient_phase_changed(
        self,
        sample_plant: Plant,
        viewer_headers: dict,
    ):
        """Viewer posting nutrient_phase_changed is rejected with 403."""
        plant_id = sample_plant.plant_id
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/plants/{plant_id}/lifecycle-event",
                json={
                    "event_type": "nutrient_phase_changed",
                    "new_phase": "bluete-bulk",
                },
                headers=viewer_headers,
            )

        assert response.status_code == 403
        assert "operator or admin role" in response.json()["detail"]


# =============================================================================
# AUT-1205: Current phase follows chronology, not insert order
# =============================================================================


class TestPhaseChronologyDerivation:
    """
    AUT-1205: a backdated phase event must be stored in full but must not
    overwrite a chronologically newer current state on the same axis.
    """

    @pytest.mark.asyncio
    async def test_backdated_phase_changed_does_not_overwrite_current(
        self,
        sample_plant: Plant,
        operator_headers: dict,
    ):
        """
        Given a plant already on bluete-stretch (newer transition recorded),
        When a backdated phase_changed to clone is posted,
        Then the event is stored and Plant.phase remains bluete-stretch.
        """
        plant_id = sample_plant.plant_id
        now = datetime.now(timezone.utc)
        newer_ts = (now - timedelta(days=5)).isoformat().replace("+00:00", "Z")
        older_ts = (now - timedelta(days=20)).isoformat().replace("+00:00", "Z")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r_newer = await client.post(
                f"/api/v1/plants/{plant_id}/lifecycle-event",
                json={
                    "event_type": "phase_changed",
                    "new_phase": "bluete-stretch",
                    "event_timestamp": newer_ts,
                },
                headers=operator_headers,
            )
            assert r_newer.status_code == 201

            r_backdated = await client.post(
                f"/api/v1/plants/{plant_id}/lifecycle-event",
                json={
                    "event_type": "phase_changed",
                    "new_phase": "clone",
                    "event_timestamp": older_ts,
                    "note": "AUT-1205 regression: backdated light-axis event",
                },
                headers=operator_headers,
            )
            assert r_backdated.status_code == 201
            backdated = r_backdated.json()
            assert backdated["new_phase"] == "clone"
            assert backdated["event_timestamp"].startswith(older_ts[:19])

            plant_response = await client.get(
                f"/api/v1/plants/{plant_id}",
                headers=operator_headers,
            )
            events_response = await client.get(
                f"/api/v1/plants/{plant_id}/lifecycle-events",
                headers=operator_headers,
            )

        assert plant_response.json()["phase"] == "bluete-stretch"
        phase_events = [
            e for e in events_response.json()["events"] if e["event_type"] == "phase_changed"
        ]
        assert len(phase_events) == 2
        assert any(e["event_id"] == backdated["event_id"] for e in phase_events)

    @pytest.mark.asyncio
    async def test_backdated_nutrient_phase_changed_does_not_overwrite_current(
        self,
        sample_plant: Plant,
        operator_headers: dict,
    ):
        """
        Symmetric AUT-1205 check for the nutrient/fertilizer axis.
        """
        plant_id = sample_plant.plant_id
        now = datetime.now(timezone.utc)
        newer_ts = (now - timedelta(days=3)).isoformat().replace("+00:00", "Z")
        older_ts = (now - timedelta(days=15)).isoformat().replace("+00:00", "Z")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r_newer = await client.post(
                f"/api/v1/plants/{plant_id}/lifecycle-event",
                json={
                    "event_type": "nutrient_phase_changed",
                    "new_phase": "veg-spaet",
                    "event_timestamp": newer_ts,
                },
                headers=operator_headers,
            )
            assert r_newer.status_code == 201

            r_backdated = await client.post(
                f"/api/v1/plants/{plant_id}/lifecycle-event",
                json={
                    "event_type": "nutrient_phase_changed",
                    "new_phase": "veg-frueh",
                    "event_timestamp": older_ts,
                },
                headers=operator_headers,
            )
            assert r_backdated.status_code == 201

            plant_response = await client.get(
                f"/api/v1/plants/{plant_id}",
                headers=operator_headers,
            )

        plant_data = plant_response.json()
        assert plant_data["nutrient_phase"] == "veg-spaet"
        # Light axis must remain untouched by nutrient-axis chronology writes
        assert plant_data["phase"] == sample_plant.phase

    @pytest.mark.asyncio
    async def test_forward_phase_changed_still_updates_current(
        self,
        sample_plant: Plant,
        operator_headers: dict,
    ):
        """
        Chronology fix must not break the normal case: the newest transition
        still becomes Plant.phase.
        """
        plant_id = sample_plant.plant_id
        now = datetime.now(timezone.utc)
        older_ts = (now - timedelta(days=10)).isoformat().replace("+00:00", "Z")
        newer_ts = (now - timedelta(days=1)).isoformat().replace("+00:00", "Z")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post(
                f"/api/v1/plants/{plant_id}/lifecycle-event",
                json={
                    "event_type": "phase_changed",
                    "new_phase": "veg-spaet",
                    "event_timestamp": older_ts,
                },
                headers=operator_headers,
            )
            r_newer = await client.post(
                f"/api/v1/plants/{plant_id}/lifecycle-event",
                json={
                    "event_type": "phase_changed",
                    "new_phase": "bluete-bulk",
                    "event_timestamp": newer_ts,
                },
                headers=operator_headers,
            )
            assert r_newer.status_code == 201

            plant_response = await client.get(
                f"/api/v1/plants/{plant_id}",
                headers=operator_headers,
            )

        assert plant_response.json()["phase"] == "bluete-bulk"


# =============================================================================
# AUT-1194: GET /v1/plants/zone-summary/{zone_id} — two-axis phase histogram
# =============================================================================


class TestZonePlantSummary:
    """
    AUT-1194: Zone plant summary must carry both phase axes so the caller
    always knows which axis each histogram refers to.

    ``phases``                   = light/growth axis (backward-compatible).
    ``nutrient_phase_histogram`` = nutrient/fertilizer axis (AUT-1183, additive).
    """

    @pytest.fixture
    async def zone_with_plants(
        self,
        db_session: AsyncSession,
        operator_user: User,
    ) -> str:
        """
        Create a subzone assigned to ``zone_bloom`` and three plants:

        - plant A: phase="bluete-bulk", nutrient_phase="veg-spaet"
        - plant B: phase="bluete-bulk", nutrient_phase=None
        - plant C: phase="veg-frueh",   nutrient_phase="veg-spaet"

        Expected histograms:
        - light/growth (``phases``):
            {"bluete-bulk": 2, "veg-frueh": 1}
        - nutrient (``nutrient_phase_histogram``):
            {"veg-spaet": 2}
            (plant B excluded because nutrient_phase is NULL)
        """
        zone_id = "zone_bloom"

        # SQLite does not enforce FK constraints in tests; we can create
        # SubzoneConfig without a corresponding ESPDevice row.
        subzone = SubzoneConfig(
            id=uuid.uuid4(),
            esp_id="ESP_ZONE_SUMMARY_TEST",
            subzone_id="sz_bloom_01",
            parent_zone_id=zone_id,
            assigned_gpios=[],
            assigned_sensor_config_ids=[],
            is_active=True,
        )
        db_session.add(subzone)
        await db_session.flush()

        # Plant A: both axes set
        plant_a = Plant(
            plant_id=uuid.uuid4(),
            genotype_label="StrainA",
            planting_date=datetime(2026, 1, 1).date(),
            phase="bluete-bulk",
            nutrient_phase="veg-spaet",
            subzone_id=subzone.id,
            qr_code=f"PL-{uuid.uuid4().hex[:8].upper()}",
            visibility="tenant_private",
        )
        # Plant B: light/growth only — nutrient_phase NULL
        plant_b = Plant(
            plant_id=uuid.uuid4(),
            genotype_label="StrainB",
            planting_date=datetime(2026, 1, 1).date(),
            phase="bluete-bulk",
            nutrient_phase=None,
            subzone_id=subzone.id,
            qr_code=f"PL-{uuid.uuid4().hex[:8].upper()}",
            visibility="tenant_private",
        )
        # Plant C: different light phase, same nutrient phase as A
        plant_c = Plant(
            plant_id=uuid.uuid4(),
            genotype_label="StrainC",
            planting_date=datetime(2026, 1, 1).date(),
            phase="veg-frueh",
            nutrient_phase="veg-spaet",
            subzone_id=subzone.id,
            qr_code=f"PL-{uuid.uuid4().hex[:8].upper()}",
            visibility="tenant_private",
        )
        for plant in (plant_a, plant_b, plant_c):
            db_session.add(plant)
        await db_session.commit()
        return zone_id

    @pytest.mark.asyncio
    async def test_zone_summary_carries_both_phase_axes(
        self,
        zone_with_plants: str,
        operator_headers: dict,
    ):
        """
        AUT-1194: GET /v1/plants/zone-summary/{zone_id} response contains
        both ``phases`` (light/growth axis) and ``nutrient_phase_histogram``
        (nutrient/fertilizer axis).  Axis identity is unambiguous from the
        field names alone.
        """
        zone_id = zone_with_plants
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/plants/zone-summary/{zone_id}",
                headers=operator_headers,
            )

        assert response.status_code == 200
        data = response.json()

        # Both axis fields must be present in the response.
        assert "phases" in data, "light/growth histogram must be present"
        assert "nutrient_phase_histogram" in data, "nutrient histogram must be present (AUT-1194)"

        # Light/growth axis: all 3 plants counted.
        assert data["phases"] == {
            "bluete-bulk": 2,
            "veg-frueh": 1,
        }, "phases must reflect the light/growth axis for all active plants"

        # Nutrient axis: only plants A and C have nutrient_phase set.
        assert data["nutrient_phase_histogram"] == {"veg-spaet": 2}, (
            "nutrient_phase_histogram must reflect the nutrient/fertilizer axis; "
            "plants without nutrient_phase must be excluded"
        )

        # plant_count is derived from the light/growth axis.
        assert data["plant_count"] == 3

    @pytest.mark.asyncio
    async def test_zone_summary_unknown_zone_returns_empty_histograms(
        self,
        operator_headers: dict,
    ):
        """
        Zone with no plants returns zero plant_count and empty histograms
        for both axes — no 404, the endpoint is zone-existence-agnostic.
        """
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/plants/zone-summary/nonexistent_zone_xyz",
                headers=operator_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["plant_count"] == 0
        assert data["phases"] == {}
        assert data["nutrient_phase_histogram"] == {}
        assert data["avg_phi2"] is None

    @pytest.mark.asyncio
    async def test_zone_summary_null_nutrient_phase_excluded_from_nutrient_histogram(
        self,
        db_session: AsyncSession,
        operator_headers: dict,
        operator_user: User,
    ):
        """
        Plants with ``nutrient_phase=NULL`` must NOT appear in
        ``nutrient_phase_histogram``.  Only plants with an explicitly set
        nutrient phase are counted there.
        """
        zone_id = "zone_null_nutrient"
        subzone = SubzoneConfig(
            id=uuid.uuid4(),
            esp_id="ESP_NULL_NUTRIENT_TEST",
            subzone_id="sz_null_nutrient",
            parent_zone_id=zone_id,
            assigned_gpios=[],
            assigned_sensor_config_ids=[],
            is_active=True,
        )
        db_session.add(subzone)
        await db_session.flush()

        # Single plant with nutrient_phase=None
        plant = Plant(
            plant_id=uuid.uuid4(),
            genotype_label="NullNutrient",
            planting_date=datetime(2026, 3, 1).date(),
            phase="clone",
            nutrient_phase=None,
            subzone_id=subzone.id,
            qr_code=f"PL-{uuid.uuid4().hex[:8].upper()}",
            visibility="tenant_private",
        )
        db_session.add(plant)
        await db_session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/plants/zone-summary/{zone_id}",
                headers=operator_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["plant_count"] == 1
        assert data["phases"] == {"clone": 1}
        # nutrient histogram must be empty — the only plant has no nutrient phase
        assert (
            data["nutrient_phase_histogram"] == {}
        ), "NULL nutrient_phase must not appear in nutrient_phase_histogram"


# =============================================================================
# AUT-1266: PlantUpdate.subzone_id (drag-and-drop Ortswechsel)
# =============================================================================


class TestPlantPatchSubzoneAut1266:
    """PATCH accepts subzone_id; unknown Ortseinheit is rejected (AUT-1266)."""

    @pytest.mark.asyncio
    async def test_patch_persists_subzone_id(
        self,
        db_session: AsyncSession,
        sample_plant: Plant,
        operator_headers: dict,
    ):
        zone = Zone(zone_id="zone_patch_sub", name="Patch Sub Zone")
        subzone = SubzoneConfig(
            id=uuid.uuid4(),
            esp_id="ESP_PATCH_SUB_AUT1266",
            subzone_id="sz_patch_sub",
            subzone_name="Patch Bench",
            parent_zone_id=zone.zone_id,
            assigned_gpios=[],
            assigned_sensor_config_ids=[],
            is_active=True,
        )
        db_session.add_all([zone, subzone])
        await db_session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.patch(
                f"/api/v1/plants/{sample_plant.plant_id}",
                json={"subzone_id": str(subzone.id)},
                headers=operator_headers,
            )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["subzone_id"] == str(subzone.id)
        assert body["subzone_name"] == "Patch Bench"
        assert body["parent_zone_id"] == "zone_patch_sub"
        assert body["zone_name"] == "Patch Sub Zone"
        assert body.get("zone_id") is None

    @pytest.mark.asyncio
    async def test_patch_rejects_unknown_subzone(
        self,
        sample_plant: Plant,
        operator_headers: dict,
    ):
        missing = uuid.uuid4()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.patch(
                f"/api/v1/plants/{sample_plant.plant_id}",
                json={"subzone_id": str(missing)},
                headers=operator_headers,
            )

        assert response.status_code == 422
        assert "nicht gefunden" in response.json()["detail"]
        assert str(missing) in response.json()["detail"]


# =============================================================================
# AUT-1073: Direct zone assignment + optional genotype/planting_date
# =============================================================================


class TestPlantDirectZoneAssignmentAut1073:
    """Plants may belong to a zone without an Ortseinheit (AUT-1073)."""

    @pytest.mark.asyncio
    async def test_create_direct_zone_without_subzone_genotype_or_date(
        self,
        db_session: AsyncSession,
        operator_headers: dict,
    ):
        zone = Zone(zone_id="zone_direct_aut1073", name="Direct Zone")
        db_session.add(zone)
        await db_session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            create_resp = await client.post(
                "/api/v1/plants",
                json={"zone_id": "zone_direct_aut1073"},
                headers=operator_headers,
            )
            assert create_resp.status_code == 201, create_resp.text
            body = create_resp.json()
            assert body["zone_id"] == "zone_direct_aut1073"
            assert body["parent_zone_id"] == "zone_direct_aut1073"
            assert body["zone_name"] == "Direct Zone"
            assert body["subzone_id"] is None
            assert body["genotype_label"] is None
            assert body["planting_date"] is None
            assert body["phase"] == "clone"

            list_resp = await client.get(
                "/api/v1/plants?zone_id=zone_direct_aut1073",
                headers=operator_headers,
            )
            assert list_resp.status_code == 200
            plant_ids = {p["plant_id"] for p in list_resp.json()["plants"]}
            assert body["plant_id"] in plant_ids

            summary_resp = await client.get(
                "/api/v1/plants/zone-summary/zone_direct_aut1073",
                headers=operator_headers,
            )
            assert summary_resp.status_code == 200
            summary = summary_resp.json()
            assert summary["plant_count"] >= 1
            assert summary["phases"].get("clone", 0) >= 1

    @pytest.mark.asyncio
    async def test_subzone_parent_zone_unchanged_when_direct_zone_null(
        self,
        db_session: AsyncSession,
        operator_headers: dict,
    ):
        """Ortseinheit path: parent_zone_id stays the subzone parent; zone_id null."""
        zone = Zone(zone_id="zone_ort_aut1073", name="Ortseinheit Zone")
        subzone = SubzoneConfig(
            id=uuid.uuid4(),
            esp_id="ESP_ORT_AUT1073",
            subzone_id="sz_ort",
            subzone_name="Topf Ort",
            parent_zone_id=zone.zone_id,
            assigned_gpios=[],
            assigned_sensor_config_ids=[],
            is_active=True,
        )
        plant = Plant(
            plant_id=uuid.uuid4(),
            genotype_label="Ortseinheit Plant",
            planting_date=datetime(2026, 1, 1).date(),
            phase="veg-frueh",
            subzone_id=subzone.id,
            qr_code=f"PL-{uuid.uuid4().hex[:8].upper()}",
            visibility="tenant_private",
        )
        db_session.add_all([zone, subzone, plant])
        await db_session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/plants/{plant.plant_id}",
                headers=operator_headers,
            )

        assert response.status_code == 200
        body = response.json()
        assert body["parent_zone_id"] == "zone_ort_aut1073"
        assert body["subzone_name"] == "Topf Ort"
        assert body["zone_id"] is None

    @pytest.mark.asyncio
    async def test_patch_rejects_conflicting_zone_and_subzone_parent(
        self,
        db_session: AsyncSession,
        sample_plant: Plant,
        operator_headers: dict,
    ):
        zone_a = Zone(zone_id="zone_conflict_a", name="Conflict A")
        zone_b = Zone(zone_id="zone_conflict_b", name="Conflict B")
        subzone = SubzoneConfig(
            id=uuid.uuid4(),
            esp_id="ESP_CONFLICT_AUT1073",
            subzone_id="sz_conflict",
            subzone_name="Conflict Bench",
            parent_zone_id=zone_a.zone_id,
            assigned_gpios=[],
            assigned_sensor_config_ids=[],
            is_active=True,
        )
        db_session.add_all([zone_a, zone_b, subzone])
        await db_session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.patch(
                f"/api/v1/plants/{sample_plant.plant_id}",
                json={
                    "subzone_id": str(subzone.id),
                    "zone_id": zone_b.zone_id,
                },
                headers=operator_headers,
            )

        assert response.status_code == 422
        detail = response.json()["detail"]
        assert "widerspricht" in detail
        assert zone_a.zone_id in detail

    @pytest.mark.asyncio
    async def test_zoneless_subzone_with_direct_zone_uses_fallback(
        self,
        db_session: AsyncSession,
        operator_headers: dict,
    ):
        """Ortseinheit without parent + plants.zone_id → effective = zone_id."""
        zone = Zone(zone_id="zone_fallback_aut1073", name="Fallback Zone")
        subzone = SubzoneConfig(
            id=uuid.uuid4(),
            esp_id="ESP_FALLBACK_AUT1073",
            subzone_id="sz_fallback",
            subzone_name="Zoneless Bench",
            parent_zone_id=None,
            assigned_gpios=[],
            assigned_sensor_config_ids=[],
            is_active=True,
        )
        plant = Plant(
            plant_id=uuid.uuid4(),
            genotype_label="Fallback Plant",
            planting_date=datetime(2026, 1, 1).date(),
            phase="veg-frueh",
            zone_id=zone.zone_id,
            subzone_id=subzone.id,
            qr_code=f"PL-{uuid.uuid4().hex[:8].upper()}",
            visibility="tenant_private",
        )
        db_session.add_all([zone, subzone, plant])
        await db_session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/plants/{plant.plant_id}",
                headers=operator_headers,
            )

        assert response.status_code == 200
        body = response.json()
        assert body["subzone_name"] == "Zoneless Bench"
        assert body["zone_id"] == "zone_fallback_aut1073"
        assert body["parent_zone_id"] == "zone_fallback_aut1073"
        assert body["zone_name"] == "Fallback Zone"
