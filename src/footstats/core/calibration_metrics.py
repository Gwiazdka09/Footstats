"""
calibration_metrics.py — metryki jakości predyktora (ścieżka A: kalibracja).

Skoro ROI-vs-rynek jest niedostępne publicznymi danymi (docs/PREDICTION_ROADMAP.md),
north-star = jak DOBRE i KALIBROWANE są nasze prawdopodobieństwa: log-loss + Brier
(niżej = lepiej), porównane z rynkiem (devig kursów).
"""
from __future__ import annotations

import math

_EPS = 1e-12


def log_loss(p_actual: float) -> float:
    """−ln(p) dla prawdopodobieństwa przypisanego FAKTYCZNEMU wynikowi. Clamp eps."""
    return -math.log(min(max(p_actual, _EPS), 1.0))


def shrink_prob(p: float, k: float, center: float = 0.5) -> float:
    """
    Kalibracja przez shrinkage ku środkowi: p' = center + (p − center)·k.
    k<1 ściąga skrajne (leczy overconfidence), k=1 bez zmian. Clamp [0,1].
    """
    return min(max(center + (p - center) * k, 0.0), 1.0)


def brier_multi(probs: list[float], actual_idx: int) -> float:
    """Brier wieloklasowy: Σ_i (p_i − 1{i=actual})². 0 = idealny."""
    return sum((p - (1.0 if i == actual_idx else 0.0)) ** 2 for i, p in enumerate(probs))


def brier_binary(prob: float, outcome: bool) -> float:
    """Brier binarny: (p − wynik)²."""
    return (prob - (1.0 if outcome else 0.0)) ** 2


def devig_two_way(odds_a: float | None, odds_b: float | None) -> tuple[float, float] | None:
    """
    Implikowane prob dwustronnego rynku (np. Over/Under) bez marży.
    p_i = (1/odds_i) / Σ(1/odds). None gdy kurs nieprawidłowy.
    """
    for o in (odds_a, odds_b):
        if o is None or (isinstance(o, float) and math.isnan(o)) or o <= 1.0:
            return None
    ia, ib = 1.0 / odds_a, 1.0 / odds_b
    s = ia + ib
    if s <= 0:
        return None
    return ia / s, ib / s
