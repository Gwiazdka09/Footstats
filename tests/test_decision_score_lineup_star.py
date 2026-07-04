"""
test_decision_score_lineup_star.py — Faza 2: kara za brak topowego strzelca w składzie
(lineup_star_penalty) obniża decision_score w fazie final. Additive, default 0.
"""
from footstats.core.decision_score import score_kandydat

_W = {"ev_netto": 0.05, "pewnosc": 0.75, "czynniki": [], "roznica_modeli": 0.0}


def test_star_penalty_lowers_final_score():
    base, _ = score_kandydat(_W, context={"lineup_ok": True}, phase="final")
    pen, reasons = score_kandydat(
        _W, context={"lineup_ok": True, "lineup_star_penalty": -15}, phase="final")
    assert pen == base - 15
    assert any("strzel" in r.lower() for r in reasons)


def test_no_penalty_default():
    a, _ = score_kandydat(_W, context={"lineup_ok": True}, phase="final")
    b, _ = score_kandydat(
        _W, context={"lineup_ok": True, "lineup_star_penalty": 0}, phase="final")
    assert a == b


def test_penalty_ignored_in_draft_phase():
    # kontekst składu tylko w final — penalty nie rusza draft
    a, _ = score_kandydat(_W, context={"lineup_star_penalty": -15}, phase="draft")
    b, _ = score_kandydat(_W, context={}, phase="draft")
    assert a == b
