"""Rozliczanie nie może zależeć od klucza, którego jedna ze ścieżek nie używa.

PO CO: `update_pending` wychodziło od razu, gdy brakowało `APISPORTS_KEY` —
mimo że fallback FlashScore (`get_match_result`) klucza nie potrzebuje wcale.
Konto API-Football zostało zawieszone 01.08.2026, więc to właśnie FlashScore
jest dziś jedyną działającą drogą do wyników. Usunięcie martwego klucza z env
— czyli sensowna reakcja na zawieszenie — zatrzymałoby rozliczanie CAŁKOWICIE:
predykcje zostają z `tip_correct = NULL`, licznik rozliczonych stoi, a
`porownaj_modele` nigdy nie wyda werdyktu.

Cisza bez wyjątku: funkcja zwraca `{"updated": 0, ...}`, więc wygląda to jak
„nie było czego rozliczać".
"""
from __future__ import annotations

import pytest

from footstats.scrapers import results_updater as ru


@pytest.fixture
def bez_klucza(monkeypatch):
    monkeypatch.setattr(ru, "_get_api_key", lambda: None)


@pytest.fixture
def jedna_predykcja_do_rozliczenia(monkeypatch):
    """Mecz z wczoraj, bez wyniku — dokładnie taki, jaki czeka na rozliczenie."""
    from datetime import datetime, timedelta

    wczoraj = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    monkeypatch.setattr(
        "footstats.core.backtest.get_pending_results",
        lambda: [{
            "id": 1, "match_date": wczoraj, "league": "J1 League",
            "team_home": "Nagoya Grampus", "team_away": "Shimizu S-Pulse",
            "ai_tip": "1",
        }],
    )
    monkeypatch.setattr("footstats.core.backtest.init_db", lambda: None)


def test_brak_klucza_nie_zatrzymuje_rozliczania(
    bez_klucza, jedna_predykcja_do_rozliczenia, monkeypatch
):
    zapisane: list[tuple] = []
    monkeypatch.setattr(
        "footstats.scrapers.flashscore_results.get_match_result",
        lambda g, a, d: "2-1",
    )
    monkeypatch.setattr(
        "footstats.core.backtest.update_result",
        lambda pid, wynik, stats=None: zapisane.append((pid, wynik)) or {"tip_correct": 1},
    )
    monkeypatch.setattr(ru, "_znajdz_wynik", lambda *a, **kw: None)

    raport = ru.update_pending(days_back=2, verbose=False)

    assert raport["updated"] == 1, f"rozliczanie stanelo bez klucza: {raport}"
    assert zapisane == [(1, "2-1")]


def test_bez_klucza_nie_bijemy_do_api_football(
    bez_klucza, jedna_predykcja_do_rozliczenia, monkeypatch
):
    """Zapytanie bez klucza to pewne 401 i zmarnowany czas — ma nie polecieć."""
    def _wybuch(*a, **kw):
        raise AssertionError("API-Football odpytane mimo braku klucza")

    monkeypatch.setattr(ru, "_fetch_fixtures_by_date", _wybuch)
    monkeypatch.setattr(ru, "_fetch_fixtures", _wybuch)
    monkeypatch.setattr(
        "footstats.scrapers.flashscore_results.get_match_result",
        lambda g, a, d: None,
    )

    raport = ru.update_pending(days_back=2, verbose=False)

    assert raport["not_found"] == 1


def test_z_kluczem_api_dalej_ma_pierwszenstwo(
    jedna_predykcja_do_rozliczenia, monkeypatch
):
    """API daje statystyki (rożne, kartki), których scraper nie ma — nie cofamy tego."""
    monkeypatch.setattr(ru, "_get_api_key", lambda: "klucz")
    monkeypatch.setattr(ru, "_fetch_fixtures_by_date", lambda k, d: [{"x": 1}])
    monkeypatch.setattr(ru, "_znajdz_wynik", lambda *a, **kw: ("3-0", {"hc": 5}))
    zapisane: list[tuple] = []
    monkeypatch.setattr(
        "footstats.core.backtest.update_result",
        lambda pid, wynik, stats=None: zapisane.append((pid, wynik, stats))
        or {"tip_correct": 1},
    )

    raport = ru.update_pending(days_back=2, verbose=False)

    assert raport["updated"] == 1
    assert zapisane[0][1] == "3-0"
    assert zapisane[0][2] == {"hc": 5}
