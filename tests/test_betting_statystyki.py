"""Rynki statystyczne dziennika: rożne, gol zawodnika, celne strzały zawodnika."""
import pytest

from footstats.utils.betting import (
    normalizuj_nazwisko,
    oblicz_tip_correct,
    wymaga_statystyk,
)

STAT = {
    "corners": (5, 3),
    "zawodnicy": {
        "bruno fernandes": {"gole": 1, "sot": 2, "zagral": True, "druzyna": "home"},
        "enzo fernandez": {"gole": 0, "sot": 1, "zagral": True, "druzyna": "away"},
        "erling haaland": {"gole": 2, "sot": 4, "zagral": True, "druzyna": "away"},
        "jan kowalski": {"gole": 0, "sot": 0, "zagral": False, "druzyna": "home"},
        "adam nowak": {"gole": 0, "sot": 0, "zagral": True, "druzyna": "home"},
    },
}


def test_normalizacja_nazwiska():
    assert normalizuj_nazwisko("Enzo Fernández") == "enzo fernandez"
    assert normalizuj_nazwisko("B. Fernandes") == "b fernandes"
    assert normalizuj_nazwisko("Łukasz Skorupski") == "lukasz skorupski"


@pytest.mark.parametrize("tip,oczekiwane", [
    ("1 CORNERS OVER 4.5", 1), ("1 CORNERS OVER 5.5", 0),
    ("2 CORNERS UNDER 3.5", 1), ("2 CORNERS UNDER 2.5", 0),
    ("CORNERS OVER 7.5", 1), ("CORNERS OVER 8.5", 0), ("corners under 8,5", 1),
])
def test_rozne(tip, oczekiwane):
    assert oblicz_tip_correct(tip, "1-0", statystyki=STAT) == oczekiwane


def test_gol_zawodnika():
    assert oblicz_tip_correct("GOL: Erling Haaland", "1-2", statystyki=STAT) == 1
    assert oblicz_tip_correct("Gol: Adam Nowak", "1-2", statystyki=STAT) == 0


def test_samobojny_nie_liczy_sie_jako_gol():
    # ESPN: samobój to osobna statystyka, `gole` = 0
    st = {"corners": None, "zawodnicy": {"adam nowak": {
        "gole": 0, "sot": 0, "zagral": True, "druzyna": "home"}}}
    assert oblicz_tip_correct("GOL: Adam Nowak", "1-0", statystyki=st) == 0


def test_sot():
    assert oblicz_tip_correct("SOT: Erling Haaland OVER 3.5", "1-2", statystyki=STAT) == 1
    assert oblicz_tip_correct("SOT: Erling Haaland OVER 4.5", "1-2", statystyki=STAT) == 0
    assert oblicz_tip_correct("SOT: Erling Haaland UNDER 4.5", "1-2", statystyki=STAT) == 1


def test_zawodnik_nie_zagral_to_none():
    assert oblicz_tip_correct("GOL: Jan Kowalski", "1-0", statystyki=STAT) is None
    assert oblicz_tip_correct("SOT: Jan Kowalski OVER 0.5", "1-0", statystyki=STAT) is None


def test_zawodnika_nie_ma_w_skladzie_to_none():
    assert oblicz_tip_correct("GOL: Ktos Obcy", "1-0", statystyki=STAT) is None


def test_samo_nazwisko_gdy_jednoznaczne():
    assert oblicz_tip_correct("GOL: Haaland", "1-2", statystyki=STAT) == 1


def test_niejednoznaczne_nazwisko_to_none():
    st = {"corners": None, "zawodnicy": {
        "bruno fernandes": {"gole": 1, "sot": 1, "zagral": True, "druzyna": "home"},
        "jose fernandes": {"gole": 0, "sot": 0, "zagral": True, "druzyna": "away"}}}
    assert oblicz_tip_correct("GOL: Fernandes", "1-0", statystyki=st) is None


def test_akcenty_w_nazwisku():
    assert oblicz_tip_correct("SOT: Enzo Fernández OVER 0.5", "1-0", statystyki=STAT) == 1


def test_bez_statystyk_none():
    assert oblicz_tip_correct("GOL: Erling Haaland", "1-2") is None
    assert oblicz_tip_correct("CORNERS OVER 7.5", "1-2", statystyki=None) is None
    pusta = {"corners": None, "zawodnicy": {}}
    assert oblicz_tip_correct("CORNERS OVER 7.5", "1-2", statystyki=pusta) is None


def test_bb_przekazuje_statystyki():
    tip = "BB: 1 CORNERS OVER 4.5 & GOL: Erling Haaland & 2"
    assert oblicz_tip_correct(tip, "1-2", statystyki=STAT) == 1
    assert oblicz_tip_correct(tip, "1-2") is None


def test_bb_przegrany_czlon_golowy_bez_statystyk():
    assert oblicz_tip_correct("BB: 1 & GOL: Erling Haaland", "0-2") == 0


def test_wymaga_statystyk():
    assert wymaga_statystyk("BB: 1 CORNERS OVER 2.5 & 1")
    assert wymaga_statystyk("gol: Haaland")
    assert wymaga_statystyk("SOT: X Y OVER 1.5")
    assert not wymaga_statystyk("BB: 1 & OVER 2.5")
    assert not wymaga_statystyk("")
