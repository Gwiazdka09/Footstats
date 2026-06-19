import pandas as pd
import pytest

from footstats.core.wf_harness import adapt_to_prod_schema


def test_adapt_to_prod_schema_maps_columns():
    df = pd.DataFrame([
        {"date": "2020-01-01", "league": "NED-Eredivisie", "home": "Ajax",
         "away": "PSV", "hg": 2, "ag": 1, "result": "H"},
    ])
    out = adapt_to_prod_schema(df)
    assert {"gospodarz", "goscie", "gole_g", "gole_a", "data"}.issubset(out.columns)
    assert out["gospodarz"].iloc[0] == "Ajax"
    assert out["goscie"].iloc[0] == "PSV"
    assert out["gole_g"].iloc[0] == 2
    assert out["gole_a"].iloc[0] == 1


def test_adapt_to_prod_schema_does_not_mutate_input():
    df = pd.DataFrame([{"date": "2020-01-01", "league": "X", "home": "A",
                        "away": "B", "hg": 1, "ag": 0, "result": "H"}])
    cols_before = list(df.columns)
    adapt_to_prod_schema(df)
    assert list(df.columns) == cols_before


def test_adapt_to_prod_schema_missing_column_raises():
    df = pd.DataFrame([{"home": "A", "away": "B"}])
    with pytest.raises(ValueError, match="brak"):
        adapt_to_prod_schema(df)
