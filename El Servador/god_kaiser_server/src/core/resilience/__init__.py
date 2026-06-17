"""
Resilience Patterns for God-Kaiser Server

Provides fault tolerance mechanisms:
- Circuit Breaker: Fail-fast when services are unhealthy
- Retry: Automatic retry with exponential backoff
- Timeout: Prevent hanging operations
- Offline Buffer: Queue messages when services are unavailable

Usage:
    from src.core.resilience import (
        CircuitBreaker,
        CircuitState,
        ResilienceRegistry,
        retry,
        timeout,
        CircuitBreakerOpenError,
    )

    # Get registry singleton
    registry = ResilienceRegistry.get_instance()

    # Register circuit breakers
    registry.register_circuit_breaker("mqtt", CircuitBreaker(
        name="mqtt",
        failure_threshold=5,
        recovery_timeout=30,
    ))

    # Use decorators
    @retry(max_attempts=3, base_delay=1.0)
    @timeout(seconds=5.0)
    async def my_function():
        ...

    # Use circuit breaker decorator
    @circuit_breaker_decorator("database")
    async def db_operation():
        ...
"""

from .circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    CircuitBreakerConfig,
    CircuitBreakerMetrics,
    circuit_breaker_decorator,
)
from .retry import (
    retry,
    retry_sync,
    RetryContext,
    calculate_backoff_delay,
    DEFAULT_RETRYABLE_EXCEPTIONS,
)
from .timeout import (
    timeout,
    timeout_with_fallback,
    TimeoutContext,
    with_timeout,
    with_timeout_fallback,
    Timeouts,
)
from .registry import (
    ResilienceRegistry,
    get_registry,
    get_circuit_breaker,
    get_health_status,
)
from .exceptions import (
    ResilienceException,
    CircuitBreakerError,
    CircuitBreakerOpenError,
    CircuitBreakerHalfOpenError,
    RetryExhaustedError,
    OperationTimeoutError,
    ServiceUnavailableError,
    OfflineBufferFullError,
)

__all__ = [
    # Circuit Breaker
    "CircuitBreaker",
    "CircuitState",
    "CircuitBreakerConfig",
    "CircuitBreakerMetrics",
    "circuit_breaker_decorator",
    # Retry
    "retry",
    "retry_sync",
    "RetryContext",
    "calculate_backoff_delay",
    "DEFAULT_RETRYABLE_EXCEPTIONS",
    # Timeout
    "timeout",
    "timeout_with_fallback",
    "TimeoutContext",
    "with_timeout",
    "with_timeout_fallback",
    "Timeouts",
    # Registry
    "ResilienceRegistry",
    "get_registry",
    "get_circuit_breaker",
    "get_health_status",
    # Exceptions
    "ResilienceException",
    "CircuitBreakerError",
    "CircuitBreakerOpenError",
    "CircuitBreakerHalfOpenError",
    "RetryExhaustedError",
    "OperationTimeoutError",
    "ServiceUnavailableError",
    "OfflineBufferFullError",
]
