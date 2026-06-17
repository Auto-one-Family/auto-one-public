"""
Timeout Decorator

Provides timeout handling for async operations:
- Uses asyncio.wait_for() for async functions
- Custom timeout error with context
- Configurable timeout values per operation type

Recommended Timeouts:
├── MQTT Publish: 5s
├── DB Query (simple): 5s
├── DB Query (complex): 30s
├── External API: 10s
├── WebSocket Send: 2s
└── Sensor Processing: 1s
"""

import asyncio
import functools
from typing import Callable, Optional, TypeVar, Any

from ..logging_config import get_logger
from .exceptions import OperationTimeoutError

logger = get_logger(__name__)

T = TypeVar("T")


# Predefined timeout values (in seconds)
class Timeouts:
    """Predefined timeout values for common operations."""

    MQTT_PUBLISH = 5.0
    DB_QUERY_SIMPLE = 5.0
    DB_QUERY_COMPLEX = 30.0
    EXTERNAL_API = 10.0
    WEBSOCKET_SEND = 2.0
    SENSOR_PROCESSING = 1.0
    DEFAULT = 10.0


def timeout(
    seconds: float,
    error_message: Optional[str] = None,
    on_timeout: Optional[Callable[[str, float], None]] = None,
):
    """
    Decorator to add timeout to async functions.

    Usage:
        @timeout(seconds=5.0)
        async def my_function():
            ...

        @timeout(seconds=10.0, error_message="Database query timed out")
        async def db_query():
            ...

    Args:
        seconds: Timeout in seconds
        error_message: Custom error message (default: auto-generated)
        on_timeout: Optional callback(func_name, timeout) called on timeout

    Raises:
        OperationTimeoutError: If operation exceeds timeout
    """

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            func_name = func.__name__
            message = error_message or f"Operation '{func_name}' timed out"

            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=seconds)
            except asyncio.TimeoutError:
                logger.error(f"[resilience] Timeout: {message} after {seconds}s")

                # Call timeout callback if provided
                if on_timeout:
                    try:
                        on_timeout(func_name, seconds)
                    except Exception as callback_error:
                        logger.warning(f"[resilience] Timeout callback error: {callback_error}")

                raise OperationTimeoutError(
                    operation=func_name,
                    timeout_seconds=seconds,
                    details=message,
                )

        return wrapper

    return decorator


def timeout_with_fallback(
    seconds: float,
    fallback_value: Any = None,
    fallback_factory: Optional[Callable[[], Any]] = None,
    log_timeout: bool = True,
):
    """
    Decorator to add timeout with fallback value instead of exception.

    Usage:
        @timeout_with_fallback(seconds=5.0, fallback_value=[])
        async def get_data():
            ...

        @timeout_with_fallback(seconds=5.0, fallback_factory=lambda: {"cached": True})
        async def get_config():
            ...

    Args:
        seconds: Timeout in seconds
        fallback_value: Value to return on timeout (static)
        fallback_factory: Factory function to create fallback value (dynamic)
        log_timeout: Whether to log timeout events

    Returns:
        Either the function result or the fallback value on timeout
    """

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            func_name = func.__name__

            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=seconds)
            except asyncio.TimeoutError:
                if log_timeout:
                    logger.warning(
                        f"[resilience] Timeout: '{func_name}' exceeded {seconds}s, "
                        f"returning fallback value"
                    )

                if fallback_factory:
                    return fallback_factory()
                return fallback_value

        return wrapper

    return decorator


class TimeoutContext:
    """
    Async context manager for timeout handling.

    Usage:
        async with TimeoutContext(seconds=5.0, operation="database_query") as ctx:
            result = await some_operation()

        # Raises OperationTimeoutError if timeout exceeded
    """

    def __init__(
        self,
        seconds: float,
        operation: str = "operation",
        error_message: Optional[str] = None,
    ):
        """
        Initialize timeout context.

        Args:
            seconds: Timeout in seconds
            operation: Name of the operation (for error messages)
            error_message: Custom error message
        """
        self.seconds = seconds
        self.operation = operation
        self.error_message = error_message or f"Operation '{operation}' timed out"
        self._task: Optional[asyncio.Task] = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is asyncio.TimeoutError:
            logger.error(f"[resilience] Timeout: {self.error_message} after {self.seconds}s")
            raise OperationTimeoutError(
                operation=self.operation,
                timeout_seconds=self.seconds,
                details=self.error_message,
            )
        return False


async def with_timeout(
    coro,
    seconds: float,
    operation: str = "operation",
    error_message: Optional[str] = None,
):
    """
    Execute a coroutine with a timeout.

    Usage:
        result = await with_timeout(
            some_operation(),
            seconds=5.0,
            operation="database_query"
        )

    Args:
        coro: Coroutine to execute
        seconds: Timeout in seconds
        operation: Name of the operation
        error_message: Custom error message

    Returns:
        Result of the coroutine

    Raises:
        OperationTimeoutError: If timeout exceeded
    """
    message = error_message or f"Operation '{operation}' timed out"

    try:
        return await asyncio.wait_for(coro, timeout=seconds)
    except asyncio.TimeoutError:
        logger.error(f"[resilience] Timeout: {message} after {seconds}s")
        raise OperationTimeoutError(
            operation=operation,
            timeout_seconds=seconds,
            details=message,
        )


async def with_timeout_fallback(
    coro,
    seconds: float,
    fallback_value: Any = None,
    fallback_factory: Optional[Callable[[], Any]] = None,
    operation: str = "operation",
    log_timeout: bool = True,
):
    """
    Execute a coroutine with timeout, returning fallback on timeout.

    Usage:
        result = await with_timeout_fallback(
            get_data(),
            seconds=5.0,
            fallback_value=[]
        )

    Args:
        coro: Coroutine to execute
        seconds: Timeout in seconds
        fallback_value: Value to return on timeout
        fallback_factory: Factory function for fallback value
        operation: Name of the operation
        log_timeout: Whether to log timeout events

    Returns:
        Either the coroutine result or fallback value
    """
    try:
        return await asyncio.wait_for(coro, timeout=seconds)
    except asyncio.TimeoutError:
        if log_timeout:
            logger.warning(
                f"[resilience] Timeout: '{operation}' exceeded {seconds}s, "
                f"returning fallback value"
            )

        if fallback_factory:
            return fallback_factory()
        return fallback_value
