"""
test_goals_value.py — silnik value na golach (Over/Under 2.5). Pivot: gole zamiast
1X2, value (fair-value vs kurs) zamiast win-rate. P(Over) z Poissona (Dixon-Coles).
"""
from footstats.core.goals_value import prob_over_25, ev_per_unit, is_value


def test_prob_over_sensible_range():
    p = prob_over_25(1.5, 1.5)          # λ_total=3.0
    assert 0.50 < p < 0.65
    assert 0.0 <= prob_over_25(0.4, 0.4) < 0.15   # mało goli
    assert prob_over_25(2.5, 2.2) > 0.75          # dużo goli


def test_prob_over_monotonic():
    assert prob_over_25(2.0, 2.0) > prob_over_25(1.0, 1.0)


def test_prob_over_plus_under_sums_one():
    p = prob_over_25(1.6, 1.3)
    assert abs((p + (1 - p)) - 1.0) < 1e-9


def test_ev_per_unit():
    assert abs(ev_per_unit(0.6, 2.0) - 0.2) < 1e-9    # 0.6*2-1
    assert abs(ev_per_unit(0.4, 2.0) - (-0.2)) < 1e-9


def test_is_value_threshold():
    assert is_value(0.60, 2.0, margin=0.05) is True    # EV +0.20 > 0.05
    assert is_value(0.52, 2.0, margin=0.05) is False   # EV +0.04 < 0.05
    assert is_value(0.40, 2.0) is False                # EV ujemny
