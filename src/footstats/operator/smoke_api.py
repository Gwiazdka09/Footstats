"""API smoke tests via TestClient (coupon wizard flow)."""

from __future__ import annotations

import logging
import os
import time

from footstats.operator.runner import RunResult

log = logging.getLogger(__name__)

_token_cache: str | None = None


_TEST_HASH: str | None = None


def _ensure_test_env() -> None:
    global _TEST_HASH
    os.environ.setdefault("JWT_SECRET", "testsecret1234567890abcdef12345678")
    os.environ.setdefault("FOOTSTATS_USER", "admin")
    import bcrypt

    if _TEST_HASH is None:
        _TEST_HASH = bcrypt.hashpw(b"testpass", bcrypt.gensalt()).decode()
    os.environ.setdefault("FOOTSTATS_PASSWORD_HASH", _TEST_HASH)


def _patch_auth_for_tests() -> None:
    import footstats.api.auth as auth_mod
    from footstats.utils.admin_user import get_operator_admin_username

    names = {"admin", "Admin_JG", get_operator_admin_username()}

    def fake_get(username: str):
        if username in names:
            return {"id": 1, "username": username, "password_hash": _TEST_HASH or ""}
        return None

    auth_mod.get_user_by_username = fake_get  # type: ignore[method-assign]


def _client():
    _ensure_test_env()
    _patch_auth_for_tests()
    from fastapi.testclient import TestClient
    from footstats.api.main import app

    return TestClient(app, raise_server_exceptions=False)


def _login(client) -> str:
    global _token_cache
    from footstats.utils.admin_user import get_operator_admin_username

    user = get_operator_admin_username()
    password = os.getenv("FOOTSTATS_PASSWORD")
    if not password:
        raise RuntimeError("FOOTSTATS_PASSWORD env var not set")
    r = client.post("/api/auth/login", json={"username": user, "password": password})
    if r.status_code != 200:
        raise RuntimeError(f"Login failed: {r.status_code} {r.text}")
    _token_cache = r.json()["access_token"]
    return _token_cache


def _headers(client) -> dict:
    return {"Authorization": f"Bearer {_login(client)}"}


def run_api_check(check: str, cap_id: str, timeout_s: int = 60) -> RunResult:
    t0 = time.monotonic()
    try:
        client = _client()
        h = _headers(client)

        if check == "health":
            r = client.get("/health")
            ok = r.status_code == 200 and r.json().get("status") == "ok"
        elif check == "login":
            _login(client)
            ok = _token_cache is not None
        elif check == "status":
            r = client.get("/api/status", headers=h)
            ok = r.status_code == 200
        elif check == "coupons_active":
            r = client.get("/api/coupons/active", headers=h)
            ok = r.status_code == 200 and isinstance(r.json(), list)
        elif check == "matches_today":
            r = client.get("/api/matches/today", headers=h)
            ok = r.status_code == 200 and isinstance(r.json(), list)
        elif check == "matches_analyze":
            r_today = client.get("/api/matches/today", headers=h)
            if r_today.status_code != 200:
                ok = False
            else:
                matches = r_today.json()
                if not matches:
                    ok = True
                else:
                    ids = [m.get("id") for m in matches[:2] if m.get("id") is not None]
                    r = client.post(
                        "/api/matches/analyze",
                        headers=h,
                        json={"match_ids": ids},
                    )
                    ok = r.status_code == 200 and isinstance(r.json(), list)
        elif check == "coupon_kelly":
            r = client.post(
                "/api/coupon/kelly",
                headers=h,
                json={
                    "selections": [{
                        "match_id": "1",
                        "home": "A",
                        "away": "B",
                        "tip": "1",
                        "odds": 2.0,
                        "win_prob": 55.0,
                    }]
                },
            )
            ok = r.status_code == 200 and "stake_pln" in r.json()
        elif check == "coupon_place_validate":
            r = client.post(
                "/api/coupon/place",
                headers=h,
                json={
                    "selections": [{
                        "match_id": "1",
                        "home": "A",
                        "away": "B",
                        "tip": "1",
                        "odds": 1.5,
                        "win_prob": 60,
                    }],
                    "total_odds": 1.5,
                    "stake_pln": 2.0,
                    "match_date": "2099-01-01",
                },
            )
            ok = r.status_code in (200, 400)
        else:
            ok = False

        duration = time.monotonic() - t0
        return RunResult(
            capability_id=cap_id,
            ok=ok,
            exit_code=0 if ok else 1,
            duration_s=duration,
            stdout_tail=check,
            stderr_tail="" if ok else f"check={check} failed",
        )
    except (RuntimeError, ValueError, KeyError) as exc:
        duration = time.monotonic() - t0
        log.exception("run_api_check %s", check)
        return RunResult(
            capability_id=cap_id,
            ok=False,
            exit_code=1,
            duration_s=duration,
            stdout_tail="",
            stderr_tail=str(exc),
        )
