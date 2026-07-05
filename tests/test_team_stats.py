"""
test_team_stats.py — siła drużyn (kadr MŚ): goals_for/against per mecz = Poisson λ
(model nie ma historii reprezentacji), avg_rating 1-10, clean_sheets. Sofascore.
"""
from footstats.core import player_db


def _rows():
    return [
        {"team": "France", "league": "WC", "season": 2026, "matches": 3,
         "goals_for": 10, "goals_against": 2, "avg_rating": 7.16,
         "possession": 60.6, "clean_sheets": 3},
        {"team": "Spain", "league": "WC", "season": 2026, "matches": 3,
         "goals_for": 5, "goals_against": 0, "avg_rating": 7.23,
         "possession": 68.0, "clean_sheets": 4},
    ]


def test_upsert_and_get(tmp_path):
    db = tmp_path / "t.db"
    player_db.upsert_team_stats(_rows(), db_path=db)
    fr = player_db.get_team_stats("France", 2026, db_path=db)
    assert fr["goals_for"] == 10
    assert abs(fr["avg_rating"] - 7.16) < 1e-6
    assert fr["clean_sheets"] == 3


def test_attack_defense_rates(tmp_path):
    db = tmp_path / "t.db"
    player_db.upsert_team_stats(_rows(), db_path=db)
    atk, dfn = player_db.team_attack_defense("France", 2026, db_path=db)
    assert abs(atk - 10 / 3) < 1e-6   # λ ataku = gole/mecz
    assert abs(dfn - 2 / 3) < 1e-6    # λ obrony = tracone/mecz


def test_attack_defense_unknown_none(tmp_path):
    db = tmp_path / "t.db"
    player_db.upsert_team_stats(_rows(), db_path=db)
    assert player_db.team_attack_defense("Poland", 2026, db_path=db) is None


def test_case_insensitive(tmp_path):
    db = tmp_path / "t.db"
    player_db.upsert_team_stats(_rows(), db_path=db)
    assert player_db.get_team_stats("spain", 2026, db_path=db)["goals_for"] == 5


def test_zero_matches_no_div_error(tmp_path):
    db = tmp_path / "t.db"
    player_db.upsert_team_stats(
        [{"team": "X", "league": "WC", "season": 2026, "matches": 0,
          "goals_for": 0, "goals_against": 0}], db_path=db)
    assert player_db.team_attack_defense("X", 2026, db_path=db) is None
