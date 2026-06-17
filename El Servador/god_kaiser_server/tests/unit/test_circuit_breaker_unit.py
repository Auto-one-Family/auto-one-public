"""
Unit Tests: Circuit Breaker

Tests für die Circuit Breaker Implementierung gemäß Paket C Anforderungen.
Testet alle State Transitions, Threshold-Verhalten und Recovery-Mechanismen.
"""

import asyncio
import pytest
import time

from src.core.resilience import (
    CircuitBreaker,
    CircuitState,
    CircuitBreakerOpenError,
)


class TestCircuitBreakerBasic:
    """Basic circuit breaker functionality tests."""

    def test_circuit_breaker_initialization(self):
        """Test circuit breaker initializes in CLOSED state."""
        cb = CircuitBreaker(
            name="test",
            failure_threshold=3,
            recovery_timeout=10.0,
        )

        assert cb.get_state() == CircuitState.CLOSED
        assert cb.failure_count == 0
        assert cb.allow_request() is True

    def test_circuit_breaker_opens_after_threshold(self):
        """Test circuit breaker opens after failure threshold exceeded."""
        cb = CircuitBreaker(
            name="test",
            failure_threshold=3,
            recovery_timeout=10.0,
        )

        # Record 3 failures
        for i in range(3):
            cb.record_failure()

        # Should be OPEN now
        assert cb.get_state() == CircuitState.OPEN
        assert cb.failure_count == 3
        assert cb.allow_request() is False

    def test_circuit_breaker_rejects_requests_when_open(self):
        """Test circuit breaker rejects requests in OPEN state."""
        cb = CircuitBreaker(
            name="test",
            failure_threshold=2,
            recovery_timeout=10.0,
        )

        # Open the breaker
        cb.record_failure()
        cb.record_failure()

        assert cb.get_state() == CircuitState.OPEN

        # Requests should be rejected
        for _ in range(5):
            assert cb.allow_request() is False

        # Verify metrics
        metrics = cb.get_metrics()
        assert metrics["state"] == "open"
        assert metrics["rejected_requests"] == 0  # Synchronous allow_request doesn't track


class TestCircuitBreakerStateTransitions:
    """Test circuit breaker state machine transitions."""

    @pytest.mark.asyncio
    async def test_transition_closed_to_open(self):
        """Test CLOSED → OPEN transition."""
        cb = CircuitBreaker(
            name="test",
            failure_threshold=3,
            recovery_timeout=1.0,
        )

        assert cb.get_state() == CircuitState.CLOSED

        # Record failures
        for i in range(3):
            cb.record_failure()
            if i < 2:
                assert cb.get_state() == CircuitState.CLOSED
            else:
                assert cb.get_state() == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_transition_open_to_half_open(self):
        """Test OPEN → HALF_OPEN transition after recovery timeout."""
        cb = CircuitBreaker(
            name="test",
            failure_threshold=2,
            recovery_timeout=0.1,  # 100ms recovery timeout
        )

        # Open the breaker
        cb.record_failure()
        cb.record_failure()
        assert cb.get_state() == CircuitState.OPEN

        # Wait for recovery timeout
        await asyncio.sleep(0.15)

        # Next request should transition to HALF_OPEN
        allowed = await cb.allow_request_async()
        assert allowed is True
        assert cb.get_state() == CircuitState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_transition_half_open_to_closed_on_success(self):
        """Test HALF_OPEN → CLOSED transition on successful request."""
        cb = CircuitBreaker(
            name="test",
            failure_threshold=2,
            recovery_timeout=0.1,
            success_threshold=1,
        )

        # Open the breaker
        cb.record_failure()
        cb.record_failure()

        # Wait and transition to HALF_OPEN
        await asyncio.sleep(0.15)
        await cb.allow_request_async()
        assert cb.get_state() == CircuitState.HALF_OPEN

        # Record success → should close
        cb.record_success()
        assert cb.get_state() == CircuitState.CLOSED
        assert cb.failure_count == 0

    @pytest.mark.asyncio
    async def test_transition_half_open_to_open_on_failure(self):
        """Test HALF_OPEN → OPEN transition on failed request."""
        cb = CircuitBreaker(
            name="test",
            failure_threshold=2,
            recovery_timeout=0.1,
        )

        # Open the breaker
        cb.record_failure()
        cb.record_failure()

        # Wait and transition to HALF_OPEN
        await asyncio.sleep(0.15)
        await cb.allow_request_async()
        assert cb.get_state() == CircuitState.HALF_OPEN

        # Record failure → should go back to OPEN
        cb.record_failure()
        assert cb.get_state() == CircuitState.OPEN


class TestCircuitBreakerMetrics:
    """Test circuit breaker metrics collection."""

    def test_metrics_track_requests(self):
        """Test metrics track total requests."""
        cb = CircuitBreaker(
            name="test",
            failure_threshold=5,
        )

        # Record some successes and failures
        for _ in range(3):
            cb.record_success()
        for _ in range(2):
            cb.record_failure()

        metrics = cb.get_metrics()
        assert metrics["successful_requests"] == 3
        assert metrics["failed_requests"] == 2
        assert metrics["consecutive_successes"] == 0  # Reset by failures
        assert metrics["consecutive_failures"] == 2

    def test_metrics_track_state_transitions(self):
        """Test metrics track state transitions."""
        cb = CircuitBreaker(
            name="test",
            failure_threshold=2,
            recovery_timeout=1.0,
        )

        initial_transitions = cb.get_metrics()["state_transitions"]

        # CLOSED → OPEN
        cb.record_failure()
        cb.record_failure()

        after_open = cb.get_metrics()["state_transitions"]
        assert after_open == initial_transitions + 1

        # Manual reset: OPEN → CLOSED
        cb.reset()

        after_reset = cb.get_metrics()["state_transitions"]
        assert after_reset == after_open + 1

    def test_metrics_timestamps(self):
        """Test metrics track last failure/success timestamps."""
        cb = CircuitBreaker(name="test")

        before = time.time()

        cb.record_success()
        metrics = cb.get_metrics()
        assert metrics["last_success_time"] >= before
        assert metrics["last_failure_time"] is None

        cb.record_failure()
        metrics = cb.get_metrics()
        assert metrics["last_failure_time"] >= before


class TestCircuitBreakerManualControl:
    """Test manual circuit breaker control."""

    def test_manual_reset(self):
        """Test manual reset to CLOSED state."""
        cb = CircuitBreaker(
            name="test",
            failure_threshold=2,
        )

        # Open the breaker
        cb.record_failure()
        cb.record_failure()
        assert cb.get_state() == CircuitState.OPEN

        # Manual reset
        cb.reset()
        assert cb.get_state() == CircuitState.CLOSED
        assert cb.failure_count == 0
        assert cb.allow_request() is True

    def test_force_open(self):
        """Test forcing circuit breaker to OPEN state."""
        cb = CircuitBreaker(name="test")

        assert cb.get_state() == CircuitState.CLOSED

        # Force open
        cb.force_open()
        assert cb.allow_request() is False

        # Should remain OPEN even with successes
        cb.record_success()
        assert cb.allow_request() is False

        # Reset clears forced open
        cb.reset()
        assert cb.allow_request() is True

    @pytest.mark.asyncio
    async def test_async_reset(self):
        """Test async reset."""
        cb = CircuitBreaker(
            name="test",
            failure_threshold=2,
        )

        # Open the breaker
        cb.record_failure()
        cb.record_failure()

        # Async reset
        await cb.reset_async()
        assert cb.get_state() == CircuitState.CLOSED


class TestCircuitBreakerSuccessReset:
    """Test success resets failure count in CLOSED state."""

    def test_success_resets_failure_count(self):
        """Test that success in CLOSED state resets failure count."""
        cb = CircuitBreaker(
            name="test",
            failure_threshold=5,
        )

        # Record some failures (but not enough to open)
        cb.record_failure()
        cb.record_failure()
        assert cb.failure_count == 2
        assert cb.get_state() == CircuitState.CLOSED

        # Record success → should reset failure count
        cb.record_success()
        assert cb.failure_count == 0
        assert cb.get_state() == CircuitState.CLOSED
