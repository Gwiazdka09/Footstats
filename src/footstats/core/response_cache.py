"""
response_cache.py – HTTP response caching with Cache-Control headers and TTL.

Exports:
    cached_response(ttl_seconds, vary_by) → decorator for FastAPI routes
    cache_key_builder(request, vary_by) → cache key from request params
    clear_response_cache(prefix) → invalidate cache by pattern
"""

import asyncio
import hashlib
import inspect
import time
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, Callable, Optional

from fastapi import Request, Response
from starlette.responses import JSONResponse

_RESPONSE_CACHE: dict[str, dict[str, Any]] = {}
_CACHE_LOCK_TIME = 0


def cache_key_builder(request_or_name: Request | str = None, vary_by: list[str] | None = None, vary_values: dict | None = None) -> str:
    """
    Build cache key from request path + vary_by parameters, or from function name + vary_by values.

    Args:
        request_or_name: FastAPI Request object OR function name string
        vary_by: List of parameter names to include in cache key
        vary_values: Dict of {param_name: value} for vary_by extraction (used with string name)

    Returns:
        Cache key string (hash of path/name + params)
    """
    vary_by = vary_by or []
    vary_values = vary_values or {}

    if isinstance(request_or_name, str):
        key_parts = [request_or_name]
        for param in vary_by:
            val = vary_values.get(param, "")
            if val is not None:
                key_parts.append(f"{param}={val}")
    else:
        request = request_or_name
        key_parts = [str(request.url.path)]
        qp = request.query_params
        if isinstance(qp, dict):
            qp_dict = qp
        else:
            qp_dict = dict(qp) if qp else {}

        if vary_by:
            for param in vary_by:
                val = qp_dict.get(param, "")
                if val:
                    key_parts.append(f"{param}={val}")
        else:
            for k, v in qp_dict.items():
                key_parts.append(f"{k}={v}")

    key_str = "|".join(str(k) for k in key_parts)
    _hash = hashlib.md5(key_str.encode()).hexdigest()
    return _hash


def cached_response(ttl_seconds: int = 300, vary_by: Optional[list[str]] = None):
    """
    Decorator for caching FastAPI endpoint responses.

    Args:
        ttl_seconds: Cache time-to-live (default 5 min)
        vary_by: List of query params that create separate cache entries

    Example:
        @app.get("/predict/{match_id}")
        @cached_response(ttl_seconds=600, vary_by=["user_id"])
        async def predict(match_id: str, user_id: str = "anonymous"):
            return {"prediction": "..."}
    """
    vary_by = vary_by or []

    def decorator(func: Callable) -> Callable:
        is_async = asyncio.iscoroutinefunction(func)

        if is_async:
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                request = None
                if args and hasattr(args[0], 'url') and hasattr(args[0], 'query_params'):
                    request = args[0]

                if request is not None:
                    vary_vals = {}
                    for param in vary_by:
                        if param in kwargs:
                            vary_vals[param] = kwargs[param]
                    cache_key = cache_key_builder(request, vary_by, vary_vals)
                else:
                    cache_key = cache_key_builder(func.__name__, vary_by, kwargs)

                entry = _RESPONSE_CACHE.get(cache_key)
                if entry is not None:
                    age = time.time() - entry["ts"]
                    if age < ttl_seconds:
                        response = JSONResponse(
                            content=entry["data"],
                            status_code=entry["status"],
                        )
                        response.headers["Cache-Control"] = f"max-age={int(ttl_seconds - age)}, must-revalidate"
                        response.headers["X-Cache"] = "HIT"
                        return response

                result = await func(*args, **kwargs)

                if isinstance(result, Response):
                    body = result.body.decode() if isinstance(result.body, bytes) else result.body
                    try:
                        import json
                        data = json.loads(body) if isinstance(body, str) else body
                    except Exception:
                        data = body
                    status = result.status_code
                else:
                    data = result
                    status = 200

                _RESPONSE_CACHE[cache_key] = {
                    "data": data,
                    "status": status,
                    "ts": time.time(),
                }

                response = JSONResponse(content=data, status_code=status)
                response.headers["Cache-Control"] = f"max-age={ttl_seconds}, must-revalidate"
                response.headers["X-Cache"] = "MISS"
                return response

            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                request = None
                if args and hasattr(args[0], 'url') and hasattr(args[0], 'query_params'):
                    request = args[0]

                if request is not None:
                    vary_vals = {}
                    for param in vary_by:
                        if param in kwargs:
                            vary_vals[param] = kwargs[param]
                    cache_key = cache_key_builder(request, vary_by, vary_vals)
                else:
                    cache_key = cache_key_builder(func.__name__, vary_by, kwargs)

                entry = _RESPONSE_CACHE.get(cache_key)
                if entry is not None:
                    age = time.time() - entry["ts"]
                    if age < ttl_seconds:
                        response = JSONResponse(
                            content=entry["data"],
                            status_code=entry["status"],
                        )
                        response.headers["Cache-Control"] = f"max-age={int(ttl_seconds - age)}, must-revalidate"
                        response.headers["X-Cache"] = "HIT"
                        return response

                result = func(*args, **kwargs)

                if isinstance(result, Response):
                    body = result.body.decode() if isinstance(result.body, bytes) else result.body
                    try:
                        import json
                        data = json.loads(body) if isinstance(body, str) else body
                    except Exception:
                        data = body
                    status = result.status_code
                else:
                    data = result
                    status = 200

                _RESPONSE_CACHE[cache_key] = {
                    "data": data,
                    "status": status,
                    "ts": time.time(),
                }

                response = JSONResponse(content=data, status_code=status)
                response.headers["Cache-Control"] = f"max-age={ttl_seconds}, must-revalidate"
                response.headers["X-Cache"] = "MISS"
                return response

            return sync_wrapper

    return decorator


def clear_response_cache(prefix: str = "") -> int:
    """
    Invalidate cache entries by prefix pattern.

    Args:
        prefix: Cache key prefix to match (empty = clear all)

    Returns:
        Number of entries cleared
    """
    global _RESPONSE_CACHE
    if not prefix:
        count = len(_RESPONSE_CACHE)
        _RESPONSE_CACHE.clear()
        return count

    keys_to_remove = [k for k in _RESPONSE_CACHE.keys() if k.startswith(prefix)]
    for k in keys_to_remove:
        del _RESPONSE_CACHE[k]
    return len(keys_to_remove)


def response_cache_info() -> dict[str, Any]:
    """
    Get cache statistics.

    Returns:
        Dict with entry count, total size estimate, oldest/newest timestamps
    """
    if not _RESPONSE_CACHE:
        return {"entries": 0, "size_kb": 0, "oldest": None, "newest": None}

    timestamps = [v["ts"] for v in _RESPONSE_CACHE.values()]
    size_kb = sum(
        len(str(v["data"]).encode()) for v in _RESPONSE_CACHE.values()
    ) // 1024

    return {
        "entries": len(_RESPONSE_CACHE),
        "size_kb": size_kb,
        "oldest": datetime.fromtimestamp(min(timestamps)).isoformat() if timestamps else None,
        "newest": datetime.fromtimestamp(max(timestamps)).isoformat() if timestamps else None,
    }


def cleanup_stale_cache(ttl_seconds: int = 300) -> int:
    """
    Remove expired entries from cache.

    Args:
        ttl_seconds: Entries older than this are removed

    Returns:
        Number of entries removed
    """
    global _RESPONSE_CACHE
    now = time.time()
    stale = [k for k, v in _RESPONSE_CACHE.items() if (now - v["ts"]) > ttl_seconds]
    for k in stale:
        del _RESPONSE_CACHE[k]
    return len(stale)
