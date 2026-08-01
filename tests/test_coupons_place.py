"""test_coupons_place.py — `/api/coupon/place`: zapis kuponu i obciazenie salda.

PO CO: to endpoint, ktorym kupon realnie trafia do bazy I zdejmuje pieniadze
z bankrolla. Ta sama klasa ryzyka co rozliczenia, tylko od drugiej strony.

Trzy bezpieczniki, ktore musza trzymac:

  * MINIMALNA STAWKA 2 PLN — nizsza nie ma sensu ekonomicznego, a zero albo
    wartosc ujemna wpisalaby do bankrolla smiec.
  * BANKROLL MUSI WYSTARCZYC. Bez tego saldo schodzi ponizej zera i cala
    dalsza matematyka (Kelly, ROI, drawdown) liczy sie z ujemnej bazy.
  * `validate_only` NIE ZAPISUJE. Ten tryb powstal po realnej awarii: operator
    smoke INSERT-owal kupony do produkcyjnej bazy i zjadal bankroll, zostawiajac
    martwe ACTIVE z data 2099 (komentarz w kodzie).

Czwarta rzecz: zapis kuponu, zdjecie salda i wpis do historii musza isc RAZEM.
Kupon bez wpisu w `bankroll_history` to dziura w audycie.
"""
from __future__ import annotations

import json
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
    """Atrapa polaczenia — notuje kazde zapytanie, oddaje saldo i nowe id."""

    def __init__(self, balance=100.0):
        self.balance = balance
        self.zapytania: list[tuple] = []

    def execute(self, sql, params=()):
        plaski = " ".join(sql.split())
        self.zapytania.append((plaski, params))
        g = plaski.upper()
        if g.startswith("SELECT BALANCE"):
            return _Kursor({"balance": self.balance} if self.balance is not None else None)
        if "INSERT INTO COUPONS" in g:
            return _Kursor({"id": 77})
        return _Kursor(None)

    def commit(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def polecenia(self, prefiks: str) -> list[tuple]:
        return [z for z in self.zapytania if z[0].upper().startswith(prefiks)]

    def zawierajace(self, fragment: str) -> list[tuple]:
        return [z for z in self.zapytania if fragment.upper() in z[0].upper()]


@pytest.fixture
def baza(monkeypatch):
    stan = {"conn": _Conn()}
    monkeypatch.setattr(cr, "_connect", lambda *a, **k: stan["conn"])
    import footstats.core.response_cache as rc
    monkeypatch.setattr(rc, "clear_response_cache", lambda: None, raising=False)
    return stan


def _noga(home="Legia", away="Lech", tip="1", odds=1.85, win_prob=60) -> dict:
    return {"match_id": "1", "home": home, "away": away,
            "tip": tip, "odds": odds, "win_prob": win_prob}


def _postaw(naglowki, **nadpisz):
    ciało = {
        "selections": [_noga()],
        "total_odds": 1.85,
        "stake_pln": 10.0,
        "match_date": "2026-08-02",
    }
    ciało.update(nadpisz)
    return client.post("/api/coupon/place", headers=naglowki, json=ciało)


# ── minimalna stawka ────────────────────────────────────────────────────────

@pytest.mark.parametrize("stawka", [0, 0.5, 1.99, -5])
def test_stawka_ponizej_dwoch_pln_odrzucona(naglowki, baza, stawka):
    r = _postaw(naglowki, stake_pln=stawka)
    assert r.status_code == 400
    assert baza["conn"].zawierajace("INSERT INTO coupons") == []


def test_stawka_dokladnie_dwa_pln_przechodzi(naglowki, baza):
    assert _postaw(naglowki, stake_pln=2.0).status_code == 200


# ── bankroll ────────────────────────────────────────────────────────────────

def test_stawka_ponad_saldo_odrzucona(naglowki, baza):
    """Bez tego saldo schodzi ponizej zera i cala matematyka liczy sie z ujemnej bazy."""
    baza["conn"].balance = 5.0
    r = _postaw(naglowki, stake_pln=50.0)

    assert r.status_code == 400
    assert "Niewystarczający bankroll" in r.json()["detail"]
    assert baza["conn"].zawierajace("INSERT INTO coupons") == []


def test_stawka_rowna_saldu_przechodzi(naglowki, baza):
    baza["conn"].balance = 10.0
    assert _postaw(naglowki, stake_pln=10.0).status_code == 200


def test_brak_wiersza_bankrolla_to_saldo_zero(naglowki, baza):
    """Nowy user bez wpisu w bankroll_state nie moze stawiac na kredyt."""
    baza["conn"].balance = None
    assert _postaw(naglowki, stake_pln=10.0).status_code == 400


# ── validate_only ───────────────────────────────────────────────────────────

def test_validate_only_nie_zapisuje_i_nie_rusza_salda(naglowki, baza):
    """REGRESJA: operator smoke INSERT-owal kupony do prod i zjadal bankroll,
    zostawiajac martwe ACTIVE z data 2099."""
    r = _postaw(naglowki, validate_only=True)

    assert r.status_code == 200
    assert r.json()["validated"] is True
    assert baza["conn"].zawierajace("INSERT INTO coupons") == []
    assert baza["conn"].zawierajace("UPDATE bankroll_state") == []
    assert baza["conn"].zawierajace("INSERT INTO bankroll_history") == []


def test_validate_only_nadal_sprawdza_bankroll(naglowki, baza):
    """Tryb walidacji ma WALIDOWAC, nie przepuszczac wszystkiego."""
    baza["conn"].balance = 1.0
    assert _postaw(naglowki, stake_pln=50.0, validate_only=True).status_code == 400


def test_validate_only_nadal_sprawdza_minimalna_stawke(naglowki, baza):
    assert _postaw(naglowki, stake_pln=0.5, validate_only=True).status_code == 400


# ── zapis kuponu ────────────────────────────────────────────────────────────

def test_zapisuje_kupon_i_zwraca_id(naglowki, baza):
    dane = _postaw(naglowki).json()
    assert dane["ok"] is True
    assert dane["coupon_id"] == 77


def test_kupon_zapisany_jako_aktywny_akumulator(naglowki, baza):
    _postaw(naglowki)
    params = baza["conn"].zawierajace("INSERT INTO coupons")[0][1]
    assert "ACTIVE" in params
    assert "accumulator" in params


def test_nogi_zapisane_jako_json(naglowki, baza):
    _postaw(naglowki, selections=[_noga("Legia", "Lech", "1", 1.85, 60),
                                  _noga("Wisła", "Raków", "X", 3.4, 28)])
    params = baza["conn"].zawierajace("INSERT INTO coupons")[0][1]
    legs = json.loads(next(p for p in params if isinstance(p, str) and p.startswith("[")))

    assert len(legs) == 2
    assert legs[0]["home"] == "Legia" and legs[0]["tip"] == "1"
    assert legs[1]["odds"] == 3.4


def test_polskie_znaki_w_nazwach_zachowane(naglowki, baza):
    _postaw(naglowki, selections=[_noga("Raków Częstochowa", "Śląsk Wrocław")])
    params = baza["conn"].zawierajace("INSERT INTO coupons")[0][1]
    legs_json = next(p for p in params if isinstance(p, str) and p.startswith("["))
    assert "Raków" in legs_json, "nazwy zapisane z escapowaniem unicode"


def test_kupon_przypisany_do_uzytkownika(naglowki, baza):
    """Kupon bez user_id byłby widoczny dla wszystkich kont."""
    _postaw(naglowki)
    sql = baza["conn"].zawierajace("INSERT INTO coupons")[0][0]
    assert "user_id" in sql


# ── bankroll: zdjecie stawki + audyt ────────────────────────────────────────

def test_saldo_pomniejszone_o_stawke(naglowki, baza):
    baza["conn"].balance = 100.0
    dane = _postaw(naglowki, stake_pln=25.0).json()

    assert dane["new_balance"] == 75.0
    update = baza["conn"].zawierajace("UPDATE bankroll_state")[0][1]
    assert update[0] == 75.0


def test_wpis_do_historii_bankrolla(naglowki, baza):
    """Kupon bez wpisu w bankroll_history to dziura w audycie."""
    _postaw(naglowki, stake_pln=10.0)
    historia = baza["conn"].zawierajace("INSERT INTO bankroll_history")

    assert len(historia) == 1
    params = historia[0][1]
    assert params[1] == -10.0, "zmiana salda ma byc UJEMNA przy postawieniu"
    assert params[3] == "BET"


def test_zapis_saldo_i_historia_ida_razem(naglowki, baza):
    _postaw(naglowki)
    conn = baza["conn"]
    assert conn.zawierajace("INSERT INTO coupons")
    assert conn.zawierajace("UPDATE bankroll_state")
    assert conn.zawierajace("INSERT INTO bankroll_history")


def test_historia_tez_przypisana_do_uzytkownika(naglowki, baza):
    _postaw(naglowki)
    sql = baza["conn"].zawierajace("INSERT INTO bankroll_history")[0][0]
    assert "user_id" in sql


def test_saldo_aktualizowane_tylko_dla_wlasciciela(naglowki, baza):
    """UPDATE bez WHERE user_id ruszylby saldo wszystkich kont."""
    _postaw(naglowki)
    sql = baza["conn"].zawierajace("UPDATE bankroll_state")[0][0]
    assert "user_id" in sql.lower()


# ── autoryzacja ─────────────────────────────────────────────────────────────

def test_bez_tokenu_odrzucone(baza):
    r = client.post("/api/coupon/place", json={
        "selections": [_noga()], "total_odds": 1.85, "stake_pln": 10.0,
    })
    assert r.status_code in (401, 403)
    assert baza["conn"].zawierajace("INSERT INTO coupons") == []
