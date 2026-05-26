"""Testy core/poisson_bayesian.py — Bayesian update vs vanilla Poisson."""
import pytest
import pandas as pd

from footstats.core.poisson_bayesian import (
    _bayesian_shrink,
    _compute_ratings,
    _league_averages,
    blend_with_classic,
    predict_match_bayesian,
)


def _fixture_df() -> pd.DataFrame:
    rows = []
    for _ in range(6):
        rows.append({"gospodarz": "Bayern", "goscie": "Dortmund", "gole_g": 2, "gole_a": 1})
        rows.append({"gospodarz": "Dortmund", "goscie": "Bayern", "gole_g": 1, "gole_a": 2})
    return pd.DataFrame(rows)


# ── _bayesian_shrink ──────────────────────────────────────────────────────

def test_shrink_no_data_returns_prior():
    assert _bayesian_shrink(0.0, 0, 1.5) == pytest.approx(1.5)


def test_shrink_large_n_approaches_observed():
    result = _bayesian_shrink(2.0, 1000, 1.5)
    assert result == pytest.approx(2.0, abs=0.05)


def test_shrink_balanced():
    # n=3 (_PRIOR_WEIGHT=3): (3*2.0 + 3*0.5) / (3+3) = 1.25
    assert _bayesian_shrink(2.0, 3, 0.5) == pytest.approx(1.25)


# ── _league_averages ──────────────────────────────────────────────────────

def test_league_averages_empty_returns_defaults():
    result = _league_averages(pd.DataFrame())
    assert result["home_avg"] == pytest.approx(1.5)
    assert result["away_avg"] == pytest.approx(1.1)


def test_league_averages_computed():
    df = pd.DataFrame([{"gole_g": 2, "gole_a": 1}, {"gole_g": 0, "gole_a": 0}])
    result = _league_averages(df)
    assert result["home_avg"] == pytest.approx(1.0)
    assert result["away_avg"] == pytest.approx(0.5)


def test_league_averages_clamped_at_half():
    df = pd.DataFrame([{"gole_g": 0, "gole_a": 0}])
    result = _league_averages(df)
    assert result["home_avg"] == pytest.approx(0.5)
    assert result["away_avg"] == pytest.approx(0.5)


# ── _compute_ratings ──────────────────────────────────────────────────────

def test_compute_ratings_unknown_team():
    df = _fixture_df()
    result = _compute_ratings("Hannover", df, is_home=True)
    assert result["n"] == 0
    assert result["att"] is None


def test_compute_ratings_home_attack():
    df = pd.DataFrame([
        {"gospodarz": "Bayern", "goscie": "A", "gole_g": 3, "gole_a": 0},
        {"gospodarz": "Bayern", "goscie": "B", "gole_g": 1, "gole_a": 2},
    ])
    result = _compute_ratings("Bayern", df, is_home=True)
    assert result["n"] == 2
    assert result["att"] > 0


def test_compute_ratings_away():
    df = pd.DataFrame([
        {"gospodarz": "A", "goscie": "Dortmund", "gole_g": 1, "gole_a": 2},
    ])
    result = _compute_ratings("Dortmund", df, is_home=False)
    assert result["n"] == 1
    assert result["att"] == pytest.approx(2.0)


# ── predict_match_bayesian ────────────────────────────────────────────────

def test_predict_returns_dict():
    result = predict_match_bayesian("Bayern", "Dortmund", _fixture_df())
    assert result is not None
    assert "pw" in result and "pr" in result and "pa" in result
    assert result["model"] == "bayesian"


def test_predict_probs_sum_to_one():
    result = predict_match_bayesian("Bayern", "Dortmund", _fixture_df())
    assert result["pw"] + result["pr"] + result["pa"] == pytest.approx(1.0, abs=0.01)


def test_predict_home_advantage_increases_lambda_g():
    df = _fixture_df()
    r_high = predict_match_bayesian("Bayern", "Dortmund", df, home_advantage=1.3)
    r_low  = predict_match_bayesian("Bayern", "Dortmund", df, home_advantage=0.9)
    assert r_high["lambda_g"] > r_low["lambda_g"]


def test_predict_unknown_team_returns_none():
    assert predict_match_bayesian("Hannover", "Dortmund", _fixture_df()) is None


def test_predict_empty_df_returns_none():
    assert predict_match_bayesian("Bayern", "Dortmund", pd.DataFrame()) is None


def test_predict_lambdas_positive():
    result = predict_match_bayesian("Bayern", "Dortmund", _fixture_df())
    assert result["lambda_g"] > 0
    assert result["lambda_a"] > 0


# ── blend_with_classic ────────────────────────────────────────────────────

_BAY = {"lambda_g": 2.0, "lambda_a": 1.0, "pw": 0.5, "pr": 0.3, "pa": 0.2}
_CLS = {"lambda_g": 1.0, "lambda_a": 0.5, "pw": 0.3, "pr": 0.4, "pa": 0.3}


def test_blend_equal_weights():
    result = blend_with_classic(_BAY, _CLS, w_bayesian=0.5)
    assert result["lambda_g"] == pytest.approx(1.5)
    assert result["pw"] == pytest.approx(0.4)
    assert "0.5b" in result["model"]


def test_blend_full_bayesian():
    result = blend_with_classic(_BAY, _CLS, w_bayesian=1.0)
    assert result["pw"] == pytest.approx(0.5)
    assert result["lambda_g"] == pytest.approx(2.0)


def test_blend_full_classic():
    result = blend_with_classic(_BAY, _CLS, w_bayesian=0.0)
    assert result["pw"] == pytest.approx(0.3)
    assert result["lambda_g"] == pytest.approx(1.0)
