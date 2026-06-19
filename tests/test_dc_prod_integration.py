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
