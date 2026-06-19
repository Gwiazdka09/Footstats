"""Testy core/poisson_bayesian.py — Bayesian update vs vanilla Poisson."""
import pytest
import pandas as pd

from footstats.core.poisson_bayesian import (
    _bayesian_shrink,
    _compute_ratings,
    _league_averages,
    blend_dixon_coles,
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


# ── blend_dixon_coles ──────────────────────────────────────────────────────

def test_blend_dc_none_returns_p_model_unchanged():
    """DC zwraca None (malo danych) -> p_model bez zmian (graceful = baseline)."""
    p_model = {"pw": 50.0, "pr": 30.0, "pp": 20.0, "bt": 55.0, "o25": 60.0}
    empty = pd.DataFrame(columns=["gospodarz", "goscie", "gole_g", "gole_a"])
    out = blend_dixon_coles(p_model, "X", "Y", empty, w_bayesian=0.5)
    assert out == p_model


def test_blend_dc_keeps_bt_o25_untouched():
    """DC nie liczy bt/o25 -> musza zostac z classic nietkniete."""
    p_model = {"pw": 50.0, "pr": 30.0, "pp": 20.0, "bt": 55.0, "o25": 60.0}
    out = blend_dixon_coles(p_model, "Bayern", "Dortmund", _fixture_df(), w_bayesian=0.5)
    assert out["bt"] == 55.0
    assert out["o25"] == 60.0


def test_blend_dc_renormalizes_1x2_to_100():
    """Po blendzie pw+pr+pp ~ 100 (zdarzenia rozlaczne, wyczerpujace)."""
    p_model = {"pw": 50.0, "pr": 30.0, "pp": 20.0, "bt": 55.0, "o25": 60.0}
    out = blend_dixon_coles(p_model, "Bayern", "Dortmund", _fixture_df(), w_bayesian=0.5)
    assert abs(out["pw"] + out["pr"] + out["pp"] - 100.0) < 0.01


def test_blend_dc_remaps_pa_to_pp_and_scales():
    """Remap pa->pp + x100: gdy DC daje silny away win, blend zwieksza pp wzgledem czystego classic."""
    # Historia: Goscie wygrywaja wyjazdy wysoko -> DC pa (away) wysoki.
    rows = []
    for _ in range(8):
        rows.append({"gospodarz": "Slaby", "goscie": "Mocny", "gole_g": 0, "gole_a": 3})
        rows.append({"gospodarz": "Mocny", "goscie": "Slaby", "gole_g": 3, "gole_a": 0})
    df = pd.DataFrame(rows)
    p_model = {"pw": 60.0, "pr": 25.0, "pp": 15.0, "bt": 40.0, "o25": 50.0}
    out = blend_dixon_coles(p_model, "Slaby", "Mocny", df, w_bayesian=1.0)  # pelny DC
    # Przy pelnym DC (w_bayesian=1.0) pp powinno odzwierciedlac sile gosci (pa->pp), > classic pp.
    assert out["pp"] > p_model["pp"]
    assert out["pw"] < p_model["pw"]


def test_blend_dc_deterministic_independent_of_system_date(monkeypatch):
    """Anty-lookahead: DC liczy tylko z dostarczonej historii, bez datetime.now().

    Podmiana daty systemowej NIE moze zmieniac predykcji (brak siegania po
    biezacy sezon/cache jak xG w predict_match).
    """
    p_model = {"pw": 45.0, "pr": 30.0, "pp": 25.0, "bt": 50.0, "o25": 55.0}
    df = _fixture_df()

    out1 = blend_dixon_coles(p_model, "Bayern", "Dortmund", df, w_bayesian=0.5)

    # Udawana zmiana "teraz" przez podmiane datetime w module (gdyby DC go uzywal).
    import footstats.core.poisson_bayesian as pb
    assert not hasattr(pb, "datetime"), "DC nie powinien importowac datetime (zrodlo lookahead)"

    out2 = blend_dixon_coles(p_model, "Bayern", "Dortmund", df, w_bayesian=0.5)
    assert out1 == out2  # determinizm


def test_blend_dc_ignores_future_match_not_in_history():
    """Mecz predykowany jest PRZYSZLY (nie ma go w df) -> brak leaku wlasnego wyniku.

    Dodanie przyszlego wyniku do historii ZMIENIA predykcje (bo to staje sie dana),
    co potwierdza ze DC korzysta WYLACZNIE z df (nie z zadnego ukrytego zrodla).
    """
    p_model = {"pw": 45.0, "pr": 30.0, "pp": 25.0}
    df_base = _fixture_df()
    out_base = blend_dixon_coles(p_model, "Bayern", "Dortmund", df_base, w_bayesian=1.0)

    extra = pd.concat([df_base, pd.DataFrame([
        {"gospodarz": "Bayern", "goscie": "Dortmund", "gole_g": 9, "gole_a": 0}
    ])], ignore_index=True)
    out_extra = blend_dixon_coles(p_model, "Bayern", "Dortmund", extra, w_bayesian=1.0)
    assert out_base != out_extra  # predykcja zalezy WYLACZNIE od dostarczonego df
