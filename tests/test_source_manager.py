"""test_source_manager.py — które źródło danych karmi model.

PO CO: `SourceManager` decyduje, z których źródeł wolno korzystać. Reszta kodu
pyta go o to przez `bzzoiro_ok` / `apisports_ok`. Pomyłka w tę stronę jest cicha:
model liczy dalej, tylko na gorszych albo niepełnych danych.

Najważniejsza własność to FAIL-CLOSED: dopóki walidacja nie przebiegła, oba
flagi muszą być False. Gdyby domyślnie były True, kod sięgałby po źródło,
którego klucza nikt nie sprawdził — i dowiedziałby się o tym dopiero z pustych
odpowiedzi.

football-data.org jest OBOWIĄZKOWE (reszta jest opcjonalna), więc jego awaria
musi być zgłoszona wprost, a nie schowana w tabeli statusu.

UWAGA: `dodaj_klucz_interaktywnie` zapisuje do .env. Tu jest zamockowane —
żaden test nie może tknąć prawdziwego pliku.
"""
from __future__ import annotations

import pytest

import footstats.scrapers.source_manager as sm
from footstats.config import ENV_APISPORTS, ENV_BZZOIRO, ENV_FOOTBALL
from footstats.scrapers.source_manager import SourceManager


class _Klient:
    """Atrapa klienta źródła — oddaje ustalony wynik walidacji."""

    def __init__(self, ok=True, msg="OK"):
        self._wynik = (ok, msg)
        self.wywolan = 0

    def waliduj(self):
        self.wywolan += 1
        return self._wynik


class _Resp:
    def __init__(self, status, dane=None):
        self.status_code = status
        self._dane = dane or {}

    def json(self):
        return self._dane


@pytest.fixture(autouse=True)
def _otoczenie(monkeypatch):
    """Wycisza konsolę i odcina cache/budżet od dysku."""
    monkeypatch.setattr(sm.console, "print", lambda *a, **k: None)
    monkeypatch.setattr(sm, "af_cache_info", lambda: {"wpisy": 0, "najnowszy": "–"})
    monkeypatch.setattr(sm, "af_budget_status", lambda: {
        "uzyto": 10, "limit": 100, "pozostalo": 90, "procent": 10.0,
        "ostrzezenie": False, "krytyczny": False})


def _manager(fdb=True, af=False, bzz=False,
             af_wynik=(True, "OK"), bzz_wynik=(True, "OK")) -> SourceManager:
    """SourceManager z podstawionymi klientami zamiast prawdziwych."""
    m = SourceManager({})
    m.fdb = object() if fdb else None            # type: ignore[assignment]
    m.af = _Klient(*af_wynik) if af else None    # type: ignore[assignment]
    m.bzz = _Klient(*bzz_wynik) if bzz else None  # type: ignore[assignment]
    return m


# ── konstruktor: klient tylko gdy jest klucz ────────────────────────────────

def test_brak_kluczy_to_brak_klientow():
    m = SourceManager({})

    assert (m.fdb, m.af, m.bzz) == (None, None, None)


def test_pusty_klucz_nie_tworzy_klienta():
    """Pusty string w .env to brak klucza, nie klucz o zerowej długości."""
    m = SourceManager({ENV_FOOTBALL: "", ENV_APISPORTS: "", ENV_BZZOIRO: ""})

    assert (m.fdb, m.af, m.bzz) == (None, None, None)


def test_klucze_tworza_klientow():
    m = SourceManager({ENV_FOOTBALL: "a", ENV_APISPORTS: "b", ENV_BZZOIRO: "c"})

    assert m.fdb is not None and m.af is not None and m.bzz is not None


# ── fail-closed: flagi przed walidacją ──────────────────────────────────────

def test_flagi_falszywe_przed_walidacja():
    """Bez tego kod sięgałby po źródło, którego klucza nikt nie sprawdził."""
    m = SourceManager({ENV_APISPORTS: "klucz", ENV_BZZOIRO: "klucz"})

    assert m.apisports_ok is False
    assert m.bzzoiro_ok is False


def test_flagi_falszywe_gdy_brak_klucza(monkeypatch):
    m = _manager(af=False, bzz=False)
    monkeypatch.setattr(m, "_test_fdb", lambda: (True, "ok"))

    m.waliduj_i_wyswietl()

    assert m.apisports_ok is False
    assert m.bzzoiro_ok is False


# ── walidacja ustawia flagi ─────────────────────────────────────────────────

def test_zrodla_poprawne_ustawiaja_flagi(monkeypatch):
    m = _manager(af=True, bzz=True)
    monkeypatch.setattr(m, "_test_fdb", lambda: (True, "12 rozgrywek"))

    m.waliduj_i_wyswietl()

    assert m.apisports_ok is True
    assert m.bzzoiro_ok is True


def test_zly_klucz_nie_wlacza_zrodla(monkeypatch):
    """Klucz obecny, ale odrzucony przez API — źródła NIE wolno używać."""
    m = _manager(af=True, bzz=True, af_wynik=(False, "401"), bzz_wynik=(False, "401"))
    monkeypatch.setattr(m, "_test_fdb", lambda: (True, "ok"))

    m.waliduj_i_wyswietl()

    assert m.apisports_ok is False
    assert m.bzzoiro_ok is False


def test_zrodla_walidowane_dokladnie_raz(monkeypatch):
    """Każda walidacja to realne zapytanie — a budżet API-Football to 100/dobę."""
    m = _manager(af=True, bzz=True)
    monkeypatch.setattr(m, "_test_fdb", lambda: (True, "ok"))

    m.waliduj_i_wyswietl()

    assert m.af.wywolan == 1
    assert m.bzz.wywolan == 1


def test_zrodla_niezalezne_od_siebie(monkeypatch):
    """Awaria jednego źródła nie może wyłączyć pozostałych."""
    m = _manager(af=True, bzz=True, af_wynik=(False, "401"))
    monkeypatch.setattr(m, "_test_fdb", lambda: (True, "ok"))

    m.waliduj_i_wyswietl()

    assert m.apisports_ok is False
    assert m.bzzoiro_ok is True


def test_awaria_obowiazkowego_zrodla_zglaszana(monkeypatch):
    """football-data.org jest obowiązkowe — jego brak nie może zginąć w tabeli."""
    komunikaty = []
    monkeypatch.setattr(sm.console, "print", lambda *a, **k: komunikaty.append(str(a)))
    m = _manager(fdb=False)

    m.waliduj_i_wyswietl()

    assert any("obowiazkowy" in k for k in komunikaty)


def test_brak_ostrzezenia_gdy_obowiazkowe_dziala(monkeypatch):
    komunikaty = []
    monkeypatch.setattr(sm.console, "print", lambda *a, **k: komunikaty.append(str(a)))
    m = _manager(fdb=True)
    monkeypatch.setattr(m, "_test_fdb", lambda: (True, "ok"))

    m.waliduj_i_wyswietl()

    assert not any("obowiazkowy" in k for k in komunikaty)


# ── _test_fdb ───────────────────────────────────────────────────────────────

@pytest.fixture
def fdb(monkeypatch):
    stan = {"odpowiedz": _Resp(200, {"competitions": [1, 2]})}

    def fake_get(url, **kw):
        o = stan["odpowiedz"]
        if isinstance(o, Exception):
            raise o
        return o

    monkeypatch.setattr(sm.requests, "get", fake_get)
    m = SourceManager({})
    m.fdb = type("_C", (), {"headers": {"X-Auth-Token": "tok"}})()
    stan["m"] = m
    return stan


def test_fdb_poprawny_klucz(fdb):
    ok, msg = fdb["m"]._test_fdb()

    assert ok is True
    assert "2 rozgrywek" in msg


def test_fdb_zly_klucz(fdb):
    fdb["odpowiedz"] = _Resp(403)

    ok, msg = fdb["m"]._test_fdb()

    assert ok is False
    assert "403" in msg


def test_fdb_inny_blad_http(fdb):
    fdb["odpowiedz"] = _Resp(500)

    ok, msg = fdb["m"]._test_fdb()

    assert ok is False
    assert "500" in msg


def test_fdb_awaria_sieci_nie_wywala(fdb):
    """Brak sieci ma dać status BŁĄD, nie wyjątek na starcie programu."""
    fdb["odpowiedz"] = OSError("connection refused")

    ok, msg = fdb["m"]._test_fdb()

    assert ok is False
    assert msg


# ── dodaj_klucz_interaktywnie (zapis do .env — zamockowany) ─────────────────

@pytest.fixture
def env_zapis(monkeypatch):
    """Przechwytuje zapis do .env; prawdziwy plik pozostaje nietknięty."""
    stan = {"zapisy": [], "odpowiedz": "nowy-klucz"}
    monkeypatch.setattr(sm, "set_key", lambda plik, k, v: stan["zapisy"].append((k, v)))
    monkeypatch.setattr(sm.Prompt, "ask", staticmethod(lambda *a, **k: stan["odpowiedz"]))
    import dotenv
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: None)
    return stan


def test_podany_klucz_zapisany(env_zapis):
    wynik = SourceManager({}).dodaj_klucz_interaktywnie(ENV_BZZOIRO)

    assert wynik == "nowy-klucz"
    assert env_zapis["zapisy"] == [(ENV_BZZOIRO, "nowy-klucz")]


@pytest.mark.parametrize("puste", ["", "   "])
def test_pusta_odpowiedz_nic_nie_zapisuje(env_zapis, puste):
    """Enter zamiast klucza nie może nadpisać .env pustą wartością."""
    env_zapis["odpowiedz"] = puste

    wynik = SourceManager({}).dodaj_klucz_interaktywnie(ENV_APISPORTS)

    assert wynik is None
    assert env_zapis["zapisy"] == []


def test_klucz_przyciety_z_bialych_znakow(env_zapis):
    """Klucz wklejony ze spacją na końcu psuje nagłówek Authorization."""
    env_zapis["odpowiedz"] = "  klucz-ze-spacjami  "

    SourceManager({}).dodaj_klucz_interaktywnie(ENV_BZZOIRO)

    assert env_zapis["zapisy"] == [(ENV_BZZOIRO, "klucz-ze-spacjami")]


def test_nieznane_zrodlo_nie_wywala(env_zapis):
    """Brak opisu w słowniku to nie powód do wyjątku."""
    assert SourceManager({}).dodaj_klucz_interaktywnie("JAKIS_INNY_KLUCZ") == "nowy-klucz"
