"""
Integration Tests: Admin Sheets-Export API (AUT-446 / S3).

Tests:
- POST /api/v1/admin/sheets-export/reset-cursor
  - happy path: cursor exists → deleted=True
  - happy path: cursor not set → deleted=False
  - all three cursor names accepted
  - unknown cursor_name → 422
  - non-admin user → 403
  - unauthenticated → 401
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token, get_password_hash
from src.db.models.user import User
from src.db.repositories.system_config_repo import (
    SHEETS_CURSOR_HISTORY,
    SHEETS_CURSOR_LOGIC,
    SHEETS_CURSOR_SENSOR,
    SystemConfigRepository,
)
from src.main import app

ENDPOINT = "/api/v1/admin/sheets-export/reset-cursor"


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def admin_user(db_session: AsyncSession) -> User:
    user = User(
        username="admin_sheets_test",
        email="admin_sheets@example.com",
        password_hash=get_password_hash("AdminP@ss123"),
        full_name="Admin Sheets Test",
        role="admin",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def operator_user(db_session: AsyncSession) -> User:
    user = User(
        username="operator_sheets_test",
        email="operator_sheets@example.com",
        password_hash=get_password_hash("OperatorP@ss123"),
        full_name="Operator Sheets Test",
        role="operator",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def admin_headers(admin_user: User) -> dict:
    token = create_access_token(
        user_id=admin_user.id, additional_claims={"role": admin_user.role}
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def operator_headers(operator_user: User) -> dict:
    token = create_access_token(
        user_id=operator_user.id, additional_claims={"role": operator_user.role}
    )
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Tests: POST /reset-cursor
# ---------------------------------------------------------------------------


class TestResetCursorEndpoint:
    @pytest.mark.asyncio
    async def test_reset_cursor_deleted_true_when_cursor_exists(
        self, admin_headers: dict, db_session: AsyncSession
    ):
        """When the cursor is set, reset returns deleted=True."""
        repo = SystemConfigRepository(db_session)
        await repo.set_sheets_export_cursor(SHEETS_CURSOR_SENSOR, "2026-05-23T10:00:00+00:00")
        await db_session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                ENDPOINT,
                json={"cursor_name": SHEETS_CURSOR_SENSOR},
                headers=admin_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["cursor_name"] == SHEETS_CURSOR_SENSOR
        assert data["deleted"] is True

    @pytest.mark.asyncio
    async def test_reset_cursor_deleted_false_when_not_set(
        self, admin_headers: dict, db_session: AsyncSession
    ):
        """When the cursor does not exist, reset returns deleted=False."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                ENDPOINT,
                json={"cursor_name": SHEETS_CURSOR_HISTORY},
                headers=admin_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["deleted"] is False

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "cursor_name",
        [SHEETS_CURSOR_SENSOR, SHEETS_CURSOR_HISTORY, SHEETS_CURSOR_LOGIC],
    )
    async def test_all_allowed_cursor_names_accepted(
        self, cursor_name: str, admin_headers: dict
    ):
        """All three cursor names must be accepted with HTTP 200."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                ENDPOINT,
                json={"cursor_name": cursor_name},
                headers=admin_headers,
            )
        assert response.status_code == 200
        assert response.json()["cursor_name"] == cursor_name

    @pytest.mark.asyncio
    async def test_unknown_cursor_name_returns_422(self, admin_headers: dict):
        """Unknown cursor_name should fail validation with HTTP 422."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                ENDPOINT,
                json={"cursor_name": "sheets_export_nonexistent_cursor"},
                headers=admin_headers,
            )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_non_admin_user_is_forbidden(self, operator_headers: dict):
        """Operator role must not access admin-only endpoint (HTTP 403)."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                ENDPOINT,
                json={"cursor_name": SHEETS_CURSOR_SENSOR},
                headers=operator_headers,
            )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_unauthenticated_is_rejected(self):
        """Requests without Authorization header must be rejected (HTTP 401)."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                ENDPOINT,
                json={"cursor_name": SHEETS_CURSOR_SENSOR},
            )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_reset_cursor_is_idempotent(
        self, admin_headers: dict, db_session: AsyncSession
    ):
        """Calling reset twice should be safe: first returns deleted=True, second deleted=False."""
        repo = SystemConfigRepository(db_session)
        await repo.set_sheets_export_cursor(SHEETS_CURSOR_LOGIC, "2026-05-23T10:00:00+00:00")
        await db_session.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r1 = await client.post(
                ENDPOINT,
                json={"cursor_name": SHEETS_CURSOR_LOGIC},
                headers=admin_headers,
            )
            r2 = await client.post(
                ENDPOINT,
                json={"cursor_name": SHEETS_CURSOR_LOGIC},
                headers=admin_headers,
            )

        assert r1.status_code == 200
        assert r1.json()["deleted"] is True
        assert r2.status_code == 200
        assert r2.json()["deleted"] is False

    @pytest.mark.asyncio
    async def test_response_contains_message_field(self, admin_headers: dict):
        """Response must include a human-readable message."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                ENDPOINT,
                json={"cursor_name": SHEETS_CURSOR_SENSOR},
                headers=admin_headers,
            )
        assert response.status_code == 200
        assert "message" in response.json()
        assert len(response.json()["message"]) > 0
