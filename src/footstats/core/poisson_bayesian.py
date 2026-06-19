"""core/poisson_bayesian.py — Bayesian Poisson extension with att/def ratings + recency weighting."""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd
from scipy.stats import poisson

from footstats.config import MAX_GOLE, BONUS_DOMOWY

_log = logging.getLogger(__name__)

# Recency weights: last 5 matches get 3x weight vs older
_W_RECENT = 3.0
_W_OLDER = 1.0
_N_RECENT = 5

# Bayesian prior strength: 1 = fully trust data, 0 = fully trust prior
# Higher value = more shrinkage toward league average (safer for small samples)
_PRIOR_WEIGHT = 3.0  # equivalent to 3 "pseudo-matches" at league average


def _compute_ratings(
    team: str, df: pd.DataFrame, is_home: bool
) -> dict[str, float]:
    """
    Compute attack and defense rating for one team from match data.
    Returns {att, def, n} or None if insufficient data.
    """
    if is_home:
        mask = df["gospodarz"] == team
        goals_scored_col, goals_conceded_col = "gole_g", "gole_a"
    else:
        mask = df["goscie"] == team
        goals_scored_col, goals_conceded_col = "gole_a", "gole_g"

    rows = df[mask].copy()
    if rows.empty:
        return {"att": None, "def": None, "n": 0}

    # Recency weights
    n = len(rows)
    cutoff = max(0, n - _N_RECENT)
    weights = np.array([_W_OLDER] * cutoff + [_W_RECENT] * (n - cutoff))

    scored = rows[goals_scored_col].values
    conceded = rows[goals_conceded_col].values

    w_sum = weights.sum()
    att = float(np.dot(weights, scored) / w_sum)
    def_ = float(np.dot(weights, conceded) / w_sum)

    return {"att": att, "def": def_, "n": int(n)}


def _league_averages(df: pd.DataFrame) -> dict[str, float]:
    """Compute league-wide avg goals scored/conceded per match."""
    if df.empty or "gole_g" not in df.columns:
        return {"home_avg": 1.5, "away_avg": 1.1}
    home_avg = float(df["gole_g"].mean())
    away_avg = float(df["gole_a"].mean())
    return {
        "home_avg": max(0.5, home_avg),
        "away_avg": max(0.5, away_avg),
    }


def _bayesian_shrink(observed: float, n: int, prior: float) -> float:
    """
    Bayesian shrinkage estimator:
    posterior = (n * observed + prior_weight * prior) / (n + prior_weight)
    """
    return (n * observed + _PRIOR_WEIGHT * prior) / (n + _PRIOR_WEIGHT)


def predict_match_bayesian(
    g: str,
    a: str,
    df: pd.DataFrame,
    home_advantage: float = BONUS_DOMOWY,
) -> Optional[dict]:
    """
    Bayesian Poisson prediction using separate attack/defense ratings.

    Model:
        lambda_home = (home_att / league_home_avg) * (away_def / league_away_avg) * league_home_avg * home_advantage
                    = home_att_ratio * away_def_ratio * league_home_avg * bonus
        lambda_away = (away_att / league_away_avg) * (home_def / league_home_avg) * league_away_avg

    Both attack and defense ratings shrunk toward league prior via Bayesian update.
    """
    if df.empty or "gole_g" not in df.columns:
        return None

    avgs = _league_averages(df)
    league_home = avgs["home_avg"]
    league_away = avgs["away_avg"]

    # Home team ratings (as home team and overall defense)
    home_home = _compute_ratings(g, df, is_home=True)
    home_away_def = _compute_ratings(g, df, is_home=False)  # how many conceded as away

    # Away team ratings (as away team and overall attack)
    away_away = _compute_ratings(a, df, is_home=False)
    away_home_def = _compute_ratings(a, df, is_home=True)  # how many conceded as home

    # Bayesian-shrunk attack/defense rates
    if home_home["att"] is None or away_away["att"] is None:
        return None

    # Home team attack (as home)
    home_att = _bayesian_shrink(home_home["att"], home_home["n"], league_home)
    # Away team defense (as away) — lower = better defense
    away_def = _bayesian_shrink(away_away["def"], away_away["n"], league_away)

    # Away team attack (as away)
    away_att = _bayesian_shrink(away_away["att"], away_away["n"], league_away)
    # Home team defense (as home)
    home_def_val = (
        _bayesian_shrink(home_home["def"], home_home["n"], league_home)
        if home_home["def"] is not None
        else league_home
    )

    # Dixon-Coles style lambdas
    # lambda_h = (home_att / league_home) * (away_def / league_away) * league_home * home_bonus
    #           = home_att * (away_def / league_away) * home_bonus
    lambda_h = max(0.05, home_att * (away_def / league_away) * home_advantage)
    lambda_a = max(0.05, away_att * (home_def_val / league_home))

    # Prediction matrix
    N = MAX_GOLE
    pmf_h = poisson.pmf(np.arange(N), lambda_h)
    pmf_a = poisson.pmf(np.arange(N), lambda_a)
    M = np.outer(pmf_h, pmf_a)
    M_sum = M.sum()
    if M_sum > 0:
        M /= M_sum

    pw = float(np.sum(np.tril(M, -1)))   # home win
    pr = float(np.trace(M))               # draw
    pa = float(np.sum(np.triu(M, 1)))    # away win

    return {
        "lambda_g": round(lambda_h, 4),
        "lambda_a": round(lambda_a, 4),
        "pw": round(pw, 4),
        "pr": round(pr, 4),
        "pa": round(pa, 4),
        "n_home": home_home["n"],
        "n_away": away_away["n"],
        "league_home_avg": round(league_home, 3),
        "league_away_avg": round(league_away, 3),
        "model": "bayesian",
    }


def blend_with_classic(
    bayesian: dict,
    classic: dict,
    w_bayesian: float = 0.5,
) -> dict:
    """
    Blend Bayesian and classic Poisson predictions.
    w_bayesian=0.5 → equal weight; 1.0 → full Bayesian.
    """
    w_c = 1.0 - w_bayesian
    return {
        "lambda_g": round(w_bayesian * bayesian["lambda_g"] + w_c * classic.get("lambda_g", bayesian["lambda_g"]), 4),
        "lambda_a": round(w_bayesian * bayesian["lambda_a"] + w_c * classic.get("lambda_a", bayesian["lambda_a"]), 4),
        "pw": round(w_bayesian * bayesian["pw"] + w_c * classic.get("pw", bayesian["pw"]), 4),
        "pr": round(w_bayesian * bayesian["pr"] + w_c * classic.get("pr", bayesian["pr"]), 4),
        "pa": round(w_bayesian * bayesian["pa"] + w_c * classic.get("pa", bayesian["pa"]), 4),
        "model": f"blend_{w_bayesian:.1f}b",
    }


def blend_dixon_coles(
    p_model: dict,
    g: str,
    a: str,
    df: pd.DataFrame,
    w_bayesian: float = 0.5,
) -> dict:
    """Blenduje ramie Dixon-Coles do p_model (TYLKO pw/pr/pp).

    p_model: dict {pw,pr,pp,...} w procentach 0-100 (z classic predict_match).
    DC zwraca pa (away win) jako ulamek 0-1 -> remap pa->pp + x100.
    Gdy DC zwroci None (za malo danych) -> p_model bez zmian (graceful, = baseline).
    Klucze spoza {pw,pr,pp} (np. bt/o25) NIE sa modyfikowane.
    Renormalizacja pw/pr/pp do 100 (zdarzenia rozlaczne i wyczerpujace).
    """
    bay = predict_match_bayesian(g, a, df)
    if not bay:
        return p_model

    p_bay = {"pw": bay["pw"] * 100.0, "pr": bay["pr"] * 100.0, "pp": bay["pa"] * 100.0}
    w_c = 1.0 - w_bayesian
    blended = {k: p_model[k] * w_c + p_bay[k] * w_bayesian for k in ("pw", "pr", "pp")}

    s = blended["pw"] + blended["pr"] + blended["pp"] or 1.0
    out = dict(p_model)  # zachowaj bt/o25 i pozostale klucze
    out["pw"] = round(blended["pw"] / s * 100.0, 4)
    out["pr"] = round(blended["pr"] / s * 100.0, 4)
    out["pp"] = round(blended["pp"] / s * 100.0, 4)
    return out
