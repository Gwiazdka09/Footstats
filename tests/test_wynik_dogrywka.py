"""Wynik po dogrywce/karnych — rozpoznany i uczciwie anulowany, nie zgadywany.

STAN ZASTANY (zmierzony 17.08 na produkcji): `oblicz_tip_correct("1X", "2-1aet")`
zwracało `None`, bo parser ucinał tylko nawiasy — `int("1aet")` wybuchał po cichu.
Noga zostawała nierozliczona, a kupon czekał **10 dni** i dopiero wtedy wpadał
w siatkę `VOID_AFTER_DAYS`. Efekt: kupon możliwy do rozstrzygnięcia znikał jako
anulowany, bez podanej przyczyny, i nie liczył się do trafności ani ROI.

DLACZEGO NIE ROZLICZAMY PO DOGRYWCE. Standardowe rynki (1X2, Over/Under, BTTS)
rozliczają się po 90 minutach, a zapis `2-1aet` niesie wynik PO dogrywce — wyniku
regulaminowego w nim nie ma. Kuszące „skoro była dogrywka, to po 90 był remis"
jest zawodne: w dwumeczu dogrywkę wymusza remis w DWUMECZU, więc sam mecz mógł
skończyć się 1-0. Zgadywanie dałoby ciche przekłamania w statystykach.

Stąd decyzja: rozpoznać format, powiedzieć to głośno i anulować od razu —
zamiast dziesięciu dni ciszy zakończonych anulowaniem bez wyjaśnienia.
"""
from __future__ import annotations

import pytest

from footstats.utils.betting import oblicz_tip_correct, powod_nierozliczalny


# ── rozpoznawanie formatu ──────────────────────────────────────────────────

@pytest.mark.parametrize("wynik", [
    "2-1aet", "2-1 aet", "2-1 AET", "2-1 (AET)", "2-1 a.e.t.", "3-2 ET",
])
def test_dogrywka_rozpoznana(wynik):
    assert powod_nierozliczalny(wynik) == "dogrywka"


@pytest.mark.parametrize("wynik", [
    "1-0 pen", "1-0 pens", "2-2 (4-3 pen)", "1-1 PEN", "0-0 ap", "1-1 karne",
])
def test_karne_rozpoznane(wynik):
    assert powod_nierozliczalny(wynik) == "karne"


@pytest.mark.parametrize("wynik", ["2-1", "0-0", "10-2", " 3 - 1 ", "3-1;HT:1-0"])
def test_zwykly_wynik_jest_rozliczalny(wynik):
    assert powod_nierozliczalny(wynik) is None


@pytest.mark.parametrize("wynik", [None, "", "   "])
def test_brak_wyniku_to_NIE_to_samo_co_nierozliczalny(wynik):
    """Brak wyniku = jeszcze nie wiemy. Nierozliczalny = wiemy i nie da się."""
    assert powod_nierozliczalny(wynik) is None


def test_nazwa_zawierajaca_pen_nie_myli():
    """`Openda` zawiera 'pen' — dopasowanie musi iść po całych słowach."""
    assert powod_nierozliczalny("2-1 Openda") is None


def test_tuple_i_lista_tez_obslugiwane():
    assert powod_nierozliczalny((2, 1)) is None


# ── parser dalej nie zgaduje ───────────────────────────────────────────────

@pytest.mark.parametrize("tip", ["1", "X", "2", "1X", "Over 2.5", "BTTS"])
def test_dogrywka_NIE_jest_rozliczana_przez_oblicz_tip_correct(tip):
    """Świadomie None: bez wyniku po 90 minutach rozliczenie byłoby zmyślone."""
    assert oblicz_tip_correct(tip, "2-1aet") is None


def test_zwykly_wynik_dalej_dziala():
    """Kontrola — gdyby parser padł, testy wyżej przechodziłyby za darmo."""
    assert oblicz_tip_correct("1", "2-1") == 1
    assert oblicz_tip_correct("X", "2-1") == 0
    assert oblicz_tip_correct("Over 2.5", "2-1") == 1


def test_nawias_z_dogrywka_dalej_nie_rozlicza():
    """Format `2-1 (AET)` parser dotad UMIAL przeciac i rozliczal po dogrywce.

    To bylo ciche przeklamanie — ten sam mecz w zapisie `2-1aet` zwracal None,
    a w zapisie `2-1 (AET)` dawal wynik. Teraz oba traktowane tak samo.
    """
    assert oblicz_tip_correct("1", "2-1 (AET)") is None
