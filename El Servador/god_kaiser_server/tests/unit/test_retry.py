"""
Unit Tests: Retry Decorator

Tests für Retry-Mechanismus mit Exponential Backoff gemäß Paket C.
"""

import asyncio
import pytest
import time

from src.core.resilience import (
    retry,
    retry_sync,
    calculate_backoff_delay,
    RetryExhaustedError,
)


class TestBackoffCalculation:
    """Test exponential backoff delay calculation."""

    def test_exponential_backoff_without_jitter(self):
        """Test exponential backoff calculation."""
        # Attempt 0: 1.0 * 2^0 = 1.0
        assert calculate_backoff_delay(0, base_delay=1.0, exponential_base=2.0, jitter=False) == 1.0

        # Attempt 1: 1.0 * 2^1 = 2.0
        assert calculate_backoff_delay(1, base_delay=1.0, exponential_base=2.0, jitter=False) == 2.0

        # Attempt 2: 1.0 * 2^2 = 4.0
        assert calculate_backoff_delay(2, base_delay=1.0, exponential_base=2.0, jitter=False) == 4.0

        # Attempt 3: 1.0 * 2^3 = 8.0
        assert calculate_backoff_delay(3, base_delay=1.0, exponential_base=2.0, jitter=False) == 8.0

    def test_backoff_respects_max_delay(self):
        """Test backoff is capped at max_delay."""
        # 1.0 * 2^10 = 1024, but max_delay=30
        delay = calculate_backoff_delay(10, base_delay=1.0, max_delay=30.0, jitter=False)
        assert delay == 30.0

    def test_jitter_adds_randomness(self):
        """Test jitter adds randomness to delay."""
        delays = [calculate_backoff_delay(3, base_delay=1.0, jitter=True) for _ in range(10)]

        # Should have some variation
        assert len(set(delays)) > 1

        # All should be >= base delay (8.0 for attempt 3)
        assert all(d >= 8.0 for d in delays)

        # All should be <= base delay + jitter (8.0 + 0.8 = 8.8)
        assert all(d <= 8.8 for d in delays)


class TestRetryDecorator:
    """Test async retry decorator."""

    @pytest.mark.asyncio
    async def test_retry_succeeds_immediately(self):
        """Test function succeeds on first attempt."""
        attempts = []

        @retry(max_attempts=3, base_delay=0.01)
        async def success_function():
            attempts.append(1)
            return "success"

        result = await success_function()
        assert result == "success"
        assert len(attempts) == 1

    @pytest.mark.asyncio
    async def test_retry_succeeds_after_failures(self):
        """Test function succeeds after transient failures."""
        attempts = []

        @retry(max_attempts=3, base_delay=0.01)
        async def flaky_function():
            attempts.append(1)
            if len(attempts) < 3:
                raise ConnectionError("Transient failure")
            return "success"

        result = await flaky_function()
        assert result == "success"
        assert len(attempts) == 3

    @pytest.mark.asyncio
    async def test_retry_fails_after_max_attempts(self):
        """Test retry gives up after max attempts."""
        attempts = []

        @retry(max_attempts=3, base_delay=0.01)
        async def always_fails():
            attempts.append(1)
            raise ConnectionError("Persistent failure")

        with pytest.raises(ConnectionError, match="Persistent failure"):
            await always_fails()

        assert len(attempts) == 3

    @pytest.mark.asyncio
    async def test_retry_only_retries_specified_exceptions(self):
        """Test retry only retries specified exception types."""
        attempts = []

        @retry(max_attempts=3, base_delay=0.01, retryable_exceptions=(ConnectionError,))
        async def wrong_exception():
            attempts.append(1)
            raise ValueError("Non-retryable")

        # Should fail immediately (ValueError not retryable)
        with pytest.raises(ValueError):
            await wrong_exception()

        assert len(attempts) == 1

    @pytest.mark.asyncio
    async def test_retry_respects_exponential_backoff(self):
        """Test retry waits with exponential backoff."""
        attempts = []
        attempt_times = []

        @retry(max_attempts=4, base_delay=0.1, exponential_base=2.0, jitter=False)
        async def timed_failure():
            attempt_times.append(time.time())
            attempts.append(1)
            if len(attempts) < 4:
                raise ConnectionError("Retry")
            return "done"

        await timed_failure()

        # Check delays between attempts
        # Attempt 1 → 2: ~0.1s
        # Attempt 2 → 3: ~0.2s
        # Attempt 3 → 4: ~0.4s
        delays = [attempt_times[i + 1] - attempt_times[i] for i in range(len(attempt_times) - 1)]

        assert delays[0] >= 0.09  # ~0.1s
        assert delays[1] >= 0.18  # ~0.2s
        assert delays[2] >= 0.38  # ~0.4s

    @pytest.mark.asyncio
    async def test_retry_callback(self):
        """Test retry calls callback on each attempt."""
        callback_calls = []

        def on_retry_callback(attempt, exception, delay):
            callback_calls.append(
                {"attempt": attempt, "exception": type(exception).__name__, "delay": delay}
            )

        @retry(max_attempts=3, base_delay=0.01, on_retry=on_retry_callback)
        async def fails_twice():
            if len(callback_calls) < 2:
                raise ConnectionError("Retry")
            return "success"

        await fails_twice()

        assert len(callback_calls) == 2
        assert callback_calls[0]["attempt"] == 1
        assert callback_calls[0]["exception"] == "ConnectionError"


class TestRetrySyncDecorator:
    """Test synchronous retry decorator."""

    def test_retry_sync_succeeds_after_failures(self):
        """Test sync retry succeeds after failures."""
        attempts = []

        @retry_sync(max_attempts=3, base_delay=0.01)
        def flaky_sync():
            attempts.append(1)
            if len(attempts) < 3:
                raise ConnectionError("Retry")
            return "success"

        result = flaky_sync()
        assert result == "success"
        assert len(attempts) == 3

    def test_retry_sync_fails_after_max_attempts(self):
        """Test sync retry fails after max attempts."""
        attempts = []

        @retry_sync(max_attempts=2, base_delay=0.01)
        def always_fails_sync():
            attempts.append(1)
            raise OSError("Always fails")

        with pytest.raises(OSError):
            always_fails_sync()

        assert len(attempts) == 2


class TestRetryContext:
    """Test RetryContext for manual control."""

    @pytest.mark.asyncio
    async def test_retry_context_manual_control(self):
        """Test manual retry control with RetryContext."""
        from src.core.resilience.retry import RetryContext

        attempts = []
        ctx = RetryContext(max_attempts=3, base_delay=0.01)

        async with ctx:
            while ctx.should_retry():
                attempts.append(1)
                try:
                    if len(attempts) < 3:
                        raise ConnectionError("Retry")
                    break
                except ConnectionError as e:
                    if ctx.should_retry():
                        await ctx.handle_error(e)
                    else:
                        raise

        assert len(attempts) == 3

    @pytest.mark.asyncio
    async def test_retry_context_exhausted(self):
        """Test RetryContext raises when exhausted."""
        from src.core.resilience.retry import RetryContext

        attempts = []
        ctx = RetryContext(max_attempts=2, base_delay=0.01)

        with pytest.raises(RetryExhaustedError):
            async with ctx:
                while ctx.should_retry():
                    attempts.append(1)
                    try:
                        raise ConnectionError("Always fails")
                    except ConnectionError as e:
                        await ctx.handle_error(e)

        assert len(attempts) == 2
