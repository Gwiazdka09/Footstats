"""Endpoint stronicowany nie moze isc przez cache przepisywany w calosci.

STAN ZASTANY (2026-09-07). Disk cache API-Football to JEDEN plik JSON,
`cache/api_football/af_cache.json`, i kazde zapytanie:

    * CZYTA go i parsuje w calosci (`_af_load_disk_cache` w `_af_cache_get`),
    * po odpowiedzi ZAPISUJE go w calosci (`_af_save_disk_cache`).

Dla pierwotnego zastosowania (`/players/topscorers`, 1 zapytanie na lige, ~16
dziennie) to jest bez znaczenia. Backfill pelnych skladow robi ~34 zapytania na
lige, czyli okolo 550 — a plik urosl do **30 MB**. To okolo 33 GB odczytu
i zapisu na jeden przebieg, przy koszcie rosnacym KWADRATOWO wraz z cache.
Zmierzone tego dnia: pobieranie zwolnilo do ~7 minut na lige, przy czym czas
szedl na dysk, nie na siec.

Odpowiedzi `/players` i tak laduja w `player_stats` (SQLite), wiec cache
trzymalby te same dane drugi raz i tylko po to, zeby spowolnic ich pobranie.
"""
from __future__ import annotations

import pytest

from footstats.scrapers.api_football import APIFootball


class _Licznik:
    def __init__(self):
        self.odczyty = 0
        self.zapisy = 0


@pytest.fixture
def licznik(monkeypatch):
    lic = _Licznik()

    def _get(klucz):
        lic.odczyty += 1
        return None

    def _set(klucz, dane, stare_dane=None):
        lic.zapisy += 1

    import footstats.scrapers.api_football as af
    monkeypatch.setattr(af, "_af_cache_get", _get)
    monkeypatch.setattr(af, "_af_cache_set", _set)
    monkeypatch.setattr(af, "bezpieczny_budget_use", lambda *a, **k: 7000)
    monkeypatch.setattr(af, "af_budget_status", lambda: {"krytyczny": False, "uzyto": 10})

    class _Odp:
        status_code = 200

        @staticmethod
        def json():
            return {"response": [], "errors": []}

    monkeypatch.setattr(af.requests, "get", lambda *a, **k: _Odp())
    return lic


def test_domyslnie_cache_dziala(licznik):
    APIFootball("klucz")._get("/leagues", params={"id": 39})
    assert licznik.odczyty == 1
    assert licznik.zapisy == 1


def test_bez_cache_nie_dotyka_pliku(licznik):
    """Ani odczytu, ani zapisu — plik 30 MB nie moze byc na sciezce gorącej."""
    APIFootball("klucz")._get("/players", params={"league": 39, "page": 7},
                              bez_cache=True)
    assert licznik.odczyty == 0
    assert licznik.zapisy == 0


def test_bez_cache_nadal_liczy_budzet(licznik, monkeypatch):
    """Pominiecie cache nie moze byc obejsciem licznika zapytan.

    Budzet chroni przed zawieszeniem konta — a to juz sie w tym projekcie
    zdarzylo dwa razy.
    """
    uzyte = []
    import footstats.scrapers.api_football as af
    monkeypatch.setattr(af, "bezpieczny_budget_use",
                        lambda endpoint: uzyte.append(endpoint) or 7000)

    APIFootball("klucz")._get("/players", params={"league": 39}, bez_cache=True)
    assert uzyte == ["/players"]


def test_bez_cache_respektuje_bramke(licznik, monkeypatch):
    """Bramka `apisports_gate` zostaje jedynym miejscem decydujacym o ruchu."""
    import footstats.core.apisports_gate as gate
    monkeypatch.setattr(gate, "wlaczone", lambda: False)

    wynik = APIFootball("klucz")._get("/players", params={"league": 39},
                                      bez_cache=True)
    assert wynik is None


def test_squad_uzywa_pominiecia(monkeypatch):
    """Straznik na wpiecie: `fetch_league_squad` ma faktycznie omijac cache.

    Sam parametr nikomu nie pomaga, jesli wywolujacy go nie poda — a to jest
    dokladnie ta klasa bledu, ktora ten projekt zbiera od tygodnia (wylacznik
    w jednym wejsciu z dwoch, CLV pod bramka nieistniejacego klucza).
    """
    from footstats.scrapers.player_stats import fetch_league_squad

    widziane = []

    class _Klient:
        def _get(self, sciezka, params=None, **kwargs):
            widziane.append(kwargs)
            return {"response": [], "paging": {"current": 1, "total": 1}}

    fetch_league_squad(39, 2025, "klucz", _klient=_Klient())
    assert widziane and all(k.get("bez_cache") for k in widziane), (
        "fetch_league_squad idzie przez cache — 30 MB na zapytanie")
