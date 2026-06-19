"""core/wf_harness.py — wierny produkcyjnie walk-forward harness (Cel A).

Replay statystycznego modelu (predict_match + Dixon-Coles + ensemble z devig
kursów historycznych) na danych z historical_loader. Offline, bez Neon, bez API.
"""
from __future__ import annotations

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
