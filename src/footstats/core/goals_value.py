"""
goals_value.py — silnik value na rynku goli (Over/Under 2.5).

Pivot strategiczny (docs/PREDICTION_ROADMAP.md): rynek 1X2 nieprzekraczalny, ale
gole (O/U) mniej efektywne. Liczymy fair-value P(Over 2.5) z Poissona (macierz
Dixona-Coles jak bet_builder) i stawiamy TYLKO gdy edge = P×kurs − 1 > próg (value
betting), zamiast gonić win-rate.
"""
from __future__ import annotations

from footstats.core.bet_builder import probability_matrix

_OVER_LINE = 2.5


def prob_over_25(lambda_h: float, lambda_a: float) -> float:
    """P(suma goli > 2.5) z macierzy Poissona (Dixon-Coles rho)."""
    mat = probability_matrix(lambda_h, lambda_a)
    n = len(mat)
    return float(sum(
        mat[h][a]
        for h in range(n)
        for a in range(len(mat[h]))
        if h + a > _OVER_LINE
    ))


def ev_per_unit(prob: float, odds: float) -> float:
    """Oczekiwany zysk na 1 jednostkę stawki: prob*kurs − 1."""
    return prob * odds - 1.0


def is_value(prob: float, odds: float, margin: float = 0.0) -> bool:
    """True gdy edge (EV na jednostkę) przekracza próg `margin`."""
    if not odds or odds <= 1.0:
        return False
    return ev_per_unit(prob, odds) > margin
