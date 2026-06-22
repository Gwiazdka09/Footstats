"""
test_results_updater_ht.py — capture wyniku półczasu (HT) z API-Football
w results_updater._fixture_to_result, wymagane przez rynki half-time (GG2H).
"""
from footstats.scrapers.results_updater import _fixture_to_result


def test_fixture_to_result_z_halftime_dodaje_sufiks_ht():
    fixture = {
        "fixture": {"status": {"short": "FT"}, "id": 1},
        "teams": {
            "home": {"name": "Tunisia"},
            "away": {"name": "Japan"},
        },
        "goals": {"home": 0, "away": 4},
        "score": {"halftime": {"home": 0, "away": 2}},
    }
    home, away, wynik, stats = _fixture_to_result(fixture)
    assert home == "Tunisia"
    assert away == "Japan"
    assert wynik == "0-4;HT:0-2"


def test_fixture_to_result_bez_halftime_samo_ft():
    fixture = {
        "fixture": {"status": {"short": "FT"}, "id": 2},
        "teams": {
            "home": {"name": "Spain"},
            "away": {"name": "Saudi Arabia"},
        },
        "goals": {"home": 4, "away": 0},
    }
    home, away, wynik, stats = _fixture_to_result(fixture)
    assert wynik == "4-0"
