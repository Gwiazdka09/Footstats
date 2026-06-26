"""M1 lever #5 — schedule-adjusted (opponent-adjusted) ratings.

Default OFF (env SCHEDULE_ADJUSTED_RATINGS); gdy ON, _oblicz_sile_wazona koryguje
atak/obronę siłą rywala. Walidacja flipu = offline walk-forward A/B (nie tu).
"""
import pandas as pd

from footstats.core.form import _oblicz_sile_wazona, _opponent_adjust


def _mecz(g, a, gg, ga, data="2026-01-01"):
    return {"gospodarz": g, "goscie": a, "gole_g": gg, "gole_a": ga, "data": data}


def test_strzelec_vs_silna_obrona_dostaje_wyzszy_atak():
    # A strzela 2 rywalowi z silną obroną (raw obrona=0.5) → 2/0.5=4.0 > raw 1.0
    df = pd.DataFrame([_mecz("A", "B", 2, 0)])
    sily = {"A": {"atak": 1.0, "obrona": 1.0}, "B": {"atak": 1.0, "obrona": 0.5}}
    out = _opponent_adjust(df, sily, srednia=1.0)
    assert out["A"]["atak"] == 4.0
    assert out["A"]["atak"] > sily["A"]["atak"]


def test_strzelec_vs_slaba_obrona_dostaje_nizszy_atak_niz_vs_silna():
    df = pd.DataFrame([_mecz("A", "B", 2, 0)])
    vs_silna = _opponent_adjust(df, {"A": {"atak": 1.0, "obrona": 1.0},
                                     "B": {"atak": 1.0, "obrona": 0.5}}, 1.0)
    vs_slaba = _opponent_adjust(df, {"A": {"atak": 1.0, "obrona": 1.0},
                                     "B": {"atak": 1.0, "obrona": 2.0}}, 1.0)
    assert vs_silna["A"]["atak"] > vs_slaba["A"]["atak"]


def test_obrona_korygowana_sila_ataku_rywala():
    # A traci 2 rywalowi ze słabym atakiem (raw atak=0.5) → 2/0.5=4.0 (gorsza obrona)
    df = pd.DataFrame([_mecz("A", "B", 0, 2)])
    out = _opponent_adjust(df, {"A": {"atak": 1.0, "obrona": 1.0},
                                "B": {"atak": 0.5, "obrona": 1.0}}, 1.0)
    assert out["A"]["obrona"] == 4.0


def test_rywal_obrona_zero_neutralne_1():
    # obrona rywala == 0 → guard `or 1.0` (brak dzielenia przez zero)
    df = pd.DataFrame([_mecz("A", "B", 2, 0)])
    out = _opponent_adjust(df, {"A": {"atak": 1.0, "obrona": 1.0},
                                "B": {"atak": 1.0, "obrona": 0.0}}, 1.0)
    assert out["A"]["atak"] == 2.0   # 2 / 1.0 (neutralne)


def test_nie_mutuje_wejscia():
    df = pd.DataFrame([_mecz("A", "B", 2, 0)])
    sily = {"A": {"atak": 1.0, "obrona": 1.0}, "B": {"atak": 1.0, "obrona": 0.5}}
    _opponent_adjust(df, sily, 1.0)
    assert sily["A"]["atak"] == 1.0   # oryginał nietknięty


def test_flaga_off_brak_korekty(monkeypatch):
    """Default OFF — _oblicz_sile_wazona zwraca raw (zero zmiany prod)."""
    monkeypatch.delenv("SCHEDULE_ADJUSTED_RATINGS", raising=False)
    df = pd.DataFrame([_mecz("A", "B", 3, 0), _mecz("B", "A", 0, 1),
                       _mecz("A", "C", 2, 1), _mecz("C", "A", 0, 0)])
    sily, _ = _oblicz_sile_wazona(df)
    # bez korekty atak = gole/srednia (raw) — sanity: A ma jakiś rating
    assert "A" in sily and sily["A"]["atak"] > 0


def test_flaga_on_zmienia_sily(monkeypatch):
    """ON — ratingi różnią się od raw (korekta zadziałała)."""
    df = pd.DataFrame([_mecz("A", "B", 3, 0), _mecz("B", "A", 0, 1),
                       _mecz("A", "C", 2, 1), _mecz("C", "A", 0, 0)])
    monkeypatch.delenv("SCHEDULE_ADJUSTED_RATINGS", raising=False)
    raw, _ = _oblicz_sile_wazona(df)
    monkeypatch.setenv("SCHEDULE_ADJUSTED_RATINGS", "1")
    adj, _ = _oblicz_sile_wazona(df)
    assert raw["A"]["atak"] != adj["A"]["atak"]
