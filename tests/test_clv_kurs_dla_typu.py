"""CLV musi porownywac kurs TEGO SAMEGO zdarzenia, na ktore postawilismy.

STAN ZASTANY (2026-09-07). `evening_agent` bral z `kursy_zamkniecia` zawsze
`kursy["home"]`, niezaleznie od typu nogi. Komentarz w kodzie bronil tego
zgodnoscia z istniejacymi CLV — a tych bylo ZERO (`clv_closing_odds IS NULL`
dla wszystkich 295 predykcji), wiec nie bylo czego zachowywac.

Rozklad typow w 531 rozliczonych nogach:

    Over 2.5    159      1     83      1X    14      BB: ...    9
    Under 2.5   139      2     22      X2     8      Over 1.5  27
    BTTS         62                    BTTS nie 3    Under 3.5  1

Mapowalne na kursy zamkniecia z football-data (`home/draw/away/over_2_5/
under_2_5`) sa 403 nogi = 76%. Pozostale 24% to zdarzenia, ktorych CSV nie
notuje — dla nich CLV musi byc NIEPOLICZONE, nie zgadniete. Do tej poprawki
wszystkie 100% dostawalyby kurs gospodarza, czyli 76% CLV byloby po cichu
policzone ze zlej ceny.
"""
from __future__ import annotations

import pytest

from footstats.scrapers.closing_odds import kurs_dla_typu

KURSY = {"home": 1.85, "draw": 3.60, "away": 4.20,
         "over_2_5": 1.95, "under_2_5": 1.88, "zrodlo": "PSC"}


@pytest.mark.parametrize("tip, oczekiwany", [
    ("1", 1.85),
    ("2", 4.20),
    ("X", 3.60),
    ("Over 2.5", 1.95),
    ("Under 2.5", 1.88),
])
def test_typ_dostaje_swoj_kurs(tip, oczekiwany):
    assert kurs_dla_typu(KURSY, tip) == oczekiwany


@pytest.mark.parametrize("tip", ["1", "  1  ", "over 2.5", "OVER 2.5", "Over  2.5"])
def test_zapis_typu_nie_ma_znaczenia(tip):
    assert kurs_dla_typu(KURSY, tip) is not None


@pytest.mark.parametrize("tip", [
    "1X", "X2",              # podwojna szansa — CSV nie notuje
    "BTTS", "BTTS nie",      # obie strzela — CSV nie notuje
    "Over 1.5", "Under 3.5",  # INNA LINIA, nie wolno podstawiac 2.5
    "BB: 2 + Over 1.5",      # kombinacja
    "", "   ", None,
])
def test_nieznany_typ_to_brak_kursu_a_nie_kurs_gospodarza(tip):
    """Najwazniejszy przypadek: 24% nog musi zostac bez CLV, nie z cudzym."""
    assert kurs_dla_typu(KURSY, tip) is None


def test_inna_linia_nie_moze_podstawic_25():
    """`Over 1.5` przy kursie 1.30 nie ma nic wspolnego z `over_2_5` 1.95."""
    assert kurs_dla_typu(KURSY, "Over 1.5") is None
    assert kurs_dla_typu(KURSY, "Over 3.5") is None


def test_brak_pola_w_kursach_to_brak_kursu():
    """CSV bez kolumn Over/Under — 1X2 dziala dalej, O/U nie zgaduje."""
    tylko_1x2 = {"home": 1.85, "draw": 3.60, "away": 4.20, "zrodlo": "PSC"}
    assert kurs_dla_typu(tylko_1x2, "1") == 1.85
    assert kurs_dla_typu(tylko_1x2, "Over 2.5") is None


def test_pusty_slownik_nie_wybucha():
    assert kurs_dla_typu({}, "1") is None
    assert kurs_dla_typu(None, "1") is None


def test_kurs_ponizej_jedynki_odrzucony():
    """Kurs <= 1.0 jest niemozliwy i psulby CLV — `calculate_clv` i tak go odrzuca."""
    assert kurs_dla_typu({"home": 0.0}, "1") is None
    assert kurs_dla_typu({"home": 1.0}, "1") is None
