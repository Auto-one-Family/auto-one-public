"""
Integration Tests: EmailLogRepository.get_pending_retries (Phase C V1.2)

Tests get_pending_retries with real DB: filter status=failed, retry_count < 3,
min_age_minutes, ordering, limit.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.email_log import EmailLog
from src.db.models.notification import Notification
from src.db.models.user import User
from src.db.repositories.email_log_repo import EmailLogRepository


@pytest.mark.asyncio
async def test_get_pending_retries_returns_only_failed_with_retry_count_lt_3(
    db_session: AsyncSession,
):
    """Only status=failed and retry_count < 3 are returned."""
    # Create user for notification FK
    user = User(
        username="retry_test_user",
        email="retry@test.com",
        password_hash="x",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    # Create notification for critical alert
    notif = Notification(
        user_id=user.id,
        channel="email",
        severity="critical",
        category="infrastructure",
        title="Test",
        body="Body",
        source="system",
    )
    db_session.add(notif)
    await db_session.flush()

    old_time = datetime.now(timezone.utc) - timedelta(minutes=10)

    # Eligible: failed, retry_count=0
    log1 = EmailLog(
        to_address="a@test.com",
        subject="Test",
        provider="resend",
        status="failed",
        retry_count=0,
        notification_id=notif.id,
        template="critical_alert",
        created_at=old_time,
    )
    db_session.add(log1)

    # Not eligible: sent
    log2 = EmailLog(
        to_address="b@test.com",
        subject="Test",
        provider="resend",
        status="sent",
        retry_count=0,
        created_at=old_time,
    )
    db_session.add(log2)

    # Not eligible: retry_count >= 3
    log3 = EmailLog(
        to_address="c@test.com",
        subject="Test",
        provider="resend",
        status="failed",
        retry_count=3,
        created_at=old_time,
    )
    db_session.add(log3)

    # Eligible: failed, retry_count=1
    log4 = EmailLog(
        to_address="d@test.com",
        subject="Test",
        provider="resend",
        status="failed",
        retry_count=1,
        template="test_email",
        created_at=old_time,
    )
    db_session.add(log4)

    await db_session.flush()

    repo = EmailLogRepository(db_session)
    pending = await repo.get_pending_retries(limit=50)

    assert len(pending) == 2
    ids = {e.id for e in pending}
    assert log1.id in ids
    assert log4.id in ids
    assert log2.id not in ids
    assert log3.id not in ids


@pytest.mark.asyncio
async def test_get_pending_retries_respects_min_age(db_session: AsyncSession):
    """Entries created less than min_age_minutes ago are excluded."""
    recent_time = datetime.now(timezone.utc) - timedelta(minutes=2)

    log = EmailLog(
        to_address="recent@test.com",
        subject="Test",
        provider="resend",
        status="failed",
        retry_count=0,
        template="test_email",
        created_at=recent_time,
    )
    db_session.add(log)
    await db_session.flush()

    repo = EmailLogRepository(db_session)
    pending = await repo.get_pending_retries(limit=50, min_age_minutes=5)

    assert len(pending) == 0


@pytest.mark.asyncio
async def test_get_pending_retries_respects_limit(db_session: AsyncSession):
    """Limit is respected."""
    old_time = datetime.now(timezone.utc) - timedelta(minutes=10)

    for i in range(5):
        log = EmailLog(
            to_address=f"user{i}@test.com",
            subject="Test",
            provider="resend",
            status="failed",
            retry_count=0,
            template="test_email",
            created_at=old_time,
        )
        db_session.add(log)

    await db_session.flush()

    repo = EmailLogRepository(db_session)
    pending = await repo.get_pending_retries(limit=2)

    assert len(pending) == 2


@pytest.mark.asyncio
async def test_get_pending_retries_ordered_by_created_at_asc(db_session: AsyncSession):
    """Oldest entries first (created_at ascending)."""
    base = datetime.now(timezone.utc) - timedelta(minutes=30)

    log1 = EmailLog(
        to_address="first@test.com",
        subject="Test",
        provider="resend",
        status="failed",
        retry_count=0,
        template="test_email",
        created_at=base,
    )
    log2 = EmailLog(
        to_address="second@test.com",
        subject="Test",
        provider="resend",
        status="failed",
        retry_count=0,
        template="test_email",
        created_at=base + timedelta(minutes=5),
    )
    log3 = EmailLog(
        to_address="third@test.com",
        subject="Test",
        provider="resend",
        status="failed",
        retry_count=0,
        template="test_email",
        created_at=base + timedelta(minutes=10),
    )
    db_session.add_all([log1, log2, log3])
    await db_session.flush()

    repo = EmailLogRepository(db_session)
    pending = await repo.get_pending_retries(limit=50)

    assert len(pending) == 3
    assert pending[0].to_address == "first@test.com"
    assert pending[1].to_address == "second@test.com"
    assert pending[2].to_address == "third@test.com"
