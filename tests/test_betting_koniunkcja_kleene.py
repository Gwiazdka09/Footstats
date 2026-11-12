"""Koniunkcja trojwartosciowa: przegrany czlon przesadza noge mimo nierozpoznanego."""
import pytest

from footstats.core.rynki_dziennika import czy_rozliczalny
from footstats.utils.betting import oblicz_tip_correct

TYP = "BB: 1 OVER 0.5 & NIEZNANY RYNEK"


def test_przegrany_czlon_przesadza_mimo_nieznanego():
    assert oblicz_tip_correct(TYP, "0-2") == 0


def test_wygrany_czlon_i_nieznany_daje_none():
    assert oblicz_tip_correct(TYP, "2-0") is None


def test_wszystkie_wygrane_daje_1():
    assert oblicz_tip_correct("BB: 1 OVER 0.5 & BTTS", "2-1") == 1


@pytest.mark.parametrize("tip", [TYP, "BB: BTTS & NIEZNANY RYNEK"])
def test_czy_rozliczalny_false_dla_nierozpoznanego(tip):
    assert czy_rozliczalny(tip) is False
