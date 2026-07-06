"""
availability_edge.py — ścieżka B (edge informacyjny): przewaga z team-news.

Teza (docs/PREDICTION_ROADMAP.md): rynku nie pobijesz modelem na publicznych danych,
ALE potwierdzona absencja gwiazdy TUŻ przed meczem rusza fair-value zanim miękkie booki
zareagują. Liczymy skorygowane λ (odejmując udział nieobecnych w golach — goal_share
z bazy graczy) → nowe P(Over) → edge vs kurs rynku (jeszcze nieprzesunięty).

Forward-only: brak historycznych składów/kontuzji → nie backtestujemy ROI, walidujemy
logikę. Reuse `injury_lambda_factors`/goal_share z pracy player-DB.
"""
from __future__ import annotations

from footstats.core.goals_value import prob_over_25

_SCALE = 0.5   # spójne z injury_lambda_factors._SCALE_GOAL_SHARE
_CAP = 0.35    # max redukcja ataku (nie zerujemy drużyny)


def absence_attack_factor(
    goal_shares_out: list[float], scale: float = _SCALE, cap: float = _CAP
) -> float:
    """Mnożnik λ ataku za potwierdzonych nieobecnych: 1 − min(Σ share × scale, cap)."""
    loss = min(sum(goal_shares_out) * scale, cap)
    return 1.0 - loss


def over_edge_from_absences(
    lambda_h: float,
    lambda_a: float,
    out_home_shares: list[float],
    out_away_shares: list[float],
    market_p_over: float | None,
) -> dict:
    """
    Przelicza P(Over 2.5) po odjęciu nieobecnych i zwraca edge vs rynek.

    Zwraca {p_over_adj, lh, la, edge}. edge = p_over_adj − market_p_over
    (None gdy brak kursu rynku). edge < 0 → nasze P niższe → value na Under
    (i odwrotnie), zanim rynek wchłonie news.
    """
    lh = lambda_h * absence_attack_factor(out_home_shares)
    la = lambda_a * absence_attack_factor(out_away_shares)
    p = prob_over_25(lh, la)
    edge = None if market_p_over is None else round(p - market_p_over, 4)
    return {"p_over_adj": round(p, 4), "lh": round(lh, 3), "la": round(la, 3), "edge": edge}
