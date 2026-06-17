"""
Unit Tests: Timeout Handling

Tests für Timeout-Mechanismen gemäß Paket C.
"""

import asyncio
import pytest

from src.core.resilience import (
    timeout,
    timeout_with_fallback,
    with_timeout,
    with_timeout_fallback,
    OperationTimeoutError,
    Timeouts,
)


class TestTimeoutDecorator:
    """Test timeout decorator."""

    @pytest.mark.asyncio
    async def test_timeout_succeeds_within_limit(self):
        """Test function completes within timeout."""

        @timeout(seconds=1.0)
        async def fast_function():
            await asyncio.sleep(0.1)
            return "success"

        result = await fast_function()
        assert result == "success"

    @pytest.mark.asyncio
    async def test_timeout_raises_on_exceeded(self):
        """Test timeout raises OperationTimeoutError when exceeded."""

        @timeout(seconds=0.1)
        async def slow_function():
            await asyncio.sleep(1.0)
            return "never"

        with pytest.raises(OperationTimeoutError) as exc_info:
            await slow_function()

        assert exc_info.value.operation == "slow_function"
        assert exc_info.value.timeout_seconds == 0.1

    @pytest.mark.asyncio
    async def test_timeout_custom_error_message(self):
        """Test timeout uses custom error message."""

        @timeout(seconds=0.1, error_message="Custom timeout message")
        async def slow_func():
            await asyncio.sleep(1.0)

        with pytest.raises(OperationTimeoutError) as exc_info:
            await slow_func()

        assert "Custom timeout message" in str(exc_info.value.details)

    @pytest.mark.asyncio
    async def test_timeout_callback(self):
        """Test timeout calls callback on timeout."""
        callback_called = []

        def on_timeout_callback(func_name, timeout):
            callback_called.append({"func": func_name, "timeout": timeout})

        @timeout(seconds=0.1, on_timeout=on_timeout_callback)
        async def slow_func():
            await asyncio.sleep(1.0)

        with pytest.raises(OperationTimeoutError):
            await slow_func()

        assert len(callback_called) == 1
        assert callback_called[0]["func"] == "slow_func"
        assert callback_called[0]["timeout"] == 0.1


class TestTimeoutWithFallback:
    """Test timeout decorator with fallback value."""

    @pytest.mark.asyncio
    async def test_fallback_returns_value_on_timeout(self):
        """Test fallback returns default value on timeout."""

        @timeout_with_fallback(seconds=0.1, fallback_value="fallback")
        async def slow_func():
            await asyncio.sleep(1.0)
            return "never"

        result = await slow_func()
        assert result == "fallback"

    @pytest.mark.asyncio
    async def test_fallback_returns_factory_value(self):
        """Test fallback uses factory function."""

        @timeout_with_fallback(seconds=0.1, fallback_factory=lambda: {"cached": True})
        async def slow_func():
            await asyncio.sleep(1.0)
            return {"cached": False}

        result = await slow_func()
        assert result == {"cached": True}

    @pytest.mark.asyncio
    async def test_fallback_returns_normal_on_success(self):
        """Test fallback returns normal value if no timeout."""

        @timeout_with_fallback(seconds=1.0, fallback_value="fallback")
        async def fast_func():
            await asyncio.sleep(0.1)
            return "success"

        result = await fast_func()
        assert result == "success"


class TestWithTimeoutFunction:
    """Test with_timeout utility function."""

    @pytest.mark.asyncio
    async def test_with_timeout_success(self):
        """Test with_timeout succeeds within limit."""

        async def fast_operation():
            await asyncio.sleep(0.1)
            return "done"

        result = await with_timeout(fast_operation(), seconds=1.0, operation="fast_op")
        assert result == "done"

    @pytest.mark.asyncio
    async def test_with_timeout_raises(self):
        """Test with_timeout raises on timeout."""

        async def slow_operation():
            await asyncio.sleep(1.0)

        with pytest.raises(OperationTimeoutError) as exc_info:
            await with_timeout(slow_operation(), seconds=0.1, operation="slow_op")

        assert exc_info.value.operation == "slow_op"


class TestWithTimeoutFallbackFunction:
    """Test with_timeout_fallback utility function."""

    @pytest.mark.asyncio
    async def test_with_timeout_fallback_returns_fallback(self):
        """Test with_timeout_fallback returns fallback on timeout."""

        async def slow_operation():
            await asyncio.sleep(1.0)
            return "never"

        result = await with_timeout_fallback(
            slow_operation(), seconds=0.1, fallback_value=[], operation="slow_op"
        )
        assert result == []


class TestPredefinedTimeouts:
    """Test predefined timeout values."""

    def test_timeouts_class_values(self):
        """Test Timeouts class has correct predefined values."""
        assert Timeouts.MQTT_PUBLISH == 5.0
        assert Timeouts.DB_QUERY_SIMPLE == 5.0
        assert Timeouts.DB_QUERY_COMPLEX == 30.0
        assert Timeouts.EXTERNAL_API == 10.0
        assert Timeouts.WEBSOCKET_SEND == 2.0
        assert Timeouts.SENSOR_PROCESSING == 1.0
