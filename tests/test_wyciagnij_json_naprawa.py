"""Zepsuty JSON od Groqa kasował CAŁY dzienny przebieg — po cichu.

PRODUKCJA 15.08.2026, przebieg `footstats-final-wvjf6` (11:00): Groq zwrócił
JSON z NADMIAROWYM nawiasem zamykającym po `kupon_a`. `_wyciagnij_json` poddało
się i oddało zaślepkę `{"typ": "brak", ...}`. Ta zaślepka nie ma klucza `top3`,
więc `ai_analiza_pewniaczki` pominęło CAŁĄ gałąź: override tipu modelem, pewność
z modelu, bramki 40%, i zapis do `predictions`.

Job zakończył się `exit=0`, wysłał Telegram i zameldował „System kupony=0" —
czyli wyglądał na spokojny dzień, a nie na utratę całego przebiegu. Zero nowych
predykcji w bazie mimo 42 kandydatów i 7 po filtrach.

Kluczowa obserwacja: ten JSON DA SIĘ uratować. Nadmiarowy nawias domyka obiekt
główny za wcześnie, więc licząc głębokość nawiasów można uciąć dokładnie tam
i odzyskać `top3` (tracąc jedynie kupony po feralnym miejscu). Lepiej odzyskać
część niż wyrzucić wszystko.
"""
from __future__ import annotations

import logging

from footstats.ai.analyzer_helpers import _wyciagnij_json


def test_poprawny_json_bez_zmian():
    assert _wyciagnij_json('{"top3": [1, 2]}')["top3"] == [1, 2]


def test_json_otoczony_gadaniem_modelu():
    tekst = 'Oto moja analiza:\n{"top3": [1]}\nMam nadzieję, że pomoglem!'
    assert _wyciagnij_json(tekst)["top3"] == [1]


def test_nadmiarowy_nawias_nie_kasuje_calego_przebiegu():
    """Dokładny kształt z produkcji 15.08 — `kupon_a` domknięty dwa razy."""
    tekst = (
        '{\n'
        '  "top3": [{"mecz": "A vs B", "typ": "X", "kurs": 3.53}],\n'
        '  "kupon_a": {\n'
        '    "zdarzenia": [{"nr": 1, "mecz": "A vs B", "typ": "X"}],\n'
        '    "kurs_laczny": 3.53}\n'
        '  },\n'
        '  "kupon_b": {"zdarzenia": []}\n'
        '}'
    )
    wynik = _wyciagnij_json(tekst)
    assert "top3" in wynik, "przebieg stracilby WSZYSTKIE predykcje"
    assert wynik["top3"][0]["mecz"] == "A vs B"
    assert wynik["kupon_a"]["kurs_laczny"] == 3.53


def test_nawias_w_tekscie_nie_myli_licznika():
    """Klamra w treści uzasadnienia to nie struktura — inaczej ucięlibyśmy w złym miejscu."""
    tekst = '{"top3": [{"uzasadnienie": "forma {slaba} u gospodarza"}], "x": 1} SMIECI'
    wynik = _wyciagnij_json(tekst)
    assert wynik["x"] == 1
    assert wynik["top3"][0]["uzasadnienie"] == "forma {slaba} u gospodarza"


def test_cudzyslow_ze_znakiem_ucieczki():
    tekst = r'{"uzasadnienie": "gospodarz gra \"u siebie\"", "ok": true} nadmiar}'
    wynik = _wyciagnij_json(tekst)
    assert wynik["ok"] is True


def test_smieci_po_domknieciu_sa_odrzucane():
    assert _wyciagnij_json('{"top3": []}\n\nDodatkowo polecam...')["top3"] == []


def test_nienaprawialny_json_daje_zaslepke_i_ERROR(caplog):
    """Gdy nie da się uratować — zaślepka zostaje, ale MUSI krzyczeć w logach.

    Wcześniej ta ścieżka milczała, więc utrata całego przebiegu wyglądała
    identycznie jak dzień bez kandydatów.
    """
    with caplog.at_level(logging.ERROR, logger="footstats.ai.analyzer_helpers"):
        wynik = _wyciagnij_json("model odmowil odpowiedzi, brak jakiegokolwiek JSON")
    assert wynik["typ"] == "brak"
    assert "top3" not in wynik
    assert any("JSON" in r.message for r in caplog.records), "cicha porazka = utrata przebiegu"


def test_naprawa_zostawia_slad_w_logach(caplog):
    """Odzyskany przebieg to nadal usterka — ma być widoczna, nie zamieciona."""
    tekst = '{"top3": [{"mecz": "A vs B"}], "kupon_a": {"x": 1}\n}\n}, "kupon_b": {}}'
    with caplog.at_level(logging.WARNING, logger="footstats.ai.analyzer_helpers"):
        wynik = _wyciagnij_json(tekst)
    assert "top3" in wynik
    assert any("napraw" in r.message.lower() for r in caplog.records)


def test_pusty_tekst_nie_wywala():
    assert _wyciagnij_json("")["typ"] == "brak"
