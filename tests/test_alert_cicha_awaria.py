"""Detektor cichej awarii patrzył w złe miejsce.

PRODUKCJA 15.08 (`footstats-final-wvjf6`): 42 kandydatów, 7 po filtrach, ZERO
zapisanych predykcji — bo JSON od Groqa nie sparsował się i cała gałąź zapisu
została pominięta. Alert nie zadziałał, bo jego warunki to:
  * `n_raw_kandydatow == 0`  → było 42, więc nie
  * `0 kuponów System` ale TYLKO przy `--system-paper`

Czyli detektor pilnował WEJŚCIA (czy źródło coś dało) i bocznej ścieżki kuponów
System, a nie GŁÓWNEGO produktu przebiegu. Run bez ani jednego typu wyglądał
identycznie jak dzień bez okazji.
"""
from __future__ import annotations

from footstats.daily_agent import wykryj_anomalie_runu as wykryj


def test_zero_kandydatow_to_anomalia():
    assert "kandydat" in (wykryj(0, 0, 0, ma_typy=False) or "").lower()


def test_typy_powstaly_to_zdrowy_run():
    assert wykryj(42, 7, 0, ma_typy=True) is None


def test_kandydaci_sa_ale_zero_typow_to_anomalia():
    """Dokładnie przypadek z 15.08 — dotad przechodzil bez slowa."""
    anomalia = wykryj(42, 7, 0, ma_typy=False)
    assert anomalia is not None
    assert "typ" in anomalia.lower()


def test_wszystko_odfiltrowane_to_NIE_anomalia():
    """Filtry wycięły komplet — to normalny dzień, nie awaria. Bez fałszywych alarmów."""
    assert wykryj(42, 0, 0, ma_typy=False) is None


def test_zero_kandydatow_wazniejsze_niz_brak_typow():
    """Gdy źródło jest puste, komunikat ma wskazywać źródło, nie skutek."""
    assert "kandydat" in (wykryj(0, 0, 0, ma_typy=False) or "").lower()


def test_kupony_system_dalej_pilnowane():
    anomalia = wykryj(42, 7, 0, ma_typy=True, system_paper=True)
    assert anomalia is not None
    assert "System" in anomalia


def test_kupony_system_bez_flagi_nie_alarmuja():
    assert wykryj(42, 7, 0, ma_typy=True, system_paper=False) is None
