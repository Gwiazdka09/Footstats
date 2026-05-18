"""Tests for HTTP response caching with Cache-Control headers."""
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Request
from starlette.responses import JSONResponse

from footstats.core.response_cache import (
    cached_response,
    cache_key_builder,
    clear_response_cache,
    response_cache_info,
    cleanup_stale_cache,
)


class TestCacheKeyBuilder:
    """cache_key_builder() key generation."""

    def test_cache_key_same_for_same_path(self):
        req1 = MagicMock(spec=Request)
        req1.url.path = "/predict/123"
        req1.query_params = {}

        req2 = MagicMock(spec=Request)
        req2.url.path = "/predict/123"
        req2.query_params = {}

        assert cache_key_builder(req1) == cache_key_builder(req2)

    def test_cache_key_different_for_different_paths(self):
        req1 = MagicMock(spec=Request)
        req1.url.path = "/predict/123"
        req1.query_params = {}

        req2 = MagicMock(spec=Request)
        req2.url.path = "/predict/456"
        req2.query_params = {}

        assert cache_key_builder(req1) != cache_key_builder(req2)

    def test_cache_key_includes_query_params(self):
        req1 = MagicMock(spec=Request)
        req1.url.path = "/predict"
        req1.query_params = {"user_id": "123"}

        req2 = MagicMock(spec=Request)
        req2.url.path = "/predict"
        req2.query_params = {"user_id": "456"}

        assert cache_key_builder(req1, vary_by=["user_id"]) != cache_key_builder(req2, vary_by=["user_id"])

    def test_cache_key_vary_by_filters_params(self):
        req = MagicMock(spec=Request)
        req.url.path = "/predict"
        req.query_params = {"user_id": "123", "lang": "pl"}

        key1 = cache_key_builder(req, vary_by=["user_id"])
        key2 = cache_key_builder(req, vary_by=["user_id", "lang"])

        assert key1 != key2


class TestCachedResponse:
    """cached_response() decorator."""

    def test_cache_hit_within_ttl(self):
        async def run():
            clear_response_cache()
            call_count = 0

            @cached_response(ttl_seconds=10, vary_by=[])
            async def endpoint(request: Request):
                nonlocal call_count
                call_count += 1
                return {"result": "data"}

            req = MagicMock(spec=Request)
            req.url.path = "/test"
            req.query_params = {}

            response1 = await endpoint(req)
            response2 = await endpoint(req)

            assert call_count == 1, "Endpoint called twice despite cache"

        asyncio.run(run())

    def test_cache_miss_after_ttl(self):
        async def run():
            clear_response_cache()
            call_count = 0

            @cached_response(ttl_seconds=0.1, vary_by=[])
            async def endpoint(request: Request):
                nonlocal call_count
                call_count += 1
                return {"result": f"call_{call_count}"}

            req = MagicMock(spec=Request)
            req.url.path = "/test"
            req.query_params = {}

            response1 = await endpoint(req)
            time.sleep(0.15)
            response2 = await endpoint(req)

            assert call_count == 2, "Endpoint not called after TTL expired"

        asyncio.run(run())

    def test_vary_by_creates_separate_cache(self):
        async def run():
            clear_response_cache()
            call_count = 0

            @cached_response(ttl_seconds=10, vary_by=["user_id"])
            async def endpoint(request: Request):
                nonlocal call_count
                call_count += 1
                return {"result": "data"}

            req1 = MagicMock(spec=Request)
            req1.url.path = "/test"
            req1.query_params = {"user_id": "user1"}

            req2 = MagicMock(spec=Request)
            req2.url.path = "/test"
            req2.query_params = {"user_id": "user2"}

            response1 = await endpoint(req1)
            response2 = await endpoint(req2)

            assert call_count == 2, "Different users should not share cache"

        asyncio.run(run())

    def test_cache_control_header_set(self):
        async def run():
            clear_response_cache()

            @cached_response(ttl_seconds=600, vary_by=[])
            async def endpoint(request: Request):
                return {"result": "data"}

            req = MagicMock(spec=Request)
            req.url.path = "/test"
            req.query_params = {}

            response = await endpoint(req)
            assert "Cache-Control" in response.headers
            assert "max-age=" in response.headers["Cache-Control"]

        asyncio.run(run())

    def test_cache_hit_header(self):
        async def run():
            clear_response_cache()

            @cached_response(ttl_seconds=10, vary_by=[])
            async def endpoint(request: Request):
                return {"result": "data"}

            req = MagicMock(spec=Request)
            req.url.path = "/test"
            req.query_params = {}

            response1 = await endpoint(req)
            response2 = await endpoint(req)

            assert response1.headers.get("X-Cache") == "MISS"
            assert response2.headers.get("X-Cache") == "HIT"

        asyncio.run(run())


class TestCacheInvalidation:
    """clear_response_cache() and cleanup."""

    def test_clear_all_cache(self):
        clear_response_cache()

        req = MagicMock(spec=Request)
        req.url.path = "/test1"
        req.query_params = {}

        key1 = cache_key_builder(req)

        from footstats.core.response_cache import _RESPONSE_CACHE
        _RESPONSE_CACHE[key1] = {"data": {"test": 1}, "status": 200, "ts": time.time()}
        _RESPONSE_CACHE["other_key"] = {"data": {"test": 2}, "status": 200, "ts": time.time()}

        cleared = clear_response_cache()
        assert cleared == 2
        assert len(_RESPONSE_CACHE) == 0

    def test_cleanup_stale_entries(self):
        clear_response_cache()

        from footstats.core.response_cache import _RESPONSE_CACHE
        _RESPONSE_CACHE["old_key"] = {"data": {"test": 1}, "status": 200, "ts": time.time() - 100}
        _RESPONSE_CACHE["new_key"] = {"data": {"test": 2}, "status": 200, "ts": time.time()}

        cleaned = cleanup_stale_cache(ttl_seconds=10)
        assert cleaned == 1
        assert "old_key" not in _RESPONSE_CACHE
        assert "new_key" in _RESPONSE_CACHE


class TestCacheInfo:
    """response_cache_info() statistics."""

    def test_cache_info_empty(self):
        clear_response_cache()
        info = response_cache_info()
        assert info["entries"] == 0
        assert info["size_kb"] == 0

    def test_cache_info_populated(self):
        clear_response_cache()

        from footstats.core.response_cache import _RESPONSE_CACHE
        _RESPONSE_CACHE["key1"] = {"data": {"test": 1}, "status": 200, "ts": time.time()}

        info = response_cache_info()
        assert info["entries"] == 1
        assert info["oldest"] is not None
        assert info["newest"] is not None
