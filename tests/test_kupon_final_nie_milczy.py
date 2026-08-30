"""Faza final przestaje po cichu nie zapisywac kuponu.

ZMIERZONE NA PRODUKCJI 30.08. Kupony `phase='final'` w bazie: 05.08, 10.08,
15.08 — i koniec. Przez czternascie dni ANI JEDNEJ linii logu o tym, dlaczego.

Lejek z logow joba (29.08):
    Bzzoiro: 40 kandydatow w oknie 72h
    Pre-filtr lig:            40 -> 33
    Pre-filtr value bet:      33 -> 6
    Final enrichment:        0/6 kandydatow wzbogacono
    [AI] Model jezykowy nie zwrocil typow — 3 typy zbudowane z modelu
    RUN SUMMARY: kandydaci=40, po filtrach=6, System kupony=0

Fallback A1 (`typy_awaryjne_z_modelu`) zapisuje typy pod kluczem `top3`, ale NIE
buduje `kupon_a.zdarzenia`. Zapis kuponu stoi za `if zdarzenia_db:` BEZ galezi
else, wiec pusta lista pomijala wszystko w ciszy.

Trzy stany, ktore wygladaly identycznie w logu (czyli wcale):
    1. LLM nie zwrocil kuponu          -> dzieje sie codziennie od 16.08
    2. kupon odrzucony przez prog      -> logowane bylo juz wczesniej
    3. kupon zapisany                  -> logowane bylo juz wczesniej

Ten plik pilnuje stanu 1.
"""
from __future__ import annotations

import logging

from footstats.daily_agent import _zgloś_brak_kuponu_do_zapisu


def test_brak_zdarzen_jest_glosny(caplog):
    """Cisza znaczyla "wszystko w porzadku" przez 14 dni."""
    with caplog.at_level(logging.WARNING):
        _zgloś_brak_kuponu_do_zapisu("final", {"top3": [{"mecz": "A - B"}]})

    assert any(r.levelno >= logging.WARNING for r in caplog.records)
    assert "final" in caplog.text.lower()


def test_log_rozroznia_brak_kuponu_od_braku_typow(caplog):
    """Sedno diagnozy: typy POWSTALY (trafily do `predictions`), zabraklo tylko
    struktury kuponu. Bez tej liczby w logu oba stany wygladaja tak samo."""
    with caplog.at_level(logging.WARNING):
        _zgloś_brak_kuponu_do_zapisu("final", {"top3": [{"m": 1}, {"m": 2}, {"m": 3}]})

    assert "3" in caplog.text
    assert "predictions" in caplog.text or "typ" in caplog.text.lower()


def test_zero_typow_to_inny_komunikat_niz_typy_bez_kuponu(caplog):
    """Zero typow = nic nie przeszlo filtrow (stan znany i normalny).
    Typy bez kuponu = warstwa LLM nie oddala struktury (awaria od 16.08)."""
    with caplog.at_level(logging.WARNING):
        _zgloś_brak_kuponu_do_zapisu("final", {"top3": []})
    bez_typow = caplog.text
    caplog.clear()

    with caplog.at_level(logging.WARNING):
        _zgloś_brak_kuponu_do_zapisu("final", {"top3": [{"m": 1}]})
    z_typami = caplog.text

    assert bez_typow != z_typami, (
        "oba stany maja rozne przyczyny i rozne dzialania naprawcze"
    )


def test_brak_danych_w_ogole_nie_wywraca_zglaszania(caplog):
    with caplog.at_level(logging.WARNING):
        _zgloś_brak_kuponu_do_zapisu("draft", {})
        _zgloś_brak_kuponu_do_zapisu("draft", None)

    assert len([r for r in caplog.records if r.levelno >= logging.WARNING]) == 2


def test_wywolanie_jest_wpiete_w_sciezke_zapisu():
    """Straznik na wypadek, gdyby ktos usunal samo wywolanie i zostawil funkcje.
    Zapis kuponu ma byc jedynym miejscem, ktore je wola."""
    import inspect

    from footstats import daily_agent

    zrodlo = inspect.getsource(daily_agent)
    assert zrodlo.count("_zgloś_brak_kuponu_do_zapisu(") >= 2, (
        "funkcja istnieje, ale nikt jej nie wola — cisza wrocila"
    )
