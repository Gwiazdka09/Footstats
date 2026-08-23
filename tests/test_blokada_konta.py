"""B7 — konto nie zamykało się nigdy, choćby prób było tysiąc.

Do 23.08 jedyną obroną przed zgadywaniem hasła był limit na adres. Po naprawie B2
ten limit realnie działa (wcześniej miał JEDNO wiadro dla wszystkich), ale nie
broni przed rotacją adresów: botnet dostaje 10 prób na minutę Z KAŻDEGO adresu,
a konto nigdy się nie zamyka.

DWIE DECYZJE, obie z kosztem — zapisane tutaj, bo obie da się „poprawić" w złą stronę:

1. ZABLOKOWANE KONTO NIE SPRAWDZA HASŁA i odpowiada tak samo jak przy złym haśle.
   Kuszące jest powiedzieć „konto zablokowane" — ale wtedy trzeba najpierw
   zweryfikować hasło, żeby wiedzieć, komu to powiedzieć. To odtwarza wyrocznię:
   napastnik dalej testuje hasła i odróżnia trafione po treści odpowiedzi.
   Blokada, która sprawdza hasło, nie jest blokadą.

2. BLOKADA JEST CZASOWA I ROŚNIE WYKŁADNICZO, nie jest trwała. Trwała blokada
   zamienia lukę na inną: znając czyjś login, można go zamknąć na stałe kilkoma
   błędnymi próbami. Rosnące okno tnie zgadywanie do kilku prób na godzinę,
   a prawdziwemu użytkownikowi każe czekać minutę, nie wiecznie.
   Koszt zostaje: napastnik nadal potrafi utrudnić komuś logowanie. Świadomie.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from footstats.api.auth import (
    BLOKADA_CAP_MINUTY,
    BLOKADA_PROG,
    czas_blokady,
    konto_zablokowane,
)


def _uzytkownik(**nadpisz) -> dict:
    dane = {"id": 1, "username": "ktos", "password_hash": "hash",
            "failed_attempts": 0, "locked_until": None}
    dane.update(nadpisz)
    return dane


def _za(minut: int) -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=minut)


# ── kiedy konto jest zamknięte ──────────────────────────────────────────────

def test_konto_bez_bledow_jest_otwarte():
    assert konto_zablokowane(_uzytkownik()) is False


def test_konto_z_blokada_w_przyszlosci_jest_zamkniete():
    assert konto_zablokowane(_uzytkownik(locked_until=_za(5))) is True


def test_blokada_wygasa_sama():
    """Czasowa, nie trwała — inaczej zamieniamy lukę na inną."""
    assert konto_zablokowane(_uzytkownik(locked_until=_za(-1))) is False


def test_brak_kolumn_nie_wywala_logowania():
    """Konto sprzed migracji 15 nie ma tych pól — logowanie ma działać dalej."""
    assert konto_zablokowane({"id": 1, "username": "ktos"}) is False


# ── narastanie okna ─────────────────────────────────────────────────────────

def test_ponizej_progu_bez_blokady():
    assert czas_blokady(BLOKADA_PROG - 1) is None


def test_prog_wlacza_blokade():
    assert czas_blokady(BLOKADA_PROG) is not None


def test_okno_rosnie_z_kazda_kolejna_proba():
    """Stałe okno daje napastnikowi stałą przepustowość — ma rosnąć."""
    kolejne = [czas_blokady(BLOKADA_PROG + i) for i in range(4)]

    assert all(a < b for a, b in zip(kolejne, kolejne[1:])), kolejne


def test_okno_ma_sufit():
    """Bez sufitu blokada staje się trwała, czyli wraca problem z decyzji 2."""
    assert czas_blokady(BLOKADA_PROG + 50) == BLOKADA_CAP_MINUTY


def test_pierwsze_okno_jest_krotkie():
    """Prawdziwy użytkownik, który się pomylił, czeka minutę, nie kwadrans."""
    assert czas_blokady(BLOKADA_PROG) <= 2


# ── zachowanie logowania ────────────────────────────────────────────────────

@pytest.fixture
def klient(monkeypatch):
    import os

    os.environ.setdefault("JWT_SECRET", "testsecret1234567890abcdef12345678")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from footstats.api.auth import router
    from footstats.api.limiter import limiter

    app = FastAPI()
    app.include_router(router)
    limiter.enabled = False
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        limiter.enabled = True


def _podstaw_uzytkownika(monkeypatch, user: dict, zapisy: list):
    from footstats.api import auth as _auth

    monkeypatch.setattr(_auth, "get_user_by_username", lambda u: dict(user))
    monkeypatch.setattr(_auth, "get_user_by_email", lambda e: None)
    monkeypatch.setattr(_auth, "_zapisz_bledne_logowanie",
                        lambda uid, n: zapisy.append(("blad", uid, n)))
    monkeypatch.setattr(_auth, "_wyczysc_bledne_logowania",
                        lambda uid: zapisy.append(("reset", uid)))


def test_zablokowane_konto_NIE_sprawdza_hasla(klient, monkeypatch):
    """Sedno decyzji 1: weryfikacja hasła przy zablokowanym koncie odtwarzałaby
    wyrocznię — napastnik dalej testowałby hasła, tylko wolniej."""
    from footstats.api import auth as _auth

    wolania = []
    _podstaw_uzytkownika(monkeypatch, _uzytkownik(locked_until=_za(10)), [])
    monkeypatch.setattr(_auth, "_verify_password",
                        lambda p, h: wolania.append(p) or True)

    r = klient.post("/api/auth/login", json={"username": "ktos", "password": "dobre"})

    assert r.status_code == 401
    assert wolania == [], "haslo bylo sprawdzane mimo blokady"


def test_zablokowane_konto_odpowiada_jak_zle_haslo(klient, monkeypatch):
    """Inna treść = wyciek informacji, kto istnieje i kto jest zablokowany."""
    from footstats.api import auth as _auth

    _podstaw_uzytkownika(monkeypatch, _uzytkownik(locked_until=_za(10)), [])
    monkeypatch.setattr(_auth, "_verify_password", lambda p, h: False)
    zablokowane = klient.post("/api/auth/login",
                              json={"username": "ktos", "password": "x"}).json()

    _podstaw_uzytkownika(monkeypatch, _uzytkownik(), [])
    zle_haslo = klient.post("/api/auth/login",
                            json={"username": "ktos", "password": "x"}).json()

    assert zablokowane == zle_haslo


def test_bledne_haslo_zwieksza_licznik(klient, monkeypatch):
    from footstats.api import auth as _auth

    zapisy: list = []
    _podstaw_uzytkownika(monkeypatch, _uzytkownik(failed_attempts=2), zapisy)
    monkeypatch.setattr(_auth, "_verify_password", lambda p, h: False)

    klient.post("/api/auth/login", json={"username": "ktos", "password": "zle"})

    assert ("blad", 1, 3) in zapisy


def test_udane_logowanie_zeruje_licznik(klient, monkeypatch):
    """Bez zerowania konto zamyka się po kilku pomyłkach rozłożonych na tygodnie."""
    from footstats.api import auth as _auth

    zapisy: list = []
    _podstaw_uzytkownika(monkeypatch, _uzytkownik(failed_attempts=3), zapisy)
    monkeypatch.setattr(_auth, "_verify_password", lambda p, h: True)

    r = klient.post("/api/auth/login", json={"username": "ktos", "password": "dobre"})

    assert r.status_code == 200
    assert ("reset", 1) in zapisy


def test_nieistniejace_konto_nie_probuje_liczyc(klient, monkeypatch):
    """Nie ma czego blokować, a zapis do bazy dla każdej zmyślonej nazwy byłby
    wektorem zaśmiecania."""
    from footstats.api import auth as _auth

    zapisy: list = []
    monkeypatch.setattr(_auth, "get_user_by_username", lambda u: None)
    monkeypatch.setattr(_auth, "get_user_by_email", lambda e: None)
    monkeypatch.setattr(_auth, "_zapisz_bledne_logowanie",
                        lambda uid, n: zapisy.append(uid))

    r = klient.post("/api/auth/login", json={"username": "nie-ma-takiego", "password": "x"})

    assert r.status_code == 401
    assert zapisy == []


# ── migracja ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("dialekt", ["sqlite", "postgresql"])
def test_migracja_dodaje_kolumny(dialekt):
    from footstats.db.migrations import _get_migrations_for_dialect

    migracje = _get_migrations_for_dialect(dialekt)
    numery = [m[0] for m in migracje]
    assert 15 in numery, f"brak migracji 15 dla {dialekt}"

    sql = " ".join(s for m in migracje if m[0] == 15 for s in m[2]).lower()
    assert "failed_attempts" in sql
    assert "locked_until" in sql
