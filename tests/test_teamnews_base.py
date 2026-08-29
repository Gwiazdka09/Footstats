"""DTO team-news.

Sedno: `pewna` musi rozrozniac TRZY stany wejsciowe, nie dwa — "Doubtful"
(moze zagra), konkretna data (nie zagra), brak danych (nie wiadomo). Bez tego
brak danych udaje niepewna absencje i wchodzi do liczenia edge'u, a to ten sam
ksztalt bledu co 50/50/50 w api_football: odbiorca dostaje wartosc i nie wie,
ze to nie pomiar.
"""
from __future__ import annotations

import dataclasses

import pytest

from footstats.scrapers.teamnews.base import (
    Absencja, TeamNews, TeamNewsSource, absencja_pewna,
)


@pytest.mark.parametrize("powrot, oczekiwana", [
    ("Mid September 2026", True),
    ("Early October 2026", True),
    ("Doubtful", False),
    ("doubtful", False),
    ("  Doubtful  ", False),
    (None, False),
    ("", False),
])
def test_regula_pewna(powrot, oczekiwana):
    assert absencja_pewna(powrot) is oczekiwana


def test_brak_danych_to_nie_to_samo_co_doubtful():
    """Oba daja pewna=False, ale `powrot` musi je rozroznic — inaczej log nie
    powie, czy zrodlo milczalo, czy powiedzialo 'watpliwy'."""
    brak = Absencja(nazwisko="X", typ="injury", powrot=None,
                    pewna=absencja_pewna(None))
    watpliwy = Absencja(nazwisko="Y", typ="injury", powrot="Doubtful",
                        pewna=absencja_pewna("Doubtful"))
    assert brak.pewna is watpliwy.pewna is False
    assert brak.powrot != watpliwy.powrot


def test_teamnews_jest_niemutowalny():
    tn = TeamNews(source="fotmob", home="A", away="B", date="2026-08-30")
    with pytest.raises(dataclasses.FrozenInstanceError):
        tn.home = "C"


def test_teamnews_domyslnie_nie_klamie_o_skladzie():
    """Brak danych to puste krotki i None — nigdy zmyslony sklad."""
    tn = TeamNews(source="fotmob", home="A", away="B", date="2026-08-30")
    assert tn.typ_skladu is None
    assert tn.xi_home == () and tn.xi_away == ()
    assert tn.absencje_home == () and tn.absencje_away == ()
    assert tn.sedzia is None and tn.sedzia_stats == {}
    assert tn.sklad_jest_prognoza is False


def test_lastStarting11_to_nie_prognoza():
    """Ostatnia jedenastka nie jest przewidywaniem skladu na TEN mecz."""
    prognoza = TeamNews(source="f", home="A", away="B", date="d",
                        typ_skladu="predicted")
    ostatni = TeamNews(source="f", home="A", away="B", date="d",
                       typ_skladu="lastStarting11")
    assert prognoza.sklad_jest_prognoza is True
    assert ostatni.sklad_jest_prognoza is False


def test_protocol_rozpoznaje_adapter():
    class Atrapa:
        name = "atrapa"

        def fetch(self, date: str) -> list:
            return []

    assert isinstance(Atrapa(), TeamNewsSource)
