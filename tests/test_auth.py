"""Tests for JWT auth module."""
import os
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("JWT_SECRET", "testsecret1234567890abcdef12345678")
os.environ.setdefault("FOOTSTATS_USER", "admin")

import bcrypt as _bcrypt_lib
_hash = _bcrypt_lib.hashpw(b"testpass", _bcrypt_lib.gensalt()).decode()
os.environ.setdefault("FOOTSTATS_PASSWORD_HASH", _hash)


def _make_app():
    from footstats.api.auth import router as auth_router, require_auth
    from footstats.api.routes.admin_users import router as admin_users_router
    from fastapi import Depends
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(admin_users_router)

    @app.get("/protected")
    def protected(user: str = Depends(require_auth)):
        return {"user": user}

    return app


@pytest.fixture
def client():
    return TestClient(_make_app())


@pytest.fixture
def admin_token(client):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "testpass"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def test_login_success(client):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "testpass"})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_wrong_password(client):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert resp.status_code == 401


def test_login_wrong_user(client):
    resp = client.post("/api/auth/login", json={"username": "hacker", "password": "testpass"})
    assert resp.status_code == 401


def test_protected_no_token(client):
    resp = client.get("/protected")
    assert resp.status_code == 401


def test_protected_valid_token(client):
    login = client.post("/api/auth/login", json={"username": "admin", "password": "testpass"})
    token = login.json()["access_token"]
    resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["user"] is not None


def test_protected_invalid_token(client):
    resp = client.get("/protected", headers={"Authorization": "Bearer badtoken"})
    assert resp.status_code == 401


def test_protected_expired_token(client):
    from datetime import datetime, timedelta, timezone
    from jose import jwt
    secret = os.environ["JWT_SECRET"]
    expired = jwt.encode(
        {"sub": "admin", "exp": datetime.now(timezone.utc) - timedelta(seconds=1)},
        secret, algorithm="HS256"
    )
    resp = client.get("/protected", headers={"Authorization": f"Bearer {expired}"})
    assert resp.status_code == 401


# --- require_admin tests ---

def test_admin_token_contains_adm_flag(client):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "testpass"})
    from jose import jwt as _jwt
    payload = _jwt.decode(
        resp.json()["access_token"],
        os.environ["JWT_SECRET"],
        algorithms=["HS256"],
    )
    assert payload.get("adm") is True


def test_list_users_requires_admin(client):
    resp = client.get("/api/admin/users")
    assert resp.status_code == 401


def test_list_users_rejects_non_admin_token(client):
    from datetime import datetime, timedelta, timezone
    from jose import jwt as _jwt
    token = _jwt.encode(
        {"sub": "regular", "uid": 999, "adm": False, "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        os.environ["JWT_SECRET"],
        algorithm="HS256",
    )
    resp = client.get("/api/admin/users", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


@pytest.mark.skipif(not os.environ.get("FOOTSTATS_TEST_DB"), reason="requires dedykowana test-DB (FOOTSTATS_TEST_DB) - NIE prod (DATABASE_URL)")
def test_list_users_as_admin(client, admin_token):
    resp = client.get("/api/admin/users", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    users = resp.json()
    assert isinstance(users, list)
    assert any(u["username"] == "admin" for u in users)


def test_create_user_requires_admin(client):
    resp = client.post("/api/admin/users", json={"username": "newuser", "password": "securepass"})
    assert resp.status_code == 401


def test_create_user_password_too_short(client, admin_token):
    resp = client.post(
        "/api/admin/users",
        json={"username": "newuser", "password": "short"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 422


def test_delete_account_requires_auth(client):
    resp = client.request("DELETE", "/api/auth/me", json={"password": "x"})
    assert resp.status_code == 401


@pytest.mark.skipif(not os.environ.get("FOOTSTATS_TEST_DB"), reason="requires dedykowana test-DB (FOOTSTATS_TEST_DB) - NIE prod (DATABASE_URL)")
def test_delete_account_admin_blocked(client, admin_token):
    resp = client.request(
        "DELETE", "/api/auth/me",
        json={"password": "testpass"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 400


@pytest.mark.skipif(not os.environ.get("FOOTSTATS_TEST_DB"), reason="requires dedykowana test-DB (FOOTSTATS_TEST_DB) - NIE prod (DATABASE_URL)")
def test_delete_account_flow(client):
    import uuid
    from footstats.utils.db import connect

    uname = f"deltest_{uuid.uuid4().hex[:8]}"
    email = f"{uname}@example.com"

    resp = client.post(
        "/api/auth/register",
        json={"username": uname, "email": email, "password": "securepass123"},
    )
    assert resp.status_code == 201
    token = resp.json()["access_token"]
    auth = {"Authorization": f"Bearer {token}"}

    # wrong password -> 401
    resp_bad = client.request("DELETE", "/api/auth/me", json={"password": "wrong"}, headers=auth)
    assert resp_bad.status_code == 401

    # correct password -> anonymized
    resp_ok = client.request("DELETE", "/api/auth/me", json={"password": "securepass123"}, headers=auth)
    assert resp_ok.status_code == 200

    # login with old credentials no longer works
    resp_login = client.post("/api/auth/login", json={"username": uname, "password": "securepass123"})
    assert resp_login.status_code == 401

    with connect() as conn:
        row = conn.execute("SELECT username, email, is_active FROM users WHERE username = ?", (uname,)).fetchone()
    assert row is None  # username zanonimizowany na deleted_user_{id}


@pytest.mark.skipif(not os.environ.get("FOOTSTATS_TEST_DB"), reason="requires dedykowana test-DB (FOOTSTATS_TEST_DB) - NIE prod (DATABASE_URL)")
def test_create_and_deactivate_user(client, admin_token):
    import uuid
    uname = f"testuser_{uuid.uuid4().hex[:8]}"
    auth = {"Authorization": f"Bearer {admin_token}"}

    # create
    resp = client.post("/api/admin/users", json={"username": uname, "password": "securepass123"}, headers=auth)
    assert resp.status_code == 201
    data = resp.json()
    assert data["username"] == uname
    assert data["is_admin"] is False
    assert data["is_active"] is True
    user_id = data["id"]

    # duplicate → 409
    resp2 = client.post("/api/admin/users", json={"username": uname, "password": "securepass123"}, headers=auth)
    assert resp2.status_code == 409

    # deactivate
    resp3 = client.delete(f"/api/admin/users/{user_id}", headers=auth)
    assert resp3.status_code == 204

    # second deactivate → 404
    resp4 = client.delete(f"/api/admin/users/{user_id}", headers=auth)
    assert resp4.status_code == 404


def test_cannot_deactivate_own_account(client, admin_token):
    from jose import jwt as _jwt
    payload = _jwt.decode(admin_token, os.environ["JWT_SECRET"], algorithms=["HS256"])
    own_id = payload["uid"]
    resp = client.delete(
        f"/api/admin/users/{own_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 400
