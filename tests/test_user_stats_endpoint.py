"""test_user_stats_endpoint.py — auth (401 bez tokenu) + kształt GET /api/stats/me (J2).

Wzorowane na test_analyses_endpoint.py: dependency_overrides[require_auth] dla klienta
zalogowanego, realny require_auth dla anonima. get_user_stats zamockowane bezpośrednio
w module trasy — zero dotykania DB (SQLite/Neon), test wyłącznie serializacji/auth.
"""
import pytest
from fastapi.testclient import TestClient

from footstats.api.auth import require_auth
from footstats.api.main import app
from footstats.core.user_stats import CouponResult, ProgressPoint, UserStats


@pytest.fixture
def client():
    """Klient ZALOGOWANY — require_auth podmienione na stałego usera 1."""
    app.dependency_overrides[require_auth] = lambda: 1
    yield TestClient(app)
    app.dependency_overrides.pop(require_auth, None)


@pytest.fixture
def anon_client():
    """Klient BEZ tokenu — realny require_auth."""
    return TestClient(app)


# ── auth ─────────────────────────────────────────────────────────────────────

def test_stats_me_wymaga_auth(anon_client):
    r = anon_client.get("/api/stats/me")
    assert r.status_code in (401, 403)   # HTTPBearer bez nagłówka → 403/401


# ── kształt odpowiedzi ───────────────────────────────────────────────────────

def test_stats_me_zwraca_ksztalt_z_danymi(client, monkeypatch):
    import footstats.api.routes.user_stats as us

    stats = UserStats(
        user_id=1, total_coupons=3, settled_count=3, wins=2, losses=1,
        win_rate=2 / 3, profit_units=10.0, roi=10.0 / 30.0, current_streak=-1,
        best_coupon=CouponResult(coupon_id=5, profit_units=20.0),
        worst_coupon=CouponResult(coupon_id=7, profit_units=-8.0),
    )
    monkeypatch.setattr(us, "get_user_stats", lambda user_id: stats)

    r = client.get("/api/stats/me")
    assert r.status_code == 200
    body = r.json()
    assert body["total_coupons"] == 3
    assert body["settled_count"] == 3
    assert body["wins"] == 2
    assert body["losses"] == 1
    assert body["win_rate"] == pytest.approx(2 / 3)
    assert body["profit_units"] == pytest.approx(10.0)
    assert body["roi"] == pytest.approx(10.0 / 30.0)
    assert body["current_streak"] == -1
    assert body["best_coupon"] == {"coupon_id": 5, "profit_units": 20.0}
    assert body["worst_coupon"] == {"coupon_id": 7, "profit_units": -8.0}


def test_stats_me_empty_user_zwraca_null_best_worst(client, monkeypatch):
    import footstats.api.routes.user_stats as us

    stats = UserStats(
        user_id=1, total_coupons=0, settled_count=0, wins=0, losses=0,
        win_rate=0.0, profit_units=0.0, roi=0.0, current_streak=0,
        best_coupon=None, worst_coupon=None,
    )
    monkeypatch.setattr(us, "get_user_stats", lambda user_id: stats)

    r = client.get("/api/stats/me")
    assert r.status_code == 200
    body = r.json()
    assert body["settled_count"] == 0
    assert body["best_coupon"] is None
    assert body["worst_coupon"] is None


# ── błąd DB → 503 ────────────────────────────────────────────────────────────

def test_stats_me_blad_db_zwraca_503(client, monkeypatch):
    import footstats.api.routes.user_stats as us

    def _boom(user_id: int):
        raise RuntimeError("DB down")

    monkeypatch.setattr(us, "get_user_stats", _boom)

    r = client.get("/api/stats/me")
    assert r.status_code == 503


# ── GET /api/stats/progress (J3) ─────────────────────────────────────────────


def test_stats_progress_wymaga_auth(anon_client):
    r = anon_client.get("/api/stats/progress")
    assert r.status_code in (401, 403)   # HTTPBearer bez nagłówka → 403/401


def test_stats_progress_zwraca_ksztalt_listy_punktow(client, monkeypatch):
    import footstats.api.routes.user_stats as us

    series = [
        ProgressPoint(date="2026-07-01", cumulative_profit=10.0, running_win_rate=1.0, settled_count=1),
        ProgressPoint(date="2026-07-02", cumulative_profit=20.0, running_win_rate=1.0, settled_count=2),
        ProgressPoint(date="2026-07-03", cumulative_profit=10.0, running_win_rate=2 / 3, settled_count=3),
    ]
    monkeypatch.setattr(us, "get_progress_series", lambda user_id: series)

    r = client.get("/api/stats/progress")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert len(body) == 3
    assert body[0] == {
        "date": "2026-07-01", "cumulative_profit": 10.0,
        "running_win_rate": 1.0, "settled_count": 1,
    }
    assert body[2]["running_win_rate"] == pytest.approx(2 / 3)


def test_stats_progress_pusta_lista_bez_crasha(client, monkeypatch):
    import footstats.api.routes.user_stats as us

    monkeypatch.setattr(us, "get_progress_series", lambda user_id: [])

    r = client.get("/api/stats/progress")
    assert r.status_code == 200
    assert r.json() == []


def test_stats_progress_blad_db_zwraca_503(client, monkeypatch):
    import footstats.api.routes.user_stats as us

    def _boom(user_id: int):
        raise RuntimeError("DB down")

    monkeypatch.setattr(us, "get_progress_series", _boom)

    r = client.get("/api/stats/progress")
    assert r.status_code == 503
