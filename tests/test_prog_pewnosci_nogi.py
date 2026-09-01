"""Prog pewnosci nogi w prompcie kuponu — konfigurowalny, nie zaszyty.

DECYZJA UZYTKOWNIKA 01.09: obnizyc z 60% do zakresu 40-50%. Wybrane **50%**,
i to nie jest srodek widelek na oko — regula tuz obok w tym samym prompcie mowi:

    - 75-100%: only with overwhelming evidence. 50-74%: normal bet. <50%: avoid.

Prog 45 albo 40 postawilby te dwie linie w sprzecznosci: jedna kazalaby unikac
zakladu ponizej 50%, druga by go dopuszczala. Ten projekt zna juz koszt dwoch
regul, ktore mowia co innego — rozjazd jest cichy, bo dokument dalej wyglada
poprawnie.

ZMIERZONE 01.09 na zywym modelu (jedna probka na komorke, `4 slips` poluzowane
jednakowo we wszystkich wierszach, wiec porownanie miedzy progami jest wazne):

    prog | 1 mecz | 3 mecze | 5 meczow
    -----|--------|---------|----------
      60 |   0    |    0    |    3
      50 |   1    |    3    |    3
      45 |   1    |    3    |    3
      40 |   0    |    1    |    3

Po filtrach wartosci zostaje zwykle 1-3 kandydatow, czyli dokladnie te komorki,
ktore prog 60 blokowal. Zejscie ponizej 50 nic nie dodaje.

DRUGA regula blokowala niezaleznie od progu: "4 slips = 4 different matches".
Przy 1-3 kandydatach jest niewykonalna — model odmawial, bo nie mial z czego
zlozyc czterech kuponow. To nie jest decyzja o ryzyku, tylko wymaganie
sprzeczne z danymi, ktore samo sobie przeczy.
"""
from __future__ import annotations

import importlib

import pytest


def _prompt(**kw) -> str:
    from footstats.ai.prompts import build_pewniaczki_prompt
    return build_pewniaczki_prompt(
        n_mecze=kw.get("n_mecze", 3), sygnaly="", kalibracja_str="",
        feedback_str="", mecze_opisy_text="MECZ", cel_kuponow_text="CEL",
    )


def _linia(tekst: str, fragment: str) -> str:
    trafienia = [l for l in tekst.splitlines() if fragment in l]
    assert trafienia, f"brak linii z {fragment!r}"
    return trafienia[0]


# ── prog jest konfigurowalny ────────────────────────────────────────────────

def test_domyslny_prog_to_50():
    assert "pewnosc_pct >= 50%" in _prompt()


def test_stare_60_juz_nie_wystepuje():
    assert "pewnosc_pct >= 60%" not in _prompt()


def test_prog_da_sie_zmienic_bez_deployu(monkeypatch):
    """Strategia zakladow ma byc pokretlem, nie zmiana w kodzie."""
    monkeypatch.setenv("KUPON_MIN_PEWNOSC_PCT", "55")

    from footstats import config
    importlib.reload(config)
    from footstats.ai import prompts
    importlib.reload(prompts)
    try:
        assert "pewnosc_pct >= 55%" in _prompt()
    finally:
        monkeypatch.delenv("KUPON_MIN_PEWNOSC_PCT", raising=False)
        importlib.reload(config)
        importlib.reload(prompts)


# ── spojnosc z sasiednia regula ─────────────────────────────────────────────

def test_prog_nie_zaprzecza_regule_ponizej_50_avoid():
    """Dwie reguly w jednym prompcie nie moga mowic czego innego.

    `<50%: avoid` stoi 26 linii wyzej. Prog 45 znaczylby: unikaj ponizej 50,
    ale wolno ci brac od 45. Model dostaje wtedy sprzecznosc do rozstrzygniecia
    sam — a zmierzone 01.09 zachowanie przy 40% bylo wlasnie takie: model
    zaczynal cytowac progi, ktorych nikt nie ustawil (63%)."""
    from footstats.config import KUPON_MIN_PEWNOSC_PCT

    assert KUPON_MIN_PEWNOSC_PCT >= 50, (
        "prog ponizej 50 kloci sie z regula `<50%: avoid` w tym samym prompcie"
    )


def test_obie_reguly_dalej_sa_w_prompcie():
    """Kontrola: obnizenie progu nie moze przy okazji skasowac drugiej reguly."""
    tekst = _prompt()
    assert "<50%: avoid" in tekst
    assert "pewnosc_pct >=" in tekst


# ── wymaganie 4 kuponow nie moze byc niewykonalne ───────────────────────────

def test_nie_zada_czterech_meczow_gdy_jest_mniej():
    """Po filtrach wartosci zostaje 1-3 kandydatow. Zadanie 'four different
    matches' bylo wtedy nie do spelnienia i model odmawial calkowicie."""
    tekst = _prompt(n_mecze=1)

    assert "4 slips = 4 different matches" not in tekst


def test_dalej_zakazuje_akumulatorow():
    """Kontrola: luzujemy LICZBE kuponow, nie zasade 'jeden kupon = jedna noga'.
    Poprzednie piec kuponow final mialo kursy do 77 i wszystkie przepadly."""
    tekst = _prompt()

    assert "EXACTLY 1 leg" in tekst
    assert "No accumulators" in tekst


@pytest.mark.parametrize("ile", [1, 2, 3, 5])
def test_prompt_powstaje_dla_kazdej_liczby_meczow(ile):
    assert _prompt(n_mecze=ile)
