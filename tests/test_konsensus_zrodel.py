"""Konsensus źródeł wyników: rozjazd nie może przepadać po cichu.

BUG (2026-08-08): `consensus_result` mimo nazwy NIE budowało konsensusu —
brało pierwszego kandydata z listy:

    wybrany = z_ht[0] if z_ht else kandydaci[0]

Gdy dwa źródła podawały RÓŻNE wyniki tego samego meczu, wygrywało to, które
akurat było wcześniej na liście, i nikt się o rozbieżności nie dowiadywał.
Prawdziwe porównanie (`compare`) istniało obok, ale nie wołał go żaden kod
produkcyjny — tylko testy i graf w `visualize_brain.py`.

To najgorsza klasa błędu, jaką ta ścieżka może mieć: kupon rozliczony CUDZYM
wynikiem wygląda identycznie jak rozliczony poprawnie. Stąd zasada fail-closed,
ta sama co przy dopasowywaniu nazw: lepiej nie rozliczyć i zauważyć, niż
rozliczyć źle. Przy remisie głosów zwracamy None — kupon zostaje ACTIVE.
"""
from __future__ import annotations

import logging

import pytest

from footstats.scrapers.sources.aggregator import consensus_result
from footstats.scrapers.sources.base import MatchData


def _mecz(source: str, ft: tuple[int, int], ht: tuple[int, int] | None = None) -> MatchData:
    return MatchData(
        source=source, home="Radomiak Radom", away="Gornik Zabrze",
        date="2026-08-08", status="finished",
        ft_home=ft[0], ft_away=ft[1],
        ht_home=ht[0] if ht else None,
        ht_away=ht[1] if ht else None,
    )


@pytest.fixture()
def zrodla(monkeypatch):
    """Podstawia odpowiedzi źródeł — bez sieci."""
    def ustaw(*mecze: MatchData):
        dane = {}
        for m in mecze:
            dane.setdefault(m.source, []).append(m)
        monkeypatch.setattr(
            "footstats.scrapers.sources.aggregator.fetch_all", lambda _d: dane
        )
    return ustaw


# ── zgodne zrodla ──────────────────────────────────────────────────────────

def test_jedno_zrodlo(zrodla) -> None:
    zrodla(_mecz("api-football", (1, 3)))
    assert consensus_result("Radomiak Radom", "Gornik Zabrze", "2026-08-08") == "1-3"


def test_zgodne_zrodla_daja_wynik(zrodla) -> None:
    zrodla(_mecz("api-football", (1, 3)), _mecz("flashscore", (1, 3)))
    assert consensus_result("Radomiak Radom", "Gornik Zabrze", "2026-08-08") == "1-3"


def test_polczas_preferowany_wsrod_zgodnych(zrodla) -> None:
    """Przy tym samym wyniku FT bierzemy wariant bogatszy o półczas."""
    zrodla(_mecz("api-football", (1, 3)), _mecz("flashscore", (1, 3), ht=(0, 2)))
    assert consensus_result("Radomiak Radom", "Gornik Zabrze", "2026-08-08") == "1-3;HT:0-2"


def test_rozny_polczas_przy_zgodnym_ft_nie_blokuje(zrodla) -> None:
    """Rozjazd HT jest mniej groźny niż FT — wynik FT i tak jest jednoznaczny."""
    zrodla(_mecz("a", (1, 3), ht=(0, 1)), _mecz("b", (1, 3), ht=(0, 2)))
    wynik = consensus_result("Radomiak Radom", "Gornik Zabrze", "2026-08-08")
    assert wynik is not None and wynik.startswith("1-3")


# ── rozjazd ────────────────────────────────────────────────────────────────

def test_wiekszosc_wygrywa(zrodla) -> None:
    zrodla(_mecz("a", (1, 3)), _mecz("b", (1, 3)), _mecz("c", (2, 2)))
    assert consensus_result("Radomiak Radom", "Gornik Zabrze", "2026-08-08") == "1-3"


def test_remis_glosow_nie_rozlicza(zrodla) -> None:
    """Fail-closed: kupon zostaje ACTIVE zamiast dostać wynik z losowego źródła."""
    zrodla(_mecz("a", (1, 3)), _mecz("b", (2, 2)))
    assert consensus_result("Radomiak Radom", "Gornik Zabrze", "2026-08-08") is None


def test_rozjazd_jest_logowany(zrodla, caplog) -> None:
    zrodla(_mecz("api-football", (1, 3)), _mecz("flashscore", (2, 2)))
    with caplog.at_level(logging.WARNING):
        consensus_result("Radomiak Radom", "Gornik Zabrze", "2026-08-08")
    zapis = caplog.text
    assert "api-football" in zapis and "flashscore" in zapis, (
        "log nie wskazuje, ktore zrodla sie rozjechaly"
    )
    assert "1-3" in zapis and "2-2" in zapis


def test_wygrana_wiekszosc_tez_zostawia_slad(zrodla, caplog) -> None:
    """Nawet gdy większość rozstrzyga, rozbieżność ma być widoczna."""
    zrodla(_mecz("a", (1, 3)), _mecz("b", (1, 3)), _mecz("c", (0, 0)))
    with caplog.at_level(logging.WARNING):
        consensus_result("Radomiak Radom", "Gornik Zabrze", "2026-08-08")
    assert "0-0" in caplog.text


def test_zgodne_zrodla_nie_smieca_w_logu(zrodla, caplog) -> None:
    zrodla(_mecz("a", (1, 3)), _mecz("b", (1, 3)))
    with caplog.at_level(logging.WARNING):
        consensus_result("Radomiak Radom", "Gornik Zabrze", "2026-08-08")
    assert "rozjazd" not in caplog.text.lower()


# ── brak danych ────────────────────────────────────────────────────────────

def test_brak_zrodel(zrodla) -> None:
    zrodla()
    assert consensus_result("Radomiak Radom", "Gornik Zabrze", "2026-08-08") is None


def test_inny_mecz_nie_jest_brany(zrodla, monkeypatch) -> None:
    inny = MatchData(
        source="a", home="Legia Warszawa", away="Lech Poznan", date="2026-08-08",
        status="finished", ft_home=2, ft_away=0, ht_home=None, ht_away=None,
    )
    monkeypatch.setattr(
        "footstats.scrapers.sources.aggregator.fetch_all", lambda _d: {"a": [inny]}
    )
    assert consensus_result("Radomiak Radom", "Gornik Zabrze", "2026-08-08") is None


def test_mecz_bez_wyniku_pomijany(zrodla) -> None:
    bez = MatchData(
        source="b", home="Radomiak Radom", away="Gornik Zabrze", date="2026-08-08",
        status="scheduled", ft_home=None, ft_away=None, ht_home=None, ht_away=None,
    )
    zrodla(_mecz("a", (1, 3)), bez)
    assert consensus_result("Radomiak Radom", "Gornik Zabrze", "2026-08-08") == "1-3"
