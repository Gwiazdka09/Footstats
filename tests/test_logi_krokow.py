"""Każdy krok przebiegu ma zostawiać ślad w logach strukturalnych.

DLACZEGO: joby logują w JSON, więc `gcloud logging` widzi `jsonPayload.msg`.
Separatory kroków szły WYŁĄCZNIE na konsolę (rich) — lądowały w `textPayload`,
połamane zawijaniem wierszy, nie do odpytania. 15.08 przy diagnozie cichej
awarii trzeba było czytać cały strumień oczami, bo z logów nie dało się
zapytać „które kroki się wykonały i ile trwały".

Drugi brak: `_blad` kończył proces `exit(1)` po WYDRUKU na konsolę, bez ani
jednego wpisu ERROR — awaria bez śladu dokładnie tam, gdzie się jej szuka.
"""
from __future__ import annotations

import logging

import pytest

from footstats import daily_agent_output as wy


@pytest.fixture(autouse=True)
def czysty_krok():
    wy._krok.update(nazwa=None, start=None)
    yield
    wy._krok.update(nazwa=None, start=None)


def test_sep_loguje_start_kroku(caplog):
    with caplog.at_level(logging.INFO, logger="footstats.daily_agent_output"):
        wy._sep("KROK 1 — Bzzoiro ML")
    assert "KROK START | KROK 1 — Bzzoiro ML" in caplog.text


def test_kolejny_sep_domyka_poprzedni_z_czasem(caplog):
    """Bez czasu trwania nie widać, który etap wisi — a to była realna diagnoza."""
    with caplog.at_level(logging.INFO, logger="footstats.daily_agent_output"):
        wy._sep("KROK 1")
        wy._sep("KROK 2")
    assert "KROK KONIEC | KROK 1" in caplog.text
    assert "KROK START | KROK 2" in caplog.text


def test_zamknij_krok_domyka_ostatni(caplog):
    with caplog.at_level(logging.INFO, logger="footstats.daily_agent_output"):
        wy._sep("KROK OSTATNI")
        wy.zamknij_krok()
    assert "KROK KONIEC | KROK OSTATNI" in caplog.text


def test_zamkniecie_bez_kroku_nie_wywala(caplog):
    with caplog.at_level(logging.INFO, logger="footstats.daily_agent_output"):
        wy.zamknij_krok()
    assert "KROK KONIEC" not in caplog.text


def test_podwojne_zamkniecie_nie_dubluje_wpisu(caplog):
    with caplog.at_level(logging.INFO, logger="footstats.daily_agent_output"):
        wy._sep("KROK X")
        wy.zamknij_krok()
        wy.zamknij_krok()
    assert caplog.text.count("KROK KONIEC | KROK X") == 1


def test_blad_loguje_ERROR_przed_wyjsciem(caplog):
    """Fatalny błąd szedł tylko na konsolę — w logach nie było po nim śladu."""
    with caplog.at_level(logging.ERROR, logger="footstats.daily_agent_output"):
        with pytest.raises(SystemExit):
            wy._blad("Bzzoiro nie zwrocilo kandydatow")
    assert "PRZERWANIE: Bzzoiro nie zwrocilo kandydatow" in caplog.text
