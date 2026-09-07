"""Padniete zrodlo ma byc pytane RAZ na lige, nie raz na noge.

STAN ZASTANY (2026-09-07). `FootballDataSource._pobierz_csv` zapisuje do cache
plikowego WYLACZNIE udane pobranie — porazka nie zostawia sladu, wiec kolejne
wywolanie znowu wychodzi do sieci. `kursy_zamkniecia` iteruje 13 lig, a od tego
dnia `evening_agent` wola je dla KAZDEJ rozliczonej nogi.

Zmierzone tego samego dnia, przy football-data.co.uk oddajacym HTTP 503 na calej
witrynie (rowniez na stronach HTML — to awaria zrodla, nie blokada na nas):

    pierwsze wywolanie 11.9s
    drugie wywolanie    7.5s      <- cache pliku nie pomaga, bo nie ma czego zapisac

Przy 30 nogach wieczornych to 13 lig x 30 nog = 390 zapytan do martwego hosta,
z timeoutem 15s kazde. Rozliczanie kuponow jest wazniejsze niz telemetria CLV,
wiec nie moze na niej wisiec.

Pamiec procesu jest tu wlasciwym poziomem: joby sa krotkotrwale (jeden przebieg
= jeden proces), wiec „raz na przebieg" i „raz na proces" to to samo, a stan
nie przezywa do nastepnego dnia.
"""
from __future__ import annotations

import pytest

import footstats.scrapers.closing_odds as co


@pytest.fixture(autouse=True)
def czysty_cache():
    co._csv_ligi.cache_clear()
    yield
    co._csv_ligi.cache_clear()


def test_padniete_zrodlo_pytane_raz_na_lige(monkeypatch):
    wywolania = []

    class _Zdechle:
        def _pobierz_csv(self, kod, sezon):
            wywolania.append((kod, sezon))
            raise OSError("503 Service Temporarily Unavailable")

    monkeypatch.setattr(co, "FootballDataSource", _Zdechle)

    for _ in range(5):
        assert co._csv_ligi("E0", "2627") is None

    assert wywolania == [("E0", "2627")], (
        f"martwe zrodlo odpytane {len(wywolania)} razy zamiast raz")


def test_udane_pobranie_tez_pamietane(monkeypatch):
    wywolania = []

    class _Zywe:
        def _pobierz_csv(self, kod, sezon):
            wywolania.append((kod, sezon))
            return "Date,HomeTeam\n"

    monkeypatch.setattr(co, "FootballDataSource", _Zywe)

    assert co._csv_ligi("E0", "2627") == "Date,HomeTeam\n"
    assert co._csv_ligi("E0", "2627") == "Date,HomeTeam\n"
    assert len(wywolania) == 1


def test_rozne_ligi_i_sezony_to_rozne_wpisy(monkeypatch):
    wywolania = []

    class _Zywe:
        def _pobierz_csv(self, kod, sezon):
            wywolania.append((kod, sezon))
            return f"{kod}/{sezon}"

    monkeypatch.setattr(co, "FootballDataSource", _Zywe)

    assert co._csv_ligi("E0", "2627") == "E0/2627"
    assert co._csv_ligi("SP1", "2627") == "SP1/2627"
    assert co._csv_ligi("E0", "2526") == "E0/2526"
    assert len(wywolania) == 3


def test_jedno_zapytanie_na_lige_mimo_wielu_meczow(monkeypatch):
    """Sedno regresji: 13 lig x N nog musi zostac 13 zapytaniami, nie 13xN."""
    wywolania = []

    class _Zdechle:
        def _pobierz_csv(self, kod, sezon):
            wywolania.append(kod)
            raise OSError("503")

    monkeypatch.setattr(co, "FootballDataSource", _Zdechle)

    for i in range(20):
        co.kursy_zamkniecia(f"Druzyna {i}", f"Rywal {i}", "2026-08-31")

    assert len(wywolania) == len(set(wywolania)) <= len(co.KODY_LIG), (
        f"{len(wywolania)} zapytan na {len(set(wywolania))} unikalnych lig")
