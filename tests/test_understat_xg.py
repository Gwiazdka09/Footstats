"""Testy scrapers/understat_xg.py — parsowanie xG z Understat (bez HTTP)."""
import json
from unittest.mock import patch, MagicMock

import pytest

from footstats.scrapers.understat_xg import (
    _to_slug,
    _parse_matches_json,
    fetch_team_xg,
)


# ── _to_slug ──────────────────────────────────────────────────────────────

def test_slug_known_teams():
    assert _to_slug("Arsenal") == "Arsenal"
    assert _to_slug("Manchester City") == "Manchester_City"
    assert _to_slug("Bayern") == "Bayern_Munich"
    assert _to_slug("PSG") == "Paris_Saint_Germain"


def test_slug_fallback_spaces_to_underscore():
    assert _to_slug("Borussia Dortmund") == "Borussia_Dortmund"
    assert _to_slug("Unknown Team FC") == "Unknown_Team_FC"


# ── _parse_matches_json ───────────────────────────────────────────────────

def _build_html(matches: list) -> str:
    raw = json.dumps(matches, ensure_ascii=False)
    # Understat osadza jako JSON.parse('...')
    escaped = raw.replace("'", "\\'")
    return f"<script>\nvar matchesData = JSON.parse('{escaped}');\n</script>"


def test_parse_matches_json_valid():
    matches = [
        {"id": "1", "isResult": True, "h": {"id": "74", "title": "Arsenal"},
         "a": {"id": "106", "title": "Chelsea"},
         "goals": {"h": "3", "a": "1"},
         "xG": {"h": "2.31", "a": "0.87"},
         "datetime": "2025-10-01 15:00:00"}
    ]
    html = _build_html(matches)
    result = _parse_matches_json(html)
    assert result is not None
    assert len(result) == 1
    assert result[0]["xG"]["h"] == "2.31"


def test_parse_matches_json_missing():
    html = "<html><body>no data here</body></html>"
    assert _parse_matches_json(html) is None


def test_parse_matches_json_empty_list():
    html = _build_html([])
    result = _parse_matches_json(html)
    assert result == []


# ── fetch_team_xg (mocked HTTP) ───────────────────────────────────────────

def _make_matches(n: int, xg_for: float = 1.5, xga: float = 1.0) -> list:
    return [
        {
            "id": str(i),
            "isResult": True,
            "h": {"id": "74", "title": "Arsenal"},
            "a": {"id": "99", "title": f"Team{i}"},
            "goals": {"h": "2", "a": "1"},
            "xG": {"h": str(xg_for), "a": str(xga)},
            "datetime": f"2025-{(i % 12) + 1:02d}-01 15:00:00",
        }
        for i in range(1, n + 1)
    ]


def _mock_response(matches: list, status: int = 200):
    resp = MagicMock()
    resp.status_code = status
    resp.text = _build_html(matches)
    return resp


def test_fetch_team_xg_returns_correct_averages():
    matches = _make_matches(5, xg_for=2.0, xga=1.0)
    with patch("footstats.scrapers.understat_xg._cache_get", return_value=None), \
         patch("footstats.scrapers.understat_xg._cache_set"), \
         patch("footstats.scrapers.understat_xg._SESSION") as mock_sess:
        mock_sess.get.return_value = _mock_response(matches)
        result = fetch_team_xg("Arsenal", season=2025, ostatnie_n=5)

    assert result is not None
    assert result["mecze"] == 5
    assert result["xg_for_avg"] == pytest.approx(2.0)
    assert result["xga_avg"] == pytest.approx(1.0)


def test_fetch_team_xg_uses_cache():
    cached = {"team": "Arsenal", "season": 2025, "mecze": 3,
              "xg_for_avg": 1.8, "xga_avg": 0.9, "historia": []}
    with patch("footstats.scrapers.understat_xg._cache_get", return_value=cached), \
         patch("footstats.scrapers.understat_xg._SESSION") as mock_sess:
        result = fetch_team_xg("Arsenal", season=2025)
    assert result == cached
    mock_sess.get.assert_not_called()


def test_fetch_team_xg_http_error_returns_none():
    with patch("footstats.scrapers.understat_xg._cache_get", return_value=None), \
         patch("footstats.scrapers.understat_xg._SESSION") as mock_sess:
        mock_sess.get.return_value = _mock_response([], status=404)
        result = fetch_team_xg("Arsenal", season=2025)
    assert result is None


def test_fetch_team_xg_no_finished_matches():
    matches = [{"id": "1", "isResult": False, "h": {"id": "74", "title": "Arsenal"},
                "a": {"id": "99", "title": "Chelsea"},
                "goals": {}, "xG": {}, "datetime": "2026-12-01 15:00:00"}]
    with patch("footstats.scrapers.understat_xg._cache_get", return_value=None), \
         patch("footstats.scrapers.understat_xg._cache_set"), \
         patch("footstats.scrapers.understat_xg._SESSION") as mock_sess:
        mock_sess.get.return_value = _mock_response(matches)
        result = fetch_team_xg("Arsenal", season=2026)
    assert result is None
