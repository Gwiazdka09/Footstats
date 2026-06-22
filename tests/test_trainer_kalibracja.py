"""Regresja 06-22: get_kalibracja_inject crashował na float korekcie (:+d → ValueError),
co wywalało CAŁY Groq (KROK 3) → 0 predykcji/kuponów Groq w run 08:00."""
from unittest.mock import patch
import footstats.ai.trainer as trainer


def _lessons(korekta):
    return {
        "updated_at": "2026-06-22T00:00:00",
        "n_matches": 1234,
        "groq_lessons": {
            "kalibracja_summary": "podsumowanie",
            "kalibracja_per_rynek": {"1X2": {"korekta_pewnosci": korekta}},
        },
    }


def test_inject_nie_crashuje_na_float_korekcie():
    # Float korekta (np. z JSON) NIE może rzucać ValueError.
    with patch.object(trainer, "load_lessons", return_value=_lessons(5.0)):
        out = trainer.get_kalibracja_inject()
    assert "1X2:+5%" in out


def test_inject_float_ujemny_i_int():
    with patch.object(trainer, "load_lessons", return_value=_lessons(-3.7)):
        assert "1X2:-4%" in trainer.get_kalibracja_inject()  # zaokrąglenie
    with patch.object(trainer, "load_lessons", return_value=_lessons(2)):
        assert "1X2:+2%" in trainer.get_kalibracja_inject()  # int też działa


def test_inject_pusty_gdy_brak_summary():
    with patch.object(trainer, "load_lessons", return_value={"groq_lessons": {}}):
        assert trainer.get_kalibracja_inject() == ""
