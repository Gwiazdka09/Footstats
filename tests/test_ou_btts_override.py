"""
test_ou_btts_override.py — model-first na rynkach 2-way (Over/Under, BTTS).
LLM odsunięty od wszystkich picków (tylko analiza). Flip gdy model daje pickowi
Groq prob < prog_2way. Audyt 07-06: BTTS 14% (Groq słaby).
"""
from footstats.ai.analyzer_helpers import koryguj_tip_ou_btts


def test_over_flip_gdy_model_faworyzuje_under():
    # Groq Over, model o25=35 (<45 → faworyzuje Under) → flip.
    tip, ov = koryguj_tip_ou_btts("Over 2.5", o25=35.0, bt=None)
    assert tip == "Under 2.5" and ov is True


def test_over_zostaje_gdy_model_zgodny():
    # Groq Over, model o25=55 (>=45) → bez zmian.
    tip, ov = koryguj_tip_ou_btts("Over 2.5", o25=55.0, bt=None)
    assert tip == "Over 2.5" and ov is False


def test_under_flip():
    # Groq Under, model o25=70 → P(Under)=30 <45 → flip na Over.
    tip, ov = koryguj_tip_ou_btts("Under 2.5", o25=70.0, bt=None)
    assert tip == "Over 2.5" and ov is True


def test_btts_flip_gdy_model_niski():
    # Groq BTTS, model bt=30 (<45) → flip BTTS NO.
    tip, ov = koryguj_tip_ou_btts("BTTS", o25=None, bt=30.0)
    assert tip == "BTTS NO" and ov is True


def test_btts_zostaje():
    tip, ov = koryguj_tip_ou_btts("BTTS", o25=None, bt=60.0)
    assert tip == "BTTS" and ov is False


def test_brak_prob_no_op():
    assert koryguj_tip_ou_btts("Over 2.5", o25=None, bt=None) == ("Over 2.5", False)
    assert koryguj_tip_ou_btts("BTTS", o25=None, bt=None) == ("BTTS", False)


def test_1x2_nie_rusza():
    # 1X2 poza zakresem tej funkcji (robi koryguj_tip_wg_modelu).
    for t in ("1", "X", "2"):
        assert koryguj_tip_ou_btts(t, o25=10.0, bt=10.0) == (t, False)
