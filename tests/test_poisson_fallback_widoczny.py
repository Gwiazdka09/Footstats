"""Potok melduje „Poisson-DC", a liczy Bzzoiro — i nikt się o tym nie dowiaduje.

ZMIERZONE 25.08.2026 na produkcji, z `model_log.model_source` (etykieta jest
per mecz i uczciwa — `quick_picks.py:336`):

    2026-08-25  poisson=  2  bzzoiro= 19  ->  Poisson tylko 9%
    2026-08-24  poisson=  7  bzzoiro= 18  ->  28%
    2026-08-23  poisson= 19  bzzoiro= 29  ->  39%
    2026-08-20  poisson= 11  bzzoiro= 38  ->  22%

Tymczasem `cloud_draft._wykryj_model_source()` zwraca „poisson-dc", bo sprawdza
JEDYNIE, czy parquet się ładuje. Odpowiedź `/cron/draft` mówi więc
`model_source: poisson-dc`, podczas gdy trzy czwarte meczów policzył fallback.

DLACZEGO NIKT TEGO NIE WIDZI: blend siedzi w `try`, którego handler to gołe
`pass  # Poisson niedostępny → zostaw Bzzoiro`. Brak historii dla pary (normalne)
wygląda identycznie jak wyjątek w naszym kodzie (bug). Ten sam kształt, który
w tym projekcie kosztował już tygodnie — komentarz przy tym samym pliku mówi
wprost: „Poisson był CICHO pomijany, fallback na Bzzoiro-ML (nasz model nie
działał live!)". Naprawiono wtedy JEDNĄ przyczynę, ale nie ciszę.

CZEGO WYMAGAMY: nie alarmu przy każdym meczu — pojedyncza para bez historii to
stan normalny i log przy każdej z nich byłby szumem. Wymagamy PODSUMOWANIA
przebiegu: ile meczów policzył Poisson, ile fallback, i z jakich powodów.
Jedna linijka, z której od razu widać różnicę między „brak historii dla 3 par"
a „wszystko leci na fallbacku".
"""
from __future__ import annotations

import logging

import pytest

from footstats.core import quick_picks as qp


def test_podsumowanie_liczy_oba_modele(caplog):
    """Jedna linijka na przebieg — ile Poisson, ile fallback."""
    with caplog.at_level(logging.WARNING, logger=qp.log.name):
        qp.raport_pokrycia_poissona(blended=2, razem=21, powody={})

    tresc = " ".join(r.getMessage() for r in caplog.records)
    assert tresc, "przebieg z 9% Poissona nie zostawil sladu"
    assert "2" in tresc and "21" in tresc, f"brak liczb w logu: {tresc}"


def test_powody_fallbacku_sa_w_logu(caplog):
    """Bez powodu nie odróżnisz braku historii od wyjątku w naszym kodzie."""
    with caplog.at_level(logging.WARNING, logger=qp.log.name):
        qp.raport_pokrycia_poissona(
            blended=1, razem=10, powody={"KeyError": 6, "ValueError": 3},
        )

    tresc = " ".join(r.getMessage() for r in caplog.records)
    assert "KeyError" in tresc, f"log nie podaje powodow: {tresc}"
    assert "6" in tresc


def test_pelne_pokrycie_nie_generuje_szumu(caplog):
    """Gdy Poisson policzył wszystko, nie ma o czym pisać."""
    with caplog.at_level(logging.WARNING, logger=qp.log.name):
        qp.raport_pokrycia_poissona(blended=21, razem=21, powody={})

    assert not caplog.records, [r.getMessage() for r in caplog.records]


def test_pusty_przebieg_nie_dzieli_przez_zero():
    """Brak kandydatów (off-season, padniete zrodlo) to nie jest awaria Poissona."""
    qp.raport_pokrycia_poissona(blended=0, razem=0, powody={})


@pytest.mark.parametrize("blended,razem,ma_krzyczec", [
    (0, 20, True),    # kompletny fallback — najgrozniejszy stan
    (2, 21, True),    # realny stan produkcji 25.08
    (20, 20, False),  # pelne pokrycie
])
def test_prog_krzyku(blended: int, razem: int, ma_krzyczec: bool, caplog):
    with caplog.at_level(logging.WARNING, logger=qp.log.name):
        qp.raport_pokrycia_poissona(blended=blended, razem=razem, powody={})

    assert bool(caplog.records) is ma_krzyczec
