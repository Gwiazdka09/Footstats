"""
test_understat_players.py — scraper Understat playersData (per-gracz gole/asysty/xG
z pełnego składu ligi). Pełny skład → prawdziwy denominator goal_share (bez zawyżenia
z topscorers). Zero sieci w teście (parser czysty na sztucznym HTML).
"""
from footstats.scrapers.understat_xg import parse_understat_players

_HTML = (
    "<script>var playersData = JSON.parse('"
    '[{"player_name":"Erling Haaland","team_title":"Manchester City","goals":"27",'
    '"assists":"5","time":"2700","xG":"29.5"},'
    '{"player_name":"Phil Foden","team_title":"Manchester City","goals":"10",'
    '"assists":"8","time":"2500","xG":"9.2"},'
    '{"player_name":"NoTeam","team_title":"","goals":"3","assists":"0","time":"100","xG":"2.0"}]'
    "');</script>"
)


def test_parse_players_basic():
    rows = parse_understat_players(_HTML)
    names = {r["name"] for r in rows}
    assert "Erling Haaland" in names
    h = next(r for r in rows if r["name"] == "Erling Haaland")
    assert h["team"] == "Manchester City"
    assert h["goals"] == 27
    assert h["assists"] == 5
    assert h["minutes"] == 2700


def test_parse_skips_no_team():
    rows = parse_understat_players(_HTML)
    assert all(r["team"] for r in rows)      # wpis bez team_title odrzucony
    assert "NoTeam" not in {r["name"] for r in rows}


def test_parse_empty_or_missing():
    assert parse_understat_players("") == []
    assert parse_understat_players("<script>var x = 1;</script>") == []
