"""Odmowa LLM-a i awaria LLM-a to dwie rozne rzeczy — log ma je rozroznic.

Zmierzone 31.08 sonda na realnym prompcie kuponu. Model NIE byl zepsuty:
oddal kompletny, poprawny JSON i swiadomie odmowil budowy kuponu, podajac powod:

    "top3": [],
    "kupon_a": {"zdarzenia": [], "ryzyko_ogolne": "Brak wystarczajacych danych
      — jedyny dostepny mecz nie spelnia wymogow minimalnej pewnosci"},
    "ostrzezenia": "pewnosc (52% dla 1) jest nizsza niz wymog 60% dla
      pojedynczej nogi. Nie mozna wiec skonstruowac zadnego sensownego kuponu."

Regula `Every leg: pewnosc_pct >= 60%` stoi w SYSTEM_TYPER_BAZA. Kandydaci po
filtrach wartosci mieli `pw` okolo 52%, wiec zaden nie kwalifikowal sie.

A log mowil:

    [AI] Model jezykowy nie zwrocil typow — 1 typow zbudowanych z modelu

...czyli brzmial jak awaria warstwy LLM. Ten sam ksztalt bledu, co reszta
znalezisk tej sesji: jeden sygnal na dwa rozne stany. Kosztowal wieczor
szukania zepsucia tam, gdzie kod dzialal poprawnie.

Prog 60% NIE jest tu zmieniany. To decyzja o strategii zakladow, nie o kodzie.
"""
from __future__ import annotations

import logging

import pytest

from footstats.ai import analyzer as an


@pytest.fixture(autouse=True)
def _typy_z_modelu_wlaczone(monkeypatch):
    from footstats import config as cfg
    monkeypatch.setattr(cfg, "TYPY_BEZ_LLM", True)
    monkeypatch.setattr(an, "zbuduj_typy_z_modelu",
                        lambda w: [{"mecz": "A - B", "typ": "1", "kurs": 1.9}])


_POWOD = ("pewnosc (52% dla 1) jest nizsza niz wymog 60% dla pojedynczej nogi")


def test_odmowa_NIE_jest_raportowana_jak_awaria(caplog):
    """Poprawny JSON z pustym `top3` to decyzja modelu, nie jego padniecie."""
    dane = {"top3": [], "ostrzezenia": _POWOD}

    with caplog.at_level(logging.DEBUG):
        an._dopisz_typy_z_modelu(dane, [{}], odmowa_llm=True)

    ostrzezenia = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert not ostrzezenia, (
        f"odmowa nie moze byc WARNING — jest: {[r.getMessage() for r in ostrzezenia]}"
    )


def test_powod_odmowy_trafia_do_logu(caplog):
    """Bez powodu zostaje samo 'brak typow', a to nie mowi, czy szukac buga."""
    dane = {"top3": [], "ostrzezenia": _POWOD}

    with caplog.at_level(logging.INFO):
        an._dopisz_typy_z_modelu(dane, [{}], odmowa_llm=True)

    assert "60%" in caplog.text or "pewnosc" in caplog.text.lower()


def test_niesparsowana_odpowiedz_DALEJ_jest_ostrzezeniem(caplog):
    """Awaria warstwy LLM zostaje glosna — tak wykryto 404 z 22.08."""
    dane = {"_raw": "jakis smiec bez JSON-a"}

    with caplog.at_level(logging.WARNING):
        an._dopisz_typy_z_modelu(dane, [{}], odmowa_llm=False)

    assert [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_domyslnie_zachowanie_bez_zmian(caplog):
    """Wolajacy, ktory nie przekaze rozroznienia, dostaje stare ostrzezenie."""
    with caplog.at_level(logging.WARNING):
        an._dopisz_typy_z_modelu({}, [{}])

    assert [r for r in caplog.records if r.levelno >= logging.WARNING]


@pytest.mark.parametrize("odmowa", [True, False])
def test_typy_z_modelu_powstaja_w_OBU_przypadkach(odmowa):
    """Kontrola: rozroznienie dotyczy logu, nie tego, czy typy powstaja."""
    dane: dict = {"top3": []} if odmowa else {}

    assert an._dopisz_typy_z_modelu(dane, [{}], odmowa_llm=odmowa) == 1
    assert len(dane["top3"]) == 1


def test_nota_o_pochodzeniu_typow_zostaje_w_obu(caplog):
    """`ostrzezenia` musi dalej mowic, ze typy sa z modelu — to jedyny slad
    w zapisanym kuponie."""
    dane = {"top3": [], "ostrzezenia": _POWOD}
    an._dopisz_typy_z_modelu(dane, [{}], odmowa_llm=True)

    assert "bez udzialu LLM" in dane["ostrzezenia"]
    assert _POWOD in dane["ostrzezenia"], "powod odmowy nie moze zniknac"
