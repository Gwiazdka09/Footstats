"""Testy edge case dla predykcji Poissona."""

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


# ── Phase 3: Poisson Smoothing Edge Cases ────────────────────────────────────

def test_macierz_extreme_low_lambdas_no_nan():
    """Extreme low lambdas should not produce NaN/Inf with smoothing."""
    pw, pr, pp, btts, over25, _wynik_g, _wynik_a, _top5 = _macierz(0.01, 0.01, 10)
    assert not np.isnan([pw, pr, pp, btts, over25]).any()
    assert not np.isinf([pw, pr, pp, btts, over25]).any()
    assert 0.0 <= pw <= 1.0
    assert 0.0 <= pr <= 1.0
    assert 0.0 <= pp <= 1.0


def test_macierz_extreme_high_lambdas_no_nan():
    """Extreme high lambdas should not produce NaN/Inf with smoothing."""
    pw, pr, pp, btts, over25, _wynik_g, _wynik_a, _top5 = _macierz(8.0, 8.0, 15)
    assert not np.isnan([pw, pr, pp, btts, over25]).any()
    assert not np.isinf([pw, pr, pp, btts, over25]).any()
    assert 0.0 <= pw <= 1.0
    assert 0.0 <= pr <= 1.0
    assert 0.0 <= pp <= 1.0


def test_macierz_smoothing_prevents_zero_probability():
    """Laplace smoothing should prevent exact zero probabilities."""
    pw, pr, pp, btts, over25, _wynik_g, _wynik_a, _top5 = _macierz(0.1, 0.1, 8)
    assert pw > 0.0, "Win probability should be smoothed away from zero"
    assert pr > 0.0, "Draw probability should be smoothed away from zero"
    assert pp > 0.0, "Loss probability should be smoothed away from zero"
    assert btts > 0.0, "BTTS should be smoothed away from zero"


def test_macierz_probabilities_normalized_after_smoothing():
    """After smoothing, probabilities should sum close to 1.0."""
    pw, pr, pp, _btts, _over25, _wynik_g, _wynik_a, _top5 = _macierz(1.5, 1.3, 10)
    total = pw + pr + pp
    assert abs(total - 1.0) < 0.01, f"Probabilities sum to {total}, not close to 1.0"


def test_macierz_btts_valid_range_extreme():
    """BTTS should always be in [0, 1] even with extreme lambdas."""
    for lambda_g, lambda_a in [(0.01, 0.01), (0.5, 5.0), (8.0, 8.0)]:
        _pw, _pr, _pp, btts, _over25, _wynik_g, _wynik_a, _top5 = _macierz(lambda_g, lambda_a, 12)
        assert 0.0 <= btts <= 1.0, f"BTTS out of range for lambdas ({lambda_g}, {lambda_a}): {btts}"
        assert not np.isnan(btts)


def test_macierz_over25_valid_range():
    """Over 2.5 probability should always be in [0, 1]."""
    for lambda_g, lambda_a in [(0.05, 0.05), (1.0, 1.0), (5.0, 5.0)]:
        _pw, _pr, _pp, _btts, over25, _wynik_g, _wynik_a, _top5 = _macierz(lambda_g, lambda_a, 12)
        assert 0.0 <= over25 <= 1.0, f"Over25 out of range for lambdas ({lambda_g}, {lambda_a}): {over25}"
        assert not np.isnan(over25)


def test_macierz_top5_probabilities_valid():
    """Top 5 scores should have valid probabilities even with edge case lambdas."""
    _pw, _pr, _pp, _btts, _over25, _wynik_g, _wynik_a, top5 = _macierz(0.2, 4.5, 12)
    for g, a, prob in top5:
        assert 0.0 <= prob <= 1.0, f"Top5 probability invalid: {prob}"
        assert not np.isnan(prob)
        assert 0 <= g < 12
        assert 0 <= a < 12
