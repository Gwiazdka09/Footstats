"""Kolektor surowych kwot per bukmacher — zero zywych zapytan.

Regula `.claude/rules/tests-no-prod.md`: zewnetrzne zrodla mockujemy.
Atrapa odwzorowuje realny ksztalt odpowiedzi The Odds API v4, sprawdzony
na produkcji 2026-08-27 (soccer_epl, region eu, 25 bukmacherow).
"""
from __future__ import annotations

import pytest

from footstats.scrapers import odds_snapshot as os_mod

ODPOWIEDZ = [
    {
        "id": "373cc6e2fb57f471cd2deab9a28a6edb",
        "commence_time": "2026-08-27T14:00:00Z",
        "home_team": "Crystal Palace",
        "away_team": "Manchester City",
        "bookmakers": [
            {"key": "pinnacle", "markets": [
                {"key": "h2h", "outcomes": [
                    {"name": "Crystal Palace", "price": 4.81},
                    {"name": "Manchester City", "price": 1.69},
                    {"name": "Draw", "price": 4.21},
                ]},
                {"key": "totals", "outcomes": [
                    {"name": "Over", "price": 1.90, "point": 2.5},
                    {"name": "Under", "price": 1.95, "point": 2.5},
                    {"name": "Over", "price": 2.60, "point": 3.5},
                ]},
            ]},
            {"key": "everygame", "markets": [
                {"key": "h2h", "outcomes": [
                    {"name": "Crystal Palace", "price": 4.50},
                    {"name": "Manchester City", "price": 1.62},
                    {"name": "Draw", "price": 4.00},
                ]},
            ]},
        ],
    }
]


class _Odp:
    def __init__(self, dane, kredyty="400", status=200):
        self._dane = dane
        self.status_code = status
        self.headers = {"x-requests-remaining": kredyty}

    def json(self):
        return self._dane


@pytest.fixture(autouse=True)
def _czysty_stan():
    """Stan modulowy `_ostatnie_kredyty` przecieka miedzy testami i bezpiecznik
    zachowywalby sie zaleznie od kolejnosci uruchomienia."""
    os_mod.zeruj_stan_kredytow()
    yield
    os_mod.zeruj_stan_kredytow()


def test_kolektor_nie_agreguje_zwraca_wiersz_na_ksiazke(monkeypatch):
    """SEDNO calego pilotu. `odds_api.mapuj_wydarzenie` bierze mediane i gubi
    nazwe ksiazki, przez co rozrzut jest liczony i wyrzucany przy kazdym
    zapytaniu. Kolektor NIE MOZE tego powtorzyc."""
    monkeypatch.setattr(os_mod.requests, "get", lambda *a, **kw: _Odp(ODPOWIEDZ))
    wiersze = os_mod.pobierz_migawke("soccer_epl", klucz="X")
    palace = [w for w in wiersze if w["market"] == "h2h" and w["outcome"] == "Crystal Palace"]
    assert {w["bookmaker"] for w in palace} == {"pinnacle", "everygame"}
    assert {w["price"] for w in palace} == {4.81, 4.50}


def test_kolektor_bierze_tylko_linie_2_5_dla_totals(monkeypatch):
    """Linia 3.5 to inny rynek — zmieszanie ich zafalszowaloby devig."""
    monkeypatch.setattr(os_mod.requests, "get", lambda *a, **kw: _Odp(ODPOWIEDZ))
    totals = [w for w in os_mod.pobierz_migawke("soccer_epl", klucz="X")
              if w["market"] == "totals"]
    assert {w["line"] for w in totals} == {2.5}
    assert {w["outcome"] for w in totals} == {"Over", "Under"}
    assert {w["price"] for w in totals} == {1.90, 1.95}, "cena z linii 3.5 przeciekla"


def test_kolektor_ustawia_line_zero_dla_h2h(monkeypatch):
    """`line` jest NOT NULL w schemacie — 0 znaczy „rynek bez linii".
    NULL rozbroilby indeks unikalny w Postgresie (dwa NULL-e sa rozne)."""
    monkeypatch.setattr(os_mod.requests, "get", lambda *a, **kw: _Odp(ODPOWIEDZ))
    wiersze = os_mod.pobierz_migawke("soccer_epl", klucz="X")
    assert all(w["line"] == 0.0 for w in wiersze if w["market"] == "h2h")


def test_kolektor_przepisuje_metadane_wydarzenia(monkeypatch):
    monkeypatch.setattr(os_mod.requests, "get", lambda *a, **kw: _Odp(ODPOWIEDZ))
    w = os_mod.pobierz_migawke("soccer_epl", klucz="X")[0]
    assert w["event_id"] == "373cc6e2fb57f471cd2deab9a28a6edb"
    assert w["team_home"] == "Crystal Palace"
    assert w["team_away"] == "Manchester City"
    assert w["sport_key"] == "soccer_epl"
    assert w["commence_time"] == "2026-08-27T14:00:00Z"


def test_kolektor_odrzuca_kurs_nie_wiekszy_od_jedynki(monkeypatch):
    """Kurs 1.0 nie jest kwotowaniem. Jeden taki wiersz robi z ksiazki 2-z-3
    w 1X2, co w `rozrzut_kursow` zawyzaloby kazdy edge."""
    zepsute = [{
        "id": "e1", "commence_time": "2026-08-27T14:00:00Z",
        "home_team": "A", "away_team": "B",
        "bookmakers": [{"key": "soft", "markets": [{"key": "h2h", "outcomes": [
            {"name": "A", "price": 2.0}, {"name": "B", "price": 1.0},
        ]}]}],
    }]
    monkeypatch.setattr(os_mod.requests, "get", lambda *a, **kw: _Odp(zepsute))
    assert [w["outcome"] for w in os_mod.pobierz_migawke("soccer_epl", klucz="X")] == ["A"]


def test_bezpiecznik_kredytowy_blokuje_kolejna_lige(monkeypatch):
    """Pula 500/mies. jest dzielona z produkcyjna sciezka kursow. Eksperyment
    nie ma prawa jej zjesc — po spadku ponizej progu zamiatanie staje."""
    wywolania = []

    def _fake(*a, **kw):
        wywolania.append(kw.get("params", {}).get("apiKey"))
        return _Odp(ODPOWIEDZ, kredyty=str(os_mod.KREDYTY_MINIMUM - 1))

    monkeypatch.setattr(os_mod.requests, "get", _fake)
    wynik = os_mod.zamiataj_pilota(klucz="X")
    assert len(wywolania) == 1, "po spadku ponizej progu nie wolno pytac dalej"
    assert wynik["zatrzymany_przez_kredyty"] is True
    assert wynik["ligi"] == 1


def test_zamiatanie_obchodzi_wszystkie_ligi_pilota(monkeypatch):
    monkeypatch.setattr(os_mod.requests, "get",
                        lambda *a, **kw: _Odp(ODPOWIEDZ, kredyty="400"))
    wynik = os_mod.zamiataj_pilota(klucz="X")
    assert wynik["ligi"] == len(os_mod.LIGI_PILOTA)
    assert wynik["zatrzymany_przez_kredyty"] is False
    assert wynik["wierszy"] == len(wynik["wiersze"]) > 0


def test_brak_klucza_zwraca_pusto_bez_zapytania(monkeypatch):
    def _nie_wolno(*a, **kw):
        raise AssertionError("bez klucza nie wolno wykonac zapytania")

    monkeypatch.setattr(os_mod.requests, "get", _nie_wolno)
    monkeypatch.delenv(os_mod.ENV_ODDS_API, raising=False)
    assert os_mod.pobierz_migawke("soccer_epl") == []


def test_blad_http_nie_rzuca_tylko_zwraca_pusto(monkeypatch):
    monkeypatch.setattr(os_mod.requests, "get", lambda *a, **kw: _Odp([], status=429))
    assert os_mod.pobierz_migawke("soccer_epl", klucz="X") == []


def test_wyjatek_sieciowy_nie_rzuca(monkeypatch):
    """Kolektor jedzie w jobie produkcyjnym — padniecie sieci nie moze go wywrocic."""
    def _wybuch(*a, **kw):
        raise os_mod.requests.RequestException("timeout")

    monkeypatch.setattr(os_mod.requests, "get", _wybuch)
    assert os_mod.pobierz_migawke("soccer_epl", klucz="X") == []


def test_ligi_pilota_to_dokladnie_trzy_ze_specu():
    assert set(os_mod.LIGI_PILOTA) == {
        "soccer_epl", "soccer_china_superleague", "soccer_japan_j_league"
    }
