"""Niedostępne AI nie może kasować całego dziennego przebiegu.

PO CO: `footstats-final` padł 09.08.2026 dwa razy, bo Groq odmówił (413), Ollamy
w kontenerze nie ma, a `zapytaj_ai` słusznie rzuca `RuntimeError`. Tyle że nikt
go nie łapał — `exit(1)`, job oznaczony jako nieudany.

To boli podwójnie, bo kroki PRZED Groqiem już się wykonały i zapisały:
rozliczenie wyników, analiza porażek (lekcje), kupony System paper-trading.
Przerwanie wyrzuca do kosza informację, że one się udały, i zostawia pipeline
w stanie „dzień nieudany", choć paliwo do nauki właśnie przybyło.

Reguła: brak warstwy AI degraduje przebieg do części modelowej — GŁOŚNO
(ERROR w logu), ale bez zabijania procesu.
"""
from __future__ import annotations

import pytest

from footstats import daily_agent


def test_brak_ai_nie_wyrzuca_wyjatku_do_gory(monkeypatch):
    """SEDNO: `RuntimeError` z warstwy AI ma sie zatrzymac tutaj."""
    def _brak_ai(*a, **kw):
        raise RuntimeError("Brak dostępnego AI. Sprawdź: 1. Klucz GROQ_API_KEY")

    monkeypatch.setattr("footstats.ai.analyzer.ai_analiza_pewniaczki", _brak_ai)
    monkeypatch.setattr("footstats.ai.analyzer.ai_groq_dostepny", lambda: True)

    wynik = daily_agent._analizuj_groq([{"gospodarz": "Legia", "goscie": "Lech"}])

    assert wynik == {}, "brak AI ma dac pusty wynik, nie wyjatek"


def test_awaria_ai_jest_zglaszana_glosno(monkeypatch, caplog):
    """Cicha degradacja jest gorsza od awarii — musi zostac slad."""
    def _brak_ai(*a, **kw):
        raise RuntimeError("Brak dostępnego AI")

    monkeypatch.setattr("footstats.ai.analyzer.ai_analiza_pewniaczki", _brak_ai)
    monkeypatch.setattr("footstats.ai.analyzer.ai_groq_dostepny", lambda: True)

    with caplog.at_level("ERROR"):
        daily_agent._analizuj_groq([{"gospodarz": "Legia", "goscie": "Lech"}])

    assert any("AI" in r.message.upper() for r in caplog.records), "brak sladu w logu"


def test_dzialajace_ai_zwraca_swoj_wynik(monkeypatch):
    """Degradacja nie moze przeslonic normalnej sciezki."""
    monkeypatch.setattr("footstats.ai.analyzer.ai_analiza_pewniaczki",
                        lambda *a, **kw: {"top3": [{"mecz": "Legia vs Lech"}]})
    monkeypatch.setattr("footstats.ai.analyzer.ai_groq_dostepny", lambda: True)

    wynik = daily_agent._analizuj_groq([{"gospodarz": "Legia", "goscie": "Lech"}])

    assert wynik["top3"]


@pytest.mark.parametrize("wyjatek", [OSError("siec"), ValueError("zly json")])
def test_inne_awarie_warstwy_ai_tez_degraduja(monkeypatch, wyjatek):
    """Nie tylko RuntimeError — kazda awaria AI ma konczyc sie degradacja."""
    def _wybuch(*a, **kw):
        raise wyjatek

    monkeypatch.setattr("footstats.ai.analyzer.ai_analiza_pewniaczki", _wybuch)
    monkeypatch.setattr("footstats.ai.analyzer.ai_groq_dostepny", lambda: True)

    assert daily_agent._analizuj_groq([{"gospodarz": "Legia"}]) == {}
