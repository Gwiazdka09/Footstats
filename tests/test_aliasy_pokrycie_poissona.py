"""Aliasy z kroku 2 odmrożenia: nazwy ze źródeł muszą trafiać w nazwy historii.

Audyt 2026-10-25: 154 z 398 meczów lig z whitelisty szło na fallback bzzoiro-ml,
bo `poisson._kanoniczne_nazwy` (celowo bez dopasowania rozmytego) nie znajdował
drużyny w zbiorze ("SG Dynamo Dresden" vs "Dresden"). Para = (nazwa źródła,
nazwa ze zbioru football-data). Bez sieci i bez bazy.
"""
from __future__ import annotations

import pandas as pd
import pytest

from footstats.core import poisson
from footstats.utils.normalize import normalize_team_name

PARY = [
    ("SG Dynamo Dresden", "Dresden"),
    ("SpVgg Greuther Fürth", "Greuther Furth"),
    ("Atlético Madrid", "Ath Madrid"),
    ("Athletic Club", "Ath Bilbao"),
    ("Levante UD", "Levante"),
    ("Olympique Lyonnais", "Lyon"),
    ("Stade de Reims", "Reims"),
    ("IF Elfsborg", "Elfsborg"),
    ("Sporting CP", "Sp Lisbon"),
    ("Beşiktaş JK", "Besiktas"),
    ("Urawa Red Diamonds", "Urawa Reds"),
    ("Pumas UNAM", "UNAM Pumas"),
    ("Flamengo", "Flamengo RJ"),
    ("CA Lanús", "Lanus"),
    ("LA Galaxy", "Los Angeles Galaxy"),
]


@pytest.mark.parametrize(("zrodlo", "zbior"), PARY)
def test_nazwa_zrodla_i_zbioru_maja_te_sama_postac(zrodlo: str, zbior: str) -> None:
    assert normalize_team_name(zrodlo) == normalize_team_name(zbior)


def test_kanoniczne_nazwy_znajduja_dresden_w_historii() -> None:
    df = pd.DataFrame({
        "gospodarz": ["Dresden", "Hertha"],
        "goscie": ["Hertha", "Dresden"],
        "data": pd.to_datetime(["2026-10-01", "2026-10-08"]),
        "league": ["GER-2. Bundesliga"] * 2,
    })
    g, a = poisson._kanoniczne_nazwy(df, "SG Dynamo Dresden", "Hertha BSC")
    assert (g, a) == ("Dresden", "Hertha")
