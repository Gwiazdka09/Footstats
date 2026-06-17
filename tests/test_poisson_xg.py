"""
test_poisson_xg.py — FAZA λ: blend xG uwzględnia obronę rywala (xGA), nie tylko atak.
Słabsza obrona gościa (wyższe xga_avg) → wyższe λ gospodarza.
"""
import pandas as pd
import pytest

from footstats.core import poisson as P


def _df():
    """Minimalna historia: A i B grają naprzemiennie, ~10 meczów każdy."""
    rows = []
    for i in range(12):
        # A u siebie strzela 1-2, B u siebie 1
        rows.append({"gospodarz": "A", "goscie": f"X{i}", "gole_g": 2, "gole_a": 1,
                     "data": f"2026-01-{i+1:02d}"})
        rows.append({"gospodarz": "B", "goscie": f"Y{i}", "gole_g": 1, "gole_a": 1,
                     "data": f"2026-02-{i+1:02d}"})
        rows.append({"gospodarz": f"X{i}", "goscie": "B", "gole_g": 1, "gole_a": 1,
                     "data": f"2026-03-{i+1:02d}"})
    return pd.DataFrame(rows)


def _lambda_g(monkeypatch, a_xga: float) -> float:
    """Zwraca lambda_g z predict_match przy danym xga gościa (B)."""
    cache = {
        "a": {"xg_for_avg": 1.6, "xga_avg": 1.0},   # gospodarz A
        "b": {"xg_for_avg": 1.2, "xga_avg": a_xga},  # gość B — zmienna obrona
    }
    monkeypatch.setattr(P, "_to_slug", lambda name: name.lower(), raising=False)

    def _fake_cache_get(slug, season):
        return cache.get(slug)

    # podmień import wewnątrz funkcji: patchujemy moduł understat_xg
    import footstats.scrapers.understat_xg as ux
    monkeypatch.setattr(ux, "_cache_get", _fake_cache_get)
    monkeypatch.setattr(ux, "_to_slug", lambda name: name.lower())

    pred = P.predict_match("A", "B", _df())
    assert pred is not None
    return pred["lambda_g"]


def test_slabsza_obrona_goscia_podnosi_lambda_gospodarza(monkeypatch):
    lg_dobra_obrona = _lambda_g(monkeypatch, a_xga=0.6)   # B broni dobrze
    lg_slaba_obrona = _lambda_g(monkeypatch, a_xga=2.2)   # B broni słabo
    assert lg_slaba_obrona > lg_dobra_obrona


def test_predict_match_zwraca_lambdy(monkeypatch):
    lg = _lambda_g(monkeypatch, a_xga=1.0)
    assert lg > 0
