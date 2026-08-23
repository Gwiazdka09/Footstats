"""B10 — skradziony token dzialal do wygasniecia i nie bylo jak go uciac.

`token_version` (B1) uniewaznia tokeny przy ZMIANIE HASLA. Ale gdy haslo jest
w porzadku, a wyciekla sama kopia tokenu — z podejrzanego urzadzenia, ze
wspoldzielonego komputera, z logu — nie bylo zadnego sposobu, zeby ja odciac
bez zmiany hasla.

CZEGO TA ZMIANA *NIE* ROBI, powiedziane wprost zamiast ukryte:

  * NIE WYKRYWA kradziezy. Token jest bezstanowy i wyglada identycznie
    u wlasciciela i u napastnika.
  * NIE WIAZE tokenu z urzadzeniem ani adresem. Sprawdzone i ODRZUCONE:
    komorka zmienia adres przy kazdym przejsciu miedzy LTE a wifi, wiec
    powiazanie z IP wylogowywaloby prawdziwych uzytkownikow po kilka razy
    dziennie. Zabezpieczenie, ktore psuje sie samo, uczy ludzi ignorowac jego
    komunikaty — a napastnik w tej samej sieci i tak je omija.

CO ROBI: daje WYLACZNIK. Jedno zadanie uniewaznia wszystkie wydane tokeny,
a wolajacy dostaje swiezy, zeby nie odcial samego siebie. To ta sama maszyneria,
ktorej uzywa zmiana hasla (`_uniewaznij_sesje`), tyle ze dostepna bez zmiany hasla.

ODRZUCONE W TRAKCIE — `last_login_at`. Kolumna z czasem ostatniego logowania
wydawala sie tania i sensowna ("zobaczysz logowanie o 3 w nocy"), ale NIE DOTYCZY
tej luki: skradziony TOKEN nigdy sie nie loguje, zlodziej uzywa gotowej kopii,
wiec znacznik ani drgnie. Bylaby to kolumna wygladajaca jak zabezpieczenie
i nim niebedaca. Wykrycie kopii tokenu wymaga zapisywania adresu/przegladarki
przy KAZDYM zadaniu — dane osobowe plus koszt zapisu na kazde zadanie — i jest
swiadomym non-goalem, przypietym testem nizej.
"""
from __future__ import annotations

import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def klient(monkeypatch):
    os.environ.setdefault("JWT_SECRET", "testsecret1234567890abcdef12345678")
    from footstats.api.auth import router
    from footstats.api.limiter import limiter

    app = FastAPI()
    app.include_router(router)
    limiter.enabled = False
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        limiter.enabled = True


@pytest.fixture
def baza(monkeypatch):
    """Minimalny stan konta w pamieci — bez dotykania jakiejkolwiek bazy."""
    from footstats.api import auth as _auth

    stan = {"wersja": 0, "uniewaznien": 0}

    def _uniewaznij(conn, user_id):
        stan["wersja"] += 1
        stan["uniewaznien"] += 1

    monkeypatch.setattr(_auth, "_uniewaznij_sesje", _uniewaznij)
    monkeypatch.setattr(_auth, "stan_sesji",
                        lambda uid: {"wersja": stan["wersja"], "aktywne": True})

    class _Conn:
        """Atrapa musi oddawać wersję PO podbiciu — tak jak realny `SELECT`
        w tej samej transakcji co `UPDATE` (ten sam wzorzec co `change_password`).
        Atrapa zwracająca `None` dawałaby świeży token z `tv=0` przy koncie na
        wersji 1, czyli test padałby na własnym uproszczeniu, nie na kodzie."""

        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, *a, **k): return self

        def fetchone(self):
            return {"username": "ktos", "is_admin": False,
                    "token_version": stan["wersja"]}

    monkeypatch.setattr("footstats.utils.db.connect", lambda *a, **k: _Conn())
    return stan


def _token(uid: int = 1, wersja: int = 0) -> str:
    from footstats.api.auth import _make_token

    return _make_token("ktos", uid, False, wersja)


# ── wylacznik dziala ────────────────────────────────────────────────────────

def test_wyloguj_wszedzie_uniewaznia_sesje(klient, baza):
    r = klient.post("/api/auth/logout-all",
                    headers={"Authorization": f"Bearer {_token()}"})

    assert r.status_code == 200
    assert baza["uniewaznien"] == 1


def test_wolajacy_dostaje_swiezy_token(klient, baza):
    """Bez tego 'wyloguj wszedzie' odcina takze osobe, ktora go klika — czyli
    kazde uzycie konczy sie koniecznoscia ponownego logowania i ludzie przestaja
    z niego korzystac."""
    r = klient.post("/api/auth/logout-all",
                    headers={"Authorization": f"Bearer {_token()}"})

    assert r.status_code == 200
    assert r.json().get("access_token"), r.json()


def test_stary_token_przestaje_dzialac(klient, baza):
    """Sedno: token wydany PRZED wylogowaniem ma odpasc."""
    stary = _token(wersja=0)
    klient.post("/api/auth/logout-all", headers={"Authorization": f"Bearer {stary}"})

    r = klient.get("/api/auth/me", headers={"Authorization": f"Bearer {stary}"})

    assert r.status_code == 401


def test_nowy_token_dziala_po_wylogowaniu(klient, baza):
    odp = klient.post("/api/auth/logout-all",
                      headers={"Authorization": f"Bearer {_token()}"})
    nowy = odp.json()["access_token"]

    r = klient.get("/api/auth/me", headers={"Authorization": f"Bearer {nowy}"})

    assert r.status_code != 401


# ── endpoint jest chroniony ─────────────────────────────────────────────────

def test_bez_tokenu_odmowa(klient, baza):
    """Gdyby dzialal bez uwierzytelnienia, kazdy mogl by wylogowywac cudze konta."""
    r = klient.post("/api/auth/logout-all")

    assert r.status_code in (401, 403)
    assert baza["uniewaznien"] == 0


def test_smieciowy_token_odmowa(klient, baza):
    r = klient.post("/api/auth/logout-all",
                    headers={"Authorization": "Bearer nie-jest-tokenem"})

    assert r.status_code == 401
    assert baza["uniewaznien"] == 0


# ── granica zakresu ─────────────────────────────────────────────────────────

def test_brak_wiazania_tokenu_z_adresem():
    """Świadomy NON-GOAL, przypięty testem, żeby nie wrócił jako „ulepszenie".

    Powiązanie tokenu z adresem IP wygląda na oczywistą poprawę i nią nie jest:
    komórka zmienia adres przy każdym przejściu między LTE a wifi, więc prawdziwi
    użytkownicy wylatywaliby po kilka razy dziennie. Zabezpieczenie, które psuje
    się samo, uczy ludzi ignorować swoje komunikaty — a napastnik w tej samej
    sieci i tak je omija.
    """
    import inspect

    from footstats.api import auth as _auth

    zrodlo = inspect.getsource(_auth.require_auth) + inspect.getsource(_auth._sprawdz_wersje)

    assert "x-forwarded-for" not in zrodlo.lower(), (
        "token wiazany z adresem — patrz uzasadnienie w docstringu tego testu"
    )
    assert "client.host" not in zrodlo, "token wiazany z adresem polaczenia"
