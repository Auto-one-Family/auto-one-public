"""
Resilience-spezifische Exceptions

Custom exceptions für Circuit Breaker, Retry und Timeout Patterns.
"""

from typing import Any, Dict, Optional


class ResilienceException(Exception):
    """Base exception for all resilience-related errors."""

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for API responses."""
        return {
            "error": self.__class__.__name__,
            "message": self.message,
            "error_code": self.error_code,
            "details": self.details,
        }


class CircuitBreakerError(ResilienceException):
    """Base exception for Circuit Breaker errors."""

    pass


class CircuitBreakerOpenError(CircuitBreakerError):
    """
    Raised when a request is rejected because the circuit breaker is OPEN.

    This indicates that the service has exceeded its failure threshold
    and is currently not accepting requests (fail-fast mode).
    """

    def __init__(
        self,
        breaker_name: str,
        recovery_timeout: float,
        failure_count: int,
        details: Optional[str] = None,
    ) -> None:
        super().__init__(
            message=f"Circuit breaker '{breaker_name}' is OPEN. Service unavailable.",
            error_code="CIRCUIT_BREAKER_OPEN",
            details={
                "breaker_name": breaker_name,
                "recovery_timeout": recovery_timeout,
                "failure_count": failure_count,
                "details": details,
            },
        )
        self.breaker_name = breaker_name
        self.recovery_timeout = recovery_timeout
        self.failure_count = failure_count


class CircuitBreakerHalfOpenError(CircuitBreakerError):
    """
    Raised when a request is rejected during HALF_OPEN state.

    In HALF_OPEN state, only a limited number of test requests are allowed.
    Additional requests are rejected until the test request completes.
    """

    def __init__(
        self,
        breaker_name: str,
        max_half_open_requests: int,
        details: Optional[str] = None,
    ) -> None:
        super().__init__(
            message=f"Circuit breaker '{breaker_name}' is HALF_OPEN. Waiting for test request.",
            error_code="CIRCUIT_BREAKER_HALF_OPEN",
            details={
                "breaker_name": breaker_name,
                "max_half_open_requests": max_half_open_requests,
                "details": details,
            },
        )
        self.breaker_name = breaker_name
        self.max_half_open_requests = max_half_open_requests


class RetryExhaustedError(ResilienceException):
    """
    Raised when all retry attempts have been exhausted.

    Contains information about the number of attempts made and the last error.
    """

    def __init__(
        self,
        operation: str,
        max_attempts: int,
        last_exception: Optional[Exception] = None,
        details: Optional[str] = None,
    ) -> None:
        last_error = str(last_exception) if last_exception else "Unknown"
        super().__init__(
            message=f"Operation '{operation}' failed after {max_attempts} attempts. Last error: {last_error}",
            error_code="RETRY_EXHAUSTED",
            details={
                "operation": operation,
                "max_attempts": max_attempts,
                "last_error": last_error,
                "details": details,
            },
        )
        self.operation = operation
        self.max_attempts = max_attempts
        self.last_exception = last_exception


class OperationTimeoutError(ResilienceException):
    """
    Raised when an operation exceeds its timeout limit.

    Custom timeout error with additional context about the operation.
    """

    def __init__(
        self,
        operation: str,
        timeout_seconds: float,
        details: Optional[str] = None,
    ) -> None:
        super().__init__(
            message=f"Operation '{operation}' timed out after {timeout_seconds}s",
            error_code="OPERATION_TIMEOUT",
            details={
                "operation": operation,
                "timeout_seconds": timeout_seconds,
                "details": details,
            },
        )
        self.operation = operation
        self.timeout_seconds = timeout_seconds


class ServiceUnavailableError(ResilienceException):
    """
    Raised when a service is unavailable due to resilience patterns.

    Generic error for when a service cannot be reached due to
    circuit breaker, too many failures, or other resilience mechanisms.
    """

    def __init__(
        self,
        service_name: str,
        reason: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message=f"Service '{service_name}' unavailable: {reason}",
            error_code="SERVICE_UNAVAILABLE",
            details={
                "service_name": service_name,
                "reason": reason,
                **(details or {}),
            },
        )
        self.service_name = service_name
        self.reason = reason


class OfflineBufferFullError(ResilienceException):
    """
    Raised when the offline buffer is full and cannot accept more messages.
    """

    def __init__(
        self,
        buffer_name: str,
        max_size: int,
        details: Optional[str] = None,
    ) -> None:
        super().__init__(
            message=f"Offline buffer '{buffer_name}' is full (max {max_size} messages)",
            error_code="OFFLINE_BUFFER_FULL",
            details={
                "buffer_name": buffer_name,
                "max_size": max_size,
                "details": details,
            },
        )
        self.buffer_name = buffer_name
        self.max_size = max_size
