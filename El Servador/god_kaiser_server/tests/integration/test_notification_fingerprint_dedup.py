"""
Integration Tests: Notification Fingerprint Dedup (FIX-F5)

Tests for NotificationRepository.create_with_fingerprint_dedup():
- Atomic INSERT with ON CONFLICT DO NOTHING (PostgreSQL only)
- Sequential dedup behaviour via router (SQLite-compatible)

Tests marked with @requires_postgresql are skipped in the standard
SQLite test environment (TESTING=true). They run in CI against a real
PostgreSQL instance or locally with a PostgreSQL DATABASE_URL.
"""

import asyncio
import os
from uuid import uuid4

import pytest

from src.db.models.notification import AlertStatus, Notification
from src.db.repositories.notification_repo import NotificationRepository
from src.schemas.notification import NotificationCreate
from src.services.notification_router import NotificationRouter

# Skip marker for tests that require PostgreSQL ON CONFLICT support
requires_postgresql = pytest.mark.skipif(
    os.environ.get("TESTING") == "true",
    reason="Requires PostgreSQL (test env uses SQLite which lacks partial-index ON CONFLICT)",
)


def _make_fingerprint_data(user_id: int, fingerprint: str) -> dict:
    """Build a minimal notification_data dict with the given fingerprint."""
    return {
        "user_id": user_id,
        "fingerprint": fingerprint,
        "title": "FP Dedup Test Alert",
        "body": "Automated test",
        "severity": "warning",
        "category": "test",
        "source": "grafana",
        "channel": "in_app",
    }


# =============================================================================
# Test 1: Sequential dedup via NotificationRepository (PostgreSQL only)
# =============================================================================


@requires_postgresql
@pytest.mark.asyncio
async def test_sequential_fingerprint_dedup_repo(db_session, sample_user):
    """
    Second create_with_fingerprint_dedup call with the same fingerprint
    returns created=False and the same notification id.
    """
    repo = NotificationRepository(db_session)
    fingerprint = "test-seq-" + uuid4().hex
    data = _make_fingerprint_data(sample_user.id, fingerprint)

    n1, created1 = await repo.create_with_fingerprint_dedup(data)
    assert created1 is True
    assert n1 is not None
    assert n1.fingerprint == fingerprint

    n2, created2 = await repo.create_with_fingerprint_dedup(data)
    assert created2 is False
    assert n2 is not None
    assert n1.id == n2.id


# =============================================================================
# Test 2: Concurrent inserts via router (PostgreSQL only)
# =============================================================================


@requires_postgresql
@pytest.mark.asyncio
async def test_concurrent_fingerprint_dedup_router(
    db_session, sample_user, mock_ws_manager, mock_email_service
):
    """
    Two concurrent route() calls with identical fingerprint produce exactly
    one DB row and no unhandled exceptions.
    """
    router = NotificationRouter(session=db_session, email_service=mock_email_service)
    fingerprint = "test-concurrent-" + uuid4().hex

    notification = NotificationCreate(
        user_id=sample_user.id,
        title="Concurrent FP Alert",
        body="Race condition test",
        severity="warning",
        category="test",
        source="grafana",
        fingerprint=fingerprint,
    )

    results = await asyncio.gather(
        router.route(notification),
        router.route(notification),
        return_exceptions=True,
    )

    # No unhandled exceptions
    for r in results:
        assert not isinstance(r, Exception), f"Unhandled exception: {r}"

    # Exactly one notification row in DB
    from sqlalchemy import select, func

    count_stmt = (
        select(func.count())
        .select_from(Notification)
        .where(Notification.fingerprint == fingerprint)
    )
    count_result = await db_session.execute(count_stmt)
    assert count_result.scalar_one() == 1


# =============================================================================
# Test 3: Fingerprint dedup via router (SQLite-compatible, regression guard)
# =============================================================================


@pytest.mark.asyncio
async def test_route_fingerprint_dedup_atomic(
    db_session, sample_user, mock_ws_manager, mock_email_service
):
    """
    Router: second notification with same fingerprint returns None.
    Uses the new create_with_fingerprint_dedup path (falls back to
    sequential check on SQLite — behaviour is identical).
    """
    router = NotificationRouter(session=db_session, email_service=mock_email_service)

    notification = NotificationCreate(
        user_id=sample_user.id,
        title="FP Atomic Dedup",
        body="Same alert",
        severity="warning",
        category="system",
        source="grafana",
        fingerprint="atomic-fp-" + uuid4().hex,
    )

    result1 = await router.route(notification)
    assert result1 is not None
    assert result1.fingerprint == notification.fingerprint

    result2 = await router.route(notification)
    assert result2 is None
