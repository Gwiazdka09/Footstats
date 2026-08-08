"""Brak `sentence-transformers` ma degradować wyszukiwanie, nie kasować lekcje.

PO CO: `retrieve_relevant_lessons` łapało `(OSError, ValueError, TypeError)`,
a brak modułu rzuca `ImportError` — więc wyjątek leciał do `analyzer.py`, gdzie
`except (ImportError, ...)` przerywał CAŁY blok feedbacku. Efekt na produkcji
(obrazy nie mają sentence-transformers): prompt Groqa nie dostawał ani lekcji
semantycznych, ani chronologicznych z `pobierz_ostatnie_wnioski` — mimo że ten
drugi tor nie potrzebuje żadnej dodatkowej zależności. 128 lekcji w bazie
i zero w prompcie.

DECYZJA (09.08.2026): nie dokładamy sentence-transformers do obrazów — model
ciągnie za sobą torch, czyli gigabajty i dłuższy zimny start Cloud Run, dla 128
krótkich tekstów. Wyszukiwanie semantyczne zostaje jako opcja lokalna; produkcja
jedzie na lekcjach chronologicznych. Degradacja ma być PRAWDZIWA, nie pozorna.
"""
from __future__ import annotations

import builtins

import pytest

from footstats.ai import rag


@pytest.fixture
def bez_sentence_transformers(monkeypatch):
    """Symuluje obraz produkcyjny: modułu po prostu nie ma."""
    prawdziwy_import = builtins.__import__

    def _import(nazwa, *a, **kw):
        if nazwa.startswith("sentence_transformers"):
            raise ImportError("No module named 'sentence_transformers'")
        return prawdziwy_import(nazwa, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", _import)
    monkeypatch.setattr("footstats.ai.rag_embeddings._EMBEDDING_MODEL", None,
                        raising=False)


def test_brak_modelu_zwraca_pusta_liste_zamiast_wyjatku(bez_sentence_transformers):
    wynik = rag.retrieve_relevant_lessons("Liga: Bundesliga | Markety: 1X2")

    assert wynik == []


def test_wolajacy_dostaje_lekcje_chronologiczne(bez_sentence_transformers, monkeypatch):
    """Sedno regresji: fallback z `analyzer.py` musi byc OSIAGALNY.

    Odtwarzamy dokladnie te dwie linie — semantyczne, a jak pusto, to ostatnie.
    """
    monkeypatch.setattr(
        "footstats.ai.post_match_analyzer.pobierz_ostatnie_wnioski",
        lambda n: ["Za wysoka pewnosc na wyjazdach", "Longshot zjadl EV"],
    )
    from footstats.ai.post_match_analyzer import pobierz_ostatnie_wnioski

    lekcje = rag.retrieve_relevant_lessons("Liga: Bundesliga", k=3, min_score=0.3)
    wnioski = ([x["reason_for_failure"] for x in lekcje] if lekcje
               else pobierz_ostatnie_wnioski(3))

    assert len(wnioski) == 2
    assert "Longshot zjadl EV" in wnioski


def test_pusty_kontekst_nie_bije_do_bazy(monkeypatch):
    """Zapytanie bez tresci nie ma czego szukac — i nie ma po co budzic modelu."""
    def _wybuch():
        raise AssertionError("model nie powinien byc ladowany dla pustego kontekstu")

    monkeypatch.setattr("footstats.ai.rag_embeddings._get_embedding_model", _wybuch)

    assert rag.retrieve_relevant_lessons("   ") == []
