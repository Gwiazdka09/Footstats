"""
test_national_lambda.py — Poisson dla reprezentacji z team_attack_defense.
Model nie ma historii kadr → λ z realnych statów turnieju (gole/mecz, tracone/mecz).
"""
from footstats.core.national_lambda import national_team_probs


def test_probs_sum_100():
    p = national_team_probs(2.0, 1.0, 2.0, 1.0)
    assert abs((p["pw"] + p["pr"] + p["pp"]) - 100.0) < 1.0
    assert 0 <= p["o25"] <= 100
    assert 0 <= p["bt"] <= 100


def test_symmetric_teams_balanced():
    p = national_team_probs(2.0, 1.0, 2.0, 1.0)
    assert abs(p["pw"] - p["pp"]) < 2.0   # równe drużyny → pw≈pp


def test_stronger_attack_favored():
    # France (atak 3.33, obrona 0.67) vs Egypt (atak 1.67, obrona 1.0)
    p = national_team_probs(3.33, 0.67, 1.67, 1.0)
    assert p["pw"] > p["pp"]              # faworyt gospodarz
    assert p["lambda_h"] > p["lambda_a"]


def test_high_lambda_high_over():
    lo = national_team_probs(0.8, 0.5, 0.7, 0.5)   # mało goli
    hi = national_team_probs(3.0, 2.0, 2.8, 2.0)   # dużo goli
    assert hi["o25"] > lo["o25"]


def test_lambda_floor_no_zero():
    p = national_team_probs(0.0, 0.0, 0.0, 0.0)
    assert p["lambda_h"] >= 0.2 and p["lambda_a"] >= 0.2
    assert abs((p["pw"] + p["pr"] + p["pp"]) - 100.0) < 1.0


def test_home_boost_raises_home():
    base = national_team_probs(2.0, 1.0, 2.0, 1.0)
    boosted = national_team_probs(2.0, 1.0, 2.0, 1.0, home_boost=1.12)
    assert boosted["lambda_h"] > base["lambda_h"]
    assert boosted["pw"] > base["pw"]          # gospodarz-host faworyzowany
    assert boosted["lambda_a"] == base["lambda_a"]  # gość bez zmian
