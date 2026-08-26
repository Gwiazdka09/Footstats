"""J1/auth — cztery ciche `except` w `api/auth.py`, teraz głośne.

DLACZEGO CISZA W UWIERZYTELNIANIU JEST GROŹNIEJSZA NIŻ GDZIE INDZIEJ: 2026-07-27
redeploy zgubił `JWT_SECRET` z env Cloud Run. Logowanie zwracało użytkownikowi
"złe hasło" — czyli błąd KONFIGURACJI wyglądał identycznie jak błąd DANYCH
WEJŚCIOWYCH, a diagnoza poszła w złą stronę (szukano literówki w haśle, nie
zgubionej zmiennej środowiskowej). Cztery handlery naprawione tutaj mają
dokładnie ten sam kształt: awaria (uszkodzony hash, niesparsowalna data, upadły
INSERT) chowa się za wynikiem, który wygląda jak normalny stan systemu.

Każdy test tutaj:
  * wymusza sytuację wyjątkową,
  * sprawdza `caplog` — log poszedł na właściwym poziomie i treść WSKAZUJE
    PRZYCZYNĘ (nie samo "error"),
  * sprawdza, że zachowanie (zwracana wartość / kod HTTP) jest DOKŁADNIE takie
    samo jak przed naprawą — to ma być wyłącznie przywrócenie widoczności,
  * dla handlerów dotykających danych uwierzytelniających — sprawdza wprost,
    że podstawiony sekret (hasło/hash) NIE występuje w treści logu.
"""
from __future__ import annotations

import logging
import os

import psycopg2
import pytest

os.environ.setdefault("JWT_SECRET", "testsecret1234567890abcdef12345678")

import footstats.api.auth as _auth  # noqa: E402

_LOGGER = _auth.log.name


# ── 1. `_verify_password` — uszkodzony hash w bazie ─────────────────────────

def test_verify_password_uszkodzony_hash_loguje_ostrzezenie(monkeypatch, caplog):
    """Zły hash (np. placeholder 'changeme') nie jest zwykłą pomyłką hasła,
    tylko awarią DANYCH — ma zostać widoczny, nie zniknąć w cichym `except`."""
    haslo_testowe = "sekretne-haslo-uzytkownika-999"
    hash_testowy = "TAJNY-USZKODZONY-HASH-Z-BAZY"

    def _wybuchowy_checkpw(plain: bytes, hashed: bytes) -> bool:
        raise ValueError(f"invalid salt: {hashed!r}")

    monkeypatch.setattr(_auth.bcrypt, "checkpw", _wybuchowy_checkpw)

    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        wynik = _auth._verify_password(haslo_testowe, hash_testowy)

    # Zachowanie niezmienione: awaria hasha == zwykłe 401, nie 500 (audyt 2026-07-27).
    assert wynik is False
    tresc = " ".join(r.getMessage() for r in caplog.records)
    assert caplog.records, "uszkodzony hash zniknął bez śladu w logu"
    assert "uszkodzony hash" in tresc.lower(), tresc
    # Sekret NIE może trafić do logu — logujemy typ wyjątku, nie ładunek.
    assert haslo_testowe not in tresc
    assert hash_testowy not in tresc


def test_verify_password_poprawna_sciezka_bez_ostrzezenia(caplog):
    """Zdrowe hasło nie ma generować szumu — inaczej log przestaje coś znaczyć."""
    import bcrypt as _bcrypt_lib

    hash_ok = _bcrypt_lib.hashpw(b"dobre-haslo", _bcrypt_lib.gensalt()).decode()

    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        wynik = _auth._verify_password("dobre-haslo", hash_ok)

    assert wynik is True
    assert not caplog.records


# ── 2. `konto_zablokowane` — nieparsowalny `locked_until` ───────────────────

def test_konto_zablokowane_niesparsowalna_data_loguje_ostrzezenie(caplog):
    """Nieparsowalna wartość CICHO wyłączała ochronę B7 (blokadę po seriach
    błędnych haseł) dla tego konkretnego konta — to ma być widoczne."""
    haslo_hash_uzytkownika = "TAJNY-HASH-KONTA-77"
    user = {
        "id": 77,
        "username": "ktos",
        "password_hash": haslo_hash_uzytkownika,
        "locked_until": "nie-jest-data-iso",
    }

    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        wynik = _auth.konto_zablokowane(user)

    # Zachowanie niezmienione: nieparsowalna data == "nie zablokowane" (fail-open).
    assert wynik is False
    tresc = " ".join(r.getMessage() for r in caplog.records)
    assert caplog.records, "niesparsowalny locked_until zniknął bez śladu"
    assert "locked_until" in tresc, tresc
    assert "77" in tresc, "log nie wskazuje, KTÓRE konto ma uszkodzoną datę"
    # `user` niesie password_hash — nie ma prawa trafić do logu.
    assert haslo_hash_uzytkownika not in tresc


def test_konto_zablokowane_poprawna_sciezka_bez_ostrzezenia(caplog):
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        wynik = _auth.konto_zablokowane({"id": 1, "locked_until": None})

    assert wynik is False
    assert not caplog.records


# ── 3 i 4. `register` — dwa best-effort kroki po założeniu konta ────────────

class _Kursor:
    def __init__(self, wiersz):
        self._w = wiersz

    def fetchone(self):
        return self._w


class _PolaczenieRejestracji:
    """Atrapa DB dla `/auth/register` — handler otwiera DWA osobne `connect()`
    (users, potem bankroll_state); atrapa obsługuje oba przez ten sam obiekt."""

    def __init__(self, id_usera: int = 1, username: str = "nowyuser") -> None:
        self.id_usera = id_usera
        self.username = username
        self.zapytania: list[tuple] = []
        self.blad_bankroll: Exception | None = None

    def execute(self, sql, params=()):
        plaski = " ".join(sql.split())
        self.zapytania.append((plaski, params))
        gorny = plaski.upper()
        if gorny.startswith("INSERT INTO USERS"):
            return _Kursor({"id": self.id_usera, "username": self.username})
        if "BANKROLL_STATE" in gorny:
            if self.blad_bankroll is not None:
                raise self.blad_bankroll
            return _Kursor(None)
        return _Kursor(None)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def klient_rejestracji():
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


_HASLO_REJESTRACJI = "bezpieczne-haslo-123"


def test_rejestracja_gdy_bankroll_state_pada_loguje_i_konto_powstaje(
    monkeypatch, klient_rejestracji, caplog
):
    """Bez logu user zostaje BEZ startowego salda i nikt się o tym nie dowie
    aż do reklamacji — konto MA mimo to powstać (rejestracja się nie wywraca)."""
    polaczenie = _PolaczenieRejestracji(id_usera=1, username="nowyuser")
    polaczenie.blad_bankroll = psycopg2.Error("insert do bankroll_state nieudany")
    monkeypatch.setattr("footstats.utils.db.connect", lambda *a, **k: polaczenie)
    monkeypatch.setattr(
        "footstats.utils.mailer.send_welcome_email", lambda *a, **k: True
    )

    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        r = klient_rejestracji.post(
            "/api/auth/register",
            json={
                "username": "nowyuser",
                "email": "nowy@example.com",
                "password": _HASLO_REJESTRACJI,
            },
        )

    # Zachowanie niezmienione: rejestracja MA się udać mimo awarii tego kroku.
    assert r.status_code == 201
    assert "access_token" in r.json()
    tresc = " ".join(rec.getMessage() for rec in caplog.records)
    assert caplog.records, "awaria bankroll_state zniknęła bez śladu"
    assert "bankroll_state" in tresc, tresc
    assert "uid=1" in tresc, "log nie wskazuje, KTÓRE konto zostało bez salda"
    assert _HASLO_REJESTRACJI not in tresc


def test_rejestracja_gdy_mail_powitalny_pada_loguje_i_konto_powstaje(
    monkeypatch, klient_rejestracji, caplog
):
    """Cisza tu jest DECYZJĄ (rejestracja nie może zależeć od maila powitalnego),
    ale rzadka awaria (np. brak modułu) ma zostać widoczna na poziomie debug,
    a nie zniknąć bez żadnego śladu."""
    polaczenie = _PolaczenieRejestracji(id_usera=2, username="ktos")
    monkeypatch.setattr("footstats.utils.db.connect", lambda *a, **k: polaczenie)

    def _wybuch(*a, **k):
        raise RuntimeError("SMTP zdechl")

    monkeypatch.setattr("footstats.utils.mailer.send_welcome_email", _wybuch)

    with caplog.at_level(logging.DEBUG, logger=_LOGGER):
        r = klient_rejestracji.post(
            "/api/auth/register",
            json={
                "username": "ktos",
                "email": "ktos@example.com",
                "password": _HASLO_REJESTRACJI,
            },
        )

    # Zachowanie niezmienione: konto powstaje, mail powitalny to best-effort.
    assert r.status_code == 201
    assert "access_token" in r.json()
    tresc = " ".join(rec.getMessage() for rec in caplog.records)
    assert caplog.records, "awaria maila powitalnego zniknęła bez śladu"
    assert "powitalny" in tresc, tresc
    assert _HASLO_REJESTRACJI not in tresc


def test_rejestracja_zdrowa_sciezka_bez_ostrzezen(monkeypatch, klient_rejestracji, caplog):
    """Zdrowa rejestracja nie ma generować szumu w logu na poziomie WARNING."""
    polaczenie = _PolaczenieRejestracji(id_usera=3, username="zdrowy")
    monkeypatch.setattr("footstats.utils.db.connect", lambda *a, **k: polaczenie)
    monkeypatch.setattr(
        "footstats.utils.mailer.send_welcome_email", lambda *a, **k: True
    )

    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        r = klient_rejestracji.post(
            "/api/auth/register",
            json={
                "username": "zdrowy",
                "email": "zdrowy@example.com",
                "password": _HASLO_REJESTRACJI,
            },
        )

    assert r.status_code == 201
    assert not caplog.records
