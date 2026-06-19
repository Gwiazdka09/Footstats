"""core/wf_harness.py — wierny produkcyjnie walk-forward harness (Cel A).

Replay statystycznego modelu (predict_match + Dixon-Coles + ensemble z devig
kursów historycznych) na danych z historical_loader. Offline, bez Neon, bez API.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

_COL_MAP = {"home": "gospodarz", "away": "goscie", "hg": "gole_g", "ag": "gole_a"}
_REQUIRED = ("home", "away", "hg", "ag")


def adapt_to_prod_schema(df: pd.DataFrame) -> pd.DataFrame:
    """Mapuje kolumny historical_loader → schema oczekiwana przez predict_match.

    Zwraca NOWY DataFrame (bez mutacji wejścia). Zachowuje date→data, league.
    """
    brak = [c for c in _REQUIRED if c not in df.columns]
    if brak:
        raise ValueError(f"adapt_to_prod_schema: brak wymaganych kolumn: {brak}")

    out = df.rename(columns=_COL_MAP).copy()
    if "date" in out.columns:
        out["data"] = out["date"]
    return out


def devig_1x2(odds_h, odds_d, odds_a) -> dict | None:
    """Z kursów 1X2 liczy prawdopodobieństwa implikowane bez marży (procenty 0-100).

    Metoda proporcjonalna (basic devig): p_i = (1/odds_i) / Σ(1/odds_j).
    Zwraca {pw, pr, pp} lub None gdy któryś kurs brakuje/nieprawidłowy.
    """
    vals = [odds_h, odds_d, odds_a]
    for o in vals:
        if o is None or (isinstance(o, float) and math.isnan(o)) or o is False or o <= 1.0:
            return None
    inv = [1.0 / o for o in vals]
    s = sum(inv)
    if s <= 0:
        return None
    return {
        "pw": round(inv[0] / s * 100, 1),
        "pr": round(inv[1] / s * 100, 1),
        "pp": round(inv[2] / s * 100, 1),
    }


@dataclass(frozen=True)
class ModelFlags:
    """Przełączniki warstw modelu do A/B. Domyślne = ścieżka produkcyjna."""
    use_bayesian: bool = False      # dołącz Dixon-Coles jako ramię modelu
    use_ensemble: bool = True       # blenduj z devig kursów (jak prod)
    use_calibration: bool = True    # load_calibration() w predict_match
    w_bayesian: float = 0.5         # waga ramienia bayesian w blendzie modelu


def _weighted_blend(a: dict, b: dict, wa: float, wb: float) -> dict:
    """Ważona średnia dwóch dictów {pw,pr,pp} (procenty). Renormalizacja do 100."""
    tot = wa + wb
    out = {k: (a[k] * wa + b[k] * wb) / tot for k in ("pw", "pr", "pp")}
    s = sum(out.values()) or 1.0
    return {k: round(v / s * 100, 4) for k, v in out.items()}


def predict_one(g, a, hist_prod, league, odds_h, odds_d, odds_a, flags) -> dict | None:
    """Pełna predykcja jednego meczu — wiernie wg produkcji.

    classic predict_match (xG OFF — replay) ⊕ opcjonalnie Dixon-Coles ⊕ devig kursów.
    Zwraca {tip, conf, pw, pr, pp, no_odds} (procenty) lub None gdy brak historii.
    """
    from footstats.core.poisson import predict_match
    from footstats.core.ensemble import ensemble_probs

    pred = predict_match(
        g, a, hist_prod,
        use_xg=False,                       # KRYTYCZNE: brak datetime.now() w replay
        use_calibration=flags.use_calibration,
    )
    if not pred:
        return None

    p_model = {"pw": pred["p_wygrana"], "pr": pred["p_remis"], "pp": pred["p_przegrana"]}

    # Ramię Dixon-Coles (opcjonalne)
    if flags.use_bayesian:
        from footstats.core.poisson_bayesian import predict_match_bayesian
        bay = predict_match_bayesian(g, a, hist_prod)
        if bay:
            p_bay = {"pw": bay["pw"] * 100, "pr": bay["pr"] * 100, "pp": bay["pa"] * 100}
            p_model = _weighted_blend(p_model, p_bay, 1.0 - flags.w_bayesian, flags.w_bayesian)

    # Ensemble z kursami (devig) — jak prod (poisson ⊕ bzzoiro)
    p_bzz = devig_1x2(odds_h, odds_d, odds_a)
    no_odds = p_bzz is None
    if flags.use_ensemble and p_bzz is not None:
        p_final = ensemble_probs(p_model, p_bzz, liga=league)
    else:
        p_final = p_model

    tip_map = {"pw": "1", "pr": "X", "pp": "2"}
    best_key = max(("pw", "pr", "pp"), key=lambda k: p_final[k])
    return {
        "tip": tip_map[best_key],
        "conf": round(p_final[best_key] / 100.0, 4),
        "pw": round(p_final["pw"], 1),
        "pr": round(p_final["pr"], 1),
        "pp": round(p_final["pp"], 1),
        "no_odds": no_odds,
    }
