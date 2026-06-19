"""core/wf_harness.py — wierny produkcyjnie walk-forward harness (Cel A).

Replay statystycznego modelu (predict_match + Dixon-Coles + ensemble z devig
kursów historycznych) na danych z historical_loader. Offline, bez Neon, bez API.
"""
from __future__ import annotations

import math

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
