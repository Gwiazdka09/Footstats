"""test_ai_scoring.py — helpery odds/value z ai/scoring.py (były 30% pokryte)."""
import pytest

from footstats.ai.scoring import kurs_do_prob, value_bet


@pytest.mark.parametrize("kurs,oczek", [
    (2.0, 50.0),
    (4.0, 25.0),
    (1.5, 66.7),
])
def test_kurs_do_prob_przelicza(kurs, oczek):
    assert kurs_do_prob(kurs) == oczek


@pytest.mark.parametrize("kurs", [None, 0, 1.0, 0.9])
def test_kurs_do_prob_niepoprawny_kurs_to_none(kurs):
    assert kurs_do_prob(kurs) is None


def test_value_bet_model_wyzszy_niz_buk():
    # buk: 100/2.0 = 50%; model 60% → edge 10% >= margin 5 → True
    assert value_bet(60.0, 2.0, margin=5.0) is True


def test_value_bet_ponizej_marginu():
    # buk 50%, model 52% → edge 2% < 5 → False
    assert value_bet(52.0, 2.0, margin=5.0) is False


def test_value_bet_brak_kursu_to_false():
    assert value_bet(80.0, None) is False


def test_value_bet_domyslny_margin():
    # buk 50%, model 55% → edge 5% >= domyślne 5 → True
    assert value_bet(55.0, 2.0) is True
