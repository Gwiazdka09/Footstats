"""Zmiana hasła musi odbierać dostęp — wcześniej nie odbierała przez 24h.

ZNALEZISKO B1 z audytu 17.08, zmierzone testem: token żyje dobę i jest bezstanowy
(brak `jti`, brak wersji, brak powiązania z urządzeniem). Po przejęciu konta
zmiana hasła NIE wyrzucała napastnika — stary token otwierał konto do końca doby.

Fix: kolumna `users.token_version` (migracja 14) + claim `tv` w tokenie.
Podbicie wersji unieważnia wszystkie wydane dotąd tokeny jednym UPDATE-em.

Dwie decyzje projektowe są tu testowane wprost, bo obie da się „naprawić" w złą stronę:
  * brak `tv` w tokenie = wersja 0 — inaczej wdrożenie wylogowałoby wszystkich;
  * błąd bazy PRZEPUSZCZA token (fail-open) — podpis jest już zweryfikowany,
    a przy niedostępnej bazie żaden endpoint i tak nie zwróci danych.
"""
from __future__ import annotations

import os

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("JWT_SECRET", "testsecret1234567890abcdef12345678")

from footstats.api import auth as _auth  # noqa: E402


@pytest.fixture()
def klient(monkeypatch):
    from footstats.api.auth import require_auth, router

    app = FastAPI()
    app.include_router(router)

    @app.get("/chronione")
    def chronione(uid: int = Depends(require_auth)):
        return {"uid": uid}

    from footstats.api.limiter import limiter
    limiter.enabled = False
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        limiter.enabled = True


def _token(wersja: int, uid: int = 1) -> str:
    return _auth._make_token("admin", uid, False, wersja)


def _ustaw_wersje_w_bazie(monkeypatch, wersja, aktywne=True):
    """Podmienia odczyt stanu sesji. `wersja=None` udaje niedostępną bazę."""
    stan = None if wersja is None else {"wersja": wersja, "aktywne": aktywne}
    monkeypatch.setattr(_auth, "stan_sesji", lambda uid: stan)


# ── podstawy ───────────────────────────────────────────────────────────────

def test_token_z_aktualna_wersja_przechodzi(klient, monkeypatch):
    _ustaw_wersje_w_bazie(monkeypatch, 3)
    r = klient.get("/chronione", headers={"Authorization": f"Bearer {_token(3)}"})
    assert r.status_code == 200


def test_token_ze_STARA_wersja_odrzucony(klient, monkeypatch):
    """Sedno B1: po podbiciu wersji stary token przestaje otwierać konto."""
    _ustaw_wersje_w_bazie(monkeypatch, 4)
    r = klient.get("/chronione", headers={"Authorization": f"Bearer {_token(3)}"})
    assert r.status_code == 401
    assert "Sesja" in r.json()["detail"]


def test_token_z_PRZYSZLA_wersja_tez_odrzucony(klient, monkeypatch):
    """Porównanie jest na równość, nie „>=" — token spoza kolejki też jest zły."""
    _ustaw_wersje_w_bazie(monkeypatch, 2)
    r = klient.get("/chronione", headers={"Authorization": f"Bearer {_token(9)}"})
    assert r.status_code == 401


# ── zgodność wstecz i odporność ────────────────────────────────────────────

def test_STARY_token_bez_claimu_tv_dalej_dziala(klient, monkeypatch):
    """Tokeny sprzed tej zmiany nie mają `tv`. Traktowanie ich jako nieważne
    wylogowałoby wszystkich przy samym wdrożeniu — kolumna startuje od 0."""
    from datetime import datetime, timedelta, timezone

    import jwt
    stary = jwt.encode(
        {"sub": "admin", "uid": 1, "adm": False,
         "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        _auth._secret(), algorithm="HS256")

    _ustaw_wersje_w_bazie(monkeypatch, 0)
    r = klient.get("/chronione", headers={"Authorization": f"Bearer {stary}"})
    assert r.status_code == 200


def test_stary_token_bez_tv_pada_po_pierwszym_uniewaznieniu(klient, monkeypatch):
    """Zgodność wstecz nie może oznaczać nieśmiertelności."""
    from datetime import datetime, timedelta, timezone

    import jwt
    stary = jwt.encode(
        {"sub": "admin", "uid": 1, "adm": False,
         "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        _auth._secret(), algorithm="HS256")

    _ustaw_wersje_w_bazie(monkeypatch, 1)
    r = klient.get("/chronione", headers={"Authorization": f"Bearer {stary}"})
    assert r.status_code == 401


def test_blad_bazy_PRZEPUSZCZA_token(klient, monkeypatch):
    """Fail-open, świadomie.

    Podpis jest już zweryfikowany, a przy niedostępnej bazie żaden endpoint i tak
    nie zwróci danych — więc to nie otwiera nowej drogi wejścia. Fail-closed
    wylogowywałby wszystkich przy każdym zakrztuszeniu bazy.
    """
    _ustaw_wersje_w_bazie(monkeypatch, None)
    r = klient.get("/chronione", headers={"Authorization": f"Bearer {_token(3)}"})
    assert r.status_code == 200


def test_podrobiony_token_dalej_odrzucany(klient, monkeypatch):
    """Kontrola: wersja tokenu to DODATKOWA bramka, nie zamiennik podpisu."""
    from datetime import datetime, timedelta, timezone

    import jwt
    obcy = jwt.encode(
        {"sub": "admin", "uid": 1, "adm": True, "tv": 0,
         "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        "sekret-atakujacego", algorithm="HS256")

    _ustaw_wersje_w_bazie(monkeypatch, 0)
    r = klient.get("/chronione", headers={"Authorization": f"Bearer {obcy}"})
    assert r.status_code == 401


# ── odczyt wersji z bazy ───────────────────────────────────────────────────

def test_konto_nieaktywne_traci_dostep_natychmiast(klient, monkeypatch):
    """Luka, ktorej `require_auth` NIE mialo wczesniej wcale.

    Strażnik przepuszczal token konta dezaktywowanego, a odsiew zalezal od tego,
    czy konkretny endpoint sam sprawdzi `is_active`. Skoro i tak czytamy baze
    przy kazdym zadaniu, sprawdzamy to raz, w jednym miejscu.
    """
    _ustaw_wersje_w_bazie(monkeypatch, 0, aktywne=False)
    r = klient.get("/chronione", headers={"Authorization": f"Bearer {_token(0)}"})
    assert r.status_code == 401
    assert "nieaktywne" in r.json()["detail"].lower()


# ── odczyt stanu z bazy ────────────────────────────────────────────────────

def test_awaria_bazy_daje_None(monkeypatch):
    """`None` (awaria) musi byc odrozialne od stanu konta — wolajacy przepuszcza."""
    def _wybuch():
        raise RuntimeError("baza padla")
    monkeypatch.setattr("footstats.utils.db.connect", _wybuch)
    assert _auth.stan_sesji(1) is None


def test_brak_wiersza_to_konto_NIEAKTYWNE_a_nie_awaria(monkeypatch):
    """Konto usuniete/zanonimizowane musi ODRZUCAC token, nie przepuszczac go.

    Pierwsza wersja tej funkcji zwracala tu `None`, czyli traktowala usuniete
    konto jak awarie bazy i wpuszczala jego token — wlasna dziura, wprowadzona
    przy naprawie B1.
    """
    class _Conn:
        def execute(self, *a, **k):
            class _K:
                def fetchone(self):
                    return None
            return _K()
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    monkeypatch.setattr("footstats.utils.db.connect", lambda: _Conn())
    stan = _auth.stan_sesji(999)
    assert stan is not None, "brak wiersza to NIE awaria"
    assert stan["aktywne"] is False


def test_odczyt_zwraca_wersje_i_aktywnosc(monkeypatch):
    class _Conn:
        def execute(self, *a, **k):
            class _K:
                def fetchone(self):
                    return {"wersja": 5, "is_active": True}
            return _K()
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    monkeypatch.setattr("footstats.utils.db.connect", lambda: _Conn())
    assert _auth.stan_sesji(1) == {"wersja": 5, "aktywne": True}
