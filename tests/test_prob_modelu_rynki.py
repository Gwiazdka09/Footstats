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


# ── Linie goli ≠ 2.5 z λ (26.10): pewność = prawdziwe P modelu, nie stałe 50 ──

from footstats.core.poisson import prob_linii_goli  # noqa: E402
from footstats.daily_agent import _powod_odrzucenia_longshot  # noqa: E402

_PRED_LAMBDA = {**_PRED, "lambda_g": 1.4, "lambda_a": 1.1}


@pytest.mark.parametrize("typ,linia,over", [
    ("Over 1.5", 1.5, True), ("Over 3.5", 3.5, True),
    ("Under 3.5", 3.5, False), ("Under 1,5", 1.5, False), ("over 0.5", 0.5, True),
])
def test_linia_goli_z_lambd_zgodna_z_prob_linii_goli(typ, linia, over):
    p_over = 100.0 * prob_linii_goli(1.4, 1.1)[linia]
    oczekiwane = p_over if over else 100.0 - p_over
    assert prob_modelu(typ, _PRED_LAMBDA) == pytest.approx(oczekiwane, abs=1e-6)


def test_over_25_zostaje_z_pred_nie_z_lambd():
    # Over 2.5 w pred to ensemble z Bzzoiro — nie nadpisujemy go czystym Poissonem.
    assert prob_modelu("Over 2.5", _PRED_LAMBDA) == _PRED["over25"]
    assert prob_modelu("Under 2.5", _PRED_LAMBDA) == _PRED["under25"]


def test_linia_goli_bez_lambd_to_none_a_nie_50():
    assert prob_modelu("Over 3.5", _PRED) is None
    assert prob_modelu("Over 5.5", _PRED_LAMBDA) is None  # linia spoza 0.5-4.5


def test_filtr_longshot_dziala_dla_over_35_z_niskim_p():
    # λ 0.8/0.7: P(Over 3.5) ≈ 5% < 40% → odrzucenie
    pred = {**_PRED, "lambda_g": 0.8, "lambda_a": 0.7}
    powod = _powod_odrzucenia_longshot("Over 3.5", 2.0, pred)
    assert powod is not None and "p_modelu" in powod
    # a Under 3.5 (≈95%) przechodzi
    assert _powod_odrzucenia_longshot("Under 3.5", 1.3, pred) is None
