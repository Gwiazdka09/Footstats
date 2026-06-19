"""Testy core/match_tips.build_tips — sugerowany typ = argmax 1X2, nie zawsze '1'."""
from footstats.core.match_tips import build_tips


def _match(ph, pr, pp, *, odds=None):
    m = {
        "id": "t1", "gosp": "A", "gosc": "B", "liga": "Test",
        "pred_ml": {"prob_home_win": ph, "prob_draw": pr, "prob_away_win": pp},
    }
    if odds:
        m["odds"] = odds
    return m


def test_suggested_tip_to_faworyt_gospodarz():
    out = build_tips(_match(0.60, 0.25, 0.15))
    assert out["suggested_tip"]["tip"] == "1"


def test_suggested_tip_to_faworyt_gosc_nie_zawsze_1():
    # Gość zdecydowany faworyt → sugerowany MUSI być "2", nie "1" (regresja buga GUI).
    out = build_tips(_match(0.15, 0.25, 0.60))
    assert out["suggested_tip"]["tip"] == "2"


def test_suggested_tip_to_remis_gdy_najwyzszy():
    out = build_tips(_match(0.30, 0.45, 0.25))
    assert out["suggested_tip"]["tip"] == "X"


def test_suggested_tip_niesie_kurs_zgodny_z_wyborem():
    odds = {"home": 5.0, "draw": 3.8, "away": 1.55}
    out = build_tips(_match(0.18, 0.27, 0.55, odds=odds))
    sug = out["suggested_tip"]
    assert sug["tip"] == "2"
    assert sug["odds"] == 1.55  # kurs sugerowanego = kurs "2", nie "1"
