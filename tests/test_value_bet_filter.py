"""Testy core/value_bet.py — EV, Kelly, filtr value betów."""
import pytest
from footstats.core.value_bet import (
    calculate_ev,
    is_value_bet,
    kelly_fraction,
    filter_value_bets,
)


# ── calculate_ev ──────────────────────────────────────────────────────────

def test_ev_positive():
    # prob=0.6, odds=2.0 → (0.6*2.0 - 1)*100 = 20%
    assert calculate_ev(0.6, 2.0) == pytest.approx(20.0)


def test_ev_negative():
    # prob=0.4, odds=2.0 → (0.4*2.0 - 1)*100 = -20%
    assert calculate_ev(0.4, 2.0) == pytest.approx(-20.0)


def test_ev_zero():
    # prob=0.5, odds=2.0 → EV=0
    assert calculate_ev(0.5, 2.0) == pytest.approx(0.0)


# ── is_value_bet ─────────────────────────────────────────────────────────

def test_is_value_bet_true():
    assert is_value_bet(0.6, 2.0) is True   # EV=20% > 3%


def test_is_value_bet_false():
    assert is_value_bet(0.4, 2.0) is False  # EV=-20%


def test_is_value_bet_custom_threshold():
    assert is_value_bet(0.52, 2.0, min_ev_pct=5.0) is False  # EV=4% < 5%
    assert is_value_bet(0.52, 2.0, min_ev_pct=3.0) is True   # EV=4% > 3%


# ── kelly_fraction ────────────────────────────────────────────────────────

def test_kelly_positive_edge():
    # f* = (0.6*2.0 - 1)/(2.0-1) = 0.2/1 = 0.2
    assert kelly_fraction(0.6, 2.0) == pytest.approx(0.2)


def test_kelly_no_edge_returns_zero():
    assert kelly_fraction(0.4, 2.0) == 0.0


def test_kelly_odds_one_returns_zero():
    assert kelly_fraction(0.9, 1.0) == 0.0


# ── filter_value_bets ─────────────────────────────────────────────────────

def test_filter_keeps_value_bets():
    kandydaci = [
        {"pewnosc_pct": 60, "odds": {"1": 2.5}},  # EV high
        {"pewnosc_pct": 40, "odds": {"1": 2.5}},  # EV negative
    ]
    result = filter_value_bets(kandydaci)
    assert len(result) == 1
    assert result[0]["pewnosc_pct"] == 60


def test_filter_keeps_no_odds():
    kandydaci = [{"pewnosc_pct": 50}]  # no odds → zawsze zachowaj
    result = filter_value_bets(kandydaci)
    assert len(result) == 1


def test_filter_adds_ev_and_kelly_fields():
    kandydaci = [{"pewnosc_pct": 60, "odds": {"1": 2.0}}]
    result = filter_value_bets(kandydaci)
    assert len(result) == 1
    assert "ev_value_pct" in result[0]
    assert "kelly_fraction_pct" in result[0]


def test_filter_empty_input():
    assert filter_value_bets([]) == []
