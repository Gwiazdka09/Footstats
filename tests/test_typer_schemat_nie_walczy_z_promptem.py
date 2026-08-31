"""Prompt systemowy typera nie moze narzucac schematu, ktorego wolajacy nie parsuje.

ZMIERZONE 31.08 na zywym Groqu. `SYSTEM_TYPER` konczy sie blokiem:

    JSON SCHEMA (OBOWIAZKOWY - Zwroc wylacznie JSON):
    {"typ": ..., "kurs": ..., "pewnosc_pct": ..., "risks_analysis": [...], ...}

czyli schematem POJEDYNCZEGO TYPU. Tymczasem `ai_analiza_pewniaczki` parsuje
`top3` i `kupon_a` — inny ksztalt. Dwa sprzeczne schematy w jednym wywolaniu.

Dlaczego dopiero teraz: `llama-3.1-8b-instant` slabo trzymala sie promptu
systemowego i szla za promptem uzytkownika. `gpt-oss-120b` trzyma sie
systemowego. Podmiana modelu 22.08 zmienila, KTORY prompt wygrywa — i kupony
`phase='final'` znikly (ostatni 15.08).

Zywy dowod (31.08, po naprawie nazwy modelu): na prompt zadajacy `top3`
i `kupon_a` model oddal `{"typ": "1", "kurs": 1.95, "risks_analysis": [...]}`.

Naprawiamy TYLKO zmierzona sciezke. Pozostale trzy wywolania typera
(`ai_sprawdz_kupon`, scout, superbet betbuilder) maja ten sam konflikt, ale nie
jest on zmierzony — zmiana w ciemno moglaby zepsuc to, co dzis dziala. Domyslne
zachowanie `_zapytaj_typera` zostaje nietkniete.
"""
from __future__ import annotations

import pytest

from footstats.ai import analyzer as an
from footstats.ai import prompts as pr


def test_schemat_pojedynczego_typu_jest_wydzielony():
    """Blok schematu musi dac sie wylaczyc — inaczej kazdy wolajacy dostaje go
    niezaleznie od tego, co parsuje."""
    assert hasattr(pr, "SCHEMAT_POJEDYNCZY_TYP")
    assert "risks_analysis" in pr.SCHEMAT_POJEDYNCZY_TYP


def test_baza_systemowa_NIE_zawiera_schematu_pojedynczego_typu():
    """Zasady analityczne (value betting, forma, H2H) zostaja wspolne.
    Schemat odpowiedzi — nie, bo zalezy od wolajacego."""
    assert "risks_analysis" not in pr.SYSTEM_TYPER_BAZA
    assert "VALUE BETTING" in pr.SYSTEM_TYPER_BAZA


def test_domyslne_zachowanie_typera_bez_zmian():
    """Trzy pozostale wywolania nie sa zmierzone — ich zachowanie ma zostac
    dokladnie takie, jakie bylo."""
    assert "risks_analysis" in pr.SYSTEM_TYPER


# ── wywolanie z prompt-em, ktory ma WLASNY schemat ──────────────────────────

class _Atrapa:
    def __init__(self):
        self.systemy = []
        self.chat = type("C", (), {})()
        self.chat.completions = type("K", (), {})()
        self.chat.completions.create = self._create

    def _create(self, **kw):
        self.systemy.append(kw["messages"][0]["content"])
        wybor = type("W", (), {})()
        wybor.message = type("M", (), {"content": "{}"})()
        wybor.finish_reason = "stop"
        return type("R", (), {"choices": [wybor]})()


@pytest.fixture
def atrapa(monkeypatch):
    a = _Atrapa()
    monkeypatch.setenv("GROQ_API_KEY", "test")
    monkeypatch.setattr(an, "_get_kalibracja_blok", lambda: "")
    monkeypatch.setattr(an, "_get_liga_statystyki_blok", lambda: "")

    class _Modul:
        Groq = staticmethod(lambda api_key: a)

    monkeypatch.setitem(__import__("sys").modules, "groq", _Modul)
    return a


def test_bez_schematu_prompt_systemowy_go_nie_narzuca(atrapa):
    an._zapytaj_typera("pytanie", schemat=None)
    assert "risks_analysis" not in atrapa.systemy[0]
    assert "VALUE BETTING" in atrapa.systemy[0], "zasady analityczne maja zostac"


def test_domyslnie_schemat_pojedynczego_typu_dalej_leci(atrapa):
    an._zapytaj_typera("pytanie")
    assert "risks_analysis" in atrapa.systemy[0]


def test_pewniaczki_wolaja_typera_BEZ_narzuconego_schematu(monkeypatch):
    """Sedno naprawy: to wywolanie parsuje `top3`/`kupon_a`, wiec prompt
    systemowy nie moze zadac innego ksztaltu."""
    widziane = {}

    def _szpieg(prompt, max_tokens=900, schemat="BRAK-PARAMETRU"):
        widziane["schemat"] = schemat
        return '{"top3": []}'

    monkeypatch.setattr(an, "_zapytaj_typera", _szpieg)
    monkeypatch.setattr(an, "_pobierz_podobne_mecze", lambda *a, **k: "")
    monkeypatch.setattr(an, "_auto_zapisz_backtest", lambda *a, **k: None)

    # NIEPUSTA lista: przy pustej funkcja wychodzi wczesniej i typera nie wola,
    # wiec test przechodzilby nie sprawdzajac niczego (zlapane mutacja 31.08).
    kandydaci = [{"gospodarz": "Arsenal", "goscie": "Chelsea", "liga": "ENG",
                  "pw": 52.0, "pr": 25.0, "pp": 23.0, "o25": 58.0, "bt": 55.0,
                  "kurs": 1.95, "typy": [("1", 5.0)]}]
    an.ai_analiza_pewniaczki(kandydaci, zapisz_predykcje=False)

    assert widziane.get("schemat") is None, (
        "pewniaczki musza wolac typera z schemat=None — inaczej prompt systemowy "
        "zada pojedynczego typu, a parser czeka na top3"
    )
