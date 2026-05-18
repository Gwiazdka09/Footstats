"""Tests for async utilities."""
import asyncio
import pytest

from footstats.core.async_utils import (
    gather_with_timeout,
    cleanup_event_loop,
    run_background_task,
    async_retry,
)


class TestGatherWithTimeout:
    """gather_with_timeout() concurrent tasks."""

    def test_gather_success(self):
        async def task(n):
            await asyncio.sleep(0.01)
            return n * 2

        async def run():
            return await gather_with_timeout(
                task(1), task(2), task(3),
                timeout=10.0,
            )

        results = asyncio.run(run())
        assert results == [2, 4, 6]

    def test_gather_timeout(self):
        async def slow_task():
            await asyncio.sleep(10)
            return "done"

        async def run():
            return await gather_with_timeout(slow_task(), timeout=0.1)

        results = asyncio.run(run())
        assert len(results) == 1
        assert isinstance(results[0], TimeoutError)

    def test_gather_multiple_with_timeout(self):
        async def task(delay):
            await asyncio.sleep(delay)
            return delay

        async def run():
            return await gather_with_timeout(
                task(0.01), task(0.02), task(0.03),
                timeout=1.0,
            )

        results = asyncio.run(run())
        assert len(results) == 3
        assert all(isinstance(r, (int, float)) for r in results)


class TestAsyncRetry:
    """async_retry() exponential backoff."""

    def test_retry_success_first_attempt(self):
        call_count = 0

        async def task():
            nonlocal call_count
            call_count += 1
            return "success"

        async def run():
            return await async_retry(task, max_retries=3)

        result = asyncio.run(run())
        assert result == "success"
        assert call_count == 1

    def test_retry_success_after_failures(self):
        call_count = 0

        async def task():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Not yet")
            return "success"

        async def run():
            return await async_retry(task, max_retries=3, backoff=0.01)

        result = asyncio.run(run())
        assert result == "success"
        assert call_count == 3

    def test_retry_exhausted(self):
        async def failing_task():
            raise ValueError("Always fails")

        async def run():
            return await async_retry(failing_task, max_retries=2, backoff=0.01)

        with pytest.raises(ValueError):
            asyncio.run(run())

    def test_retry_timeout(self):
        async def slow_task():
            await asyncio.sleep(10)

        async def run():
            return await async_retry(slow_task, max_retries=1, timeout=0.05)

        with pytest.raises(asyncio.TimeoutError):
            asyncio.run(run())


class TestRunBackgroundTask:
    """run_background_task() fire-and-forget."""

    def test_background_task_created(self):
        async def task():
            await asyncio.sleep(0.01)
            return "done"

        async def run():
            t = run_background_task(task(), "test_task")
            assert t is not None
            assert isinstance(t, asyncio.Task)
            await asyncio.sleep(0.05)  # Let task complete

        asyncio.run(run())


class TestCleanupEventLoop:
    """cleanup_event_loop() task cleanup."""

    def test_cleanup_no_loop(self):
        # Should not raise if no loop exists
        cleanup_event_loop()
