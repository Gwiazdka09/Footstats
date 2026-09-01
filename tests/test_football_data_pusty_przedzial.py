"""football-data.org: `dateTo` jest WYLACZAJACE, wiec dateFrom==dateTo nic nie zwraca.

ZMIERZONE 01.09 na zywym API (klucz produkcyjny, HTTP 200, bez limitu):

    2026-08-28 .. 2026-08-28  ->  count=0
    2026-08-29 .. 2026-08-29  ->  count=0
    2026-08-27 .. 2026-08-28  ->  count=2, daty w odpowiedzi: ['2026-08-27']
    2026-08-25 .. 2026-08-31  ->  63 mecze, w tym Wrexham AFC vs Birmingham City FC (08-28)

`_get_matches_fdb` wolalo z `dateFrom=date_str, dateTo=date_str`, czyli o PUSTY
przedzial. To zrodlo nie oddalo ani jednego meczu, odkad istnieje — a bylo drugim
z czterech ogniw rozliczania i JEDYNYM, ktore siega dalej niz doba wstecz
(API-Football na planie Free: "Free plans do not have access to this date,
try from 2026-08-31 to 2026-09-02").

SKUTEK ZMIERZONY: 24 kupony `phase='system'` z 25-30.08 wisialy ACTIVE, mimo ze
wynik byl w football-data.org. Po `VOID_AFTER_DAYS = 10` wypadaja jako VOID,
czyli znikaja z accuracy i ROI — 21 takich w ostatnich 30 dniach.

Awaria byla niewidoczna, bo pusta odpowiedz z pustego przedzialu wyglada
identycznie jak "tego dnia nic sie nie odbylo", a jedyny slad po bledzie HTTP
szedl na `log.debug`.
"""
from __future__ import annotations

import logging

import pytest

from footstats.core.coupon_settlement import _get_matches_fdb


class _Odp:
    def __init__(self, kod=200, dane=None):
        self.status_code = kod
        self._dane = dane if dane is not None else {"matches": []}

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"{self.status_code} error")

    def json(self):
        return self._dane


@pytest.fixture
def przechwyc(monkeypatch):
    """Podglada parametry, ktore ida do football-data.org."""
    zapis = {}

    def _get(url, headers=None, params=None, timeout=None):
        zapis["url"] = url
        zapis["params"] = params
        return zapis.get("_odp") or _Odp()

    import requests
    monkeypatch.setattr(requests, "get", _get)
    return zapis


def test_dateTo_jest_pozniejsze_niz_dateFrom(przechwyc):
    """Sedno: rowne daty to pusty przedzial i gwarantowane zero wynikow."""
    _get_matches_fdb("klucz", "2026-08-28")

    p = przechwyc["params"]
    assert p["dateFrom"] == "2026-08-28"
    assert p["dateTo"] > p["dateFrom"], (
        f"dateTo={p['dateTo']} nie jest pozniejsze niz dateFrom={p['dateFrom']} — "
        f"to pusty przedzial, API zwroci 0 meczow niezaleznie od danych"
    )


def test_dateTo_to_dokladnie_nastepny_dzien(przechwyc):
    """Szerszy zakres zuzywalby limit (10 zapytan/min) i wciagal obce mecze."""
    _get_matches_fdb("klucz", "2026-08-28")

    assert przechwyc["params"]["dateTo"] == "2026-08-29"


def test_mecz_z_NASTEPNEGO_dnia_nie_wchodzi_do_wyniku(przechwyc):
    """Skoro pytamy o dwa dni, musimy odsiac ten drugi — inaczej rozliczylibysmy
    kupon wynikiem innego meczu tej samej pary z kolejnego dnia."""
    przechwyc["_odp"] = _Odp(dane={"matches": [
        {"utcDate": "2026-08-28T18:00:00Z", "homeTeam": {"name": "Wrexham AFC"},
         "awayTeam": {"name": "Birmingham City FC"}, "score": {"fullTime": {"home": 1, "away": 2}}},
        {"utcDate": "2026-08-29T18:00:00Z", "homeTeam": {"name": "Inny"},
         "awayTeam": {"name": "Mecz"}, "score": {"fullTime": {"home": 9, "away": 9}}},
    ]})

    mecze = _get_matches_fdb("klucz", "2026-08-28")

    assert len(mecze) == 1
    assert mecze[0]["homeTeam"]["name"] == "Wrexham AFC"


def test_mecz_z_zadanego_dnia_przechodzi(przechwyc):
    """Kontrola negatywna: filtr nie moze wyciac tego, po co przyszlismy."""
    przechwyc["_odp"] = _Odp(dane={"matches": [
        {"utcDate": "2026-08-28T18:00:00Z", "homeTeam": {"name": "A"},
         "awayTeam": {"name": "B"}, "score": {"fullTime": {"home": 1, "away": 0}}},
    ]})

    assert len(_get_matches_fdb("klucz", "2026-08-28")) == 1


def test_brak_klucza_nie_wola_sieci(przechwyc):
    assert _get_matches_fdb("", "2026-08-28") == []
    assert "params" not in przechwyc


# ── blad HTTP nie moze wygladac jak pusty dzien ─────────────────────────────

def test_limit_zapytan_jest_GLOSNY(przechwyc, caplog):
    """429 i "tego dnia nic nie grano" dawaly identyczna pusta liste, a jedyny
    slad szedl na `log.debug` — czyli w produkcji nigdzie. Limit free to
    10 zapytan/min, a rozliczanie chodzi po kilkudziesieciu kuponach."""
    przechwyc["_odp"] = _Odp(kod=429)

    with caplog.at_level(logging.WARNING):
        wynik = _get_matches_fdb("klucz", "2026-08-28")

    assert wynik == []
    tekst = " ".join(r.getMessage() for r in caplog.records)
    assert "429" in tekst or "limit" in tekst.lower(), (
        f"blad HTTP nie zostawil sladu na WARNING: {tekst!r}"
    )


def test_pusty_dzien_zostaje_cichy(przechwyc, caplog):
    """Kontrola negatywna: dzien bez meczow to stan normalny, nie awaria."""
    with caplog.at_level(logging.WARNING):
        _get_matches_fdb("klucz", "2026-08-28")

    assert not caplog.records, f"pusty dzien zalogowany jako problem: {caplog.records}"
