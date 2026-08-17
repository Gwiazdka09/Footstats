"""Selekcja wybiera rynek o NAJMNIEJSZEJ liczbie wyników, nie ten z przewagą.

ZMIERZONE 17.08.2026 (walk-forward, 1755 meczów z 8 lig, bez lookaheadu):

    co wybiera selekcja        średnie p modelu        >=50% w
      Under 2.5   34.1%          1          44.7%       36.4% meczów
      BTTS        28.2%          X          23.8%        0.0% meczów  ← nigdy
      1           17.9%          2          31.5%       12.6% meczów
      Over 2.5    15.0%          Over 2.5   51.6%       56.4% meczów
      2            4.8%          Under 2.5  48.4%       43.9% meczów
                                 BTTS       51.6%       58.7% meczów

    najlepszy typ 1X2   : średnio 51.9%
    najlepszy typ 2-way : średnio 60.0%
    2-way wygrywa argmax w 74.0% meczów

MECHANIZM. `najlepszy_typ` bierze typ o najwyższym SUROWYM prawdopodobieństwie
spośród sześciu. Rynek dwustronny ma zawsze jedną stronę >= 50% z definicji,
a trzystronny dzieli prawdopodobieństwo na trzy części i faworyt średnio ma 44.7%.
Argmax po surowym p faworyzuje więc rynki 2-way NIEZALEŻNIE od tego, gdzie model
ma przewagę. Remis nie może zostać wybrany NIGDY — p(X) nie sięga 50% w żadnym
meczu, a średnio wynosi 23.8%.

CZEGO TO **NIE** ZNACZY. Sprawdziłem dwie „oczywiste" alternatywy na tych samych
danych, rozliczone na realnych wynikach (podatek 12%, płaska stawka):

    reguła                       zakł.  trafność     ROI
    A argmax p (produkcja)        1752     56.3%   -10.7%
    B argmax EV                   1752     47.5%   -13.5%
    C argmax przewagi nad rynkiem 1752     47.3%   -14.7%

Obie „poprawki" są GORSZE od stanu obecnego. Powód jest spójny z resztą pomiarów:
model przegrywa tam, gdzie rozjeżdża się z rynkiem, a EV i przewaga selekcjonują
DOKŁADNIE ten rozjazd. Zmiana reguły przetasowuje straty, nie usuwa ich.

Ten plik NIE narzuca więc żadnej reguły — pilnuje, żeby stronniczość była
świadoma i udokumentowana, a nie odkrywana od nowa co kilka miesięcy.
"""
from __future__ import annotations

import pytest

from footstats.core.system_paper import najlepszy_typ


def _mecz(pw, pr, pp, o25, bt, kursy=None):
    return {
        "pw": pw, "pr": pr, "pp": pp, "o25": o25, "bt": bt,
        "odds": kursy or {
            "home": 2.0, "draw": 3.4, "away": 3.8,
            "over_2_5": 1.9, "under_2_5": 1.9, "btts": 1.8,
        },
    }


def test_rynek_2way_wygrywa_z_faworytem_1x2():
    """Faworyt 1X2 z 48% przegrywa z Under 2.5 majacym 55% — mimo ze to ten sam mecz."""
    wynik = najlepszy_typ(_mecz(pw=48, pr=27, pp=25, o25=45, bt=52))
    assert wynik is not None
    assert wynik[1] == "Under 2.5", "argmax po surowym p faworyzuje rynek 2-way"


def test_remis_nie_zostaje_wybrany_nawet_gdy_jest_argmaxem_1x2():
    """p(X) nie siega progu — remis jest strukturalnie poza zasiegiem selekcji."""
    wynik = najlepszy_typ(_mecz(pw=30, pr=38, pp=32, o25=44, bt=51))
    assert wynik is not None
    assert wynik[1] != "X"


def test_1x2_wygrywa_tylko_przy_bardzo_silnym_faworycie():
    """Zeby 1X2 przebilo 2-way, faworyt musi miec przewage rzedu 60%+."""
    wynik = najlepszy_typ(_mecz(pw=68, pr=20, pp=12, o25=52, bt=55))
    assert wynik is not None
    assert wynik[1] == "1"


def test_progu_NIE_DA_SIE_zastosowac_do_rynku_2way():
    """Sedno stronniczosci: rynku dwustronnego nie da sie oslabic.

    Prob progowy (domyslnie 40, podnoszony `SELECTION_MIN_CONF`) mial odcinac
    slabe typy. Na rynku 2-way jest bezradny: jesli jedna strona jest slaba,
    DRUGA jest o tyle samo silna. Tu model daje Over 2.5 tylko 38%, wiec
    Under 2.5 dostaje 62% i spokojnie przechodzi.

    Wniosek: prog realnie filtruje WYLACZNIE 1X2. Podnoszenie
    `SELECTION_MIN_CONF` (lewar M1 #1) zaostrza selekcje tylko po jednej stronie
    i jeszcze mocniej przechyla ja ku rynkom golowym.
    """
    wynik = najlepszy_typ(_mecz(pw=35, pr=33, pp=32, o25=38, bt=39))
    assert wynik is not None, "rynek 2-way zawsze ma strone powyzej progu"
    assert wynik[1] == "Under 2.5"
    assert wynik[0] == pytest.approx(62.0)


def test_prog_odcina_typy_1x2():
    """Ta sama bramka na 1X2 dziala normalnie — bo tam zadna strona nie jest dopelnieniem."""
    kursy = {"home": 2.0, "draw": 3.4, "away": 3.8}   # tylko 1X2, bez rynkow golowych
    assert najlepszy_typ(_mecz(pw=35, pr=33, pp=32, o25=38, bt=39, kursy=kursy)) is None


def test_kurs_poza_pasmem_wyklucza_typ():
    """Longshot i kotwica sa poza [1.20, 4.00] niezaleznie od prawdopodobienstwa."""
    kursy = {"home": 1.05, "draw": 3.4, "away": 9.0,
             "over_2_5": 1.9, "under_2_5": 1.9, "btts": 1.8}
    wynik = najlepszy_typ(_mecz(pw=85, pr=10, pp=5, o25=45, bt=52, kursy=kursy))
    assert wynik is not None
    assert wynik[1] != "1", "kurs 1.05 jest ponizej MIN_KURS i typ nie moze przejsc"


def test_brak_kursu_wyklucza_rynek():
    """Rynek bez kursu nie startuje — tak dziala produkcja przy brakach w zrodle."""
    kursy = {"home": 2.0, "draw": 3.4, "away": 3.8}
    wynik = najlepszy_typ(_mecz(pw=48, pr=27, pp=25, o25=45, bt=90, kursy=kursy))
    assert wynik is not None
    assert wynik[1] not in ("BTTS", "Over 2.5", "Under 2.5")


@pytest.mark.parametrize("bt,oczekiwany", [(75, "BTTS"), (30, "Under 2.5")])
def test_btts_konkuruje_obiema_stronami_dopiero_przy_fladze(bt, oczekiwany):
    """Przy BTTS_TWO_WAY=0 strona NIE nie gra, wiec niskie p(BTTS) NIE daje typu BTTS.

    Model dajacy BTTS 30% jest w 70% pewny strony przeciwnej, ale selekcja tej
    strony nie zna — to ta sama luka, ktora opisuje `test_btts_dwustronne.py`.
    """
    wynik = najlepszy_typ(_mecz(pw=40, pr=28, pp=32, o25=45, bt=bt))
    assert wynik is not None
    assert wynik[1] == oczekiwany
