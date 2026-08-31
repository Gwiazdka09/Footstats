"""Dwie sciezki, ktore deklaruja odpornosc, ale jej nie mialy.

Obie zlapane 31.08 przy odpalaniu realnej analizy lokalnie — nie z przegladu
kodu, tylko dlatego, ze wywalily przebieg.

1. `_pobierz_podobne_mecze` ma w komentarzu wprost: "RAG jest opcjonalny, nie
   blokuje predykcji". Ale lapal tylko ImportError/KeyError/AttributeError/
   TypeError, a `utils.db.connect()` przy niedostepnej bazie rzuca RuntimeError.
   Padnieta baza zabijala CALA analize, mimo ze RAG to dodatek per-mecz.

2. `_wymusz_40pct` czyta `dane.get("kupon_a", {})`. Wartosc domyslna dziala
   tylko wtedy, gdy klucza NIE MA. Model jezykowy potrafi zwrocic klucz
   obecny z wartoscia `null` — wtedy `.get` na None wywala AttributeError.
   Zmierzone: przy jednym kandydacie gpt-oss-120b oddal `kupon_c` z pustymi
   polami i przebieg padl.

Obie to ten sam ksztalt: intencja opisana w komentarzu, kod jej nie dowozi.
"""
from __future__ import annotations

import logging

import pytest

from footstats.ai import analyzer as an
from footstats.ai.analyzer_helpers import _wymusz_40pct


# ── RAG nie moze zabic przebiegu ────────────────────────────────────────────

@pytest.mark.parametrize("wyjatek", [
    RuntimeError("DATABASE_URL env var not set"),
    OSError("connection refused"),
    ImportError("brak modulu"),
])
def test_awaria_rag_nie_zatrzymuje_analizy(monkeypatch, wyjatek):
    """Kazdy z tych bledow realnie wychodzi z warstwy bazy."""
    def _wybuch(*a, **k):
        raise wyjatek

    monkeypatch.setattr(
        "footstats.ai.post_match_analyzer.pobierz_ostatnie_wnioski", _wybuch)

    assert an._pobierz_podobne_mecze("Arsenal", "Chelsea") == ""


def test_awaria_rag_zostawia_slad(monkeypatch, caplog):
    """Cisza tez nie — to ma byc widoczne w debugu, nie zniknac."""
    def _wybuch(*a, **k):
        raise RuntimeError("baza padla")

    monkeypatch.setattr(
        "footstats.ai.post_match_analyzer.pobierz_ostatnie_wnioski", _wybuch)

    with caplog.at_level(logging.DEBUG):
        an._pobierz_podobne_mecze("Arsenal", "Chelsea")

    assert "Arsenal" in caplog.text


# ── kupon = null nie moze wywracac walidacji ────────────────────────────────

def test_kupon_o_wartosci_null_nie_wywraca_walidacji():
    """Klucz OBECNY z wartoscia None — `dict.get(k, {})` tego nie ratuje."""
    dane = {"kupon_a": None, "kupon_b": None}
    _wymusz_40pct(dane, min_szansa=40.0)   # nie moze rzucic


def test_brak_klucza_kuponu_dalej_dziala():
    _wymusz_40pct({}, min_szansa=40.0)


def test_poprawny_kupon_dalej_jest_przycinany():
    """Kontrola: naprawa nie moze wylaczyc wlasciwej logiki."""
    dane = {"kupon_a": {"zdarzenia": [
        {"mecz": "A - B", "typ": "1", "kurs": 2.0, "pewnosc_pct": 50},
        {"mecz": "C - D", "typ": "1", "kurs": 2.0, "pewnosc_pct": 50},
    ]}}
    _wymusz_40pct(dane, min_szansa=40.0)
    # 0.5 * 0.5 = 25% < 40% → najslabsza noga ma wypasc
    assert len(dane["kupon_a"]["zdarzenia"]) == 1
