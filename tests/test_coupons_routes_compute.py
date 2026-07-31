"""test_coupons_routes_compute.py — helpery predykcji + endpointy obliczeniowe.

PO CO: `api/routes/coupons.py` mial 58%. Dwie rzeczy szczegolnie:

1. `_fallback_predictions` to BEZPIECZNIK: bez `DEMO_MODE=1` musi zwrocic pusta
   liste, nie mocka. Docstring mowi wprost — "bez tego realny user widzialby
   falszywe mecze (Legia/Lech) jako prawdziwe". To bylo nieprzetestowane, wiec
   nic nie chronilo przed powrotem mocka na produkcje.

2. `/api/coupon/kelly` liczy STAWKE. Ma dwa ograniczniki (min 2 PLN, max 20%
   bankrolla) i zaden nie mial testu — a to one stoja miedzy modelem
   a realnym pieniedzmi.
"""
from __future__ import annotations

import os

import bcrypt
import pytest

os.environ.setdefault("JWT_SECRET", "testsecret1234567890abcdef12345678")
os.environ.setdefault("FOOTSTATS_USER", "admin")
os.environ.setdefault("OPERATOR_ADMIN_USERNAME", "admin")
os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:5173")

_hash = bcrypt.hashpw(b"testpass", bcrypt.gensalt()).decode()
os.environ.setdefault("FOOTSTATS_PASSWORD_HASH", _hash)

from fastapi.testclient import TestClient  # noqa: E402

import footstats.api.routes.coupons as cr  # noqa: E402
from footstats.api.main import app  # noqa: E402

client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _admin(monkeypatch):
    def fake_get(username: str):
        if username in ("admin", "Admin_JG"):
            return {"id": 1, "username": username, "password_hash": _hash}
        return None

    monkeypatch.setattr("footstats.api.auth.get_user_by_username", fake_get)


@pytest.fixture
def naglowki() -> dict:
    r = client.post("/api/auth/login", json={"username": "admin", "password": "testpass"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


class _Kursor:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _Conn:
    """Atrapa polaczenia: bankroll 100 PLN, kelly_fraction 4."""

    def __init__(self, bankroll=100.0, fraction=4):
        self._bankroll = bankroll
        self._fraction = fraction

    def execute(self, sql, params=()):
        if "bankroll_state" in sql:
            return _Kursor({"balance": self._bankroll})
        if "bot_settings" in sql:
            return _Kursor({"value": self._fraction})
        return _Kursor(None)

    def commit(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def baza(monkeypatch):
    """Podstawia _connect w module tras — endpoint kelly czyta bankroll z DB."""
    stan = {"conn": _Conn()}
    monkeypatch.setattr(cr, "_connect", lambda *a, **k: stan["conn"])
    return stan


# ── _fallback_predictions / _mock_predictions ───────────────────────────────

def test_bez_demo_mode_zwraca_pusto(monkeypatch):
    """BEZPIECZNIK: realny user nie moze zobaczyc zmyslonych meczow."""
    monkeypatch.delenv("DEMO_MODE", raising=False)
    assert cr._fallback_predictions() == []


@pytest.mark.parametrize("wartosc", ["0", "", "true", "yes", " "])
def test_tylko_dokladnie_jedynka_wlacza_demo(monkeypatch, wartosc):
    monkeypatch.setenv("DEMO_MODE", wartosc)
    assert cr._fallback_predictions() == []


def test_demo_mode_zwraca_mocki(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "1")
    wynik = cr._fallback_predictions()
    assert wynik
    assert wynik == cr._mock_predictions() or len(wynik) == len(cr._mock_predictions())


def test_demo_mode_toleruje_spacje(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "  1  ")
    assert cr._fallback_predictions() != []


def test_mocki_maja_daty_w_przyszlosci():
    """Mock z przeszla data wygladalby jak zaleglosc do rozliczenia."""
    from datetime import datetime

    dzis = datetime.now().strftime("%Y-%m-%d")
    for m in cr._mock_predictions():
        data = m.get("data") or m.get("date") or ""
        if data:
            assert data >= dzis, f"mock ma date z przeszlosci: {data}"


# ── _fetch_predictions ──────────────────────────────────────────────────────

def test_brak_klucza_bzzoiro_idzie_w_fallback(monkeypatch):
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.setenv("BZZOIRO_KEY", "")
    assert cr._fetch_predictions() == []


def test_pusta_odpowiedz_bzzoiro_idzie_w_fallback(monkeypatch):
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.setenv("BZZOIRO_KEY", "klucz")

    import footstats.scrapers.bzzoiro as bz

    class _Klient:
        def __init__(self, key):
            pass

        def predykcje_tygodnia(self):
            return []

    monkeypatch.setattr(bz, "BzzoiroClient", _Klient)
    assert cr._fetch_predictions() == []


def test_realne_predykcje_przechodza(monkeypatch):
    monkeypatch.setenv("BZZOIRO_KEY", "klucz")

    import footstats.scrapers.bzzoiro as bz

    class _Klient:
        def __init__(self, key):
            pass

        def predykcje_tygodnia(self):
            return [{"mecz": "A vs B"}]

    monkeypatch.setattr(bz, "BzzoiroClient", _Klient)
    assert cr._fetch_predictions() == [{"mecz": "A vs B"}]


def test_awaria_bzzoiro_nie_wywala_endpointu(monkeypatch):
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.setenv("BZZOIRO_KEY", "klucz")

    import footstats.scrapers.bzzoiro as bz

    class _Klient:
        def __init__(self, key):
            raise RuntimeError("API padlo")

    monkeypatch.setattr(bz, "BzzoiroClient", _Klient)
    assert cr._fetch_predictions() == []


# ── /api/coupon/kelly ───────────────────────────────────────────────────────

def _kelly(naglowki, selections, **extra):
    return client.post("/api/coupon/kelly", headers=naglowki,
                       json={"selections": selections, **extra})


def _typ(odds=2.0, win_prob=55.0, **kw) -> dict:
    baza = {"match_id": "1", "home": "A", "away": "B", "tip": "1",
            "odds": odds, "win_prob": win_prob}
    baza.update(kw)
    return baza


def test_kelly_bez_typow_daje_400(naglowki, baza):
    assert _kelly(naglowki, []).status_code == 400


def test_kelly_liczy_kurs_laczny_i_prawdopodobienstwo(naglowki, baza):
    r = _kelly(naglowki, [_typ(odds=2.0, win_prob=50.0), _typ(odds=1.5, win_prob=80.0)])
    assert r.status_code == 200, r.text
    dane = r.json()
    assert dane["total_odds"] == 3.0            # 2.0 * 1.5
    assert dane["win_prob_pct"] == 40.0         # 0.5 * 0.8


def test_kelly_akceptuje_prawdopodobienstwo_jako_ulamek(naglowki, baza):
    """win_prob moze przyjsc jako 0.55 albo 55 — oba znacza to samo."""
    r1 = _kelly(naglowki, [_typ(win_prob=0.55)])
    r2 = _kelly(naglowki, [_typ(win_prob=55.0)])
    assert r1.json()["win_prob_pct"] == r2.json()["win_prob_pct"] == 55.0


def test_kelly_minimalna_stawka_2_pln(naglowki, baza):
    """Ujemny edge → f*=0, ale stawka nie schodzi ponizej 2 PLN."""
    r = _kelly(naglowki, [_typ(odds=1.2, win_prob=30.0)])
    dane = r.json()
    assert dane["f_star_pct"] == 0.0
    assert dane["stake_pln"] == 2.0


def test_kelly_maksymalnie_20_procent_bankrolla(naglowki, baza):
    """Ogranicznik ryzyka: nawet przy ogromnym edge nie stawiamy wiecej niz 20%."""
    r = _kelly(naglowki, [_typ(odds=10.0, win_prob=95.0)])
    dane = r.json()
    assert dane["stake_pln"] <= round(dane["bankroll"] * 0.20, 2) + 0.01


def test_kelly_zwraca_komplet_pol(naglowki, baza):
    dane = _kelly(naglowki, [_typ()]).json()
    for pole in ("total_odds", "win_prob_pct", "f_star_pct", "stake_pln",
                 "bankroll", "kelly_fraction"):
        assert pole in dane, f"brak pola {pole}"


def test_kelly_wymaga_autoryzacji():
    assert client.post("/api/coupon/kelly",
                       json={"selections": [_typ()]}).status_code in (401, 403)


# ── /api/betbuilder/markets ─────────────────────────────────────────────────

def test_betbuilder_zwraca_lambdy_i_rynki(naglowki):
    r = client.post("/api/betbuilder/markets", headers=naglowki, json={
        "prob_home_win": 0.50, "prob_away_win": 0.25, "prob_over_25": 0.55,
        "selected": [],
    })
    assert r.status_code == 200, r.text
    dane = r.json()
    assert "lambdas" in dane
    assert dane["lambdas"]["home"] > 0 and dane["lambdas"]["away"] > 0


def test_betbuilder_faworyt_ma_wyzsza_lambde(naglowki):
    """Sanity: gospodarz z 70% szans na wygrana musi miec wieksze lambda."""
    r = client.post("/api/betbuilder/markets", headers=naglowki, json={
        "prob_home_win": 0.70, "prob_away_win": 0.10, "prob_over_25": 0.55,
        "selected": [],
    })
    lam = r.json()["lambdas"]
    assert lam["home"] > lam["away"]


def test_betbuilder_wymaga_autoryzacji():
    assert client.post("/api/betbuilder/markets", json={
        "prob_home_win": 0.50, "prob_away_win": 0.25, "prob_over_25": 0.55,
        "selected": [],
    }).status_code in (401, 403)


# ── /api/markets/catalog ────────────────────────────────────────────────────

def test_katalog_rynkow_zwraca_grupy(naglowki):
    r = client.post("/api/markets/catalog", headers=naglowki, json={
        "prob_home_win": 0.45, "prob_away_win": 0.30, "prob_over_25": 0.52,
    })
    assert r.status_code == 200, r.text
    dane = r.json()
    assert "lambdas" in dane and "grupy" in dane
    assert dane["grupy"], "pusty katalog rynkow"


def test_katalog_przyjmuje_kursy_bzzoiro(naglowki):
    r = client.post("/api/markets/catalog", headers=naglowki, json={
        "prob_home_win": 0.45, "prob_away_win": 0.30, "prob_over_25": 0.52,
        "odds": {"over_2_5": 1.85},
    })
    assert r.status_code == 200, r.text


def test_katalog_wymaga_autoryzacji():
    assert client.post("/api/markets/catalog", json={
        "prob_home_win": 0.45, "prob_away_win": 0.30, "prob_over_25": 0.52,
    }).status_code in (401, 403)


def test_procenty_odrzucane_bledem_422(naglowki):
    """Kontrakt to ULAMKI. Procenty konczyly sie cichym (1.0, 1.0) i bezsensownym
    katalogiem rynkow przy HTTP 200 — teraz to jawny blad walidacji."""
    for sciezka, ciało in (
        ("/api/betbuilder/markets",
         {"prob_home_win": 70.0, "prob_away_win": 10.0, "prob_over_25": 55.0,
          "selected": []}),
        ("/api/markets/catalog",
         {"prob_home_win": 45.0, "prob_away_win": 30.0, "prob_over_25": 52.0}),
    ):
        assert client.post(sciezka, headers=naglowki, json=ciało).status_code == 422, sciezka


def test_ujemne_prawdopodobienstwo_odrzucane(naglowki):
    r = client.post("/api/markets/catalog", headers=naglowki, json={
        "prob_home_win": -0.1, "prob_away_win": 0.3, "prob_over_25": 0.5,
    })
    assert r.status_code == 422
