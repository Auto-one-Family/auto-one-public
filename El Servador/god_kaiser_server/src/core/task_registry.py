"""Central registry for fire-and-forget background tasks.

Provides a single point of tracking and cleanup for asyncio tasks created
with create_task() to ensure graceful shutdown and visibility into active
background operations.
"""

import asyncio
import logging
from typing import Any, Coroutine, Set

logger = logging.getLogger(__name__)

_background_tasks: Set[asyncio.Task] = set()


def create_tracked_task(
    coro: Coroutine[Any, Any, Any],
    *,
    name: str | None = None,
) -> asyncio.Task:
    """Create a tracked background task that auto-removes on completion.

    Args:
        coro: Coroutine to execute in background
        name: Optional name for debugging/logging

    Returns:
        asyncio.Task instance (automatically tracked)
    """
    task = asyncio.create_task(coro, name=name)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


def get_active_task_count() -> int:
    """Return number of currently active background tasks."""
    return len(_background_tasks)


async def cancel_all_background_tasks(timeout: float = 10.0) -> int:
    """Cancel all tracked background tasks. Returns count of cancelled tasks.

    Args:
        timeout: Wait up to this many seconds for tasks to finish

    Returns:
        Count of tasks that were active when called
    """
    count = len(_background_tasks)
    if count == 0:
        return 0

    logger.info("Cancelling %d background tasks...", count)
    for task in list(_background_tasks):
        task.cancel()

    if _background_tasks:
        done, pending = await asyncio.wait(list(_background_tasks), timeout=timeout)
        if pending:
            logger.warning(
                "%d background tasks did not finish within %fs",
                len(pending),
                timeout,
            )

    logger.info("Background task cleanup complete")
    return count
