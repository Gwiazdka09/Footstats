"""Kalibracja i Kelly potrafiły zniknąć bez słowa, zmieniając stawki.

`_dodaj_kelly` ma trzy milczące handlery i każdy zmienia PIENIĄDZE na kuponie:

1. `except ImportError: return` — gdy nie wstanie `kelly` albo `calibration`,
   funkcja wychodzi i ŻADNE zdarzenie nie dostaje `kelly_stake`. Kupon powstaje
   normalnie, tylko bez wyliczonej stawki.
2. `except ImportError: calibrate_confidence = lambda pct: pct / 100.0` — cicha
   podmiana kalibracji na funkcję tożsamościową. Pewności przestają być
   kalibrowane, stawki się zmieniają, w logu ani słowa.
3. `except (TypeError, ZeroDivisionError): z["kelly_stake"] = 1.0` (dwa razy) —
   błędny kurs albo pewność dostaje stawkę 1.0 PLN i wygląda jak świadoma decyzja.

Wszystkie trzy to ten sam wzorzec, który 24-25.08 wyszedł w tym projekcie
wielokrotnie: system robi dokładnie to, co ma zrobić, wynik jest inny niż
zakładamy, i nikt się nie dowiaduje.

Wymagamy logu, nie zmiany zachowania — fallbacki zostają, bo kupon bez stawki
jest lepszy niż brak kuponu. Chodzi o to, żeby dało się to zobaczyć w Cloud
Logging zamiast zgadywać, czemu stawki wyglądają dziwnie.
"""
from __future__ import annotations

import logging
import sys

import pytest

from footstats.core import daily_phases as dp


def test_kalibrator_dziala_normalnie():
    """Ścieżka zdrowa: prawdziwy kalibrator, zero szumu w logu."""
    fn = dp._kalibrator_pewnosci()

    assert callable(fn)
    assert 0.0 <= fn(60) <= 1.0


def test_brak_kalibratora_jest_glosny(monkeypatch, caplog):
    """Podmiana na tożsamość musi zostawić ślad — inaczej stawki cicho się zmieniają."""
    monkeypatch.setitem(sys.modules, "footstats.core.probability_calibrator", None)

    with caplog.at_level(logging.WARNING, logger=dp.log.name):
        fn = dp._kalibrator_pewnosci()

    assert fn(60) == pytest.approx(0.6), "fallback ma dzialac, nie tylko krzyczec"
    assert caplog.records, "kalibracja podmieniona po cichu"
    tresc = " ".join(r.getMessage() for r in caplog.records).lower()
    assert "kalibr" in tresc, tresc


def test_zdrowa_sciezka_nie_loguje(caplog):
    """Log przy każdym przebiegu przestaje cokolwiek znaczyć."""
    with caplog.at_level(logging.WARNING, logger=dp.log.name):
        dp._kalibrator_pewnosci()

    assert not caplog.records, [r.getMessage() for r in caplog.records]


# ── nieudane wyliczenie stawki ─────────────────────────────────────────────

def test_bledna_stawka_dostaje_wartosc_awaryjna_i_log(caplog):
    """1.0 PLN po błędzie wygląda jak decyzja modelu — musi być odróżnialne."""
    def _wybuch(*a, **k):
        raise ZeroDivisionError("kurs 0")

    with caplog.at_level(logging.WARNING, logger=dp.log.name):
        wynik = dp._bezpieczny_kelly(_wybuch, 0.5, 0.0, 100.0)

    assert wynik == 1.0
    assert caplog.records, "stawka awaryjna zapisana bez sladu"


def test_poprawna_stawka_bez_logu(caplog):
    with caplog.at_level(logging.WARNING, logger=dp.log.name):
        wynik = dp._bezpieczny_kelly(lambda p, o, bankroll: 12.5, 0.6, 2.0, 100.0)

    assert wynik == 12.5
    assert not caplog.records
