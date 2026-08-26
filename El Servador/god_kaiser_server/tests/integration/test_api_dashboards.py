"""
Integration Tests: Dashboard API (AUT-1095)

Tests the existing dashboard CRUD endpoints AND the new n:m user assignment
endpoints. Verifies the additive design: owner_id and is_shared are never
changed by assignment operations.

Covered cases:
- List: owned, shared, and explicitly assigned dashboards
- Get by ID: access via ownership, sharing, assignment, or denial
- Assignments: create, duplicate (409), delete, list
- Invariant: owner_id and is_shared unchanged after any assignment op
"""

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token, get_password_hash
from src.db.models.dashboard import Dashboard
from src.db.models.user import User
from src.main import app

BASE_URL = "http://test"
API_PREFIX = "/api/v1/dashboards"


# =============================================================================
# Fixtures
# =============================================================================


@pytest_asyncio.fixture
async def owner_user(db_session: AsyncSession) -> User:
    """Operator user who owns the test dashboard."""
    user = User(
        username="dash_owner",
        email="dash_owner@example.com",
        password_hash=get_password_hash("OwnerPass1!"),
        full_name="Dashboard Owner",
        role="operator",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def other_user(db_session: AsyncSession) -> User:
    """Operator user who will receive dashboard assignments."""
    user = User(
        username="dash_other",
        email="dash_other@example.com",
        password_hash=get_password_hash("OtherPass1!"),
        full_name="Other Operator",
        role="operator",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def viewer_user(db_session: AsyncSession) -> User:
    """Viewer user — has no assignment, no ownership, no shared."""
    user = User(
        username="dash_viewer",
        email="dash_viewer@example.com",
        password_hash=get_password_hash("ViewerPass1!"),
        full_name="Viewer",
        role="viewer",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_dashboard(db_session: AsyncSession, owner_user: User) -> Dashboard:
    """Private (non-shared) dashboard owned by owner_user."""
    dashboard = Dashboard(
        name="Test Dashboard AUT-1095",
        description="Integration test dashboard",
        owner_id=owner_user.id,
        is_shared=False,
        widgets=[],
        scope=None,
        zone_id=None,
        auto_generated=False,
    )
    db_session.add(dashboard)
    await db_session.commit()
    await db_session.refresh(dashboard)
    return dashboard


@pytest_asyncio.fixture
async def shared_dashboard(db_session: AsyncSession, owner_user: User) -> Dashboard:
    """Shared dashboard (is_shared=True) owned by owner_user."""
    dashboard = Dashboard(
        name="Shared Dashboard AUT-1095",
        description="Shared test dashboard",
        owner_id=owner_user.id,
        is_shared=True,
        widgets=[],
        scope=None,
        zone_id=None,
        auto_generated=False,
    )
    db_session.add(dashboard)
    await db_session.commit()
    await db_session.refresh(dashboard)
    return dashboard


def _token(user: User) -> dict:
    """Return Authorization header dict for a user."""
    token = create_access_token(
        user_id=user.id,
        additional_claims={"role": user.role},
    )
    return {"Authorization": f"Bearer {token}"}


# =============================================================================
# Tests: List endpoint visibility
# =============================================================================


class TestListDashboardsVisibility:
    """GET /dashboards reflects ownership, sharing, and assignment."""

    @pytest.mark.asyncio
    async def test_owner_sees_own_dashboard(
        self, owner_user: User, test_dashboard: Dashboard
    ):
        """Owner always sees their own dashboard in the list."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url=BASE_URL
        ) as client:
            resp = await client.get(API_PREFIX, headers=_token(owner_user))

        assert resp.status_code == 200
        ids = [d["id"] for d in resp.json()["data"]]
        assert str(test_dashboard.id) in ids

    @pytest.mark.asyncio
    async def test_unassigned_user_cannot_see_private_dashboard(
        self, other_user: User, test_dashboard: Dashboard
    ):
        """other_user has no assignment and dashboard is not shared → not visible."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url=BASE_URL
        ) as client:
            resp = await client.get(API_PREFIX, headers=_token(other_user))

        assert resp.status_code == 200
        ids = [d["id"] for d in resp.json()["data"]]
        assert str(test_dashboard.id) not in ids

    @pytest.mark.asyncio
    async def test_any_user_sees_shared_dashboard(
        self, other_user: User, shared_dashboard: Dashboard
    ):
        """is_shared=True dashboards appear for every authenticated user."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url=BASE_URL
        ) as client:
            resp = await client.get(API_PREFIX, headers=_token(other_user))

        assert resp.status_code == 200
        ids = [d["id"] for d in resp.json()["data"]]
        assert str(shared_dashboard.id) in ids

    @pytest.mark.asyncio
    async def test_assigned_user_sees_private_dashboard(
        self, owner_user: User, other_user: User, test_dashboard: Dashboard
    ):
        """After assignment, other_user sees the private dashboard in the list."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url=BASE_URL
        ) as client:
            # Assign other_user via operator (owner)
            assign_resp = await client.post(
                f"{API_PREFIX}/{test_dashboard.id}/assignments",
                json={"user_id": other_user.id},
                headers=_token(owner_user),
            )
            assert assign_resp.status_code == 201

            # Now other_user should see the dashboard
            list_resp = await client.get(API_PREFIX, headers=_token(other_user))

        assert list_resp.status_code == 200
        ids = [d["id"] for d in list_resp.json()["data"]]
        assert str(test_dashboard.id) in ids


# =============================================================================
# Tests: Get by ID access control
# =============================================================================


class TestGetDashboardAccess:
    """GET /dashboards/{id} respects ownership, sharing, and assignment."""

    @pytest.mark.asyncio
    async def test_owner_can_get_own_dashboard(
        self, owner_user: User, test_dashboard: Dashboard
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url=BASE_URL
        ) as client:
            resp = await client.get(
                f"{API_PREFIX}/{test_dashboard.id}", headers=_token(owner_user)
            )
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == str(test_dashboard.id)

    @pytest.mark.asyncio
    async def test_unassigned_user_cannot_get_private_dashboard(
        self, other_user: User, test_dashboard: Dashboard
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url=BASE_URL
        ) as client:
            resp = await client.get(
                f"{API_PREFIX}/{test_dashboard.id}", headers=_token(other_user)
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_assigned_user_can_get_dashboard_by_id(
        self, owner_user: User, other_user: User, test_dashboard: Dashboard
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url=BASE_URL
        ) as client:
            await client.post(
                f"{API_PREFIX}/{test_dashboard.id}/assignments",
                json={"user_id": other_user.id},
                headers=_token(owner_user),
            )
            resp = await client.get(
                f"{API_PREFIX}/{test_dashboard.id}", headers=_token(other_user)
            )
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == str(test_dashboard.id)


# =============================================================================
# Tests: Assignment CRUD
# =============================================================================


class TestDashboardAssignments:
    """POST / DELETE / GET /dashboards/{id}/assignments"""

    @pytest.mark.asyncio
    async def test_assign_user_returns_201(
        self, owner_user: User, other_user: User, test_dashboard: Dashboard
    ):
        """Assigning a user returns 201 with the assignment data."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url=BASE_URL
        ) as client:
            resp = await client.post(
                f"{API_PREFIX}/{test_dashboard.id}/assignments",
                json={"user_id": other_user.id},
                headers=_token(owner_user),
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["success"] is True
        assert len(data["data"]) == 1
        assignment = data["data"][0]
        assert assignment["user_id"] == other_user.id
        assert assignment["dashboard_id"] == str(test_dashboard.id)

    @pytest.mark.asyncio
    async def test_duplicate_assignment_returns_409(
        self, owner_user: User, other_user: User, test_dashboard: Dashboard
    ):
        """Assigning the same user twice returns HTTP 409 (not 500)."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url=BASE_URL
        ) as client:
            await client.post(
                f"{API_PREFIX}/{test_dashboard.id}/assignments",
                json={"user_id": other_user.id},
                headers=_token(owner_user),
            )
            resp = await client.post(
                f"{API_PREFIX}/{test_dashboard.id}/assignments",
                json={"user_id": other_user.id},
                headers=_token(owner_user),
            )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_list_assignments_returns_assigned_users(
        self, owner_user: User, other_user: User, test_dashboard: Dashboard
    ):
        """GET /assignments lists all assigned users for a dashboard."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url=BASE_URL
        ) as client:
            await client.post(
                f"{API_PREFIX}/{test_dashboard.id}/assignments",
                json={"user_id": other_user.id},
                headers=_token(owner_user),
            )
            resp = await client.get(
                f"{API_PREFIX}/{test_dashboard.id}/assignments",
                headers=_token(owner_user),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        user_ids = [a["user_id"] for a in data["data"]]
        assert other_user.id in user_ids

    @pytest.mark.asyncio
    async def test_unassign_user_returns_200_and_denies_access(
        self, owner_user: User, other_user: User, test_dashboard: Dashboard
    ):
        """After unassignment, user can no longer access the dashboard."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url=BASE_URL
        ) as client:
            # Assign
            await client.post(
                f"{API_PREFIX}/{test_dashboard.id}/assignments",
                json={"user_id": other_user.id},
                headers=_token(owner_user),
            )
            # Unassign
            unassign_resp = await client.delete(
                f"{API_PREFIX}/{test_dashboard.id}/assignments/{other_user.id}",
                headers=_token(owner_user),
            )
            assert unassign_resp.status_code == 200

            # Access should now be denied
            get_resp = await client.get(
                f"{API_PREFIX}/{test_dashboard.id}", headers=_token(other_user)
            )
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_unassign_nonexistent_returns_404(
        self, owner_user: User, test_dashboard: Dashboard
    ):
        """Unassigning a user who was never assigned returns 404."""
        nonexistent_user_id = 99999
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url=BASE_URL
        ) as client:
            resp = await client.delete(
                f"{API_PREFIX}/{test_dashboard.id}/assignments/{nonexistent_user_id}",
                headers=_token(owner_user),
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_assign_to_nonexistent_dashboard_returns_404(
        self, owner_user: User, other_user: User
    ):
        """Assigning to a non-existent dashboard returns 404."""
        nonexistent_id = uuid.uuid4()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url=BASE_URL
        ) as client:
            resp = await client.post(
                f"{API_PREFIX}/{nonexistent_id}/assignments",
                json={"user_id": other_user.id},
                headers=_token(owner_user),
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_viewer_cannot_assign(
        self, viewer_user: User, other_user: User, test_dashboard: Dashboard
    ):
        """Viewers are not allowed to create assignments (403)."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url=BASE_URL
        ) as client:
            resp = await client.post(
                f"{API_PREFIX}/{test_dashboard.id}/assignments",
                json={"user_id": other_user.id},
                headers=_token(viewer_user),
            )
        assert resp.status_code == 403


# =============================================================================
# Tests: Invariant — owner_id and is_shared unchanged after assignment
# =============================================================================


class TestAssignmentInvariant:
    """owner_id and is_shared must remain unchanged after any assignment op."""

    @pytest.mark.asyncio
    async def test_owner_id_and_shared_unchanged_after_assign_and_unassign(
        self, owner_user: User, other_user: User, test_dashboard: Dashboard
    ):
        """
        GIVEN dashboard with owner=owner_user, is_shared=False
        WHEN  other_user is assigned and then unassigned
        THEN  owner_id and is_shared on the dashboard are unmodified
        """
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url=BASE_URL
        ) as client:
            # Assign
            await client.post(
                f"{API_PREFIX}/{test_dashboard.id}/assignments",
                json={"user_id": other_user.id},
                headers=_token(owner_user),
            )
            # Unassign
            await client.delete(
                f"{API_PREFIX}/{test_dashboard.id}/assignments/{other_user.id}",
                headers=_token(owner_user),
            )
            # Check dashboard as owner
            resp = await client.get(
                f"{API_PREFIX}/{test_dashboard.id}", headers=_token(owner_user)
            )

        assert resp.status_code == 200
        d = resp.json()["data"]
        assert d["owner_id"] == owner_user.id
        assert d["is_shared"] is False
