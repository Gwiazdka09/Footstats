"""Fixtures wspólne dla wszystkich testów FootStats."""
import os
import pandas as pd
import pytest
from datetime import datetime, timedelta


@pytest.fixture(autouse=True)
def _patch_auth_db_when_no_database_url(monkeypatch):
    """Patch get_user_by_username to use env vars when DATABASE_URL not set (CI)."""
    if os.environ.get("DATABASE_URL"):
        yield
        return

    import footstats.api.auth as _auth

    pw_hash = os.environ.get("FOOTSTATS_PASSWORD_HASH", "")
    admin_user = os.environ.get("FOOTSTATS_USER", "admin")

    def _fake_get_user(username: str):
        if username == admin_user and pw_hash:
            return {"id": 1, "username": username, "password_hash": pw_hash, "is_admin": True}
        return None

    monkeypatch.setattr(_auth, "get_user_by_username", _fake_get_user)
    yield


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Reset slowapi in-memory limiter before each test to prevent cross-test contamination."""
    try:
        from footstats.api.main import limiter
        limiter._storage.reset()
    except Exception:
        pass
    yield


@pytest.fixture
def df_mecze_minimal():
    """Minimalne DataFrame meczów do testów (kolumny polskie: gospodarz/goscie/gole_g/gole_a)."""
    today = datetime.now()
    mecze = []
    druzyny = ["Arsenal", "Chelsea", "Liverpool", "Man Utd"]
    for i in range(20):
        g = druzyny[i % 4]
        a = druzyny[(i + 1) % 4]
        if g == a:
            a = druzyny[(i + 2) % 4]
        mecze.append({
            "gospodarz": g,
            "goscie": a,
            "gole_g": (i % 4),
            "gole_a": (i % 3),
            "data": (today - timedelta(days=i * 7)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "faza": "REGULAR_SEASON",
        })
    return pd.DataFrame(mecze)


@pytest.fixture
def klucze_env():
    """Przykładowe klucze API (fake)."""
    return {
        "FOOTBALL_API_KEY": "test_fdb_key",
        "APISPORTS_KEY": "test_af_key",
        "BZZOIRO_KEY": "test_bzz_key",
    }
