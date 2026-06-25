"""test_ml_features.py — inżynieria cech ML (no-lookahead, pi-ratings/elo/form)."""
from __future__ import annotations

import math

import pandas as pd
import pytest

from footstats.core.ml_features import build_features, FEATURE_COLS


def _df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _match(date, h, a, hg, ag, **extra):
    res = "H" if hg > ag else "A" if hg < ag else "D"
    return {"date": pd.Timestamp(date), "league": "L", "season": "2023/24",
            "home": h, "away": a, "hg": hg, "ag": ag, "result": res, **extra}


class TestBuildFeatures:
    def test_kolumny_i_target(self) -> None:
        df = _df([_match("2023-08-01", "A", "B", 2, 0), _match("2023-08-08", "B", "A", 1, 1)])
        f = build_features(df)
        for c in FEATURE_COLS + ["y", "date", "league"]:
            assert c in f.columns
        assert set(f["y"].unique()) <= {0, 1, 2}

    def test_no_lookahead_pierwszy_mecz_pusty_stan(self) -> None:
        """Pierwszy mecz: brak historii → forma NaN, pi=0, elo_diff=przewaga boiska."""
        df = _df([_match("2023-08-01", "A", "B", 3, 1)])
        f = build_features(df)
        r = f.iloc[0]
        assert math.isnan(r["h_gf5"]) and math.isnan(r["a_gf5"])  # zero historii
        assert r["pi_home"] == 0.0 and r["pi_away"] == 0.0        # ratingi startowe
        assert r["elo_diff"] == pytest.approx(65.0)               # tylko home advantage
        assert math.isnan(r["h_rest"])                            # brak poprzedniego meczu

    def test_forma_uwzglednia_tylko_przeszlosc(self) -> None:
        """Po 1. meczu A(strzelił 3) — w 2. meczu A.h_gf5 widzi tamten wynik, nie bieżący."""
        df = _df([
            _match("2023-08-01", "A", "B", 3, 0),
            _match("2023-08-08", "A", "C", 0, 5),  # bieżący NIE może wpłynąć na cechy tego meczu
        ])
        f = build_features(df).reset_index(drop=True)
        r2 = f.iloc[1]
        assert r2["h_gf5"] == pytest.approx(3.0)   # tylko mecz #1 (3 gole), nie #2 (0)
        assert r2["h_pts5"] == pytest.approx(3.0)  # wygrana #1

    def test_pi_rating_rosnie_po_wygranej(self) -> None:
        df = _df([
            _match("2023-08-01", "A", "B", 3, 0),
            _match("2023-09-01", "A", "B", 2, 0),
        ])
        f = build_features(df).reset_index(drop=True)
        # w 2. meczu pi_home[A] > 0 (po wygranej 3-0 w #1)
        assert f.iloc[1]["pi_home"] > 0
        # pi_diff (A dom vs B wyjazd) dodatnie — A silniejsze
        assert f.iloc[1]["pi_diff"] > 0

    def test_pomija_mecze_bez_wyniku(self) -> None:
        df = _df([_match("2023-08-01", "A", "B", 1, 0),
                  {"date": pd.Timestamp("2023-08-08"), "league": "L", "season": "2023/24",
                   "home": "C", "away": "D", "hg": None, "ag": None, "result": None}])
        f = build_features(df)
        assert len(f) == 1  # mecz bez wyniku pominięty
