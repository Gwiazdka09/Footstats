"""test_standings.py — rekonstrukcja tabeli ligowej (core/standings)."""
from __future__ import annotations

import pandas as pd
import pytest

from footstats.core.standings import build_table, season_start_year, table_asof


class TestSeasonStartYear:
    @pytest.mark.parametrize("wejscie,oczekiwane", [
        ("2016/17", 2016), ("2016/2017", 2016), ("2023/24", 2023),
        ("2012/2013", 2012), (2020, 2020), ("brak", None), ("", None), (None, None),
    ])
    def test_normalizacja(self, wejscie, oczekiwane) -> None:
        assert season_start_year(wejscie) == oczekiwane


def _mecze(rows: list[tuple]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["home", "away", "hg", "ag"])


class TestBuildTable:
    def test_punkty_i_pozycja(self) -> None:
        # A bije B 2-0; B remis C 1-1; A bije C 3-1
        df = _mecze([("A", "B", 2, 0), ("B", "C", 1, 1), ("A", "C", 3, 1)])
        t = build_table(df)
        # A: 2W=6pkt, B: 1R 1P=1pkt, C: 1R 1P=1pkt
        a = t[t["Druzyna"] == "A"].iloc[0]
        assert a["Pkt"] == 6 and a["M"] == 2 and a["Poz."] == 1
        assert t["Poz."].tolist() == [1, 2, 3]  # posortowane
        assert set(t["Druzyna"]) == {"A", "B", "C"}

    def test_gd_rozstrzyga_pozycje(self) -> None:
        # A i B po 3 pkt, ale A ma lepszy bilans bramek
        df = _mecze([("A", "X", 5, 0), ("B", "Y", 1, 0)])
        t = build_table(df)
        assert t.iloc[0]["Druzyna"] == "A"  # GD +5 > +1

    def test_pomija_mecze_bez_wyniku(self) -> None:
        df = _mecze([("A", "B", 2, 0), ("C", "D", None, None)])
        t = build_table(df)
        assert set(t["Druzyna"]) == {"A", "B"}  # C/D pominięte

    def test_pusty_zwraca_pusty(self) -> None:
        t = build_table(_mecze([]))
        assert t.empty and "Poz." in t.columns


class TestTableAsof:
    def test_filtruje_date_lige_sezon(self) -> None:
        df = pd.DataFrame({
            "league": ["L1", "L1", "L1", "L2"],
            "season": ["2023/24", "2023/2024", "2024/25", "2023/24"],
            "date": pd.to_datetime(["2024-01-01", "2024-02-01", "2024-08-01", "2024-01-01"]),
            "home": ["A", "A", "A", "Z"], "away": ["B", "C", "D", "W"],
            "hg": [1, 2, 0, 3], "ag": [0, 0, 0, 0],
        })
        # as-of 2024-03-01, L1, sezon 2023(/24 i /2024 scalone) → 2 mecze A
        t = table_asof(df, "L1", "2023/24", pd.Timestamp("2024-03-01"))
        a = t[t["Druzyna"] == "A"].iloc[0]
        assert a["M"] == 2 and a["Pkt"] == 6  # 2 wygrane, scalony sezon
        assert "Z" not in set(t["Druzyna"])  # inna liga
        assert "D" not in set(t["Druzyna"])  # inny sezon (2024/25)
