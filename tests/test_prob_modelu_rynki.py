"""Prawdopodobieństwo modelu dla podwójnej szansy i linii goli (krok 0, 22.10).

Do 22.10 `1X` dostawało samo P(1), `X2` samo P(2) — zaniżone o remis (~25 pp),
a `12` nie istniało. `Over 1.5`/`Over 3.5` dostawały P(Over 2.5), czyli liczbę
z innego rynku. Ta sama reguła żyła w dwóch kopiach (analyzer_helpers
i daily_agent) i rozjechała się (daily_agent nie znał BTTS NIE).
"""
import pytest

from footstats.ai.analyzer_helpers import prob_modelu
from footstats.daily_agent import _prob_modelu_dla_typu

_PRED = {
    "p_wygrana": 50.0, "p_remis": 27.0, "p_przegrana": 23.0,
    "over25": 55.0, "under25": 45.0, "btts": 52.0,
}


@pytest.mark.parametrize("typ, oczekiwane", [
    ("1X", 77.0), ("1x", 77.0), ("X2", 50.0), ("x2", 50.0), ("12", 73.0),
])
def test_podwojna_szansa_to_suma_dwoch_wynikow(typ, oczekiwane):
    assert prob_modelu(typ, _PRED) == pytest.approx(oczekiwane)


def test_podwojna_szansa_bez_skladnika_daje_none():
    assert prob_modelu("1X", {"p_wygrana": 50.0}) is None


@pytest.mark.parametrize("typ, oczekiwane", [
    ("Over 2.5", 55.0), ("over2.5", 55.0), ("Over", 55.0), ("over 2,5", 55.0),
    ("Under 2.5", 45.0), ("under", 45.0),
])
def test_linia_2_5_bez_zmian(typ, oczekiwane):
    assert prob_modelu(typ, _PRED) == oczekiwane


@pytest.mark.parametrize("typ", ["Over 1.5", "Over 3.5", "Under 1.5", "Under 3.5", "over 0.5"])
def test_inna_linia_goli_nie_dostaje_liczby_z_2_5(typ):
    assert prob_modelu(typ, _PRED) is None


@pytest.mark.parametrize("typ", [
    "1", "X", "2", "1X", "X2", "12", "Over 2.5", "Over 1.5",
    "Under 2.5", "BTTS", "BTTS NIE", "nieznany",
])
def test_daily_agent_liczy_tak_samo_jak_analyzer(typ):
    # Jedna reguła — daily_agent deleguje, nie trzyma własnej kopii.
    assert _prob_modelu_dla_typu(typ, _PRED) == prob_modelu(typ, _PRED)
