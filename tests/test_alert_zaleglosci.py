"""Alarm o zaległościach nie może palić się wiecznie.

PRODUKCJA 22.08.2026: alert „pipeline nie produkuje" zgłaszał 97 predykcji bez
rozliczenia. 49 z nich to jednak wpisy ŚWIADOMIE PORZUCONE — po pięciu nieudanych
próbach nadrabianie przestaje je ruszać (`_wybierz_do_rozliczenia`), bo żadne
źródło nie ma już ich wyniku. Liczenie ich w alarmie czyniło go WIECZNYM.

To nie jest kosmetyka. Tego dnia alarm palił się obok PRAWDZIWEJ awarii (Groq
wycofał model, potok stał 6 dni) i ją zagłuszył — bo wyglądał tak samo jak przez
poprzedni tydzień. Alarm, który nigdy nie gaśnie, uczy go ignorować.
"""
from __future__ import annotations

from footstats.scrapers.results_updater import MAX_PROB_ROZLICZENIA


def test_prog_prob_jest_dodatni():
    """Bez tego zapytanie odcinałoby wszystko albo nic."""
    assert MAX_PROB_ROZLICZENIA >= 1


def test_zapytanie_alarmu_wyklucza_porzucone():
    """Zapytanie MUSI filtrować po `settle_attempts` — inaczej alarm jest wieczny."""
    from pathlib import Path
    zrodlo = (Path(__file__).resolve().parents[1]
              / "src" / "footstats" / "api" / "routes" / "status.py").read_text(encoding="utf-8")
    fragment = zrodlo[zrodlo.index("tip_correct IS NULL"):][:400]
    assert "settle_attempts" in fragment, (
        "alarm liczy predykcje porzucone po MAX_PROB_ROZLICZENIA probach —"
        " bedzie sie palil niezaleznie od stanu potoku")
    assert "MAX_PROB_ROZLICZENIA" in zrodlo, "prog ma pochodzic z jednego zrodla prawdy"


def test_prog_nie_jest_zaszyty_na_sztywno():
    """Duplikat stałej rozjechałby się przy zmianie limitu prób."""
    from pathlib import Path
    zrodlo = (Path(__file__).resolve().parents[1]
              / "src" / "footstats" / "api" / "routes" / "status.py").read_text(encoding="utf-8")
    assert "< 5" not in zrodlo.replace("< 50", ""), "prog wpisany liczba zamiast stalej"
