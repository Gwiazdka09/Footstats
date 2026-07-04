"""
test_player_db.py — Faza 1: baza graczy + goal_share (udział w golach drużyny).
Football logic: utrata topowego strzelca (share 0.4) boli mocniej niż rezerwowy (0.02).
Denominator = suma goli zapisanych graczy drużyny (topscorers ≈ większość goli zespołu).
"""
from footstats.core import player_db


def _rows(season=2025):
    return [
        {"name": "Haaland", "team": "Manchester City", "league": "PL", "season": season,
         "goals": 20, "assists": 5, "minutes": 1800},
        {"name": "Foden", "team": "Manchester City", "league": "PL", "season": season,
         "goals": 5, "assists": 8, "minutes": 1700},
        {"name": "Alvarez", "team": "Manchester City", "league": "PL", "season": season,
         "goals": 5, "assists": 3, "minutes": 900},
    ]


def test_upsert_and_goal_shares(tmp_path):
    db = tmp_path / "t.db"
    player_db.upsert_players(_rows(), db_path=db)
    shares = player_db.team_goal_shares("Manchester City", 2025, db_path=db)
    # total goli = 30 → Haaland .667, Foden/Alvarez .167 każdy
    assert abs(shares["Haaland"] - 20 / 30) < 1e-6
    assert abs(shares["Foden"] - 5 / 30) < 1e-6
    assert abs(sum(shares.values()) - 1.0) < 1e-6


def test_zero_total_goals_empty(tmp_path):
    db = tmp_path / "t.db"
    rows = [dict(r, goals=0) for r in _rows()]
    player_db.upsert_players(rows, db_path=db)
    assert player_db.team_goal_shares("Manchester City", 2025, db_path=db) == {}


def test_upsert_idempotent_latest_wins(tmp_path):
    db = tmp_path / "t.db"
    player_db.upsert_players(_rows(), db_path=db)
    # ten sam gracz, nowa liczba goli — brak duplikatu, wygrywa nowsza
    player_db.upsert_players(
        [{"name": "Haaland", "team": "Manchester City", "league": "PL",
          "season": 2025, "goals": 30, "assists": 5, "minutes": 2000}],
        db_path=db,
    )
    shares = player_db.team_goal_shares("Manchester City", 2025, db_path=db)
    # total = 30(Haaland) + 5 + 5 = 40
    assert abs(shares["Haaland"] - 30 / 40) < 1e-6
    assert len(shares) == 3  # brak duplikatu Haalanda


def test_team_lookup_case_insensitive(tmp_path):
    db = tmp_path / "t.db"
    player_db.upsert_players(_rows(), db_path=db)
    shares = player_db.team_goal_shares("manchester city", 2025, db_path=db)
    assert "Haaland" in shares


def test_unknown_team_empty(tmp_path):
    db = tmp_path / "t.db"
    player_db.upsert_players(_rows(), db_path=db)
    assert player_db.team_goal_shares("Real Madrid", 2025, db_path=db) == {}


def test_recent_walks_back_to_season_with_data(tmp_path):
    db = tmp_path / "t.db"
    player_db.upsert_players(_rows(2024), db_path=db)  # dane tylko 2024
    # zapytanie o 2026 (pusty) → walk-back 2025(pusty)→2024(dane)
    shares = player_db.team_goal_shares_recent("Manchester City", 2026, lookback=2, db_path=db)
    assert abs(shares["Haaland"] - 20 / 30) < 1e-6


def test_recent_lookback_zero_only_current(tmp_path):
    db = tmp_path / "t.db"
    player_db.upsert_players(_rows(2024), db_path=db)
    assert player_db.team_goal_shares_recent("Manchester City", 2026, lookback=0, db_path=db) == {}


def test_recent_returns_first_season_with_data(tmp_path):
    db = tmp_path / "t.db"
    player_db.upsert_players(_rows(2026), db_path=db)  # dane bieżące
    player_db.upsert_players(
        [{"name": "Old", "team": "Manchester City", "league": "PL", "season": 2024,
          "goals": 9, "assists": 0, "minutes": 900}], db_path=db)
    shares = player_db.team_goal_shares_recent("Manchester City", 2026, lookback=2, db_path=db)
    assert "Old" not in shares          # bieżący sezon ma dane → nie schodzi niżej
    assert "Haaland" in shares


def test_season_isolation(tmp_path):
    db = tmp_path / "t.db"
    player_db.upsert_players(_rows(2025), db_path=db)
    player_db.upsert_players(
        [{"name": "Haaland", "team": "Manchester City", "league": "PL",
          "season": 2024, "goals": 10, "assists": 0, "minutes": 900}],
        db_path=db,
    )
    s25 = player_db.team_goal_shares("Manchester City", 2025, db_path=db)
    s24 = player_db.team_goal_shares("Manchester City", 2024, db_path=db)
    assert len(s25) == 3
    assert list(s24.keys()) == ["Haaland"]
    assert s24["Haaland"] == 1.0  # jedyny gracz 2024
