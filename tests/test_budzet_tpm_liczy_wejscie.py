"""Sufit `max_tokens` musi znac rozmiar WEJSCIA, nie tylko wyjscia.

Zmierzone 31.08 na produkcyjnym przebiegu `footstats-final-h6gg8`:

    Typer Groq: 413 (APIStatusError) — ponawiam z promptem krotszym o polowe
    [AI] Model jezykowy nie zwrocil typow — 3 typow zbudowanych z modelu
    Faza final: kupon NIE zostal zapisany (kupon_a.zdarzenia puste)

413 przyszlo przy TRZECH kandydatach, wiec masa nie siedziala w opisach meczow.
Rozklad promptu, policzony `szacuj_tokeny`:

    SYSTEM_TYPER_BAZA                2475 tok
    kalibracja                         86 tok
    statystyki lig                    484 tok
    -------------------------------------------
    prompt systemowy RAZEM           3045 tok
    effective_max_tokens(1500)       3750 tok   <- 47% calego limitu
    -------------------------------------------
    limit TPM                        8000 tok
    zostaje na opisy meczow          1205 tok

`effective_max_tokens` liczylo sufit jako 75% TPM, patrzac WYLACZNIE na wyjscie.
Przy 3045 tokenach systemowego request wychodzil ponad limit, zanim doszedl
choc jeden mecz.

Ratunek przez przycinanie promptu uzytkownika bil w zle miejsce: wycinal opisy
meczow, czyli jedyna rzecz, ktorej model potrzebuje, i zostawial balast.
Stad "nie zwrocil typow" tuz po UDANYM ponowieniu.
"""
from __future__ import annotations

import logging

import pytest

from footstats.ai.client import AI_TPM_LIMIT, effective_max_tokens

_MODEL = "openai/gpt-oss-120b"


# ── zgodnosc wstecz ─────────────────────────────────────────────────────────

def test_bez_prompt_tokens_zachowanie_bez_zmian():
    """Wolajacy, ktory nie zna rozmiaru wejscia, dostaje to co dotad."""
    assert effective_max_tokens(500, model=_MODEL) == 1250
    assert effective_max_tokens(3000, model=_MODEL) == 6000
    assert effective_max_tokens(1500, model="llama-3.3-70b-versatile") == 1500


# ── sufit swiadomy wejscia ──────────────────────────────────────────────────

def test_wejscie_plus_wyjscie_miesci_sie_w_limicie():
    """Dokladnie przypadek z produkcji: 5379 tok wejscia przy limicie 8000."""
    wynik = effective_max_tokens(1500, model=_MODEL, prompt_tokens=5379)

    assert 5379 + wynik <= AI_TPM_LIMIT, (
        f"{5379} + {wynik} = {5379 + wynik} > {AI_TPM_LIMIT} — to jest 413"
    )


@pytest.mark.parametrize("wejscie", [1000, 2500, 4000, 5379, 6500])
def test_suma_nigdy_nie_przekracza_limitu(wejscie):
    wynik = effective_max_tokens(1500, model=_MODEL, prompt_tokens=wejscie)
    assert wejscie + wynik <= AI_TPM_LIMIT


def test_maly_prompt_nie_obcina_skalowania():
    """Naprawa nie moze zabrac budzetu tam, gdzie go nie brakuje —
    inaczej odpowiedzi zaczna sie urywac bez powodu."""
    assert (effective_max_tokens(500, model=_MODEL, prompt_tokens=200)
            == effective_max_tokens(500, model=_MODEL))


def test_jest_podloga_zeby_odpowiedz_nie_byla_smieciem():
    """Prompt niemal na caly limit: lepiej oddac odpowiedz urwana (jest
    `_kontynuuj_uciety_json`) niz zerowa albo ujemna."""
    wynik = effective_max_tokens(1500, model=_MODEL, prompt_tokens=AI_TPM_LIMIT - 10)

    assert wynik > 0, "zero albo liczba ujemna to blad API, nie oszczednosc"


def test_obciecie_zostawia_slad_w_logu(caplog):
    """Mniejszy budzet wyjscia zmienia zachowanie modelu — to musi byc
    widoczne, inaczej urwany JSON wyglada na kaprys modelu."""
    with caplog.at_level(logging.WARNING):
        effective_max_tokens(1500, model=_MODEL, prompt_tokens=6500)

    assert "budzet" in caplog.text.lower() or "tpm" in caplog.text.lower()


def test_brak_obciecia_to_brak_logu(caplog):
    with caplog.at_level(logging.WARNING):
        effective_max_tokens(500, model=_MODEL, prompt_tokens=200)

    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


# ── typer faktycznie podaje rozmiar wejscia ─────────────────────────────────

def test_typer_liczy_TAKZE_prompt_systemowy(monkeypatch):
    """Prompt systemowy to 3045 tok — pominiecie go w rachunku znaczyloby,
    ze najwiekszy skladnik nie jest liczony."""
    from footstats.ai import analyzer as an
    from footstats.ai import client as cl

    stan = {}

    class _Odp:
        def __init__(self):
            w = type("W", (), {})()
            w.message = type("M", (), {"content": "{}"})()
            w.finish_reason = "stop"
            self.choices = [w]

    def _create(**kw):
        stan.update(kw)
        return _Odp()

    k = type("K", (), {})()
    k.chat = type("C", (), {})()
    k.chat.completions = type("KK", (), {})()
    k.chat.completions.create = _create

    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr(cl, "GROQ_MODEL", _MODEL)
    monkeypatch.setattr(an, "_get_kalibracja_blok", lambda: "")
    monkeypatch.setattr(an, "_get_liga_statystyki_blok", lambda: "")
    monkeypatch.setitem(__import__("sys").modules, "groq",
                        type("M", (), {"Groq": staticmethod(lambda api_key: k)}))

    # Krotki prompt uzytkownika — caly ciezar jest po stronie systemowego.
    an._zapytaj_typera("Oceń: Arsenal vs Chelsea", max_tokens=1500)

    from footstats.ai.client import szacuj_tokeny
    wejscie = sum(szacuj_tokeny(m["content"]) for m in stan["messages"])

    assert wejscie + stan["max_tokens"] <= AI_TPM_LIMIT, (
        f"wejscie {wejscie} + wyjscie {stan['max_tokens']} przekracza {AI_TPM_LIMIT}"
    )
