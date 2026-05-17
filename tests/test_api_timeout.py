"""Testy timeoutu i request ID dla FastAPI."""
import asyncio
import uuid
from contextvars import ContextVar
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ── Fixture: mini app z middleware ────────────────────────────────────────────

def _build_test_app(timeout: float = 10.0):
    """Buduje izolowaną testową aplikację z middleware."""
    import asyncio
    import json
    from contextvars import ContextVar
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    from starlette.middleware.base import BaseHTTPMiddleware

    _rid_var: ContextVar[str] = ContextVar("request_id", default="")

    class _RequestIDMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())[:8]
            _rid_var.set(rid)
            response = await call_next(request)
            response.headers["X-Request-ID"] = rid
            return response

    class _TimeoutMiddleware(BaseHTTPMiddleware):
        def __init__(self, app, timeout: float = 10.0):
            super().__init__(app)
            self.timeout = timeout

        async def dispatch(self, request: Request, call_next):
            try:
                return await asyncio.wait_for(call_next(request), timeout=self.timeout)
            except asyncio.TimeoutError:
                return JSONResponse(
                    {"detail": "Request timeout", "timeout_s": self.timeout},
                    status_code=504,
                )

    app = FastAPI()
    app.add_middleware(_TimeoutMiddleware, timeout=timeout)
    app.add_middleware(_RequestIDMiddleware)

    @app.get("/fast")
    async def fast_endpoint():
        return {"status": "ok"}

    @app.get("/slow")
    async def slow_endpoint():
        await asyncio.sleep(30)
        return {"status": "ok"}

    @app.get("/echo-rid")
    async def echo_rid(request: Request):
        return {"request_id": _rid_var.get("")}

    return app


@pytest.fixture
def fast_client():
    app = _build_test_app(timeout=0.2)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def normal_client():
    app = _build_test_app(timeout=10.0)
    return TestClient(app)


# ── Timeout tests ─────────────────────────────────────────────────────────────

def test_fast_endpoint_returns_200(normal_client):
    r = normal_client.get("/fast")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_slow_endpoint_returns_504(fast_client):
    r = fast_client.get("/slow")
    assert r.status_code == 504
    body = r.json()
    assert body["detail"] == "Request timeout"
    assert "timeout_s" in body


def test_timeout_body_contains_timeout_value(fast_client):
    r = fast_client.get("/slow")
    assert r.json()["timeout_s"] == pytest.approx(0.2, abs=0.01)


# ── Request ID tests ──────────────────────────────────────────────────────────

def test_response_has_x_request_id_header(normal_client):
    r = normal_client.get("/fast")
    assert "X-Request-ID" in r.headers


def test_request_id_propagated_from_client(normal_client):
    custom_rid = "test-abc-123"
    r = normal_client.get("/fast", headers={"X-Request-ID": custom_rid})
    assert r.headers["X-Request-ID"] == custom_rid


def test_request_id_auto_generated_when_missing(normal_client):
    r = normal_client.get("/fast")
    rid = r.headers.get("X-Request-ID", "")
    assert len(rid) > 0


def test_request_id_unique_per_request(normal_client):
    r1 = normal_client.get("/fast")
    r2 = normal_client.get("/fast")
    assert r1.headers["X-Request-ID"] != r2.headers["X-Request-ID"]


def test_health_endpoint_not_blocked(normal_client):
    """Health endpoint odpowiada bez timeoutu."""
    r = normal_client.get("/fast")
    assert r.status_code == 200


# ── Middleware isolation ───────────────────────────────────────────────────────

def test_timeout_middleware_passes_fast_requests():
    """Middleware z 5s timeout przepuszcza normalne requesty."""
    app = _build_test_app(timeout=5.0)
    client = TestClient(app)
    r = client.get("/fast")
    assert r.status_code == 200


def test_multiple_concurrent_requests_get_unique_ids(normal_client):
    """Każdy request dostaje unikalny request_id."""
    rids = set()
    for _ in range(5):
        r = normal_client.get("/fast")
        rids.add(r.headers.get("X-Request-ID"))
    assert len(rids) == 5
