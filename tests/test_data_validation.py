"""Tests for data validation + deduplication."""
import pandas as pd
import pytest

from footstats.core.data import GameRecord, validate_games, deduplicate_games


class TestGameRecord:
    """Pydantic model validation."""

    def test_valid_game_record(self):
        rec = GameRecord(
            match_date="2026-05-18",
            team_home="TeamA",
            team_away="TeamB",
            league="Premier League",
        )
        assert rec.match_date == "2026-05-18"
        assert rec.team_home == "TeamA"

    def test_invalid_date_format(self):
        with pytest.raises(Exception):
            GameRecord(
                match_date="18-05-2026",  # Wrong format
                team_home="TeamA",
                team_away="TeamB",
            )

    def test_teams_not_equal(self):
        with pytest.raises(Exception):
            GameRecord(
                match_date="2026-05-18",
                team_home="TeamA",
                team_away="TeamA",  # Same team
            )

    def test_goals_in_range(self):
        rec = GameRecord(
            match_date="2026-05-18",
            team_home="TeamA",
            team_away="TeamB",
            gole_g=2,
            gole_a=1,
        )
        assert rec.gole_g == 2
        assert rec.gole_a == 1

    def test_goals_out_of_range(self):
        with pytest.raises(Exception):
            GameRecord(
                match_date="2026-05-18",
                team_home="TeamA",
                team_away="TeamB",
                gole_g=21,  # > 20
            )


class TestValidateGames:
    """validate_games() function."""

    def test_empty_dataframe(self):
        df = pd.DataFrame()
        valid, errors = validate_games(df)
        assert valid.empty
        assert errors.empty

    def test_valid_games(self):
        df = pd.DataFrame({
            "match_date": ["2026-05-18", "2026-05-19"],
            "team_home": ["TeamA", "TeamC"],
            "team_away": ["TeamB", "TeamD"],
            "league": ["League1", "League2"],
        })
        valid, errors = validate_games(df)
        assert len(valid) == 2
        assert len(errors) == 0

    def test_invalid_games_logged(self):
        df = pd.DataFrame({
            "match_date": ["2026-05-18", "invalid-date"],
            "team_home": ["TeamA", "TeamC"],
            "team_away": ["TeamB", "TeamD"],
        })
        valid, errors = validate_games(df)
        assert len(valid) == 1
        assert len(errors) == 1
        assert "_error" in errors.columns


class TestDeduplicateGames:
    """deduplicate_games() function."""

    def test_no_duplicates(self):
        df = pd.DataFrame({
            "match_date": ["2026-05-18", "2026-05-19"],
            "team_home": ["TeamA", "TeamC"],
            "team_away": ["TeamB", "TeamD"],
        })
        result = deduplicate_games(df)
        assert len(result) == 2

    def test_removes_duplicates(self):
        df = pd.DataFrame({
            "match_date": ["2026-05-18", "2026-05-18", "2026-05-19"],
            "team_home": ["TeamA", "TeamA", "TeamC"],
            "team_away": ["TeamB", "TeamB", "TeamD"],
        })
        result = deduplicate_games(df, keep="first")
        assert len(result) == 2
        assert list(result["team_home"]) == ["TeamA", "TeamC"]

    def test_keep_last(self):
        df = pd.DataFrame({
            "match_date": ["2026-05-18", "2026-05-18"],
            "team_home": ["TeamA", "TeamA"],
            "team_away": ["TeamB", "TeamB"],
            "source": ["bzzoiro", "sts"],
        })
        result = deduplicate_games(df, keep="last")
        assert result["source"].iloc[0] == "sts"
