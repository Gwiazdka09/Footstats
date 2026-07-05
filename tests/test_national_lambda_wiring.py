"""
test_national_lambda_wiring.py — _apply_national_lambda: mecze kadr (obie drużyny
w team_stats) dostają Poisson λ blendowany z Bzzoiro. Kluby bez team_stats = bez zmian.
"""
from footstats.core import player_db, daily_phases


def test_national_match_gets_lambda(monkeypatch):
    monkeypatch.setattr(
        player_db, "team_attack_defense",
        lambda team, season, db_path=None: {"France": (3.33, 0.67),
                                             "Egypt": (1.67, 1.0)}.get(team))
    w = {"gospodarz": "France", "goscie": "Egypt",
         "pw": 40.0, "pr": 30.0, "pp": 30.0, "o25": 50.0, "bt": 50.0}
    daily_phases._apply_national_lambda([w])
    assert w.get("national_lambda") is True
    assert w["lambda_h"] > w["lambda_a"]          # France silniejsza
    assert w["pw"] > w["pp"]
    assert abs((w["pw"] + w["pr"] + w["pp"]) - 100.0) < 1.5


def test_club_match_untouched(monkeypatch):
    monkeypatch.setattr(player_db, "team_attack_defense",
                        lambda team, season, db_path=None: None)
    w = {"gospodarz": "Arsenal", "goscie": "Chelsea",
         "pw": 45.0, "pr": 27.0, "pp": 28.0}
    daily_phases._apply_national_lambda([w])
    assert "national_lambda" not in w
    assert w["pw"] == 45.0                          # klub bez zmian


def test_one_team_missing_stats_skips(monkeypatch):
    monkeypatch.setattr(
        player_db, "team_attack_defense",
        lambda team, season, db_path=None: (2.0, 1.0) if team == "Brazil" else None)
    w = {"gospodarz": "Brazil", "goscie": "Unknown FC", "pw": 50.0, "pr": 25.0, "pp": 25.0}
    daily_phases._apply_national_lambda([w])
    assert "national_lambda" not in w
