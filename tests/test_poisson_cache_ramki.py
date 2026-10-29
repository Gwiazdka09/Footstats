"""Cache `poisson.py` (mapa nazw, siły lig, świeżość, kraje) trzymany POZA `df.attrs`.

29.10 cProfile KROKU 1: 87% czasu `predict_match` to `copy.deepcopy` — pandas
kopiuje `attrs` przy każdej operacji tworzącej nową ramkę/serię, a w `attrs`
siedziała mapa nazw całej historii. KROK 1 `footstats-final` trwał ~1950 s
i job dobijał do timeoutu. Wyniki przed/po: 120 par, zero różnic.
"""
from __future__ import annotations

import gc

import pandas as pd

from footstats.core import poisson


def _ramka() -> pd.DataFrame:
    return pd.DataFrame({
        "gospodarz": ["Arsenal", "Chelsea", "Arsenal"],
        "goscie": ["Chelsea", "Arsenal", "Everton"],
        "gole_g": [2, 1, 3], "gole_a": [1, 1, 0],
        "data": pd.to_datetime(["2026-09-01", "2026-09-20", "2026-10-05"]),
        "league": ["ENG-Premier League"] * 3,
    })


def test_kanoniczne_nazwy_nie_pisza_do_attrs():
    df = _ramka()
    poisson._kanoniczne_nazwy(df, "Arsenal", "Chelsea")
    poisson._swieze_nazwy(df)
    poisson._kraje_nazwy(df)
    assert df.attrs == {}, "cache w attrs = deepcopy przy kazdej operacji pandas"


def test_cache_jest_wspolny_dla_tej_samej_ramki():
    df = _ramka()
    assert poisson._cache_ramki(df) is poisson._cache_ramki(df)


def test_wycinek_nie_dziedziczy_cache():
    # Wycinek to inna historia (np. walk-forward do daty) — cache rodzica
    # (siły lig z PEŁNEJ historii) w wycinku byłby zaglądaniem w przyszłość.
    df = _ramka()
    poisson._cache_ramki(df)["x"] = 1
    assert "x" not in poisson._cache_ramki(df[df["gole_g"] > 1])


def test_wpis_znika_razem_z_ramka():
    df = _ramka()
    klucz = id(df)
    poisson._cache_ramki(df)["x"] = 1
    del df
    gc.collect()
    assert klucz not in poisson._CACHE_RAMEK
