"""test_betting_gole_druzyny.py — rynki "Gospodarz strzeli 0.5+" muszą się rozliczać.

PO CO: `bet_builder` generuje typy w zapisie "Gospodarz strzeli 0.5+" /
"Gość strzeli 0.5+" / "Gospodarz strzeli 1.5+" (linie 150-154). `oblicz_tip_correct`
znało tylko zapis "GOSPODARZ OVER 0.5" — dwa słowniki, obsługiwany jeden.

Skutek był cichy i kosztowny: predykcja na taki rynek NIGDY nie dostawała
`tip_correct`, więc:
  * nie liczyła się jako rozliczona,
  * nie trafiała do statystyk trafności,
  * NIE STAWAŁA SIĘ LEKCJĄ w pętli uczenia.

W bazie produkcyjnej leżała predykcja #8 (Athletico vs Internacional) z gotowym
wynikiem "2-0" i pustym `tip_correct` — wynik był, tylko nikt nie umiał go
zestawić z typem. Przy 15 predykcjach w całej historii dwie takie martwe pozycje
to ~13% całego paliwa nauki.

Semantyka: "strzeli 0.5+" znaczy WIĘCEJ NIŻ 0.5 gola, czyli co najmniej jeden —
identycznie jak "OVER 0.5". Zapis z plusem to konwencja bukmacherska.
"""
from __future__ import annotations

import pytest

from footstats.utils.betting import oblicz_tip_correct


# ── gospodarz ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("wynik", ["1-0", "2-0", "3-1", "1-1"])
def test_gospodarz_05_trafiony_gdy_strzelil(wynik):
    assert oblicz_tip_correct("Gospodarz strzeli 0.5+", wynik) == 1


@pytest.mark.parametrize("wynik", ["0-0", "0-1", "0-3"])
def test_gospodarz_05_pudlo_gdy_nie_strzelil(wynik):
    assert oblicz_tip_correct("Gospodarz strzeli 0.5+", wynik) == 0


def test_gospodarz_15_wymaga_dwoch_goli():
    assert oblicz_tip_correct("Gospodarz strzeli 1.5+", "2-0") == 1
    assert oblicz_tip_correct("Gospodarz strzeli 1.5+", "1-0") == 0


def test_gospodarz_25_wymaga_trzech_goli():
    assert oblicz_tip_correct("Gospodarz strzeli 2.5+", "3-1") == 1
    assert oblicz_tip_correct("Gospodarz strzeli 2.5+", "2-1") == 0


# ── gość (oba zapisy, z diakrytykami i bez) ────────────────────────────────

@pytest.mark.parametrize("typ", [
    "Gość strzeli 0.5+", "Gosc strzeli 0.5+",
    "Goscie strzela 0.5+", "Goście strzelą 0.5+",
])
def test_gosc_05_trafiony(typ):
    """Zapis bywa różny — z diakrytykami, bez, w liczbie mnogiej."""
    assert oblicz_tip_correct(typ, "0-1") == 1


@pytest.mark.parametrize("typ", ["Gość strzeli 0.5+", "Gosc strzeli 0.5+"])
def test_gosc_05_pudlo(typ):
    assert oblicz_tip_correct(typ, "2-0") == 0


def test_gosc_liczony_z_wlasciwej_strony():
    """Zamiana stron dawałaby wynik odwrotny przy każdym meczu bez remisu."""
    assert oblicz_tip_correct("Gospodarz strzeli 0.5+", "3-0") == 1
    assert oblicz_tip_correct("Gość strzeli 0.5+", "3-0") == 0


# ── wielkość liter i spacje ────────────────────────────────────────────────

@pytest.mark.parametrize("typ", [
    "gospodarz strzeli 0.5+", "GOSPODARZ STRZELI 0.5+", "  Gospodarz strzeli 0.5+  ",
])
def test_zapis_niewrazliwy_na_forme(typ):
    assert oblicz_tip_correct(typ, "1-0") == 1


def test_sufiks_z_szansa_nie_psuje_rozliczenia():
    """`bet_builder` dokleja "(Szansa: 78%)" — nie może to blokować rozliczenia."""
    assert oblicz_tip_correct("Gospodarz strzeli 0.5+ (Szansa: 78%)", "1-0") == 1


# ── zgodność ze starym zapisem ─────────────────────────────────────────────

def test_stary_zapis_over_nadal_dziala():
    """Poprawka nie może zepsuć zapisu, który działał wcześniej."""
    assert oblicz_tip_correct("GOSPODARZ OVER 0.5", "1-0") == 1
    assert oblicz_tip_correct("GOŚĆ OVER 1.5", "0-2") == 1


def test_oba_zapisy_daja_ten_sam_wynik():
    for wynik in ("0-0", "1-0", "0-1", "2-2", "3-0"):
        assert (oblicz_tip_correct("Gospodarz strzeli 0.5+", wynik)
                == oblicz_tip_correct("GOSPODARZ OVER 0.5", wynik)), wynik


# ── przypadki brzegowe ─────────────────────────────────────────────────────

def test_brak_wyniku_to_nierozliczone():
    assert oblicz_tip_correct("Gospodarz strzeli 0.5+", None) is None


def test_wynik_1x2_bez_bramek_nie_rozlicza():
    """Sam "1" nie mówi, ile goli padło — nie da się ocenić rynku bramkowego."""
    assert oblicz_tip_correct("Gospodarz strzeli 0.5+", "1") is None


def test_wynik_z_dogrywka_NIE_jest_rozliczany():
    """ZMIANA INTENCJI 17.08 — rynek goli drużyny też rozlicza się po 90 minutach.

    Gol strzelony w dogrywce nie liczy się do zakładu, a zapis `2-1 (AET)` nie
    mówi, ile padło w regulaminowym czasie. Wcześniej sufiks był obcinany i typ
    rozliczany z sumy po dogrywce.
    """
    assert oblicz_tip_correct("Gospodarz strzeli 0.5+", "2-1 (AET)") is None


def test_sufiks_polowy_nie_przeszkadza():
    assert oblicz_tip_correct("Gospodarz strzeli 0.5+", "1-0;HT:0-0") == 1


# ── w kombinacji BetBuilder ────────────────────────────────────────────────

def test_czlon_w_kombinacji_bb():
    """Kombinacja to koniunkcja — nierozliczalny człon psuł CAŁE combo."""
    assert oblicz_tip_correct("BB: 1 + Gospodarz strzeli 0.5+", "2-0") == 1


def test_kombinacja_pudlo_gdy_czlon_nietrafiony():
    assert oblicz_tip_correct("BB: 1 + Gospodarz strzeli 1.5+", "1-0") == 0
