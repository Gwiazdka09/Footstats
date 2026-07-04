"""
test_lineup_strength.py — Faza 2: siła składu. Ocena wyjściowej XI vs siła strzelecka
zespołu (goal_share z Fazy 1). Brak topowego strzelca w składzie → λ własnego ataku ↓.
Nazwy z API-Football (lineups) == nazwy topscorers (ta sama baza) → dopasowanie casefold.
"""
from footstats.core import lineup_strength as ls

_GS = {"Haaland": 0.5, "Foden": 0.2, "Alvarez": 0.1, "Grealish": 0.05}


def test_full_strength_all_scorers_present():
    xi = ["Haaland", "Foden", "Alvarez", "Grealish", "Rodri", "Dias"]
    assert abs(ls.lineup_offensive_strength(xi, _GS) - 0.85) < 1e-9
    assert ls.absent_stars(xi, _GS) == {}
    assert ls.lineup_lambda_factor(xi, _GS) == 1.0


def test_missing_star_lowers_lambda():
    xi = ["Foden", "Alvarez", "Rodri", "Dias"]  # Haaland (0.5) NIE gra
    absent = ls.absent_stars(xi, _GS, threshold=0.15)
    assert "Haaland" in absent and "Foden" not in absent  # Foden 0.2 gra
    # kara = 0.5*scale(0.5)=0.25 → factor 0.75, ale cap ±20% → 0.8
    assert ls.lineup_lambda_factor(xi, _GS, threshold=0.15) == 0.8


def test_minor_scorer_absent_below_threshold_ignored():
    xi = ["Haaland", "Foden", "Alvarez", "Rodri"]  # Grealish 0.05 NIE gra
    assert ls.absent_stars(xi, _GS, threshold=0.15) == {}
    assert ls.lineup_lambda_factor(xi, _GS, threshold=0.15) == 1.0


def test_empty_goal_shares_no_penalty():
    xi = ["A", "B", "C"]
    assert ls.lineup_offensive_strength(xi, {}) == 0.0
    assert ls.absent_stars(xi, {}) == {}
    assert ls.lineup_lambda_factor(xi, {}) == 1.0


def test_empty_xi_no_penalty():
    # brak danych o składzie (pusta XI) → nie karz (fallback, nie wiadomo kto gra)
    assert ls.lineup_lambda_factor([], _GS) == 1.0


def test_case_insensitive_match():
    xi = ["haaland", "FODEN"]
    assert ls.absent_stars(xi, _GS, threshold=0.15) == {}


def test_cap_multiple_absent_stars():
    gs = {"A": 0.6, "B": 0.5}
    xi = ["X", "Y", "Z"]  # obaj strzelcy nieobecni → kara duża, ale cap 0.8
    assert ls.lineup_lambda_factor(xi, gs, threshold=0.15) == 0.8


def test_confidence_penalty_v2_scales_with_absent_power():
    lineup = {
        "home": {"startXI": ["Foden", "Rodri"]},          # Haaland 0.5 out
        "away": {"startXI": ["Salah", "Nunez", "Diaz"]},  # komplet
    }
    gs_away = {"Salah": 0.4, "Nunez": 0.2}
    pen = ls.lineup_confidence_penalty_v2(lineup, _GS, gs_away)
    assert pen < 0                       # dom traci gwiazdę
    pen_full = ls.lineup_confidence_penalty_v2(
        {"home": {"startXI": ["Haaland"]}, "away": {"startXI": ["Salah"]}}, _GS, gs_away)
    assert pen_full == 0                 # obie gwiazdy grają
