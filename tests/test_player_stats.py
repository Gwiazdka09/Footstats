"""
test_player_stats.py — Faza 1: fetch+parse statystyk graczy z API-Football
(/players/topscorers) i zasilenie player_db. Sieć mockowana (zero requestów w CI).
"""
from footstats.core import player_db
from footstats.scrapers import player_stats

_PAYLOAD = {
    "response": [
        {
            "player": {"id": 1, "name": "Haaland"},
            "statistics": [
                {
                    "team": {"name": "Manchester City"},
                    "goals": {"total": 20, "assists": 6},
                    "games": {"minutes": 1800, "appearences": 22},
                }
            ],
        },
        {
            "player": {"id": 2, "name": "Salah"},
            "statistics": [
                {
                    "team": {"name": "Liverpool"},
                    "goals": {"total": 15, "assists": 10},
                    "games": {"minutes": 2000, "appearences": 24},
                }
            ],
        },
        {  # brak goli (None) → goals=0, nie wywala
            "player": {"id": 3, "name": "Keeper"},
            "statistics": [
                {"team": {"name": "Arsenal"}, "goals": {"total": None, "assists": None},
                 "games": {"minutes": None}}
            ],
        },
    ]
}


def test_parse_topscorers_basic():
    rows = player_stats.parse_topscorers(_PAYLOAD)
    assert len(rows) == 3
    h = next(r for r in rows if r["name"] == "Haaland")
    assert h["team"] == "Manchester City"
    assert h["goals"] == 20
    assert h["assists"] == 6
    assert h["minutes"] == 1800


def test_parse_handles_none_and_empty():
    assert player_stats.parse_topscorers({}) == []
    assert player_stats.parse_topscorers({"response": []}) == []
    k = next(r for r in player_stats.parse_topscorers(_PAYLOAD) if r["name"] == "Keeper")
    assert k["goals"] == 0
    assert k["minutes"] == 0


def test_parse_skips_entry_without_stats():
    payload = {"response": [{"player": {"name": "Ghost"}, "statistics": []}]}
    assert player_stats.parse_topscorers(payload) == []


def test_refresh_tracked_leagues_iterates(tmp_path, monkeypatch):
    db = tmp_path / "t.db"
    calls = []

    def fake_refresh(lid, season, api_key, db_path, league_code=None):
        calls.append((lid, league_code))
        return 1

    monkeypatch.setattr(player_stats, "refresh_league_players", fake_refresh)
    total = player_stats.refresh_tracked_leagues("key", season=2025, db_path=db)
    # 16 śledzonych lig w _APISPORTS_LIGI → 16 wywołań, każde +1
    assert total == 16
    assert len(calls) == 16
    assert (39, "PL") in calls  # Premier League


def test_refresh_tracked_leagues_no_key(tmp_path):
    assert player_stats.refresh_tracked_leagues("", db_path=tmp_path / "t.db") == 0


def test_refresh_understat_leagues_upserts(tmp_path, monkeypatch):
    db = tmp_path / "t.db"
    from footstats.scrapers import understat_xg

    def fake_fetch(ukey, season):
        if ukey != "EPL":
            return []
        return [
            {"name": "Salah", "team": "Liverpool", "goals": 20, "assists": 5, "minutes": 3000, "xg": 18.0},
            {"name": "Núñez", "team": "Liverpool", "goals": 10, "assists": 3, "minutes": 2000, "xg": 11.0},
        ]

    monkeypatch.setattr(understat_xg, "fetch_league_players_understat", fake_fetch)
    n = player_stats.refresh_understat_leagues(2024, db_path=db, only=["PL"])
    assert n == 2
    shares = player_db.team_goal_shares("Liverpool", 2024, db_path=db)
    # pełen skład: Salah 20/(20+10)=0.667 (nie 1.0 jak z pojedynczego topscorera)
    assert abs(shares["Salah"] - 20 / 30) < 1e-6


def test_refresh_league_players_upserts(tmp_path, monkeypatch):
    db = tmp_path / "t.db"
    monkeypatch.setattr(player_stats, "fetch_league_players",
                        lambda lid, season, api_key: player_stats.parse_topscorers(_PAYLOAD))
    n = player_stats.refresh_league_players(
        39, 2025, api_key="x", db_path=db, league_code="PL")
    assert n == 3
    # goal_share pełny zespół z jednym strzelcem = 1.0
    shares = player_db.team_goal_shares("Liverpool", 2025, db_path=db)
    assert shares == {"Salah": 1.0}
