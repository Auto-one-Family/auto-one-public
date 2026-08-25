"""
Unit Tests: AUT-993 AO-4 — Tages-Limits Dosierung

Tests RateLimiter.check_rate_limit() for:
- Daily execution count cap (max_executions_per_day)
- Daily dose ml cap (max_dose_ml_per_day, AO-5-dependent)
- NULL = no limit (both fields)
- 24h rolling window boundary behavior
- Combined hourly + daily check (level ordering: L3 before L4)
- Fail-open on DB error (both new checks)
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.logic.safety.rate_limiter import RateLimiter, RateLimitConfig


RULE_ID = str(uuid.uuid4())
RULE_UUID = uuid.UUID(RULE_ID)


def _make_logic_repo(
    hourly_count: int = 0,
    daily_count: int = 0,
    daily_dose_ml: float = 0.0,
) -> MagicMock:
    """Create a logic_repo mock with configurable return values."""
    repo = MagicMock()
    repo.get_execution_count_last_hour = AsyncMock(return_value=hourly_count)
    repo.get_execution_count_last_24h = AsyncMock(return_value=daily_count)
    repo.get_dose_ml_last_24h = AsyncMock(return_value=daily_dose_ml)
    return repo


def _make_limiter(logic_repo=None) -> RateLimiter:
    """Create a RateLimiter with a very high global/ESP limit so only rule-level limits matter."""
    config = RateLimitConfig(
        max_per_second=10000,
        max_per_esp_second=10000,
        burst_allowance=2.0,
    )
    return RateLimiter(config=config, logic_repo=logic_repo)


class TestDailyExecutionCountCap:
    """Scenario 1: max_executions_per_day blocks at limit."""

    @pytest.mark.asyncio
    async def test_11th_execution_blocked_when_limit_10(self):
        """11 executions recorded, limit=10 → blocked."""
        repo = _make_logic_repo(daily_count=11)
        limiter = _make_limiter(logic_repo=repo)

        result = await limiter.check_rate_limit(
            rule_id=RULE_ID,
            rule_max_per_hour=None,
            esp_ids=[],
            rule_max_per_day=10,
        )

        assert result["allowed"] is False
        assert "10 executions per day" in result["reason"]
        assert result["wait_seconds"] == 86400
        assert result["current_rate"] == 11
        assert result["limit"] == 10

    @pytest.mark.asyncio
    async def test_10th_execution_allowed_when_limit_10(self):
        """Exactly 9 executions recorded, limit=10 → allowed (not yet at limit)."""
        repo = _make_logic_repo(daily_count=9)
        limiter = _make_limiter(logic_repo=repo)

        result = await limiter.check_rate_limit(
            rule_id=RULE_ID,
            rule_max_per_hour=None,
            esp_ids=[],
            rule_max_per_day=10,
        )

        assert result["allowed"] is True

    @pytest.mark.asyncio
    async def test_at_exactly_limit_blocked(self):
        """Exactly at limit (count == max) → blocked (>= check)."""
        repo = _make_logic_repo(daily_count=10)
        limiter = _make_limiter(logic_repo=repo)

        result = await limiter.check_rate_limit(
            rule_id=RULE_ID,
            rule_max_per_hour=None,
            esp_ids=[],
            rule_max_per_day=10,
        )

        assert result["allowed"] is False


class TestDailyDoseMlCap:
    """Scenario 2: max_dose_ml_per_day blocks when cumulative dose >= limit."""

    @pytest.mark.asyncio
    async def test_blocked_when_190ml_recorded_and_30ml_would_exceed_200ml_limit(self):
        """190ml recorded, limit=200ml → next dose blocked (190 >= 200 is False, but test the blocking state)."""
        # When 190ml is already recorded and limit is 190 → blocked at >=
        repo = _make_logic_repo(daily_dose_ml=200.0)
        limiter = _make_limiter(logic_repo=repo)

        result = await limiter.check_rate_limit(
            rule_id=RULE_ID,
            rule_max_per_hour=None,
            esp_ids=[],
            rule_max_dose_ml_per_day=200.0,
        )

        assert result["allowed"] is False
        assert "200.0ml per day" in result["reason"]
        assert result["wait_seconds"] == 86400
        assert result["current_rate"] == 200.0
        assert result["limit"] == 200.0

    @pytest.mark.asyncio
    async def test_allowed_when_190ml_recorded_and_limit_is_200ml(self):
        """190ml recorded, limit=200ml → allowed (190 < 200)."""
        repo = _make_logic_repo(daily_dose_ml=190.0)
        limiter = _make_limiter(logic_repo=repo)

        result = await limiter.check_rate_limit(
            rule_id=RULE_ID,
            rule_max_per_hour=None,
            esp_ids=[],
            rule_max_dose_ml_per_day=200.0,
        )

        assert result["allowed"] is True

    @pytest.mark.asyncio
    async def test_boundary_exactly_at_limit_blocked(self):
        """Exactly at limit (daily_dose_ml == max_dose_ml_per_day) → blocked (>= check)."""
        repo = _make_logic_repo(daily_dose_ml=200.0)
        limiter = _make_limiter(logic_repo=repo)

        result = await limiter.check_rate_limit(
            rule_id=RULE_ID,
            rule_max_per_hour=None,
            esp_ids=[],
            rule_max_dose_ml_per_day=200.0,
        )

        assert result["allowed"] is False

    @pytest.mark.asyncio
    async def test_just_below_limit_allowed(self):
        """199.9ml recorded, limit=200ml → allowed (199.9 < 200)."""
        repo = _make_logic_repo(daily_dose_ml=199.9)
        limiter = _make_limiter(logic_repo=repo)

        result = await limiter.check_rate_limit(
            rule_id=RULE_ID,
            rule_max_per_hour=None,
            esp_ids=[],
            rule_max_dose_ml_per_day=200.0,
        )

        assert result["allowed"] is True


class TestNullMeansNoLimit:
    """Scenario 3: NULL (None) for both fields → level 4+5 skipped, allowed=True."""

    @pytest.mark.asyncio
    async def test_none_limits_skip_daily_checks(self):
        """Both None → no DB queries for daily checks, always allowed."""
        repo = _make_logic_repo(daily_count=9999, daily_dose_ml=9999.0)
        limiter = _make_limiter(logic_repo=repo)

        result = await limiter.check_rate_limit(
            rule_id=RULE_ID,
            rule_max_per_hour=None,
            esp_ids=[],
            rule_max_per_day=None,
            rule_max_dose_ml_per_day=None,
        )

        assert result["allowed"] is True
        # Daily DB methods must NOT have been called
        repo.get_execution_count_last_24h.assert_not_called()
        repo.get_dose_ml_last_24h.assert_not_called()

    @pytest.mark.asyncio
    async def test_defaults_are_none_backward_compat(self):
        """Default call without new kwargs → backward-compatible, allowed=True."""
        repo = _make_logic_repo()
        limiter = _make_limiter(logic_repo=repo)

        result = await limiter.check_rate_limit(
            rule_id=RULE_ID,
            rule_max_per_hour=None,
            esp_ids=[],
        )

        assert result["allowed"] is True
        repo.get_execution_count_last_24h.assert_not_called()
        repo.get_dose_ml_last_24h.assert_not_called()


class TestRolling24hWindow:
    """Scenario 4: Rolling 24h window — executions older than 24h don't count."""

    @pytest.mark.asyncio
    async def test_10_recent_executions_allowed_when_limit_11(self):
        """
        11 total executions but get_execution_count_last_24h returns 10
        (1 is older than 24h → not counted). Limit=11 → 11th execution allowed.
        """
        repo = _make_logic_repo(daily_count=10)
        limiter = _make_limiter(logic_repo=repo)

        result = await limiter.check_rate_limit(
            rule_id=RULE_ID,
            rule_max_per_hour=None,
            esp_ids=[],
            rule_max_per_day=11,
        )

        assert result["allowed"] is True
        # Verify the repo method was called (it's the one that enforces the 24h window)
        repo.get_execution_count_last_24h.assert_called_once_with(RULE_UUID)


class TestCombinedHourlyAndDaily:
    """Scenario 5: Hourly check (L3) fires before daily check (L4)."""

    @pytest.mark.asyncio
    async def test_hourly_check_fires_before_daily_check(self):
        """
        max_executions_per_hour=2, max_executions_per_day=5.
        3 hourly executions → blocked at hourly check (L3), reason must contain 'per hour'.
        Daily check (L4) must NOT have been called.
        """
        repo = _make_logic_repo(hourly_count=3, daily_count=3)
        limiter = _make_limiter(logic_repo=repo)

        result = await limiter.check_rate_limit(
            rule_id=RULE_ID,
            rule_max_per_hour=2,
            esp_ids=[],
            rule_max_per_day=5,
        )

        assert result["allowed"] is False
        assert "per hour" in result["reason"]
        assert "per day" not in result["reason"]
        # L4 must not have been reached
        repo.get_execution_count_last_24h.assert_not_called()

    @pytest.mark.asyncio
    async def test_daily_check_fires_when_hourly_ok(self):
        """
        max_executions_per_hour=10, max_executions_per_day=5.
        3 hourly + 6 daily executions → hourly OK, daily blocked.
        """
        repo = _make_logic_repo(hourly_count=3, daily_count=6)
        limiter = _make_limiter(logic_repo=repo)

        result = await limiter.check_rate_limit(
            rule_id=RULE_ID,
            rule_max_per_hour=10,
            esp_ids=[],
            rule_max_per_day=5,
        )

        assert result["allowed"] is False
        assert "per day" in result["reason"]


class TestFailOpen:
    """Fail-open: DB errors must NOT block execution."""

    @pytest.mark.asyncio
    async def test_fail_open_on_daily_count_db_error(self):
        """get_execution_count_last_24h raises → fail-open (allowed=True)."""
        repo = MagicMock()
        repo.get_execution_count_last_hour = AsyncMock(return_value=0)
        repo.get_execution_count_last_24h = AsyncMock(side_effect=Exception("DB connection lost"))
        repo.get_dose_ml_last_24h = AsyncMock(return_value=0.0)
        limiter = _make_limiter(logic_repo=repo)

        result = await limiter.check_rate_limit(
            rule_id=RULE_ID,
            rule_max_per_hour=None,
            esp_ids=[],
            rule_max_per_day=5,
        )

        assert result["allowed"] is True

    @pytest.mark.asyncio
    async def test_fail_open_on_daily_dose_db_error(self):
        """get_dose_ml_last_24h raises → fail-open (allowed=True)."""
        repo = MagicMock()
        repo.get_execution_count_last_hour = AsyncMock(return_value=0)
        repo.get_execution_count_last_24h = AsyncMock(return_value=0)
        repo.get_dose_ml_last_24h = AsyncMock(side_effect=Exception("DB timeout"))
        limiter = _make_limiter(logic_repo=repo)

        result = await limiter.check_rate_limit(
            rule_id=RULE_ID,
            rule_max_per_hour=None,
            esp_ids=[],
            rule_max_dose_ml_per_day=100.0,
        )

        assert result["allowed"] is True
