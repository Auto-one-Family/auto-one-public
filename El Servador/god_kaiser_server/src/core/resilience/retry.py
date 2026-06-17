"""
Retry Decorator with Exponential Backoff

Provides retry logic for transient failures:
- Exponential backoff: base_delay * (exponential_base ^ attempt)
- Optional jitter to prevent thundering herd
- Configurable retryable exceptions
- Callback support for retry events

Reference: ESP32 Exponential Backoff:
└── 1s → 2s → 4s → ... → 60s max
"""

import asyncio
import functools
import random
import time
from typing import Callable, Optional, Tuple, Type

from ..logging_config import get_logger
from .exceptions import RetryExhaustedError

logger = get_logger(__name__)


# Default retryable exceptions (transient failures)
DEFAULT_RETRYABLE_EXCEPTIONS: Tuple[Type[Exception], ...] = (
    ConnectionError,
    TimeoutError,
    OSError,  # Network errors
)

# Non-retryable exceptions (permanent failures)
NON_RETRYABLE_EXCEPTIONS: Tuple[Type[Exception], ...] = (
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
)


def calculate_backoff_delay(
    attempt: int,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    jitter_factor: float = 0.1,
) -> float:
    """
    Calculate delay for the next retry attempt using exponential backoff.

    Args:
        attempt: Current attempt number (0-indexed)
        base_delay: Base delay in seconds
        max_delay: Maximum delay cap in seconds
        exponential_base: Base for exponential calculation
        jitter: Whether to add random jitter
        jitter_factor: Factor for jitter (0.1 = up to 10% additional delay)

    Returns:
        Delay in seconds before next retry
    """
    # Calculate exponential delay
    delay = base_delay * (exponential_base**attempt)

    # Cap at max delay
    delay = min(delay, max_delay)

    # Add jitter to prevent thundering herd
    if jitter and delay > 0:
        jitter_amount = random.uniform(0, jitter_factor * delay)
        delay += jitter_amount

    return delay


def retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retryable_exceptions: Optional[Tuple[Type[Exception], ...]] = None,
    on_retry: Optional[Callable[[int, Exception, float], None]] = None,
    reraise_final: bool = True,
):
    """
    Decorator for retrying async functions with exponential backoff.

    Usage:
        @retry(max_attempts=3, base_delay=1.0)
        async def my_function():
            ...

        @retry(
            max_attempts=5,
            retryable_exceptions=(ConnectionError, TimeoutError),
            on_retry=lambda attempt, exc, delay: print(f"Retry {attempt}")
        )
        async def another_function():
            ...

    Args:
        max_attempts: Maximum number of attempts (including initial)
        base_delay: Base delay in seconds for backoff calculation
        max_delay: Maximum delay cap in seconds
        exponential_base: Base for exponential backoff (default 2)
        jitter: Whether to add random jitter to delays
        retryable_exceptions: Tuple of exceptions that should trigger retry
        on_retry: Optional callback(attempt, exception, delay) called before retry
        reraise_final: Whether to reraise or wrap final exception

    Raises:
        RetryExhaustedError: If all retries fail (when reraise_final=False)
        Original exception: If all retries fail (when reraise_final=True)
    """
    if retryable_exceptions is None:
        retryable_exceptions = DEFAULT_RETRYABLE_EXCEPTIONS

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception: Optional[Exception] = None
            func_name = func.__name__

            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)

                except retryable_exceptions as e:
                    last_exception = e

                    if attempt < max_attempts - 1:
                        # Calculate delay
                        delay = calculate_backoff_delay(
                            attempt=attempt,
                            base_delay=base_delay,
                            max_delay=max_delay,
                            exponential_base=exponential_base,
                            jitter=jitter,
                        )

                        logger.warning(
                            f"[resilience] Retry: Attempt {attempt + 1}/{max_attempts} "
                            f"failed for {func_name}: {type(e).__name__}: {e}"
                        )
                        logger.info(
                            f"[resilience] Retry: Waiting {delay:.2f}s before "
                            f"attempt {attempt + 2}/{max_attempts}"
                        )

                        # Call retry callback if provided
                        if on_retry:
                            try:
                                on_retry(attempt + 1, e, delay)
                            except Exception as callback_error:
                                logger.warning(
                                    f"[resilience] Retry callback error: {callback_error}"
                                )

                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            f"[resilience] Retry: All {max_attempts} attempts failed "
                            f"for {func_name}: {type(e).__name__}: {e}"
                        )

                except Exception as e:
                    # Non-retryable exception, fail immediately
                    logger.error(
                        f"[resilience] Retry: Non-retryable exception in {func_name}: "
                        f"{type(e).__name__}: {e}"
                    )
                    raise

            # All retries exhausted
            if reraise_final and last_exception:
                raise last_exception
            else:
                raise RetryExhaustedError(
                    operation=func_name,
                    max_attempts=max_attempts,
                    last_exception=last_exception,
                )

        return wrapper

    return decorator


def retry_sync(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retryable_exceptions: Optional[Tuple[Type[Exception], ...]] = None,
    on_retry: Optional[Callable[[int, Exception, float], None]] = None,
    reraise_final: bool = True,
):
    """
    Decorator for retrying synchronous functions with exponential backoff.

    Same as retry() but for sync functions using time.sleep().
    """
    if retryable_exceptions is None:
        retryable_exceptions = DEFAULT_RETRYABLE_EXCEPTIONS

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception: Optional[Exception] = None
            func_name = func.__name__

            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)

                except retryable_exceptions as e:
                    last_exception = e

                    if attempt < max_attempts - 1:
                        delay = calculate_backoff_delay(
                            attempt=attempt,
                            base_delay=base_delay,
                            max_delay=max_delay,
                            exponential_base=exponential_base,
                            jitter=jitter,
                        )

                        logger.warning(
                            f"[resilience] Retry: Attempt {attempt + 1}/{max_attempts} "
                            f"failed for {func_name}: {type(e).__name__}: {e}"
                        )
                        logger.info(
                            f"[resilience] Retry: Waiting {delay:.2f}s before "
                            f"attempt {attempt + 2}/{max_attempts}"
                        )

                        if on_retry:
                            try:
                                on_retry(attempt + 1, e, delay)
                            except Exception as callback_error:
                                logger.warning(
                                    f"[resilience] Retry callback error: {callback_error}"
                                )

                        time.sleep(delay)
                    else:
                        logger.error(
                            f"[resilience] Retry: All {max_attempts} attempts failed "
                            f"for {func_name}: {type(e).__name__}: {e}"
                        )

                except Exception as e:
                    logger.error(
                        f"[resilience] Retry: Non-retryable exception in {func_name}: "
                        f"{type(e).__name__}: {e}"
                    )
                    raise

            if reraise_final and last_exception:
                raise last_exception
            else:
                raise RetryExhaustedError(
                    operation=func_name,
                    max_attempts=max_attempts,
                    last_exception=last_exception,
                )

        return wrapper

    return decorator


class RetryContext:
    """
    Context manager for retry logic with manual control.

    Usage:
        async with RetryContext(max_attempts=3) as ctx:
            while ctx.should_retry():
                try:
                    result = await operation()
                    break
                except ConnectionError as e:
                    await ctx.handle_error(e)
    """

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
    ):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter

        self.current_attempt = 0
        self.last_exception: Optional[Exception] = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    def should_retry(self) -> bool:
        """Check if more retry attempts are available."""
        return self.current_attempt < self.max_attempts

    async def handle_error(self, exception: Exception) -> None:
        """
        Handle an error and wait before next retry.

        Args:
            exception: The exception that occurred

        Raises:
            RetryExhaustedError: If no more retries available
        """
        self.last_exception = exception
        self.current_attempt += 1

        if self.current_attempt >= self.max_attempts:
            raise RetryExhaustedError(
                operation="RetryContext",
                max_attempts=self.max_attempts,
                last_exception=exception,
            )

        delay = calculate_backoff_delay(
            attempt=self.current_attempt - 1,
            base_delay=self.base_delay,
            max_delay=self.max_delay,
            exponential_base=self.exponential_base,
            jitter=self.jitter,
        )

        logger.warning(
            f"[resilience] RetryContext: Attempt {self.current_attempt}/{self.max_attempts} "
            f"failed: {type(exception).__name__}"
        )
        logger.info(f"[resilience] RetryContext: Waiting {delay:.2f}s before next attempt")

        await asyncio.sleep(delay)
