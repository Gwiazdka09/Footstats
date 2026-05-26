"""Testy pre-filtrów w daily_agent.py."""
import pytest
from unittest.mock import patch

from footstats.daily_agent import (
    _pre_filtruj_ligi,
    _pre_filtruj_kursy,
    _pre_filtruj_tokenow,
)


BLACKLIST = {"Ligue 1", "MLS", "Saudi Pro League"}


# ── _pre_filtruj_ligi ─────────────────────────────────────────────────────

def test_ligi_blacklisted_removed():
    kandydaci = [
        {"liga": "Ligue 1", "gospodarz": "PSG"},
        {"liga": "Bundesliga", "gospodarz": "Bayern"},
    ]
    with patch("footstats.config.LIGI_BLACKLIST", BLACKLIST):
        result = _pre_filtruj_ligi(kandydaci)
    assert len(result) == 1
    assert result[0]["liga"] == "Bundesliga"


def test_ligi_empty_liga_kept():
    kandydaci = [{"liga": "", "gospodarz": "Bayern"}]
    with patch("footstats.config.LIGI_BLACKLIST", BLACKLIST):
        result = _pre_filtruj_ligi(kandydaci)
    assert len(result) == 1


def test_ligi_missing_liga_key_kept():
    kandydaci = [{"gospodarz": "Bayern"}]
    with patch("footstats.config.LIGI_BLACKLIST", BLACKLIST):
        result = _pre_filtruj_ligi(kandydaci)
    assert len(result) == 1


def test_ligi_all_blacklisted():
    kandydaci = [
        {"liga": "Ligue 1"},
        {"liga": "MLS"},
    ]
    with patch("footstats.config.LIGI_BLACKLIST", BLACKLIST):
        result = _pre_filtruj_ligi(kandydaci)
    assert result == []


def test_ligi_empty_input():
    with patch("footstats.config.LIGI_BLACKLIST", BLACKLIST):
        assert _pre_filtruj_ligi([]) == []


# ── _pre_filtruj_kursy ────────────────────────────────────────────────────

def test_kursy_valid_range_kept():
    kandydaci = [{"odds": {"1": 1.80}}]
    result = _pre_filtruj_kursy(kandydaci)
    assert len(result) == 1


def test_kursy_out_of_range_removed():
    kandydaci = [{"odds": {"1": 0.5}}, {"odds": {"2": 20.0}}]
    result = _pre_filtruj_kursy(kandydaci)
    assert result == []


def test_kursy_no_odds_kept():
    kandydaci = [{"gospodarz": "Bayern"}]  # no 'odds' field
    result = _pre_filtruj_kursy(kandydaci)
    assert len(result) == 1


def test_kursy_mixed_values_kept_if_one_valid():
    kandydaci = [{"odds": {"1": 0.5, "2": 2.0}}]  # 2.0 valid
    result = _pre_filtruj_kursy(kandydaci)
    assert len(result) == 1


# ── _pre_filtruj_tokenow ──────────────────────────────────────────────────

def test_tokenow_valid_kept():
    kandydaci = [{"gospodarz": "Bayern", "goscie": "Dortmund", "liga": "Bundesliga"}]
    result = _pre_filtruj_tokenow(kandydaci)
    assert len(result) == 1


def test_tokenow_missing_gospodarz_removed():
    kandydaci = [{"goscie": "Dortmund", "liga": "Bundesliga"}]
    result = _pre_filtruj_tokenow(kandydaci)
    assert result == []


def test_tokenow_missing_liga_removed():
    kandydaci = [{"gospodarz": "Bayern", "goscie": "Dortmund"}]
    result = _pre_filtruj_tokenow(kandydaci)
    assert result == []


def test_tokenow_whitespace_only_removed():
    kandydaci = [{"gospodarz": "  ", "goscie": "Dortmund", "liga": "Bundesliga"}]
    result = _pre_filtruj_tokenow(kandydaci)
    assert result == []
