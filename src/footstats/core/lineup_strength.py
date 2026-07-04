"""
lineup_strength.py — Faza 2: ocena siły wyjściowego składu (startXI) względem siły
strzeleckiej zespołu z Fazy 1 (goal_share). Brak topowego strzelca w składzie →
λ własnego ataku ↓ i kara do decision_score. Zastępuje crude `len(startXI)<11`.

Nazwy w startXI (API-Football /fixtures/lineups) pochodzą z tego samego źródła co
topscorers → dopasowanie po casefold. Brak danych (pusta XI lub pusty goal_shares)
→ zero kary (nie wiadomo kto realnie gra → nie zgadujemy).
"""
from __future__ import annotations

_LAMBDA_SCALE = 0.5   # spójne z injury_lambda_factors._SCALE_GOAL_SHARE
_CAP = 0.20           # ±20% cap na λ (jak Kontuzje v2)
_STAR_THRESHOLD = 0.15
_PENALTY_SCALE = 30   # power 0.5 → -15 (magnituda starego flat -15)


def _casefold_set(start_xi: list[str]) -> set[str]:
    return {(n or "").strip().casefold() for n in start_xi if (n or "").strip()}


def lineup_offensive_strength(start_xi: list[str], goal_shares: dict[str, float]) -> float:
    """Suma goal_share graczy obecnych w startXI (0-1) = % siły strzeleckiej na boisku."""
    if not start_xi or not goal_shares:
        return 0.0
    present = _casefold_set(start_xi)
    s = sum(sh for n, sh in goal_shares.items() if (n or "").strip().casefold() in present)
    return max(0.0, min(1.0, s))


def absent_stars(
    start_xi: list[str], goal_shares: dict[str, float], threshold: float = _STAR_THRESHOLD
) -> dict[str, float]:
    """{gracz: share} strzelców o share≥threshold NIEOBECNych w startXI. Pusty gdy brak danych."""
    if not start_xi or not goal_shares:
        return {}
    present = _casefold_set(start_xi)
    return {
        n: sh for n, sh in goal_shares.items()
        if sh >= threshold and (n or "").strip().casefold() not in present
    }


def lineup_lambda_factor(
    start_xi: list[str],
    goal_shares: dict[str, float],
    threshold: float = _STAR_THRESHOLD,
    scale: float = _LAMBDA_SCALE,
    cap: float = _CAP,
) -> float:
    """
    Mnożnik λ własnego ataku za nieobecnych strzelców w startXI: 1 - Σ(share_absent)*scale,
    przycięty do [1-cap, 1.0]. Brak danych → 1.0. Zakłada pełną znaną startXI.
    """
    absent = absent_stars(start_xi, goal_shares, threshold)
    if not absent:
        return 1.0
    factor = 1.0 - sum(absent.values()) * scale
    return round(max(1.0 - cap, min(1.0, factor)), 4)


def _top_scorer_absent_power(
    start_xi: list[str], goal_shares: dict[str, float], threshold: float
) -> float:
    """share topowego strzelca zespołu jeśli NIE ma go w startXI (else 0). Robust na skrócone XI."""
    if not start_xi or not goal_shares:
        return 0.0
    name, share = max(goal_shares.items(), key=lambda kv: kv[1])
    if share < threshold:
        return 0.0
    return 0.0 if (name or "").strip().casefold() in _casefold_set(start_xi) else share


def lineup_confidence_penalty_v2(
    lineup: dict | None,
    goal_shares_home: dict[str, float],
    goal_shares_away: dict[str, float],
    threshold: float = _STAR_THRESHOLD,
) -> int:
    """
    Kara do decision_score skalowana siłą nieobecnego TOP strzelca każdej strony
    (-round(power*30); power 0.5 → -15). 0 gdy główny strzelec gra / brak danych.
    Precyzyjniejsza niż `lineup_confidence_penalty` (crude len<11).
    """
    if not lineup:
        return 0
    penalty = 0
    for side, gs in (("home", goal_shares_home), ("away", goal_shares_away)):
        xi = (lineup.get(side, {}) or {}).get("startXI", []) or []
        power = _top_scorer_absent_power(xi, gs or {}, threshold)
        penalty -= round(power * _PENALTY_SCALE)
    return penalty
