"""Wylacznik SofaScore musi obowiazywac w KAZDYM wejsciu, nie w jednym z dwoch.

STAN ZASTANY (2026-09-07, dowod z logow produkcji). SofaScore odrzuca nas 403 na
KAZDYM endpoincie — sprawdzone tego dnia rowniez z przegladarkowym User-Agentem
i na `/sport/football/events/live`, wiec to nie jest blokada samego `/search/all`.
Przez 14 dni: **146 zapytan, 146 razy HTTP 403, zero sukcesow.**

Wylacznik `_SOFA_ZABLOKOWANY` powstal 30.08 wlasnie po to, zeby po pierwszym 403
nie uruchamiac przegladarki dla kolejnych druzyn. Trafil jednak WYLACZNIE do
`pobierz_forme` (jedna druzyna), a potok dzienny wola `pobierz_forme_meczu`
(`core/daily_phases.py:175`, `ai/analyzer_helpers.py:93`) — i ta funkcja
wylacznika nie czytala.

Skutek widac w logu jobu z 07.09: KROK 2 dla 4 meczow to 8 blokad i **39.7 s**
spalonych na pewne niepowodzenie. Przez 14 dni przebiegi trwaly od 30 do 63 s
dluzej, kazdego dnia, za zero danych.

To ten sam ksztalt bledu, ktory ten projekt trafia raz po raz: jedna regula
zapisana w dwoch miejscach, poprawka w jednym.
"""
from __future__ import annotations

import pytest

import footstats.scrapers.form_scraper as fs


@pytest.fixture
def zablokowany(monkeypatch):
    monkeypatch.setattr(fs, "_SOFA_ZABLOKOWANY", True)
    monkeypatch.setattr(fs, "PLAYWRIGHT_OK", True)
    monkeypatch.setattr(fs, "_sofa_session",
                        lambda *a, **k: pytest.fail(
                            "przegladarka uruchomiona mimo znanej blokady 403"))
    monkeypatch.setattr(fs, "get_form_flashscore", lambda nazwa: None)


def test_pobierz_forme_nie_odpala_przegladarki(zablokowany):
    """Regresja juz pokryta 30.08 — zostaje jako straznik."""
    wynik = fs.pobierz_forme("Arsenal")
    assert wynik["team"] == "Arsenal"
    assert not wynik.get("form")


def test_pobierz_forme_meczu_nie_odpala_przegladarki(zablokowany):
    """Rdzen: to JEST funkcja, ktorej uzywa potok dzienny."""
    wynik = fs.pobierz_forme_meczu("Arsenal", "Chelsea")
    assert set(wynik) >= {"home", "away", "h2h"}
    assert not wynik["home"].get("form")
    assert not wynik["away"].get("form")


def test_ksztalt_wyniku_taki_sam_jak_przy_dzialajacym_zrodle(zablokowany):
    """Wolajacy nie moze rozrozniac 'zablokowane' od 'brak danych' po ksztalcie.

    `daily_phases` czyta `forma.get("home", {}).get("form")` i przypisuje
    warunkowo. Inny ksztalt przy blokadzie wywrocilby tamten kod albo, gorzej,
    po cichu skasowal absencje zapisane wczesniej przez FotMob — to jest ta sama
    awaria, ktora naprawiano 31.08.
    """
    wynik = fs.pobierz_forme_meczu("Arsenal", "Chelsea")
    assert isinstance(wynik["home"], dict) and isinstance(wynik["away"], dict)
    assert wynik["h2h"] == []
    assert wynik["home"].get("injuries", []) == []


def test_blokada_na_gospodarzu_oszczedza_goscia(monkeypatch):
    """Jeden mecz = jedno pewne 403, nie dwa.

    `find_team_id` z podanym `page` nie sprawdza wylacznika (robi to wolajacy),
    wiec bez warunku miedzy druzynami kazdy mecz kosztowalby dwa zapytania do
    zablokowanego zrodla. W logu z 07.09 widac to jako 8 blokad na 4 mecze.
    """
    monkeypatch.setattr(fs, "_SOFA_ZABLOKOWANY", False)
    monkeypatch.setattr(fs, "PLAYWRIGHT_OK", True)
    monkeypatch.setattr(fs, "_sofa_session", lambda *a, **k: (_Nic(), _Nic(), object()))
    monkeypatch.setattr(fs, "get_form_flashscore", lambda nazwa: None)

    szukane = []

    def _blokada(nazwa, page=None):
        szukane.append(nazwa)
        fs._SOFA_ZABLOKOWANY = True      # tak robi `_sofa_fetch` po HTTP 403
        return None

    monkeypatch.setattr(fs, "find_team_id", _blokada)
    fs.pobierz_forme_meczu("Arsenal", "Chelsea")

    assert szukane == ["Arsenal"], f"goscia tez odpytano: {szukane}"


class _Nic:
    """Atrapa `browser`/`playwright` — `pobierz_forme_meczu` zamyka je w `finally`."""

    def close(self):
        pass

    def stop(self):
        pass


def test_flashscore_dostaje_szanse_mimo_blokady(monkeypatch):
    """Wylacznik omija SofaScore, nie caly tor formy."""
    monkeypatch.setattr(fs, "_SOFA_ZABLOKOWANY", True)
    monkeypatch.setattr(fs, "PLAYWRIGHT_OK", True)
    monkeypatch.setattr(fs, "_sofa_session",
                        lambda *a, **k: pytest.fail("przegladarka mimo blokady"))
    monkeypatch.setattr(fs, "get_form_flashscore",
                        lambda nazwa: {"team": nazwa, "form": ["W", "W", "L"],
                                       "goals_scored": 5, "goals_conceded": 2,
                                       "injuries": []})

    wynik = fs.pobierz_forme_meczu("Arsenal", "Chelsea")
    assert wynik["home"]["form"] == ["W", "W", "L"]
    assert wynik["away"]["form"] == ["W", "W", "L"]


#: Funkcje, ktore realnie ida do SofaScore. NIE `_sofa_session` — mimo nazwy
#: jest to generyczna fabryka przegladarki Playwright i uzywa jej rowniez
#: `get_form_flashscore`, czyli FALLBACK. Wyłączenie go razem z SofaScore
#: odcieloby jedyne dzialajace zrodlo formy.
_WOLA_SOFASCORE = ("_sofa_fetch(", "find_team_id(", "get_form_sofascore(")


def test_kazde_wejscie_sprawdza_wylacznik():
    """Straznik na ksztalt: nowe wejscie do SofaScore tez musi pytac o wylacznik.

    Blad z 30.08 polegal na tym, ze poprawka trafila do jednej z dwoch funkcji
    wejsciowych, a potok chodzil druga. Ten test liczy wejscia sam, wiec trzecie
    i czwarte (`find_team_id`, `get_form_sofascore` z wlasna sesja) tez wylapal.
    """
    import inspect

    pominiete = {"_sofa_fetch", "find_team_id", "get_form_sofascore"}
    sprawdzone = []
    for nazwa, obiekt in vars(fs).items():
        if not (inspect.isfunction(obiekt) and obiekt.__module__ == fs.__name__):
            continue
        tresc = inspect.getsource(obiekt)
        if not any(w in tresc for w in _WOLA_SOFASCORE):
            continue
        sprawdzone.append(nazwa)
        if nazwa in pominiete:
            # Te trzy maja wlasna bramke przy `own_session` — sprawdzana nizej.
            continue
        assert "sofascore_zablokowany()" in tresc, (
            f"{nazwa} idzie do SofaScore bez sprawdzenia wylacznika")

    assert "pobierz_forme_meczu" in sprawdzone, (
        "test przestal widziec funkcje uzywana przez potok dzienny")

    # Wejscia z wlasna sesja musza sie bronic same — `page=None` znaczy, ze nikt
    # przed nimi wylacznika nie sprawdzil.
    for nazwa in ("find_team_id", "get_form_sofascore"):
        tresc = inspect.getsource(getattr(fs, nazwa))
        assert "sofascore_zablokowany()" in tresc, (
            f"{nazwa} otwiera wlasna przegladarke bez sprawdzenia wylacznika")
