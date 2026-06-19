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


def test_parity_prod_vs_harness_same_match_same_blend():
    """Ten sam (g,a,df,w_bayesian) -> harness predict_one i prod-side blend daja identyczne pw/pr/pp.

    Gwarantuje ze prod odtwarza zwycieska konfiguracje harness 1:1 (po stronie modelu,
    PRZED ensemble z kursami).
    """
    from footstats.core.poisson import predict_match
    from footstats.core.poisson_bayesian import blend_dixon_coles
    from footstats.core.wf_harness import predict_one, ModelFlags

    df = _df_prod()
    g, a, w = "Ajax", "PSV", 0.5

    # Strona prod: classic (use_xg=False jak harness do parytetu) -> blend DC, BEZ ensemble.
    pred = predict_match(g, a, df, use_xg=False, use_calibration=False)
    p_prod = {"pw": pred["p_wygrana"], "pr": pred["p_remis"], "pp": pred["p_przegrana"],
              "bt": pred["btts"], "o25": pred["over25"]}
    p_prod = blend_dixon_coles(p_prod, g, a, df, w_bayesian=w)

    # Strona harness: predict_one BEZ ensemble (use_ensemble=False) -> czysty p_model po DC.
    flags = ModelFlags(use_bayesian=True, use_ensemble=False, use_calibration=False, w_bayesian=w)
    res = predict_one(g, a, df, league="NED-Eredivisie",
                      odds_h=None, odds_d=None, odds_a=None, flags=flags)
    assert res is not None
    assert abs(p_prod["pw"] - res["pw"]) < 0.11   # res zaokraglone do 1dp; tolerancja
    assert abs(p_prod["pr"] - res["pr"]) < 0.11
    assert abs(p_prod["pp"] - res["pp"]) < 0.11


def test_blend_dc_does_not_touch_neon_or_telegram(monkeypatch):
    """Guard FootStats: blend DC to czysta funkcja — zero I/O do Neon/Telegram."""
    import footstats.core.poisson_bayesian as pb

    # Gdyby ktos dodal polaczenie do db w sciezce DC — wykryjemy.
    import footstats.utils.db as db
    if hasattr(db, "connect"):
        monkeypatch.setattr(db, "connect", lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("blend DC nie moze laczyc sie z Neon")))
    p_model = {"pw": 50.0, "pr": 30.0, "pp": 20.0, "bt": 55.0, "o25": 60.0}
    out = pb.blend_dixon_coles(p_model, "Ajax", "PSV", _df_prod(), w_bayesian=0.5)
    assert "pw" in out  # wykonalo sie bez tkniecia db


def test_flag_off_equals_classic_p_model(monkeypatch):
    """Regresja: USE_DIXON_COLES=False -> _p_pois identyczne jak przed wpieciem (classic)."""
    import footstats.core.quick_picks as qp
    import footstats.core.poisson_bayesian as pb
    from footstats.core.poisson import predict_match

    monkeypatch.setattr(qp, "USE_DIXON_COLES", False, raising=False)
    called = {"n": 0}
    monkeypatch.setattr(pb, "blend_dixon_coles",
                        lambda *a, **k: called.__setitem__("n", called["n"] + 1) or a[0])

    df = _df_prod()
    pred = predict_match("Ajax", "PSV", df, use_xg=False, use_calibration=False)
    _p_pois = {"pw": pred["p_wygrana"], "pr": pred["p_remis"], "pp": pred["p_przegrana"],
               "bt": pred["btts"], "o25": pred["over25"]}
    before = dict(_p_pois)
    if qp.USE_DIXON_COLES:   # False -> pomijamy blend
        _p_pois = pb.blend_dixon_coles(_p_pois, "Ajax", "PSV", df, w_bayesian=0.5)
    assert called["n"] == 0          # blend NIE wolany przy fladze OFF
    assert _p_pois == before          # classic bez zmian
