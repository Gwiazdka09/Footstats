"""API flow for Coupon Creator (preview.html / App.jsx)."""
import os

import bcrypt
import pytest

os.environ.setdefault("JWT_SECRET", "testsecret1234567890abcdef12345678")
os.environ.setdefault("FOOTSTATS_USER", "admin")
os.environ.setdefault("OPERATOR_ADMIN_USERNAME", "admin")
os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:5173")

_hash = bcrypt.hashpw(b"testpass", bcrypt.gensalt()).decode()
os.environ.setdefault("FOOTSTATS_PASSWORD_HASH", _hash)

from fastapi.testclient import TestClient

from footstats.api.main import app

client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _mock_admin_login(monkeypatch):
    def fake_get(username: str):
        if username in ("admin", "Admin_JG"):
            return {"id": 1, "username": username, "password_hash": _hash}
        return None

    monkeypatch.setattr("footstats.api.auth.get_user_by_username", fake_get)


def _token() -> str:
    r = client.post("/api/auth/login", json={"username": "admin", "password": "testpass"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_wizard_matches_today():
    token = _token()
    r = client.get("/api/matches/today", headers=_h(token))
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_wizard_analyze_empty_ids():
    token = _token()
    r = client.post("/api/matches/analyze", headers=_h(token), json={"match_ids": []})
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="requires live DB")
def test_wizard_kelly_minimal():
    token = _token()
    r = client.post(
        "/api/coupon/kelly",
        headers=_h(token),
        json={
            "selections": [{
                "match_id": "1",
                "home": "A",
                "away": "B",
                "tip": "1",
                "odds": 2.1,
                "win_prob": 52.0,
            }]
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert "stake_pln" in data
    assert data["stake_pln"] >= 2.0


@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="requires live DB")
def test_wizard_place_or_bankroll_guard():
    token = _token()
    r = client.post(
        "/api/coupon/place",
        headers=_h(token),
        json={
            "selections": [
                {
                    "match_id": "1",
                    "home": "Test A",
                    "away": "Test B",
                    "tip": "1",
                    "odds": 1.9,
                    "win_prob": 55,
                },
            ],
            "total_odds": 1.9,
            "stake_pln": 2.0,
            "match_date": "2099-12-31",
        },
    )
    assert r.status_code in (200, 400)

    # Cleanup: nie zaśmiecaj prod DB testowym kuponem
    if r.status_code == 200:
        from footstats.utils.db import connect
        coupon_id = r.json()["coupon_id"]
        with connect() as conn:
            conn.execute("DELETE FROM coupons WHERE id = ?", (coupon_id,))
