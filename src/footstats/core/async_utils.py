"""
async_utils.py – Async/await hardening for scrapers + background tasks.

Exports:
    gather_with_timeout(tasks, timeout=30) -> results
    cleanup_event_loop() -> None
    run_background_task(coro) -> Task
"""

import asyncio
import logging
from typing import Any, Coroutine, Optional

logger = logging.getLogger(__name__)


async def gather_with_timeout(
    *coros: Coroutine,
    timeout: float = 30.0,
    return_exceptions: bool = True,
) -> list[Any]:
    """
    Run multiple coroutines concurrently with timeout.

    Args:
        *coros: Coroutines to run
        timeout: Max seconds to wait (default 30)
        return_exceptions: If True, return exceptions in results (don't raise)

    Returns:
        List of results (or exceptions if return_exceptions=True)
    """
    try:
        results = await asyncio.wait_for(
            asyncio.gather(*coros, return_exceptions=return_exceptions),
            timeout=timeout,
        )
        logger.debug(f"[Async] gather_with_timeout: {len(coros)} tasks completed in < {timeout}s")
        return results
    except asyncio.TimeoutError:
        logger.warning(f"[Async] gather_with_timeout: Timeout after {timeout}s ({len(coros)} tasks)")
        # Cancel remaining tasks
        for coro in coros:
            if hasattr(coro, "cancel"):
                coro.cancel()
        return [TimeoutError(f"Task timeout > {timeout}s")] * len(coros)


def cleanup_event_loop() -> None:
    """Clean up event loop (close pending tasks, drain queue)."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()

    if loop.is_closed():
        logger.debug("[Async] Event loop already closed")
        return

    # Cancel pending tasks
    pending = asyncio.all_tasks(loop)
    for task in pending:
        task.cancel()
        logger.debug(f"[Async] Cancelled pending task: {task.get_name()}")

    # Run loop once more to process cancellations
    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
    logger.info(f"[Async] Cleaned up {len(pending)} pending tasks")


def run_background_task(coro: Coroutine, task_name: str = "bg_task") -> Optional[asyncio.Task]:
    """
    Schedule a coroutine as background task (fire-and-forget).

    Args:
        coro: Coroutine to run
        task_name: Name for logging

    Returns:
        asyncio.Task or None if no event loop
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()

    if loop.is_closed():
        logger.warning(f"[Async] Event loop closed, cannot schedule: {task_name}")
        return None

    task = loop.create_task(coro)
    task.set_name(task_name)
    logger.debug(f"[Async] Created background task: {task_name}")

    return task


async def async_retry(
    coro_factory,
    max_retries: int = 3,
    backoff: float = 2.0,
    timeout: float = 30.0,
    *args,
    **kwargs,
) -> Any:
    """
    Retry async operation with exponential backoff.

    Args:
        coro_factory: Async function to call
        max_retries: Max attempts
        backoff: Backoff multiplier (1s → 2s → 4s)
        timeout: Timeout per attempt
        *args, **kwargs: Passed to coro_factory

    Returns:
        Result of successful call
    """
    last_exc = None
    for attempt in range(max_retries):
        try:
            result = await asyncio.wait_for(
                coro_factory(*args, **kwargs),
                timeout=timeout,
            )
            return result
        except asyncio.TimeoutError as exc:
            last_exc = exc
            logger.warning(
                f"[Async] Attempt {attempt + 1}/{max_retries} timeout ({timeout}s)"
            )
        except Exception as exc:
            last_exc = exc
            logger.warning(f"[Async] Attempt {attempt + 1}/{max_retries} failed: {exc}")

        if attempt < max_retries - 1:
            wait = backoff ** attempt
            logger.debug(f"[Async] Waiting {wait}s before retry")
            await asyncio.sleep(wait)

    raise last_exc or RuntimeError(f"Failed after {max_retries} attempts")
