"""
test_injury_goalshare_wiring.py — Faza 1 wpięcie: _apply_injury_corrections używa
goal_share z player_db. Utrata topowego strzelca (share 0.5) obniża λ/pw mocniej
niż rezerwowy (share 0.02). Brak danych → flat fallback (non-breaking, v1).
"""
from footstats.core import daily_phases

_BASE = {"gospodarz": "City", "goscie": "B", "pw": 45.0, "pr": 27.0, "pp": 28.0,
         "o25": 55.0, "bt": 52.0}


def test_star_injury_hits_harder_than_sub(monkeypatch):
    monkeypatch.setattr(daily_phases, "_goal_shares_for",
                        lambda team, side=None: {"Star": 0.5, "Sub": 0.02})

    w_star = dict(_BASE, injuries_home=[{"position": "F", "name": "Star"}], injuries_away=[])
    w_sub = dict(_BASE, injuries_home=[{"position": "F", "name": "Sub"}], injuries_away=[])
    daily_phases._apply_injury_corrections([w_star])
    daily_phases._apply_injury_corrections([w_sub])

    # utrata gwiazdy → większy spadek pw niż utrata rezerwowego
    assert w_star["pw"] < w_sub["pw"]
    assert w_star["pw"] < _BASE["pw"]


def test_no_player_data_flat_fallback(monkeypatch):
    # brak goal_share (pusty) → zachowanie v1 (flat), nie wywala
    monkeypatch.setattr(daily_phases, "_goal_shares_for", lambda team, side=None: {})
    w = dict(_BASE, injuries_home=[{"position": "F", "name": "X"}], injuries_away=[])
    daily_phases._apply_injury_corrections([w])
    assert w["pw"] < _BASE["pw"]  # nadal spada (flat kara)
    assert abs((w["pw"] + w["pr"] + w["pp"]) - 100.0) < 1.0
