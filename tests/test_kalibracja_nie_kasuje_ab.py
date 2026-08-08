"""Zapis kalibracji nie może kasować wyników, których nie policzył.

PO CO: `save_calibration` budowało payload od zera i nadpisywało nim CAŁY
`data/model_calibration.json`. A w tym pliku mieszkają też rzeczy z zupełnie
innych przebiegów — `ab_test_weights`, `selected_weights` (dziś 70/30 Poisson),
`calibration_note`, `per_league_notes`, `n_settled`. Jedno uruchomienie
rekalibracji λ kasowało cały ten dorobek bezpowrotnie i bez ostrzeżenia,
przez co bano się ją w ogóle odpalać — a factory siedziały na n=1996 przy
139 102 dostępnych meczach.

Klucze, które funkcja LICZY, mają się nadpisać. Reszta ma przetrwać.
"""
from __future__ import annotations

import json

import pytest

from footstats.core import lambda_optimizer as lo


@pytest.fixture
def plik_kalibracji(tmp_path, monkeypatch):
    sciezka = tmp_path / "model_calibration.json"
    sciezka.write_text(json.dumps({
        "factor_home": 0.9,
        "factor_away": 0.9,
        "n_matches": 100,
        "ab_test_weights": [{"poisson": 0.3, "bzzoiro": 0.7, "log_loss": 1.07}],
        "selected_weights": {"poisson": 0.7, "bzzoiro": 0.3},
        "calibration_note": "70/30 optymalne pod log-loss",
        "per_league_notes": "International Friendly Games: Poisson=1.00",
        "n_settled": 67,
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(lo, "CALIBRATION_PATH", sciezka)
    monkeypatch.setattr(lo, "invalidate_cache", lambda: None)
    return sciezka


def test_wyniki_ab_przezywaja_rekalibracje(plik_kalibracji):
    lo.save_calibration(bias_h=1.02, bias_a=0.98, n_matches=139102, acc_1x2=48.5)

    dane = json.loads(plik_kalibracji.read_text(encoding="utf-8"))

    assert dane["selected_weights"] == {"poisson": 0.7, "bzzoiro": 0.3}
    assert dane["ab_test_weights"][0]["log_loss"] == 1.07
    assert dane["calibration_note"].startswith("70/30")
    assert dane["per_league_notes"].startswith("International")
    assert dane["n_settled"] == 67


def test_wlasne_klucze_sa_nadpisywane(plik_kalibracji):
    """Merge nie może zamienić się w „nigdy nie aktualizuj"."""
    lo.save_calibration(bias_h=1.02, bias_a=0.98, n_matches=139102, acc_1x2=48.5)

    dane = json.loads(plik_kalibracji.read_text(encoding="utf-8"))

    assert dane["factor_home"] == 1.02
    assert dane["n_matches"] == 139102
    assert dane["acc_1x2_pct"] == 48.5


def test_brak_pliku_nie_wywala_zapisu(tmp_path, monkeypatch):
    """Pierwsze uruchomienie na czystym środowisku — po prostu tworzy plik."""
    sciezka = tmp_path / "nowy" / "model_calibration.json"
    monkeypatch.setattr(lo, "CALIBRATION_PATH", sciezka)
    monkeypatch.setattr(lo, "invalidate_cache", lambda: None)

    lo.save_calibration(bias_h=1.0, bias_a=1.0, n_matches=500)

    assert json.loads(sciezka.read_text(encoding="utf-8"))["n_matches"] == 500


def test_uszkodzony_plik_nie_blokuje_kalibracji(plik_kalibracji):
    """Nieczytelny JSON nie może zamrozić factorów na zawsze."""
    plik_kalibracji.write_text("{ to nie jest json", encoding="utf-8")

    wynik = lo.save_calibration(bias_h=1.0, bias_a=1.0, n_matches=500)

    assert wynik["n_matches"] == 500
    assert json.loads(plik_kalibracji.read_text(encoding="utf-8"))["n_matches"] == 500
