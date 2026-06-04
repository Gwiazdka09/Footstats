"""Scoring helpers for FootStats AI analyzer.

Extracted from analyzer.py — odds/value calculations.
"""
from __future__ import annotations


def kurs_do_prob(kurs: float | None) -> float | None:
    """Zamienia kurs bukmacherski na prawdopodobieństwo (%)."""
    if kurs and kurs > 1.0:
        return round(100 / kurs, 1)
    return None


def value_bet(prob_model: float, kurs_buk: float | None, margin: float = 5.0) -> bool:
    """Value bet: model szacuje wyższe prawdop. niż bukmacher (margin w %)."""
    if not kurs_buk:
        return False
    prob_buk = 100 / kurs_buk
    return (prob_model - prob_buk) >= margin
