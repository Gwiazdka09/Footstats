"""Gdy JSON od modelu nie parsuje sie, log ma powiedziec DLACZEGO.

ZMIERZONE 01.09 (`footstats-final-5rz25`, obraz z whitelista rynkow):

    [AI] Nie udalo sie sparsowac JSON z odpowiedzi modelu — przebieg NIE zapisze
    zadnych predykcji. Poczatek odpowiedzi: {   "top3": [     {  "mecz":
    "FC Zurich vs BSC Young Boys", "typ": "2", "kurs": 1.57, "pewnosc_pct": 55,

Z tego nie da sie orzec niczego. Dwie zupelnie rozne przyczyny wygladaja
identycznie na pierwszych 200 znakach:

  * odpowiedz URWANA        -> nawiasy niezbilansowane, `finish_reason='length'`,
                               naprawa: budzet wyjscia albo kontynuacja
  * odpowiedz USZKODZONA    -> nawiasy zbilansowane, smiec w srodku lub wokol,
                               naprawa: prompt / parser

W tym przebiegu kontynuacja po urwaniu NIE odpalila (jest podpieta pod
`finish_reason == "length"`, a w logach nie ma po niej sladu), wiec urwanie
limitem jest malo prawdopodobne — ale bez licznika nawiasow to dalej domysl.
Trzy razy tego dnia zgadywalem przyczyne i trzy razy pomiar ja obalil.
"""
from __future__ import annotations

import logging

import pytest

from footstats.ai.analyzer_helpers import _wyciagnij_json


def _log(caplog) -> str:
    return " ".join(r.getMessage() for r in caplog.records)


@pytest.fixture
def smiec(caplog):
    caplog.set_level(logging.ERROR)
    return caplog


def test_log_podaje_KONCOWKE_a_nie_tylko_poczatek(smiec):
    """Uszkodzenie siedzi zwykle na koncu — poczatek zawsze wyglada poprawnie."""
    tekst = '{"top3": [{"mecz": "A vs B", "typ": "1"' + ", x" * 300 + "ZNACZNIK_KONCA"

    _wyciagnij_json(tekst)

    assert "ZNACZNIK_KONCA" in _log(smiec), "log nie pokazuje konca odpowiedzi"


def test_log_podaje_bilans_nawiasow(smiec):
    """Niezbilansowane = urwanie. Zbilansowane = uszkodzenie. Rozne naprawy."""
    tekst = "{" * 3 + "nie-json" + "}" * 1

    _wyciagnij_json(tekst)

    tekst_logu = _log(smiec)
    assert "3" in tekst_logu and "1" in tekst_logu, (
        f"log nie niesie licznika nawiasow: {tekst_logu}"
    )


def test_log_podaje_dlugosc(smiec):
    tekst = "!" * 4321

    _wyciagnij_json(tekst)

    assert "4321" in _log(smiec)


def test_poczatek_dalej_jest_w_logu(smiec):
    """Kontrola negatywna: dokladamy koncowke, nie podmieniamy poczatku."""
    _wyciagnij_json("ZNACZNIK_POCZATKU" + "?" * 400)

    assert "ZNACZNIK_POCZATKU" in _log(smiec)


def test_poprawny_json_nie_loguje_bledu(smiec):
    """Kontrola negatywna: nowy log nie moze odpalac sie na zdrowej sciezce."""
    wynik = _wyciagnij_json('{"top3": [], "ostrzezenia": "ok"}')

    assert wynik["ostrzezenia"] == "ok"
    assert not smiec.records, f"blad zalogowany mimo poprawnego JSON: {_log(smiec)}"
