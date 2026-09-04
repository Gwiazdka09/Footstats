"""Kolumny xG w ramce modelu — schemat definiuje loader, nie scalanie z AF.

`af_stats.scal_statystyki` ma w kontrakcie punkt "zadnych nowych kolumn" i to
jest dobra bramka: dokladanie kolumn przy DOPELNIANIU danych zmienialoby schemat
w miejscu, ktorego nikt o to nie prosi. Wiec `xg_home`/`xg_away` powstaja przy
ODCZYCIE datasetu, a AF je tylko wypelnia — tak jak `hst`/`ast`.

Parquet na dysku zostal zbudowany, zanim xG istnialo, wiec loader musi umiec
dolozyc brakujace kolumny opcjonalne bez ponownego pobierania calego zbioru.
"""
from __future__ import annotations

import pandas as pd
import pytest

from footstats.data import af_stats
from footstats.data.historical_loader import KOLUMNY_OPCJONALNE, uzupelnij_schemat


def test_uzupelnij_schemat_dodaje_brakujace_kolumny_jako_puste():
    df = pd.DataFrame({"home": ["A"], "away": ["B"], "hg": [1], "ag": [0]})
    out = uzupelnij_schemat(df)
    for kol in KOLUMNY_OPCJONALNE:
        assert kol in out.columns
        assert out[kol].isna().all()


def test_uzupelnij_schemat_nie_rusza_kolumn_ktore_sa():
    df = pd.DataFrame({"home": ["A"], "away": ["B"], "xg_home": [1.5], "xg_away": [0.3]})
    out = uzupelnij_schemat(df)
    assert out.loc[0, "xg_home"] == 1.5
    assert out.loc[0, "xg_away"] == 0.3


def test_uzupelnij_schemat_nie_mutuje_wejscia():
    df = pd.DataFrame({"home": ["A"], "away": ["B"]})
    uzupelnij_schemat(df)
    assert "xg_home" not in df.columns


def test_uzupelnij_schemat_zachowuje_wiersze_i_kolejnosc():
    df = pd.DataFrame({"home": list("ABCDE"), "away": list("VWXYZ")})
    out = uzupelnij_schemat(df)
    assert list(out["home"]) == list("ABCDE")
    assert list(out.index) == list(df.index)


def test_xg_jest_promowane_z_af():
    """Bez tego kolumny zostalyby puste i cala warstwa xG byla martwa."""
    assert "xg_home" in af_stats.KOLUMNY_PROMOWANE
    assert "xg_away" in af_stats.KOLUMNY_PROMOWANE


def test_scal_statystyki_wypelnia_xg_gdy_kolumny_juz_sa():
    df = pd.DataFrame({
        "date": [pd.Timestamp("2025-03-01")], "home": ["A"], "away": ["B"],
        "hst": [None], "ast": [None], "xg_home": [None], "xg_away": [None],
    })
    af = pd.DataFrame({
        "date": [pd.Timestamp("2025-03-01")], "home": ["A"], "away": ["B"],
        "hst": [4], "ast": [2], "xg_home": [1.7], "xg_away": [0.6],
    })
    out = af_stats.scal_statystyki(df, af)
    assert out.loc[0, "xg_home"] == 1.7
    assert out.loc[0, "xg_away"] == 0.6


def test_scal_statystyki_dalej_nie_tworzy_kolumn():
    """Bramka z kontraktu AF zostaje nietknieta — kolumn nie ma, wiec nie wchodza."""
    df = pd.DataFrame({
        "date": [pd.Timestamp("2025-03-01")], "home": ["A"], "away": ["B"],
        "hst": [None], "ast": [None],
    })
    af = pd.DataFrame({
        "date": [pd.Timestamp("2025-03-01")], "home": ["A"], "away": ["B"],
        "hst": [4], "ast": [2], "xg_home": [1.7], "xg_away": [0.6],
    })
    out = af_stats.scal_statystyki(df, af)
    assert "xg_home" not in out.columns


def test_load_cached_oddaje_ramke_z_xg():
    pytest.importorskip("pyarrow")
    from footstats.data.historical_loader import load_cached, sciezka_pelnego
    if not sciezka_pelnego().exists():
        pytest.skip("brak full_dataset.parquet")
    df = load_cached()
    assert {"xg_home", "xg_away"} <= set(df.columns)
    assert df["xg_home"].notna().sum() > 0, "kolumna jest, ale pusta — AF nie dopelnil"
