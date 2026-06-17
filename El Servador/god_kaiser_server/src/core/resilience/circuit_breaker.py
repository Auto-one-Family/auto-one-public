"""
Circuit Breaker Implementation

Provides circuit breaker pattern for fault tolerance:
- CLOSED: Normal operation, requests pass through
- OPEN: Failure threshold exceeded, requests are rejected (fail-fast)
- HALF_OPEN: Recovery period, limited test requests allowed

Thread-safe implementation using asyncio.Lock for async code.

Reference: ESP32 Circuit Breaker (mqtt_client.cpp):
├── MQTT: 5 failures → 30s OPEN → 10s HALF_OPEN test
├── WiFi: 10 failures → 60s OPEN → 15s HALF_OPEN test
└── Exponential Backoff: 1s → 2s → 4s → ... → 60s max
"""

import asyncio
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from ..logging_config import get_logger
from .exceptions import CircuitBreakerOpenError

logger = get_logger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreakerMetrics:
    """Metrics collected by the circuit breaker."""

    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    rejected_requests: int = 0  # Requests rejected during OPEN state
    state_transitions: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    current_state: CircuitState = CircuitState.CLOSED
    time_in_current_state: float = 0.0
    consecutive_successes: int = 0
    consecutive_failures: int = 0


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""

    failure_threshold: int = 5
    recovery_timeout: float = 30.0  # seconds to wait in OPEN before HALF_OPEN
    half_open_timeout: float = 10.0  # seconds to wait in HALF_OPEN
    half_open_max_requests: int = 1  # max test requests in HALF_OPEN
    success_threshold: int = 1  # successes needed in HALF_OPEN to close


class CircuitBreaker:
    """
    Circuit Breaker implementation with async support.

    Features:
    - Thread-safe state management with asyncio.Lock
    - Automatic state transitions based on thresholds
    - Metrics collection for monitoring
    - Manual reset capability
    - Force open for testing

    Usage:
        breaker = CircuitBreaker("mqtt", failure_threshold=5, recovery_timeout=30)

        if breaker.allow_request():
            try:
                result = await some_operation()
                breaker.record_success()
            except Exception as e:
                breaker.record_failure()
                raise
        else:
            # Request rejected - circuit is OPEN
            handle_rejection()
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_timeout: float = 10.0,
        half_open_max_requests: int = 1,
        success_threshold: int = 1,
    ):
        """
        Initialize circuit breaker.

        Args:
            name: Unique identifier for this circuit breaker
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds to wait in OPEN before trying HALF_OPEN
            half_open_timeout: Seconds to wait for test request in HALF_OPEN
            half_open_max_requests: Maximum concurrent requests in HALF_OPEN
            success_threshold: Successes needed in HALF_OPEN to close circuit
        """
        self.name = name
        self.config = CircuitBreakerConfig(
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            half_open_timeout=half_open_timeout,
            half_open_max_requests=half_open_max_requests,
            success_threshold=success_threshold,
        )

        # State management
        self._state = CircuitState.CLOSED
        self._state_changed_at = time.time()
        self._failure_count = 0
        self._success_count_half_open = 0
        self._half_open_requests = 0

        # Thread safety
        self._lock = asyncio.Lock()

        # Metrics
        self._metrics = CircuitBreakerMetrics()

        # Force open flag (for testing)
        self._forced_open = False

        logger.info(
            f"[resilience] CircuitBreaker[{name}] initialized: "
            f"threshold={failure_threshold}, recovery={recovery_timeout}s, "
            f"half_open={half_open_timeout}s"
        )

    @property
    def is_open(self) -> bool:
        """Check if circuit breaker is in OPEN state (quick check, not thread-safe)."""
        return self._state == CircuitState.OPEN or self._forced_open

    @property
    def failure_count(self) -> int:
        """Get current failure count."""
        return self._failure_count

    @property
    def last_failure_time(self) -> Optional[float]:
        """Get timestamp of last failure."""
        return self._metrics.last_failure_time

    def allow_request(self) -> bool:
        """
        Check if a request should be allowed through the circuit breaker.

        This is the synchronous version for quick checks.
        For async code with state transitions, use allow_request_async().

        Returns:
            True if request should proceed, False if rejected
        """
        # Quick check without lock for performance
        if self._forced_open:
            return False

        current_time = time.time()

        if self._state == CircuitState.CLOSED:
            return True

        if self._state == CircuitState.OPEN:
            # Check if recovery timeout has elapsed
            elapsed = current_time - self._state_changed_at
            if elapsed >= self.config.recovery_timeout:
                # Transition to HALF_OPEN will happen in async version
                return True
            return False

        if self._state == CircuitState.HALF_OPEN:
            # Allow limited test requests
            return self._half_open_requests < self.config.half_open_max_requests

        return True

    async def allow_request_async(self) -> bool:
        """
        Check if a request should be allowed (async version with state transitions).

        This method handles automatic state transitions:
        - OPEN → HALF_OPEN when recovery timeout elapses

        Returns:
            True if request should proceed, False if rejected
        """
        async with self._lock:
            self._metrics.total_requests += 1

            if self._forced_open:
                self._metrics.rejected_requests += 1
                return False

            current_time = time.time()

            if self._state == CircuitState.CLOSED:
                return True

            if self._state == CircuitState.OPEN:
                # Check if recovery timeout has elapsed
                elapsed = current_time - self._state_changed_at
                if elapsed >= self.config.recovery_timeout:
                    # Transition to HALF_OPEN
                    self._transition_to(CircuitState.HALF_OPEN)
                    self._half_open_requests = 1
                    return True
                else:
                    self._metrics.rejected_requests += 1
                    return False

            if self._state == CircuitState.HALF_OPEN:
                # Allow limited test requests
                if self._half_open_requests < self.config.half_open_max_requests:
                    self._half_open_requests += 1
                    return True
                else:
                    self._metrics.rejected_requests += 1
                    return False

            return True

    def record_success(self) -> None:
        """
        Record a successful operation.

        In HALF_OPEN state, may transition to CLOSED if success threshold is met.
        """
        # Use synchronous approach to avoid nested async
        self._metrics.successful_requests += 1
        self._metrics.last_success_time = time.time()
        self._metrics.consecutive_successes += 1
        self._metrics.consecutive_failures = 0

        if self._state == CircuitState.HALF_OPEN:
            self._success_count_half_open += 1
            if self._success_count_half_open >= self.config.success_threshold:
                self._transition_to(CircuitState.CLOSED)
        elif self._state == CircuitState.CLOSED:
            # Reset failure count on success
            self._failure_count = 0

    async def record_success_async(self) -> None:
        """Record a successful operation (async version)."""
        async with self._lock:
            self.record_success()

    def record_failure(self) -> None:
        """
        Record a failed operation.

        May transition to OPEN if failure threshold is exceeded.
        """
        self._metrics.failed_requests += 1
        self._metrics.last_failure_time = time.time()
        self._metrics.consecutive_failures += 1
        self._metrics.consecutive_successes = 0
        self._failure_count += 1

        if self._state == CircuitState.HALF_OPEN:
            # Any failure in HALF_OPEN goes back to OPEN
            self._transition_to(CircuitState.OPEN)
        elif self._state == CircuitState.CLOSED:
            if self._failure_count >= self.config.failure_threshold:
                self._transition_to(CircuitState.OPEN)
            else:
                logger.warning(
                    f"[resilience] CircuitBreaker[{self.name}]: "
                    f"Failure recorded ({self._failure_count}/{self.config.failure_threshold})"
                )

    async def record_failure_async(self) -> None:
        """Record a failed operation (async version)."""
        async with self._lock:
            self.record_failure()

    def get_state(self) -> CircuitState:
        """Get current circuit breaker state."""
        return self._state

    def get_metrics(self) -> dict:
        """
        Get circuit breaker metrics.

        Returns:
            Dictionary with all collected metrics
        """
        current_time = time.time()
        return {
            "name": self.name,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "failure_threshold": self.config.failure_threshold,
            "total_requests": self._metrics.total_requests,
            "successful_requests": self._metrics.successful_requests,
            "failed_requests": self._metrics.failed_requests,
            "rejected_requests": self._metrics.rejected_requests,
            "state_transitions": self._metrics.state_transitions,
            "last_failure_time": self._metrics.last_failure_time,
            "last_success_time": self._metrics.last_success_time,
            "time_in_current_state": current_time - self._state_changed_at,
            "consecutive_successes": self._metrics.consecutive_successes,
            "consecutive_failures": self._metrics.consecutive_failures,
            "forced_open": self._forced_open,
            "config": {
                "failure_threshold": self.config.failure_threshold,
                "recovery_timeout": self.config.recovery_timeout,
                "half_open_timeout": self.config.half_open_timeout,
                "half_open_max_requests": self.config.half_open_max_requests,
                "success_threshold": self.config.success_threshold,
            },
        }

    def reset(self) -> None:
        """
        Manually reset the circuit breaker to CLOSED state.

        Clears failure count and forced_open flag.
        """
        previous_state = self._state
        self._state = CircuitState.CLOSED
        self._state_changed_at = time.time()
        self._failure_count = 0
        self._success_count_half_open = 0
        self._half_open_requests = 0
        self._forced_open = False
        self._metrics.state_transitions += 1

        logger.info(
            f"[resilience] CircuitBreaker[{self.name}]: "
            f"Manual reset ({previous_state.value} → closed)"
        )

    async def reset_async(self) -> None:
        """Manually reset the circuit breaker (async version)."""
        async with self._lock:
            self.reset()

    def force_open(self) -> None:
        """
        Force the circuit breaker to OPEN state (for testing).

        The circuit will remain open until reset() is called.
        """
        self._forced_open = True
        logger.warning(f"[resilience] CircuitBreaker[{self.name}]: " f"Forced OPEN (for testing)")

    async def force_open_async(self) -> None:
        """Force the circuit breaker to OPEN state (async version)."""
        async with self._lock:
            self.force_open()

    def _transition_to(self, new_state: CircuitState) -> None:
        """
        Transition to a new state.

        Handles logging and metric updates.
        """
        previous_state = self._state
        self._state = new_state
        self._state_changed_at = time.time()
        self._metrics.state_transitions += 1
        self._metrics.current_state = new_state

        # Reset state-specific counters
        if new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._success_count_half_open = 0
            self._half_open_requests = 0
        elif new_state == CircuitState.HALF_OPEN:
            self._success_count_half_open = 0
            self._half_open_requests = 0

        logger.warning(
            f"[resilience] CircuitBreaker[{self.name}]: "
            f"{previous_state.value.upper()} → {new_state.value.upper()}"
        )

    def __repr__(self) -> str:
        return (
            f"CircuitBreaker(name='{self.name}', state={self._state.value}, "
            f"failures={self._failure_count}/{self.config.failure_threshold})"
        )


def circuit_breaker_decorator(breaker_name: str):
    """
    Decorator to wrap async functions with circuit breaker protection.

    Usage:
        @circuit_breaker_decorator("database")
        async def save_data(data):
            ...

    Args:
        breaker_name: Name of the circuit breaker in the registry

    Raises:
        CircuitBreakerOpenError: If circuit breaker is OPEN
    """

    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Import here to avoid circular imports
            from .registry import ResilienceRegistry

            registry = ResilienceRegistry.get_instance()
            breaker = registry.get_circuit_breaker(breaker_name)

            if breaker is None:
                # No breaker registered, just run the function
                return await func(*args, **kwargs)

            if not await breaker.allow_request_async():
                raise CircuitBreakerOpenError(
                    breaker_name=breaker_name,
                    recovery_timeout=breaker.config.recovery_timeout,
                    failure_count=breaker.failure_count,
                    details=f"Function: {func.__name__}",
                )

            try:
                result = await func(*args, **kwargs)
                await breaker.record_success_async()
                return result
            except Exception:
                await breaker.record_failure_async()
                raise

        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper

    return decorator
