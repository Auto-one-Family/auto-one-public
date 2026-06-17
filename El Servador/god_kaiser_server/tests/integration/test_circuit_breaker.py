"""
Circuit Breaker Tests for Server-Side Resilience Patterns.

Tests the server's CircuitBreaker implementation which mirrors ESP32 patterns:
- MQTT CB: 5 failures / 30s recovery
- WiFi CB: 10 failures / 60s recovery
- PiServer CB: 5 failures / 60s recovery

The server implements a generic CircuitBreaker class in src.core.resilience
with configurable thresholds. These tests validate state transitions,
metrics, and integration with the ResilienceRegistry.
"""

import time
import asyncio
import pytest
from unittest.mock import patch

from src.core.resilience import (
    CircuitBreaker,
    CircuitState,
    CircuitBreakerConfig,
    ResilienceRegistry,
    CircuitBreakerOpenError,
    ServiceUnavailableError,
    circuit_breaker_decorator,
)


class TestCircuitBreakerStateMachine:
    """Core state machine: CLOSED → OPEN → HALF_OPEN → CLOSED."""

    def test_initial_state_is_closed(self):
        """Circuit breaker starts in CLOSED state."""
        cb = CircuitBreaker("test_init", failure_threshold=5, recovery_timeout=30.0)
        assert cb.get_state() == CircuitState.CLOSED
        assert cb.failure_count == 0
        assert cb.is_open is False

    def test_stays_closed_below_threshold(self):
        """Failures below threshold keep circuit CLOSED."""
        cb = CircuitBreaker("test_below", failure_threshold=5)

        for _ in range(4):
            cb.record_failure()

        assert cb.get_state() == CircuitState.CLOSED
        assert cb.failure_count == 4

    def test_opens_at_failure_threshold(self):
        """Circuit opens when failure count reaches threshold."""
        cb = CircuitBreaker("test_open", failure_threshold=5)

        for _ in range(5):
            cb.record_failure()

        assert cb.get_state() == CircuitState.OPEN
        assert cb.is_open is True

    def test_success_resets_failure_count(self):
        """A success in CLOSED state resets the failure counter."""
        cb = CircuitBreaker("test_reset", failure_threshold=5)

        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        assert cb.failure_count == 3

        cb.record_success()
        assert cb.failure_count == 0

    def test_open_rejects_requests(self):
        """OPEN state rejects all requests immediately."""
        cb = CircuitBreaker("test_reject", failure_threshold=3)

        for _ in range(3):
            cb.record_failure()

        assert cb.get_state() == CircuitState.OPEN
        assert cb.allow_request() is False

    def test_open_transitions_to_half_open_after_recovery_timeout(self):
        """After recovery_timeout, OPEN transitions to HALF_OPEN."""
        cb = CircuitBreaker(
            "test_half_open",
            failure_threshold=3,
            recovery_timeout=0.1,  # 100ms for fast test
        )

        for _ in range(3):
            cb.record_failure()
        assert cb.get_state() == CircuitState.OPEN

        # Wait for recovery timeout
        time.sleep(0.15)

        # allow_request checks elapsed time and allows through
        assert cb.allow_request() is True

    @pytest.mark.asyncio
    async def test_async_open_to_half_open_transition(self):
        """Async allow_request_async transitions OPEN → HALF_OPEN."""
        cb = CircuitBreaker(
            "test_async_half",
            failure_threshold=3,
            recovery_timeout=0.1,
        )

        for _ in range(3):
            cb.record_failure()
        assert cb.get_state() == CircuitState.OPEN

        await asyncio.sleep(0.15)

        allowed = await cb.allow_request_async()
        assert allowed is True
        assert cb.get_state() == CircuitState.HALF_OPEN

    def test_half_open_closes_on_success(self):
        """Success in HALF_OPEN transitions to CLOSED."""
        cb = CircuitBreaker(
            "test_close",
            failure_threshold=3,
            recovery_timeout=0.01,
            success_threshold=1,
        )

        for _ in range(3):
            cb.record_failure()

        time.sleep(0.02)
        # Manually set to HALF_OPEN for deterministic test
        cb._state = CircuitState.HALF_OPEN
        cb._state_changed_at = time.time()

        cb.record_success()
        assert cb.get_state() == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_half_open_reopens_on_failure(self):
        """Failure in HALF_OPEN transitions back to OPEN."""
        cb = CircuitBreaker("test_reopen", failure_threshold=3)

        # Force to HALF_OPEN
        cb._state = CircuitState.HALF_OPEN
        cb._state_changed_at = time.time()

        cb.record_failure()
        assert cb.get_state() == CircuitState.OPEN


class TestCircuitBreakerMQTTConfig:
    """Tests with MQTT-like configuration (5 failures / 30s recovery)."""

    def test_mqtt_config_values(self):
        """Verify MQTT circuit breaker uses documented thresholds."""
        cb = CircuitBreaker(
            "mqtt",
            failure_threshold=5,
            recovery_timeout=30.0,
            half_open_timeout=10.0,
        )

        assert cb.config.failure_threshold == 5
        assert cb.config.recovery_timeout == 30.0
        assert cb.config.half_open_timeout == 10.0

    def test_mqtt_needs_exactly_5_failures_to_open(self):
        """MQTT CB opens after exactly 5 failures."""
        cb = CircuitBreaker("mqtt_test", failure_threshold=5, recovery_timeout=30.0)

        for i in range(4):
            cb.record_failure()
            assert cb.get_state() == CircuitState.CLOSED, f"Should be CLOSED after {i+1} failures"

        cb.record_failure()
        assert cb.get_state() == CircuitState.OPEN


class TestCircuitBreakerWiFiConfig:
    """Tests with WiFi-like configuration (10 failures / 60s recovery)."""

    def test_wifi_needs_10_failures_to_open(self):
        """WiFi CB has higher tolerance - 10 failures needed."""
        cb = CircuitBreaker(
            "wifi_test",
            failure_threshold=10,
            recovery_timeout=60.0,
            half_open_timeout=15.0,
        )

        for i in range(9):
            cb.record_failure()
            assert cb.get_state() == CircuitState.CLOSED

        cb.record_failure()
        assert cb.get_state() == CircuitState.OPEN


class TestCircuitBreakerMetrics:
    """Test metrics collection and reporting."""

    def test_metrics_track_all_operations(self):
        """Metrics accurately track successes, failures, rejections."""
        cb = CircuitBreaker("metrics_test", failure_threshold=3)

        # Record operations
        cb.record_success()
        cb.record_success()
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()  # Opens circuit

        metrics = cb.get_metrics()

        assert metrics["successful_requests"] == 2
        assert metrics["failed_requests"] == 3
        assert metrics["state"] == "open"
        assert metrics["failure_count"] == 3
        assert metrics["failure_threshold"] == 3

    def test_metrics_track_consecutive_counts(self):
        """Metrics track consecutive successes and failures."""
        cb = CircuitBreaker("consec_test", failure_threshold=10)

        cb.record_success()
        cb.record_success()
        cb.record_success()

        metrics = cb.get_metrics()
        assert metrics["consecutive_successes"] == 3
        assert metrics["consecutive_failures"] == 0

        cb.record_failure()

        metrics = cb.get_metrics()
        assert metrics["consecutive_successes"] == 0
        assert metrics["consecutive_failures"] == 1

    def test_metrics_track_state_transitions(self):
        """Metrics count state transitions."""
        cb = CircuitBreaker("trans_test", failure_threshold=2)

        initial_transitions = cb.get_metrics()["state_transitions"]

        cb.record_failure()
        cb.record_failure()  # CLOSED → OPEN

        assert cb.get_metrics()["state_transitions"] == initial_transitions + 1

    def test_metrics_include_config(self):
        """Metrics include the circuit breaker configuration."""
        cb = CircuitBreaker(
            "config_test",
            failure_threshold=5,
            recovery_timeout=30.0,
            half_open_timeout=10.0,
        )

        metrics = cb.get_metrics()
        assert "config" in metrics
        assert metrics["config"]["failure_threshold"] == 5
        assert metrics["config"]["recovery_timeout"] == 30.0


class TestCircuitBreakerForceAndReset:
    """Test manual force open and reset operations."""

    def test_force_open(self):
        """force_open immediately blocks all requests."""
        cb = CircuitBreaker("force_test", failure_threshold=5)
        assert cb.allow_request() is True

        cb.force_open()

        assert cb.is_open is True
        assert cb.allow_request() is False

    def test_reset_clears_everything(self):
        """reset returns to CLOSED with zero failure count."""
        cb = CircuitBreaker("reset_test", failure_threshold=3)

        for _ in range(3):
            cb.record_failure()
        assert cb.get_state() == CircuitState.OPEN

        cb.reset()

        assert cb.get_state() == CircuitState.CLOSED
        assert cb.failure_count == 0
        assert cb.is_open is False
        assert cb.allow_request() is True

    def test_reset_clears_force_open(self):
        """reset also clears the forced_open flag."""
        cb = CircuitBreaker("force_reset_test", failure_threshold=5)

        cb.force_open()
        assert cb.is_open is True

        cb.reset()
        assert cb.is_open is False

    @pytest.mark.asyncio
    async def test_async_force_and_reset(self):
        """Async versions of force_open and reset work correctly."""
        cb = CircuitBreaker("async_fr_test", failure_threshold=3)

        await cb.force_open_async()
        assert cb.is_open is True

        await cb.reset_async()
        assert cb.get_state() == CircuitState.CLOSED


class TestCircuitBreakerIndependence:
    """Multiple circuit breakers operate independently."""

    def test_separate_breakers_are_independent(self):
        """Failures in one breaker don't affect another."""
        mqtt_cb = CircuitBreaker("mqtt_indep", failure_threshold=5)
        wifi_cb = CircuitBreaker("wifi_indep", failure_threshold=10)
        db_cb = CircuitBreaker("db_indep", failure_threshold=5)

        # Trip only MQTT
        for _ in range(5):
            mqtt_cb.record_failure()

        assert mqtt_cb.get_state() == CircuitState.OPEN
        assert wifi_cb.get_state() == CircuitState.CLOSED
        assert db_cb.get_state() == CircuitState.CLOSED

    def test_all_can_be_open_simultaneously(self):
        """All breakers can be OPEN at the same time."""
        breakers = [CircuitBreaker(f"sim_{i}", failure_threshold=2) for i in range(3)]

        for cb in breakers:
            cb.record_failure()
            cb.record_failure()

        for cb in breakers:
            assert cb.get_state() == CircuitState.OPEN


class TestResilienceRegistryIntegration:
    """Test ResilienceRegistry with multiple circuit breakers."""

    def test_registry_is_singleton(self):
        """Registry uses singleton pattern."""
        r1 = ResilienceRegistry.get_instance()
        r2 = ResilienceRegistry.get_instance()
        assert r1 is r2

    def test_registry_health_status(self):
        """Registry aggregates health from all registered breakers."""
        registry = ResilienceRegistry.get_instance()
        health = registry.get_health_status()

        assert "healthy" in health
        assert "breakers" in health
        assert "summary" in health
        assert "total" in health["summary"]
        assert "closed" in health["summary"]

    def test_registry_reset_all(self):
        """Registry can reset all registered breakers."""
        registry = ResilienceRegistry.get_instance()

        # Register a test breaker and trip it
        test_cb = CircuitBreaker("reg_reset_test", failure_threshold=2)
        registry.register_circuit_breaker("reg_reset_test", test_cb)

        test_cb.record_failure()
        test_cb.record_failure()
        assert test_cb.get_state() == CircuitState.OPEN

        count = registry.reset_all()
        assert count >= 1

        assert test_cb.get_state() == CircuitState.CLOSED

        # Clean up
        registry.unregister("reg_reset_test")


class TestCircuitBreakerHalfOpenLimiting:
    """Test HALF_OPEN request limiting behavior."""

    @pytest.mark.asyncio
    async def test_half_open_limits_concurrent_requests(self):
        """HALF_OPEN only allows half_open_max_requests through."""
        cb = CircuitBreaker(
            "half_limit_test",
            failure_threshold=2,
            recovery_timeout=0.01,
            half_open_max_requests=1,
        )

        cb.record_failure()
        cb.record_failure()
        assert cb.get_state() == CircuitState.OPEN

        await asyncio.sleep(0.02)

        # First request transitions to HALF_OPEN and is allowed
        first = await cb.allow_request_async()
        assert first is True
        assert cb.get_state() == CircuitState.HALF_OPEN

        # Second request should be rejected (max 1 in HALF_OPEN)
        second = await cb.allow_request_async()
        assert second is False

    @pytest.mark.asyncio
    async def test_rejected_in_half_open_increments_metrics(self):
        """Rejected requests in HALF_OPEN increment rejected_requests metric."""
        cb = CircuitBreaker(
            "half_reject_test",
            failure_threshold=2,
            recovery_timeout=0.01,
            half_open_max_requests=1,
        )

        cb.record_failure()
        cb.record_failure()

        await asyncio.sleep(0.02)

        await cb.allow_request_async()  # Allowed (transitions to HALF_OPEN)
        await cb.allow_request_async()  # Rejected

        metrics = cb.get_metrics()
        assert metrics["rejected_requests"] >= 1
