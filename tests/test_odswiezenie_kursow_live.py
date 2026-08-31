"""KROK 3b: odswiezenie kursow tuz przed weryfikacja anty-halucynacyjna.

31.08 produkcja zaraportowala `Odswiezono kursy LIVE: 0/46 meczow
zaktualizowanych` — i nie dalo sie z tego wyczytac, czy to sukces czy awaria.
Zero znaczylo naraz TRZY rzeczy:

  a) zrodlo oddalo pusta liste (Bzzoiro padlo)          → AWARIA
  b) zaden klucz nie trafil w indeks (rozjazd nazw)     → AWARIA
  c) kursy sie po prostu nie ruszyly w trakcie przebiegu → PRAWDA

Ten sam ksztalt bledu, ktory ten projekt mierzyl juz przy `Final enrichment:
0/N` i przy wycofanym modelu Groqa: wartosc znaczy dwie rzeczy, a cisza czyni
je nierozroznialnymi. Funkcja nie miala ZADNEGO testu.
"""
from __future__ import annotations

import logging

import pytest

from footstats import daily_agent as da
from footstats.scrapers.bzzoiro import ENV_BZZOIRO


def _indeks(*pary):
    return {(da._norm(g), da._norm(a)): {
        "odds": {"home": 2.0, "draw": 3.4, "away": 3.6},
        "gospodarz": g, "goscie": a, "liga": "PL", "pred": {}, "data": "2026-08-31",
    } for g, a in pary}


@pytest.fixture(autouse=True)
def _klucz(monkeypatch):
    monkeypatch.setenv(ENV_BZZOIRO, "test-key")

    class _Klient:
        _valid = True

        def __init__(self, *a, **k):
            pass

        def waliduj(self):
            return True, "ok"

    monkeypatch.setattr("footstats.scrapers.bzzoiro.BzzoiroClient", _Klient)


def _podstaw_fresh(monkeypatch, fresh):
    monkeypatch.setattr("footstats.core.quick_picks.szybkie_pewniaczki_2dni",
                        lambda *a, **k: fresh)


def test_zmieniony_kurs_trafia_do_indeksu(monkeypatch):
    idx = _indeks(("Arsenal", "Chelsea"))
    _podstaw_fresh(monkeypatch, [
        {"gospodarz": "Arsenal", "goscie": "Chelsea",
         "odds": {"home": 1.85, "draw": 3.5, "away": 4.2}},
    ])

    out = da._odswiez_kursy_live(idx)

    assert out[(da._norm("Arsenal"), da._norm("Chelsea"))]["odds"]["home"] == 1.85


def test_identyczne_kursy_to_NIE_alarm(monkeypatch, caplog):
    """Rynek stoi — to normalny stan, nie awaria. Ostrzezenie tutaj byloby
    szumem, a szum zabija alarmy tak samo skutecznie jak cisza."""
    idx = _indeks(("Arsenal", "Chelsea"))
    _podstaw_fresh(monkeypatch, [
        {"gospodarz": "Arsenal", "goscie": "Chelsea",
         "odds": {"home": 2.0, "draw": 3.4, "away": 3.6}},
    ])

    with caplog.at_level(logging.WARNING):
        da._odswiez_kursy_live(idx)

    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_puste_zrodlo_jest_glosne(monkeypatch, caplog):
    """Bzzoiro oddalo zero meczow — to awaria, a wygladala jak `0/46`."""
    idx = _indeks(("Arsenal", "Chelsea"), ("Ajax", "PSV"))
    _podstaw_fresh(monkeypatch, [])

    with caplog.at_level(logging.WARNING):
        da._odswiez_kursy_live(idx)

    assert [r for r in caplog.records if r.levelno >= logging.WARNING], (
        "puste zrodlo musi byc odroznialne od braku ruchu na kursach"
    )


def test_zaden_klucz_nie_pasuje_jest_glosne(monkeypatch, caplog):
    """Zrodlo zylo, ale nazwy sie rozjechaly — cichy zabojca `Final enrichment`."""
    idx = _indeks(("Arsenal", "Chelsea"))
    _podstaw_fresh(monkeypatch, [
        {"gospodarz": "Zupelnie", "goscie": "Inne", "odds": {"home": 1.5}},
        {"gospodarz": "Tez", "goscie": "Inne", "odds": {"home": 2.5}},
    ])

    with caplog.at_level(logging.WARNING):
        da._odswiez_kursy_live(idx)

    assert [r for r in caplog.records if r.levelno >= logging.WARNING], (
        "rozjazd nazw musi byc odroznialny od braku ruchu na kursach"
    )


def test_czesciowe_dopasowanie_nie_alarmuje(monkeypatch, caplog):
    """Okno 72h lapie mecze spoza indeksu — dopoki cokolwiek trafilo, jest OK."""
    idx = _indeks(("Arsenal", "Chelsea"))
    _podstaw_fresh(monkeypatch, [
        {"gospodarz": "Arsenal", "goscie": "Chelsea", "odds": {"home": 2.0}},
        {"gospodarz": "Spoza", "goscie": "Indeksu", "odds": {"home": 1.4}},
    ])

    with caplog.at_level(logging.WARNING):
        da._odswiez_kursy_live(idx)

    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_pusty_kurs_nie_kasuje_starego(monkeypatch):
    """Brak kursu w swiezym wyniku nie moze wyczyscic dzialajacego starego."""
    idx = _indeks(("Arsenal", "Chelsea"))
    _podstaw_fresh(monkeypatch, [
        {"gospodarz": "Arsenal", "goscie": "Chelsea", "odds": {}},
    ])

    out = da._odswiez_kursy_live(idx)

    assert out[(da._norm("Arsenal"), da._norm("Chelsea"))]["odds"]["home"] == 2.0


def test_pusty_indeks_nie_alarmuje(monkeypatch, caplog):
    """Nie ma czego odswiezac — brak kandydatow zglasza wczesniejszy krok."""
    _podstaw_fresh(monkeypatch, [])

    with caplog.at_level(logging.WARNING):
        da._odswiez_kursy_live({})

    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
