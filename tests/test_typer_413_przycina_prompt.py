"""Wyspecjalizowany typer musi przezyc 413, tak jak przezywa go fallback.

Zmierzone 31.08 na pelnym przebiegu fazy final:

    Wyspecjalizowany typer Groq zawiodl (APIStatusError: Error code: 413 -
    Request too large for model `openai/gpt-oss-120b` ... tokens per minute
    (TPM): Limit 8000, Requested 9129) - przechodze na fallback zapytaj_ai

Kupon powstal, ale ZE SCIEZKI AWARYJNEJ. Roznica nie jest kosmetyczna: typer
dostaje prompt systemowy z kalibracja i statystykami ligowymi, fallback nie.

Dlaczego fallback przezyl, a typer nie: `client._groq` ma obsluge 413 —
przycina prompt o polowe i ponawia RAZ, z komentarzem, ze bierze odpowiedz od
zrodla prawdy zamiast ufac wlasnej arytmetyce tokenow. `_zapytaj_typera` tej
polityki nie mial, mimo ze wysyla WIEKSZY prompt (systemowy + uzytkownika).

Ten sam ksztalt co reszta znalezisk tego dnia: awaria pochlonieta przez
fallback, przebieg konczy sie sukcesem, a wynik pochodzi z gorszej sciezki.
"""
from __future__ import annotations

import logging

import pytest

from footstats.ai import analyzer as an
from footstats.ai import client as cl


class _Odpowiedz:
    def __init__(self, tresc='{"ok": 1}'):
        wybor = type("W", (), {})()
        wybor.message = type("M", (), {"content": tresc})()
        wybor.finish_reason = "stop"
        self.choices = [wybor]


class _Blad413(Exception):
    def __str__(self):
        return ("Error code: 413 - Request too large for model "
                "`openai/gpt-oss-120b` on tokens per minute (TPM): "
                "Limit 8000, Requested 9129")


@pytest.fixture
def klient(monkeypatch):
    """Groq, ktory odmawia pierwszemu (za duzemu) promptowi."""
    # Prog w ZNAKACH, a `dopasuj_do_budzetu` tnie do polowy TOKENOW: prompt
    # 10 800 znakow schodzi do ~5 400. Prog musi lezec MIEDZY nimi, inaczej
    # test mierzy wlasna arytmetyke zamiast zachowania kodu.
    stan = {"wywolania": [], "prog_znakow": 6000}

    def _create(**kw):
        stan["wywolania"].append(kw)
        uzytkownik = next(m["content"] for m in kw["messages"]
                          if m["role"] == "user")
        if len(uzytkownik) > stan["prog_znakow"]:
            raise _Blad413()
        return _Odpowiedz()

    k = type("K", (), {})()
    k.chat = type("C", (), {})()
    k.chat.completions = type("KK", (), {})()
    k.chat.completions.create = _create

    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr(an, "_get_kalibracja_blok", lambda: "")
    monkeypatch.setattr(an, "_get_liga_statystyki_blok", lambda: "")
    monkeypatch.setattr(cl, "GROQ_MODEL", "openai/gpt-oss-120b")
    monkeypatch.setitem(__import__("sys").modules, "groq",
                        type("M", (), {"Groq": staticmethod(lambda api_key: k)}))
    monkeypatch.setattr(an, "zapytaj_ai",
                        lambda *a, **kw: '{"zrodlo": "fallback"}')
    return stan


_DLUGI = "Mecz numer X: Arsenal vs Chelsea, kurs 1.85, EV +2%. " * 200


def test_413_konczy_sie_odpowiedzia_typera_a_nie_fallbackiem(klient):
    wynik = an._zapytaj_typera(_DLUGI, max_tokens=1500)

    assert "fallback" not in wynik, (
        "po 413 typer ma przyciac prompt i sprobowac jeszcze raz, nie oddawac "
        "roboty sciezce awaryjnej"
    )


def test_ponowienie_wysyla_KROTSZY_prompt(klient):
    an._zapytaj_typera(_DLUGI, max_tokens=1500)

    dlugosci = [len(next(m["content"] for m in w["messages"] if m["role"] == "user"))
                for w in klient["wywolania"]]
    assert len(dlugosci) == 2, f"oczekiwano 2 wywolan, bylo {len(dlugosci)}"
    assert dlugosci[1] < dlugosci[0]


def test_ponowienie_dzieje_sie_RAZ(klient):
    """Prompt nieprzycinalny nie moze wpasc w petle ciecia."""
    klient["prog_znakow"] = 1   # kazdy prompt za duzy

    wynik = an._zapytaj_typera(_DLUGI, max_tokens=1500)

    assert len(klient["wywolania"]) == 2, "drugie 413 ma isc na fallback, nie ciac dalej"
    assert "fallback" in wynik


def test_413_zostawia_slad_w_logu(klient, caplog):
    """Przycinanie gubi opisy meczow — to musi byc widoczne, nie ciche."""
    with caplog.at_level(logging.WARNING):
        an._zapytaj_typera(_DLUGI, max_tokens=1500)

    assert "413" in caplog.text


def test_inne_bledy_dalej_ida_na_fallback(klient, monkeypatch):
    """Kontrola: naprawa dotyczy WYLACZNIE 413. Wycofany model (404) ma dalej
    schodzic na fallback — tak dzialal ratunek z 22.08."""
    def _wybuch(**kw):
        klient["wywolania"].append(kw)
        raise RuntimeError("404 - The model `x` does not exist")

    import sys
    monkeypatch.setattr(sys.modules["groq"].Groq("k").chat.completions,
                        "create", _wybuch)

    assert "fallback" in an._zapytaj_typera("krotki", max_tokens=900)
    assert len(klient["wywolania"]) == 1, "404 nie ma byc ponawiane z ciecien"


def test_krotki_prompt_nie_jest_ruszany(klient):
    """Bez 413 nie ma ciecia — jedno wywolanie, prompt bez zmian."""
    an._zapytaj_typera("krotki prompt", max_tokens=900)

    assert len(klient["wywolania"]) == 1
    tresc = next(m["content"] for m in klient["wywolania"][0]["messages"]
                 if m["role"] == "user")
    assert tresc == "krotki prompt"
