"""
test_analyses_route.py — endpoint Analizy meczowe: filtr ważnych lig + budowa kart
z eventów Bzzoiro. Bez sieci/DB (mock player_db).
"""
from footstats.api.routes import analyses


_EVENTS = [
    {"gosp": "France", "gosc": "Egypt", "liga": "World Cup 2026", "data": "2026-07-08",
     "pred_ml": {"prob_home_win": 56, "prob_draw": 24, "prob_away_win": 20,
                 "prob_over_25": 54, "prob_btts_yes": 54}, "odds": {"home": 1.4}},
    {"gosp": "Foo", "gosc": "Bar", "liga": "Botola Pro",   # nieważna liga → odpada
     "data": "2026-07-08", "pred_ml": {"prob_home_win": 40}},
]


def test_build_cards_filtruje_wazne(monkeypatch):
    monkeypatch.setattr(analyses, "get_team_stats",
                        lambda t, s: {"matches": 3, "goals_for": 10, "goals_against": 2,
                                      "avg_rating": 7.16} if t == "France" else None)
    monkeypatch.setattr(analyses, "team_goal_shares_recent", lambda t, s: {})
    cards = analyses._build_cards(_EVENTS)
    assert len(cards) == 1                       # tylko World Cup, Botola odpada
    c = cards[0]
    assert c["home"] == "France" and c["host"] == "France"
    assert c["model"]["pw"] == 56
    assert abs(c["home_stats"]["gf_pg"] - 10 / 3) < 0.01


def test_wazna_liga():
    assert analyses._wazna("Premier League") is True
    assert analyses._wazna("World Cup 2026") is True
    assert analyses._wazna("PKO BP Ekstraklasa") is True
    assert analyses._wazna("Botola Pro") is False


def test_norm():
    assert analyses._norm(56) == 56       # już %
    assert analyses._norm(0.56) == 56.0   # 0-1 → %
    assert analyses._norm(None) is None
