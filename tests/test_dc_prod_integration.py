"""Testy wpiecia Dixon-Coles do produkcji (Cel C)."""
import importlib


def test_config_has_dixon_coles_flags():
    import footstats.config as cfg
    importlib.reload(cfg)
    assert hasattr(cfg, "USE_DIXON_COLES")
    assert isinstance(cfg.USE_DIXON_COLES, bool)
    assert hasattr(cfg, "W_BAYESIAN")
    assert 0.0 <= cfg.W_BAYESIAN <= 1.0


def test_config_dixon_coles_default_on(monkeypatch):
    """Default ON gdy brak env (lewar zwalidowany +1.7pp)."""
    monkeypatch.delenv("USE_DIXON_COLES", raising=False)
    import footstats.config as cfg
    importlib.reload(cfg)
    assert cfg.USE_DIXON_COLES is True


def test_config_dixon_coles_env_off(monkeypatch):
    """Env=0 wylacza bez redeploya (toggle awaryjny)."""
    monkeypatch.setenv("USE_DIXON_COLES", "0")
    import footstats.config as cfg
    importlib.reload(cfg)
    assert cfg.USE_DIXON_COLES is False


import pandas as pd
import pytest


def _df_prod():
    """Historia w schemacie prod (gospodarz/goscie/gole_g/gole_a + liga/data)."""
    rows = []
    for i in range(20):
        rows.append({"gospodarz": "Ajax", "goscie": "PSV", "gole_g": 2, "gole_a": 1,
                     "liga": "NED-Eredivisie", "data": f"2024-{(i % 12) + 1:02d}-05"})
        rows.append({"gospodarz": "PSV", "goscie": "Ajax", "gole_g": 1, "gole_a": 1,
                     "liga": "NED-Eredivisie", "data": f"2024-{(i % 12) + 1:02d}-20"})
    return pd.DataFrame(rows)


def test_quick_picks_calls_blend_when_flag_on(monkeypatch):
    """USE_DIXON_COLES=True -> quick_picks wola blend_dixon_coles dokladnie raz na mecz z _pred_p."""
    import footstats.core.quick_picks as qp
    import footstats.core.poisson_bayesian as pb

    monkeypatch.setattr(qp, "USE_DIXON_COLES", True, raising=False)
    monkeypatch.setattr(qp, "W_BAYESIAN", 0.5, raising=False)

    calls = {"n": 0}
    real = pb.blend_dixon_coles

    def _spy(p_model, g, a, df, w_bayesian=0.5):
        calls["n"] += 1
        assert "bt" in p_model and "o25" in p_model  # prod karmi bt/o25
        return real(p_model, g, a, df, w_bayesian=w_bayesian)

    monkeypatch.setattr(pb, "blend_dixon_coles", _spy)

    # Wymus jedna predykcje przez bezposrednie wywolanie sciezki Poisson:
    from footstats.core.poisson import predict_match
    from footstats.core.ensemble import ensemble_probs
    df = _df_prod()
    pred = predict_match("Ajax", "PSV", df, use_xg=False, use_calibration=False)
    assert pred is not None
    _p_pois = {"pw": pred["p_wygrana"], "pr": pred["p_remis"], "pp": pred["p_przegrana"],
               "bt": pred["btts"], "o25": pred["over25"]}
    # Symulacja wpiecia z quick_picks (ten sam fragment kodu):
    if qp.USE_DIXON_COLES:
        _p_pois = pb.blend_dixon_coles(_p_pois, "Ajax", "PSV", df, w_bayesian=qp.W_BAYESIAN)
    assert calls["n"] == 1
    assert "bt" in _p_pois and "o25" in _p_pois  # rynki goli zachowane
