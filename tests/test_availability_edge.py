"""
test_availability_edge.py — ścieżka B: edge z team-news (absencje). Stawiaj ZANIM
rynek wchłonie wiadomość o składzie. Forward-only (brak historycznych kontuzji do
backtestu) — waliduje logikę, nie ROI. Reuse goal_share z bazy graczy.
"""
from footstats.core.availability_edge import absence_attack_factor, over_edge_from_absences


def test_no_absences_factor_one():
    assert absence_attack_factor([]) == 1.0


def test_star_absence_reduces():
    # gwiazda share 0.3 → 1 - 0.3*0.5 = 0.85
    assert abs(absence_attack_factor([0.3]) - 0.85) < 1e-9


def test_cap_prevents_zero():
    # 2 gwiazdy 0.5+0.5=1.0 *0.5 = 0.5 → cap 0.35 → factor 0.65
    assert abs(absence_attack_factor([0.5, 0.5]) - 0.65) < 1e-9


def test_striker_out_lowers_over_and_flags_under():
    base = over_edge_from_absences(1.6, 1.4, [], [], market_p_over=0.55)
    out = over_edge_from_absences(1.6, 1.4, [0.35], [], market_p_over=0.55)
    assert out["p_over_adj"] < base["p_over_adj"]   # mniej goli bez strzelca
    assert out["lh"] < base["lh"]
    assert out["edge"] < 0                          # nasz P<rynek → value na Under


def test_no_news_edge_near_zero_vs_matching_market():
    r = over_edge_from_absences(1.5, 1.5, [], [], market_p_over=None)
    assert r["edge"] is None                        # brak kursu rynku → brak edge
