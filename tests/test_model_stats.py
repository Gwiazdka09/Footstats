"""Testy admin-only endpointu /api/admin/model-vs-live (guard, bez prod-DB)."""
import os
import pytest
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jose import jwt

os.environ.setdefault("JWT_SECRET", "testsecret1234567890abcdef12345678")


def _make_app():
    from footstats.api.routes.model_stats import router
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client():
    return TestClient(_make_app())


def _token(adm: bool, uid: int = 1) -> str:
    return jwt.encode(
        {"sub": "u", "uid": uid, "adm": adm, "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        os.environ["JWT_SECRET"], algorithm="HS256",
    )


def test_model_vs_live_requires_auth(client):
    assert client.get("/api/admin/model-vs-live").status_code == 401


def test_model_vs_live_rejects_non_admin(client):
    resp = client.get("/api/admin/model-vs-live", headers={"Authorization": f"Bearer {_token(adm=False)}"})
    assert resp.status_code == 403
