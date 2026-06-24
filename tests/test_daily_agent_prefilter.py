"""Testy pre-filtrów w daily_agent.py."""

from footstats.daily_agent import (
    _pre_filtruj_ligi,
    _pre_filtruj_kursy,
    _pre_filtruj_tokenow,
)


# ── _pre_filtruj_ligi ─────────────────────────────────────────────────────

def test_ligi_friendlies_removed():
    kandydaci = [
        {"liga": "Friendlies International", "gospodarz": "Haiti"},
        {"liga": "Bundesliga", "gospodarz": "Bayern"},
    ]
    result = _pre_filtruj_ligi(kandydaci)
    assert len(result) == 1
    assert result[0]["liga"] == "Bundesliga"


def test_ligi_afc_removed():
    kandydaci = [{"liga": "AFC Asian Qualifiers", "gospodarz": "Singapore"}]
    result = _pre_filtruj_ligi(kandydaci)
    assert result == []


def test_ligi_concacaf_removed():
    kandydaci = [{"liga": "CONCACAF Nations League", "gospodarz": "Mexico"}]
    result = _pre_filtruj_ligi(kandydaci)
    assert result == []


def test_ligi_copa_america_removed():
    kandydaci = [{"liga": "Copa America", "gospodarz": "Argentina"}]
    result = _pre_filtruj_ligi(kandydaci)
    assert result == []


def test_ligi_known_good_kept():
    kandydaci = [
        {"liga": "Premier League", "gospodarz": "Arsenal"},
        {"liga": "PKO BP Ekstraklasa", "gospodarz": "Lech"},
        {"liga": "Bundesliga", "gospodarz": "Bayern"},
        {"liga": "Eredivisie", "gospodarz": "Ajax"},
    ]
    result = _pre_filtruj_ligi(kandydaci)
    assert len(result) == 4


def test_ligi_empty_liga_kept():
    kandydaci = [{"liga": "", "gospodarz": "Bayern"}]
    result = _pre_filtruj_ligi(kandydaci)
    assert len(result) == 1


def test_ligi_missing_liga_key_kept():
    kandydaci = [{"gospodarz": "Bayern"}]
    result = _pre_filtruj_ligi(kandydaci)
    assert len(result) == 1


def test_ligi_empty_input():
    assert _pre_filtruj_ligi([]) == []


def test_ligi_keyword_case_insensitive():
    kandydaci = [{"liga": "FRIENDLIES INTERNATIONAL", "gospodarz": "X"}]
    result = _pre_filtruj_ligi(kandydaci)
    assert result == []


# ── FAZA 17.4: egzekwowanie whitelist ────────────────────────────────────

def test_ligi_spoza_whitelist_odrzucone():
    # Allsvenskan/Veikkausliiga nie są w whitelist → odrzuć (gdy enforce=True).
    # (Botola Pro dodane do whitelist 2026-06-19 — patrz test_whitelist_active_leagues.)
    kandydaci = [
        {"liga": "Allsvenskan", "gospodarz": "Malmö"},
        {"liga": "Veikkausliiga", "gospodarz": "HJK"},
    ]
    result = _pre_filtruj_ligi(kandydaci)
    assert result == []


def test_ligi_whitelist_normalizacja_akcentow_i_prefiksu():
    # "Brasileirão Serie A" (akcent) i "ENG-Premier League" (prefiks) muszą przejść.
    kandydaci = [
        {"liga": "Brasileirão Serie A", "gospodarz": "Flamengo"},
        {"liga": "ENG-Premier League", "gospodarz": "Arsenal"},
        {"liga": "ESP-La Liga", "gospodarz": "Real"},
    ]
    result = _pre_filtruj_ligi(kandydaci)
    assert len(result) == 3


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
    kandydaci = [{"gospodarz": "Bayern"}]
    result = _pre_filtruj_kursy(kandydaci)
    assert len(result) == 1


def test_kursy_mixed_values_kept_if_one_valid():
    kandydaci = [{"odds": {"1": 0.5, "2": 2.0}}]
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
