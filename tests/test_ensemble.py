import pytest

from footstats.core.ensemble import ensemble_probs, get_roznica, get_weights_for_league


_P_POISSON = {"win": 0.55, "draw": 0.25, "loss": 0.20, "over25": 0.65}
_P_BZZ     = {"win": 0.50, "draw": 0.28, "loss": 0.22, "over25": 0.70}


def test_ensemble_default_weights_sum_to_one():
    result = ensemble_probs(_P_POISSON, _P_BZZ)
    assert abs(result["win"] + result["draw"] + result["loss"] - 1.0) < 0.01


def test_ensemble_with_default_weights_between_models():
    result = ensemble_probs(_P_POISSON, _P_BZZ)
    assert _P_POISSON["win"] <= result["win"] <= _P_BZZ["win"] or \
           _P_BZZ["win"] <= result["win"] <= _P_POISSON["win"]


def test_ensemble_custom_weights():
    wagi = {"poisson": 1.0, "bzzoiro": 0.0}
    result = ensemble_probs(_P_POISSON, _P_BZZ, wagi=wagi)
    assert abs(result["win"] - _P_POISSON["win"]) < 0.001


def test_ensemble_bzzoiro_only():
    wagi = {"poisson": 0.0, "bzzoiro": 1.0}
    result = ensemble_probs(_P_POISSON, _P_BZZ, wagi=wagi)
    assert abs(result["win"] - _P_BZZ["win"]) < 0.001


def test_ensemble_missing_key_in_bzzoiro():
    p_bzz_partial = {"win": 0.50, "draw": 0.28, "loss": 0.22}
    result = ensemble_probs(_P_POISSON, p_bzz_partial)
    assert "over25" in result
    assert abs(result["over25"] - _P_POISSON["over25"]) < 0.001


def test_ensemble_both_empty_returns_empty():
    result = ensemble_probs({}, {})
    assert result == {}


def test_get_roznica_detects_disagreement():
    p_e = {"win": 0.52, "draw": 0.26, "loss": 0.22}
    rozn = get_roznica(p_e, _P_POISSON, _P_BZZ)
    assert isinstance(rozn, float)
    assert rozn >= 0


def test_get_roznica_identical_models_is_zero():
    rozn = get_roznica(_P_POISSON, _P_POISSON, _P_POISSON)
    assert rozn < 0.01


# ── Flaga ENSEMBLE_MARKET_WEIGHT (reweight ku rynkowi, default OFF) ──────────────

def test_env_market_weight_nieustawiony_zachowuje_default(monkeypatch):
    """Brak env → zero zmiany prod (per-league / default 70/30)."""
    monkeypatch.delenv("ENSEMBLE_MARKET_WEIGHT", raising=False)
    w = get_weights_for_league(None)
    assert abs(w["poisson"] - 0.70) < 1e-9 and abs(w["bzzoiro"] - 0.30) < 1e-9


def test_env_market_weight_override(monkeypatch):
    """ENSEMBLE_MARKET_WEIGHT=0.70 → 30/70 (model/rynek), nadrzędne nad per-league."""
    monkeypatch.setenv("ENSEMBLE_MARKET_WEIGHT", "0.70")
    w = get_weights_for_league("ENG-Premier League")
    assert abs(w["bzzoiro"] - 0.70) < 1e-9 and abs(w["poisson"] - 0.30) < 1e-9


def test_env_market_weight_zmienia_blend(monkeypatch):
    """Override realnie przesuwa wynik ensemble ku rynkowi (bzzoiro)."""
    monkeypatch.setenv("ENSEMBLE_MARKET_WEIGHT", "0.85")
    r = ensemble_probs(_P_POISSON, _P_BZZ)
    assert abs(r["win"] - _P_BZZ["win"]) < abs(r["win"] - _P_POISSON["win"])  # bliżej rynku


@pytest.mark.parametrize("bad", ["", "abc", "1.5", "-0.2"])
def test_env_market_weight_niepoprawny_ignorowany(monkeypatch, bad):
    """Pusty/zły/poza [0,1] → ignorowany, fallback do default 70/30."""
    monkeypatch.setenv("ENSEMBLE_MARKET_WEIGHT", bad)
    w = get_weights_for_league(None)
    assert abs(w["poisson"] - 0.70) < 1e-9 and abs(w["bzzoiro"] - 0.30) < 1e-9
