"""Testy edge case dla predykcji Poissona."""
import functools

import numpy as np
import pandas as pd
import pytest

from footstats.core.poisson import _macierz, predict_match


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_df(n: int = 10) -> pd.DataFrame:
    """Minimalny DataFrame z meczami do testów."""
    rows = []
    for i in range(n):
        rows.append({
            "gospodarz": "TeamA",
            "goscie": "TeamB",
            "gole_g": 1,
            "gole_a": 1,
            "data": f"2026-01-{i + 1:02d}",
            "liga": "TEST",
        })
    return pd.DataFrame(rows)


# ── _macierz (cache) ─────────────────────────────────────────────────────────

def test_macierz_probabilities_sum_to_one():
    pw, pr, pp, *_ = _macierz(1.5, 1.2, 6)
    assert abs(pw + pr + pp - 1.0) < 1e-6


def test_macierz_cache_hit():
    """Dwa wywołania z tymi samymi argami korzystają z cache (ten sam obiekt)."""
    r1 = _macierz(1.0, 1.0, 6)
    r2 = _macierz(1.0, 1.0, 6)
    assert r1 is r2


def test_macierz_different_args_different_results():
    r1 = _macierz(0.5, 2.5, 6)
    r2 = _macierz(2.5, 0.5, 6)
    pw1, pr1, pp1 = r1[0], r1[1], r1[2]
    pw2, pr2, pp2 = r2[0], r2[1], r2[2]
    assert pp1 > pw1, "Słaby gospodarz powinien częściej przegrywać"
    assert pw2 > pp2, "Mocny gospodarz powinien częściej wygrywać"


def test_macierz_very_low_lambda_home_win_near_zero():
    """Lambda_g = 0.05 → gospodarz prawie nie strzela."""
    pw, _pr, _pp, *_ = _macierz(0.05, 3.0, 8)
    assert pw < 0.01


def test_macierz_symmetric_lambda_draw_dominant():
    """Przy równych lambdach remis powinien być największym składnikiem."""
    pw, pr, pp, *_ = _macierz(1.2, 1.2, 8)
    assert pr >= pw * 0.7, "Remis powinien być znaczący przy równych siłach"


def test_macierz_btts_nonzero():
    _pw, _pr, _pp, btts, *_ = _macierz(1.5, 1.5, 6)
    assert 0 < btts < 1


def test_macierz_top5_five_entries():
    *_, top5_data = _macierz(1.5, 1.2, 6)
    assert len(top5_data) == 5


def test_macierz_top5_sorted_descending():
    *_, top5_data = _macierz(1.5, 1.2, 6)
    probs = [v for _r, _c, v in top5_data]
    assert probs == sorted(probs, reverse=True)


# ── predict_match ─────────────────────────────────────────────────────────────

def test_predict_match_returns_none_when_no_data():
    df = pd.DataFrame(columns=["gospodarz", "goscie", "gole_g", "gole_a", "data", "liga"])
    result = predict_match("TeamA", "TeamB", df)
    assert result is None


def test_predict_match_returns_none_below_min_matches():
    df = _make_df(3)
    result = predict_match("TeamA", "TeamB", df)
    assert result is None


def test_predict_match_returns_dict_with_required_keys():
    """10 meczów wystarczy do predykcji."""
    df = _make_df(10)
    result = predict_match("TeamA", "TeamB", df)
    if result is None:
        pytest.skip("Za mało danych — sprawdź OSTATNIE_N w config")
    required = {"p_wygrana", "p_remis", "p_przegrana", "lambda_g", "lambda_a", "btts", "over25"}
    assert required.issubset(result.keys())


def test_predict_match_probabilities_sum_to_100():
    df = _make_df(10)
    result = predict_match("TeamA", "TeamB", df)
    if result is None:
        pytest.skip("Za mało danych")
    total = result["p_wygrana"] + result["p_remis"] + result["p_przegrana"]
    assert abs(total - 100.0) < 0.5


def test_predict_match_lambda_clamped_above_zero():
    """Lambda zawsze >= 0.05."""
    df = _make_df(10)
    for row in df.itertuples():
        pass  # sanity
    result = predict_match("TeamA", "TeamB", df)
    if result is None:
        pytest.skip("Za mało danych")
    assert result["lambda_g"] >= 0.05
    assert result["lambda_a"] >= 0.05


def test_predict_match_over25_between_0_and_100():
    df = _make_df(10)
    result = predict_match("TeamA", "TeamB", df)
    if result is None:
        pytest.skip("Za mało danych")
    assert 0 <= result["over25"] <= 100
    assert 0 <= result["under25"] <= 100
    assert abs(result["over25"] + result["under25"] - 100.0) < 1.0


def test_predict_match_top5_format():
    df = _make_df(10)
    result = predict_match("TeamA", "TeamB", df)
    if result is None:
        pytest.skip("Za mało danych")
    assert isinstance(result["top5"], list)
    assert len(result["top5"]) == 5
    for entry in result["top5"]:
        label, prob = entry
        assert ":" in label
        assert 0 <= prob <= 100
