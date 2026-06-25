"""
core/standings.py — rekonstrukcja tabeli ligowej z wyników (as-of-date, no-lookahead).

Liczy tabelę (punkty 3/1/0, pozycja wg Pkt → GD → GF) z meczów rozegranych w obrębie
ligi+sezonu. Działa offline z historii (backtest ImportanceIndex) i live (z bieżących
wyników), bez zależności od zewnętrznego API standings.

Zwraca DataFrame zgodny z `core.importance.ImportanceIndex` (kolumny Druzyna/Poz./M).
"""
from __future__ import annotations

import pandas as pd

_PKT_KOLUMNY = ["Druzyna", "M", "Pkt", "GF", "GA", "GD", "Poz."]


def season_start_year(season: object) -> int | None:
    """Normalizuje etykietę sezonu do roku startowego ('2016/17' i '2016/2017' → 2016).

    Łączy duplikaty etykiet sezonów z różnych źródeł (te same mecze pod różnym formatem).
    """
    s = str(season).strip()
    if len(s) >= 4 and s[:4].isdigit():
        return int(s[:4])
    return None


def build_table(matches: pd.DataFrame) -> pd.DataFrame:
    """Buduje tabelę z meczów (kolumny wymagane: home, away, hg, ag). Punkty 3/1/0.

    Mecze bez wyniku (NaN w hg/ag) są pomijane. Zwraca DataFrame posortowany
    malejąco wg (Pkt, GD, GF) z kolumną Poz. (1 = lider). Pusty gdy brak meczów.
    """
    rekordy: dict[str, dict] = {}

    def _ensure(team: str) -> None:
        if team not in rekordy:
            rekordy[team] = {"Druzyna": team, "M": 0, "Pkt": 0, "GF": 0, "GA": 0}

    for r in matches.itertuples(index=False):
        hg, ag = r.hg, r.ag
        if pd.isna(hg) or pd.isna(ag):
            continue
        hg, ag = int(hg), int(ag)
        h, a = r.home, r.away
        _ensure(h)
        _ensure(a)
        rekordy[h]["M"] += 1
        rekordy[a]["M"] += 1
        rekordy[h]["GF"] += hg
        rekordy[h]["GA"] += ag
        rekordy[a]["GF"] += ag
        rekordy[a]["GA"] += hg
        if hg > ag:
            rekordy[h]["Pkt"] += 3
        elif hg < ag:
            rekordy[a]["Pkt"] += 3
        else:
            rekordy[h]["Pkt"] += 1
            rekordy[a]["Pkt"] += 1

    if not rekordy:
        return pd.DataFrame(columns=_PKT_KOLUMNY)

    df = pd.DataFrame(list(rekordy.values()))
    df["GD"] = df["GF"] - df["GA"]
    df = df.sort_values(["Pkt", "GD", "GF"], ascending=False).reset_index(drop=True)
    df["Poz."] = range(1, len(df) + 1)
    return df[_PKT_KOLUMNY]


def table_asof(
    df: pd.DataFrame,
    league: str,
    season,
    as_of_date,
    date_col: str = "date",
) -> pd.DataFrame:
    """Tabela ligi+sezonu wg stanu PRZED `as_of_date` (no-lookahead).

    Filtruje `df` do meczów tej ligi i sezonu (po roku startowym) z datą < as_of_date,
    następnie buduje tabelę. Pusta gdy brak meczów przed datą.
    """
    rok = season_start_year(season)
    maska = (df["league"] == league) & (df[date_col] < as_of_date)
    sub = df[maska]
    if rok is not None and "season" in df.columns:
        sub = sub[sub["season"].map(season_start_year) == rok]
    return build_table(sub)
