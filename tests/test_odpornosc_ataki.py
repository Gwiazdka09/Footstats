"""Odporność na trzy klasyczne ataki: wstrzyknięcie SQL, brute-force, kradzież tokenu.

Te testy istnieją, żeby odpowiedź była MIERZONA, a nie deklarowana. Sprawdzają
zachowanie aplikacji, nie treść kodu — więc wyłapią też regresję, w której ktoś
w przyszłości przepisze zapytanie na f-stringa albo zdejmie limit z logowania.

ZERO kontaktu z produkcją: warstwa DB jest podmieniona na atrapę, która
zapamiętuje SQL i parametry ODDZIELNIE — to właśnie ten rozdział dowodzi
parametryzacji. Limiter jest resetowany między testami (współdzieli pamięć).

Trzy testy są celowo napisane „na zielono" wobec ISTNIEJĄCYCH LUK
(`test_BRAK_*`, `test_token_dziala_z_DOWOLNEGO_*`, `test_zmiana_hasla_NIE_*`).
Gdy luka zostanie załatana, taki test PADNIE — i to jest jego zadanie:
wymusić świadomą aktualizację audytu zamiast cichego rozjazdu dokumentacji.
"""
from __future__ import annotations

import os

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("JWT_SECRET", "testsecret1234567890abcdef12345678")

import bcrypt  # noqa: E402

_HASLO = "PoprawneHaslo123"
_HASH = bcrypt.hashpw(_HASLO.encode(), bcrypt.gensalt()).decode()

# `conftest` (autouse) podmienia `get_user_by_username` na atrape czytajaca env,
# gdy nie ma DATABASE_URL. Dla wiekszosci testow to wygodne, ale dowod
# parametryzacji SQL wymaga PRAWDZIWEJ funkcji — inaczej sprawdzalibysmy atrape.
# Chwytamy oryginal przy imporcie modulu, czyli ZANIM fikstury zdaza go podmienic,
# i przywracamy go we wlasnych fiksturach.
#
# Swiadomie NIE ruszamy tu `FOOTSTATS_PASSWORD_HASH`: inne pliki testowe ustawiaja
# go przez `setdefault`, wiec nadpisanie z tego modulu zabieraloby im haslo
# w zaleznosci od kolejnosci importow — klasyczne zatrucie miedzy testami.
from footstats.api import auth as _auth  # noqa: E402

_PRAWDZIWY_GET_USER = _auth.get_user_by_username

# Klasyka wstrzyknięć. Gdyby zapytanie było sklejane, każdy z tych ciągów albo
# obszedłby uwierzytelnienie, albo zmienił sens zapytania.
WSTRZYKNIECIA = [
    "admin' OR '1'='1",
    "admin' OR 1=1 --",
    "' OR ''='",
    "admin'--",
    "admin'; DROP TABLE users; --",
    "admin' UNION SELECT 1,2,3,4 --",
    "admin' AND 1=1; --",
]


class _Kursor:
    def __init__(self, wiersz):
        self._w = wiersz

    def fetchone(self):
        return self._w

    def fetchall(self):
        return [self._w] if self._w else []


class _Polaczenie:
    """Atrapa DB — zapamiętuje SQL i parametry OSOBNO.

    Zwraca użytkownika wyłącznie przy DOKŁADNYM dopasowaniu nazwy. Gdyby kod
    sklejał zapytanie, ładunek `' OR '1'='1` wylądowałby w tekście SQL i nigdy
    nie trafił tu jako parametr — co wykrywa `test_ladunek_idzie_PARAMETREM`.
    """

    zapisane: list[tuple] = []

    def execute(self, sql, params=()):
        _Polaczenie.zapisane.append((sql, params))
        if "FROM users" in sql and params and params[0] == "admin":
            return _Kursor({"id": 1, "username": "admin",
                            "password_hash": _HASH, "is_admin": False})
        return _Kursor(None)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _aplikacja():
    from footstats.api.auth import require_auth, router

    app = FastAPI()
    app.include_router(router)

    @app.get("/chronione")
    def chronione(uid: int = Depends(require_auth)):
        return {"uid": uid}

    return app


@pytest.fixture()
def klient(monkeypatch):
    """Prawdziwa ścieżka do bazy + atrapa połączenia. Limiter wyłączony.

    Przywracamy oryginalne `get_user_by_username`, bo tylko ono naprawdę buduje
    zapytanie — na atrapie z `conftest` dowód parametryzacji byłby bezwartościowy.
    """
    from footstats.api.limiter import limiter

    _Polaczenie.zapisane.clear()
    monkeypatch.setattr(_auth, "get_user_by_username", _PRAWDZIWY_GET_USER)
    monkeypatch.setattr("footstats.utils.db.connect", lambda: _Polaczenie())
    limiter.reset()
    limiter.enabled = False
    try:
        yield TestClient(_aplikacja(), raise_server_exceptions=False)
    finally:
        limiter.enabled = True
        limiter.reset()


def _zaloguj(klient) -> str:
    r = klient.post("/api/auth/login", json={"username": "admin", "password": _HASLO})
    assert r.status_code == 200, f"logowanie zwrocilo {r.status_code} — test nic nie sprawdza"
    return r.json()["access_token"]


# ── 1. Wstrzyknięcie SQL ───────────────────────────────────────────────────

def test_poprawne_dane_dalej_dzialaja(klient):
    """KONTROLA. Bez tego wszystkie testy niżej przechodziłyby na 401 „za darmo"."""
    assert _zaloguj(klient)


@pytest.mark.parametrize("ladunek", WSTRZYKNIECIA)
def test_wstrzykniecie_w_loginie_nie_wpuszcza(klient, ladunek):
    r = klient.post("/api/auth/login", json={"username": ladunek, "password": "cokolwiek"})
    assert r.status_code == 401, f"ladunek przeszedl: {ladunek}"


@pytest.mark.parametrize("ladunek", WSTRZYKNIECIA)
def test_wstrzykniecie_w_hasle_nie_wpuszcza(klient, ladunek):
    r = klient.post("/api/auth/login", json={"username": "admin", "password": ladunek})
    assert r.status_code == 401


def test_ladunek_idzie_PARAMETREM_a_nie_do_tekstu_sql(klient):
    """Sedno dowodu: ciąg ataku nie może pojawić się w TEKŚCIE zapytania."""
    klient.post("/api/auth/login",
                json={"username": "admin' OR 1=1 --", "password": "x"})
    zapytania = [z for z in _Polaczenie.zapisane if "FROM users" in z[0]]
    assert zapytania, "logowanie nie odpytalo bazy — test nic nie sprawdza"
    for sql, params in zapytania:
        assert "OR 1=1" not in sql, "ladunek trafil do TEKSTU SQL — sklejanie zapytan"
        assert "--" not in sql
        assert params and "OR 1=1" in str(params[0]), "ladunek powinien byc PARAMETREM"


def test_wstrzykniecie_przez_pole_email(klient):
    """Logowanie po e-mailu to druga ścieżka do bazy — też musi być parametryzowana."""
    klient.post("/api/auth/login",
                json={"username": "a@b.pl' OR '1'='1", "password": "x"})
    for sql, params in _Polaczenie.zapisane:
        assert "'1'='1" not in sql


# ── 2. Brute-force ─────────────────────────────────────────────────────────

@pytest.fixture()
def klient_z_limitem(monkeypatch):
    """Limiter WŁĄCZONY i wyzerowany — tu mierzymy realne blokowanie."""
    from footstats.api.limiter import limiter

    _Polaczenie.zapisane.clear()
    monkeypatch.setattr(_auth, "get_user_by_username", _PRAWDZIWY_GET_USER)
    monkeypatch.setattr("footstats.utils.db.connect", lambda: _Polaczenie())
    limiter.reset()
    limiter.enabled = True
    try:
        yield TestClient(_aplikacja(), raise_server_exceptions=False)
    finally:
        limiter.reset()


def test_zgadywanie_hasla_zostaje_ZABLOKOWANE(klient_z_limitem):
    """Realny pomiar: ile prób przechodzi, zanim limiter utnie."""
    odpowiedzi = [
        klient_z_limitem.post("/api/auth/login",
                              json={"username": "admin", "password": f"proba{i}"}).status_code
        for i in range(15)
    ]
    zablokowane = [s for s in odpowiedzi if s != 401]
    assert zablokowane, "15 prob zgadywania hasla przeszlo bez blokady"
    assert odpowiedzi.count(401) <= 10, (
        f"limit przepuscil {odpowiedzi.count(401)} prob — mial przepuscic 10")


def test_bledne_haslo_nie_zdradza_czy_konto_istnieje(klient):
    """Ta sama odpowiedź dla nieistniejącego konta i złego hasła — brak enumeracji."""
    a = klient.post("/api/auth/login", json={"username": "admin", "password": "zle"})
    b = klient.post("/api/auth/login", json={"username": "nieistnieje", "password": "zle"})
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


def test_BRAK_blokady_konta_po_serii_bledow():
    """UDOKUMENTOWANA LUKA, nie życzenie.

    Nie ma licznika nieudanych prób ani blokady konta — jedyną obroną jest limit
    per adres IP. Napastnik z puli adresów (botnet, rotacja proxy) dostaje
    10 prób na minutę Z KAŻDEGO adresu, a konto nigdy się nie zamyka.
    """
    import inspect

    from footstats.api import auth
    zrodlo = inspect.getsource(auth)
    for slad in ("failed_attempts", "lockout", "locked_until", "blokada_konta"):
        assert slad not in zrodlo, (
            f"pojawil sie '{slad}' — blokada konta chyba zostala dodana;"
            " zaktualizuj ten test i znalezisko B7 w audycie")


# ── 3. Kradzież / przenoszenie tokenu ──────────────────────────────────────

def test_token_dziala_z_DOWOLNEGO_adresu_i_przegladarki(klient):
    """UDOKUMENTOWANA LUKA: token nie jest z niczym związany.

    Skradziony token (XSS, log, cudzy komputer) działa z każdego adresu IP
    i każdej przeglądarki aż do wygaśnięcia — do 24 godzin.
    """
    token = _zaloguj(klient)
    r = klient.get("/chronione", headers={
        "Authorization": f"Bearer {token}",
        "User-Agent": "zupelnie-inna-przegladarka/1.0",
        "X-Forwarded-For": "203.0.113.77",
    })
    assert r.status_code == 200, "test opisuje stan faktyczny — zmien go razem z fixem"


def test_token_nie_niesie_odcisku_urzadzenia(klient):
    """Brak `jti`, powiązania z IP czy user-agentem = kopii tokenu nie da się wykryć."""
    from jose import jwt

    from footstats.api.auth import _secret

    dane = jwt.decode(_zaloguj(klient), _secret(), algorithms=["HS256"])
    assert set(dane) == {"sub", "uid", "adm", "exp"}, (
        "zmienil sie zestaw claimow — jesli doszedl jti/token_version,"
        " zaktualizuj znalezisko B1 w audycie")


def test_token_zyje_najwyzej_dobe(klient):
    """24h to długo dla tokenu bez możliwości odwołania — pilnujemy, by nie urosło."""
    from datetime import datetime, timezone

    from jose import jwt

    from footstats.api.auth import _secret

    dane = jwt.decode(_zaloguj(klient), _secret(), algorithms=["HS256"])
    godzin = (datetime.fromtimestamp(dane["exp"], timezone.utc)
              - datetime.now(timezone.utc)).total_seconds() / 3600
    assert godzin <= 24.1, "token zyje dluzej niz dobe, a nie da sie go uniewaznic"


def test_token_podpisany_obcym_sekretem_odrzucony(klient):
    """Kontrola pozytywna: podrobienie tokenu NIE działa."""
    from datetime import datetime, timedelta, timezone

    from jose import jwt

    obcy = jwt.encode(
        {"sub": "admin", "uid": 1, "adm": True,
         "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        "zupelnie-inny-sekret-atakujacego", algorithm="HS256")
    r = klient.get("/chronione", headers={"Authorization": f"Bearer {obcy}"})
    assert r.status_code == 401


def test_zmiana_hasla_NIE_uniewaznia_starego_tokenu(klient):
    """UDOKUMENTOWANA LUKA (B1) — sedno pytania o „przenoszenie tokenów".

    Po zmianie hasła stary token dalej otwiera konto. Przy przejęciu konta
    zmiana hasła NIE odbiera napastnikowi dostępu — do 24 godzin.
    """
    token = _zaloguj(klient)
    klient.post("/api/auth/change-password",
                headers={"Authorization": f"Bearer {token}"},
                json={"current_password": _HASLO, "new_password": "NoweHaslo12345"})

    r = klient.get("/chronione", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, (
        "stary token przestal dzialac — czyli doszlo uniewaznianie sesji;"
        " zaktualizuj ten test i znalezisko B1")
