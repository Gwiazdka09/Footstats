"""
test_pewnosc_z_modelu.py — FAZA 17.1/17.6: pewność liczona z prawdopodobieństwa
modelu, nie z EV. Blokuje regresję antykalibracji (longshot dostawał 95%).
"""
from footstats.ai.analyzer_helpers import pewnosc_z_modelu, prob_modelu

# Germany vs Curaçao: model daje Niemcom ~92% wygranej, Curaçao ~2%
_PRED = {
    "p_wygrana": 92.0, "p_remis": 6.0, "p_przegrana": 2.0,
    "over25": 70.0, "under25": 30.0, "btts": 45.0,
}


def test_prob_modelu_mapuje_typy():
    assert prob_modelu("1", _PRED) == 92.0
    assert prob_modelu("X", _PRED) == 6.0
    assert prob_modelu("2", _PRED) == 2.0
    assert prob_modelu("Over 2.5", _PRED) == 70.0
    assert prob_modelu("Under 2.5", _PRED) == 30.0
    assert prob_modelu("BTTS", _PRED) == 45.0


def test_prob_modelu_brak_pred_zwraca_none():
    assert prob_modelu("1", {}) is None
    assert prob_modelu("nieznany", _PRED) is None


def test_longshot_dostaje_niska_pewnosc():
    # Kluczowy test 17.1: Curaçao wygrana (longshot) NIE może dostać 95%.
    conf = pewnosc_z_modelu("2", _PRED, fallback_pct=95)
    assert conf == 2, f"longshot powinien mieć ~2% pewności, dostał {conf}"


def test_faworyt_dostaje_wysoka_pewnosc():
    conf = pewnosc_z_modelu("1", _PRED)
    assert conf == 92


def test_pewnosc_deterministyczna_per_typ():
    # 17.6: ten sam typ+pred ZAWSZE daje tę samą pewność (niezależnie od kontekstu).
    c1 = pewnosc_z_modelu("2", _PRED, fallback_pct=95)   # ścieżka top3
    c2 = pewnosc_z_modelu("2", _PRED, fallback_pct=65)   # ścieżka kupon_a
    assert c1 == c2 == 2, "pewność musi być stabilna niezależnie od fallback/kupon_type"


def test_fallback_gdy_brak_modelu():
    # Brak pred → użyj LLM pewnosc_pct.
    assert pewnosc_z_modelu("1", {}, fallback_pct=70) == 70
    # Brak pred i brak fallback → 50.
    assert pewnosc_z_modelu("1", {}, fallback_pct=None) == 50


def test_pewnosc_w_zakresie_1_99():
    # Clamp górny: 100% -> 99
    assert pewnosc_z_modelu("1", {"p_wygrana": 100.0}) == 99
    # Clamp dolny: 0% -> 1 (0.0 to wartość modelu, nie brak danych)
    assert pewnosc_z_modelu("2", {"p_przegrana": 0.0}) == 1
