"""test_api_football_bledy_w_tresci.py — API-Football zglasza bledy przy HTTP 200.

PO CO: api-sports.io NIE uzywa kodow HTTP do sygnalizowania problemow z kontem.
Zawieszone konto, zly klucz i przekroczony plan zwracaja **HTTP 200** z trescia:

    {"errors": {"access": "Your account is suspended..."}, "response": []}

Kod traktowal to jak poprawna odpowiedz, przez co:

  * `_get` ZAPISYWAL pusta odpowiedz do cache na 24h — jedna awaria konta
    zatruwala dane na dobe, nawet po jej usunieciu;
  * `_enrichuj_finalna_faza` widzial `response: []`, bral to za "brak meczow
    dzis" i pomijal wszystkich kandydatow. Fallback FlashScore siedzi WEWNATRZ
    petli po kandydatach, wiec nie odpalal sie ani razu;
  * `waliduj()` wywalal sie nieprzechwyconym AttributeError, bo `response` bylo
    lista `[]`, a kod robil na niej `.get()`. `SourceManager` nie lapie tego
    wyjatku, wiec CLI padalo przy starcie.

Zdarzylo sie naprawde: 2026-08-01 konto zostalo zawieszone i zaden z tych trzech
objawow nie powiedzial, co jest grane. Patrz [[project-apifootball-zawieszone]].
"""
from __future__ import annotations

import pytest

import footstats.scrapers.api_football as af_mod
from footstats.scrapers.api_football import APIFootball

ZAWIESZONE = {
    "get": "status",
    "errors": {"access": "Your account is suspended, check on https://dashboard.api-football.com."},
    "results": 0,
    "response": [],
}
POPRAWNE_STATUS = {
    "errors": [],
    "response": {"requests": {"current": 12, "limit_day": 100},
                 "subscription": {"plan": "Free"}},
}


class _Resp:
    def __init__(self, dane, status=200):
        self.status_code = status
        self._dane = dane

    def json(self):
        return self._dane


@pytest.fixture
def siec(monkeypatch, tmp_path):
    """Podstawia siec i cache; zwraca uchwyt do sterowania odpowiedzia."""
    stan = {"odpowiedz": _Resp(POPRAWNE_STATUS), "zapisane": [], "wywolania": 0}

    def fake_get(url, **kw):
        stan["wywolania"] += 1
        return stan["odpowiedz"]

    monkeypatch.setattr(af_mod.requests, "get", fake_get)
    monkeypatch.setattr(af_mod, "_af_cache_get", lambda k: None)
    monkeypatch.setattr(af_mod, "_af_cache_set",
                        lambda k, d, s=None: stan["zapisane"].append((k, d)))
    monkeypatch.setattr(af_mod, "_af_load_disk_cache", lambda: {})
    monkeypatch.setattr(af_mod, "af_budget_status", lambda: {
        "uzyto": 0, "limit": 100, "pozostalo": 100, "procent": 0.0,
        "krytyczny": False, "ostrzezenie": False})
    monkeypatch.setattr(af_mod, "bezpieczny_budget_use", lambda e: 99)
    monkeypatch.setattr(af_mod.console, "print", lambda *a, **k: None)
    return stan


# ── waliduj: zawieszone konto ───────────────────────────────────────────────

def test_zawieszone_konto_nie_wywala_walidacji(siec):
    """REGRESJA: `response` bylo lista, kod robil `.get()` -> AttributeError.
    SourceManager tego nie lapie, wiec CLI padalo przy starcie."""
    siec["odpowiedz"] = _Resp(ZAWIESZONE)

    ok, msg = APIFootball("klucz").waliduj()

    assert ok is False
    assert msg


def test_zawieszone_konto_zglasza_powod(siec):
    """Komunikat ma powiedziec, CO jest nie tak — inaczej zostaje zgadywanie."""
    siec["odpowiedz"] = _Resp(ZAWIESZONE)

    _, msg = APIFootball("klucz").waliduj()

    assert "suspend" in msg.lower()


def test_zawieszone_konto_nie_jest_wazne(siec):
    """`_valid=True` na zawieszonym koncie kazalby reszcie kodu z niego korzystac."""
    siec["odpowiedz"] = _Resp(ZAWIESZONE)
    af = APIFootball("klucz")

    af.waliduj()

    assert af._valid is False


def test_poprawne_konto_nadal_dziala(siec):
    ok, msg = APIFootball("klucz").waliduj()

    assert ok is True
    assert "12" in msg or "88" in msg


# ── _get: bledy w tresci przy HTTP 200 ──────────────────────────────────────

def test_blad_w_tresci_nie_jest_wynikiem(siec):
    siec["odpowiedz"] = _Resp(ZAWIESZONE)

    assert APIFootball("klucz")._get("/fixtures", {"date": "2026-08-02"}) is None


def test_blad_w_tresci_nie_trafia_do_cache(siec):
    """NAJWAZNIEJSZE: zapis pustej odpowiedzi zatruwal cache na 24h — awaria
    konta psula dane jeszcze dlugo po jej usunieciu."""
    siec["odpowiedz"] = _Resp(ZAWIESZONE)

    APIFootball("klucz")._get("/fixtures", {"date": "2026-08-02"})

    assert siec["zapisane"] == []


@pytest.mark.parametrize("errors", [
    {"access": "Your account is suspended"},
    {"token": "Error/Missing application key"},
    {"requests": "You have reached the request limit for the day"},
    {"plan": "This endpoint does not exist for your plan"},
])
def test_kazdy_rodzaj_bledu_konta_rozpoznany(siec, errors):
    """Wszystkie problemy z kontem api-sports zglasza tak samo: HTTP 200 + errors."""
    siec["odpowiedz"] = _Resp({"errors": errors, "response": []})

    assert APIFootball("klucz")._get("/fixtures") is None
    assert siec["zapisane"] == []


def test_puste_errors_to_poprawna_odpowiedz(siec):
    """API zwraca `errors: []` (pusta lista) gdy wszystko gra — to NIE jest blad."""
    siec["odpowiedz"] = _Resp({"errors": [], "response": [{"fixture": {"id": 1}}]})

    wynik = APIFootball("klucz")._get("/fixtures")

    assert wynik is not None
    assert len(siec["zapisane"]) == 1


def test_brak_pola_errors_to_poprawna_odpowiedz(siec):
    siec["odpowiedz"] = _Resp({"response": [{"fixture": {"id": 1}}]})

    assert APIFootball("klucz")._get("/fixtures") is not None


def test_pusta_lista_meczow_bez_bledu_jest_ok(siec):
    """Dzien bez meczow to poprawna odpowiedz, nie awaria — nie wolno jej mylic
    z zawieszonym kontem."""
    siec["odpowiedz"] = _Resp({"errors": [], "response": []})

    wynik = APIFootball("klucz")._get("/fixtures", {"date": "2026-12-25"})

    assert wynik == {"errors": [], "response": []}
    assert len(siec["zapisane"]) == 1


def test_odpowiedz_nie_bedaca_slownikiem_nie_wywala(siec):
    """Proxy albo strona bledu potrafia oddac cokolwiek."""
    siec["odpowiedz"] = _Resp(["nieoczekiwana", "lista"])

    assert APIFootball("klucz")._get("/fixtures") is None
    assert siec["zapisane"] == []


def test_fixture_id_nie_szuka_w_zepsutej_odpowiedzi(siec):
    """Skoro `_get` zwraca None, wyszukiwanie meczu ma sie poddac, a nie zgadywac."""
    siec["odpowiedz"] = _Resp(ZAWIESZONE)

    assert APIFootball("klucz").znajdz_fixture_id("Legia", "Lech", "2026-08-02") is None
