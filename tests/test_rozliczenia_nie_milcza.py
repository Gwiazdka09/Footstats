"""J1 w warstwie rozliczeń: niesparsowana data albo nieznany format wyniku
nie mogą znikać bez śladu.

DLACZEGO AKURAT TU. 28.08 znaleźliśmy w dzienniku 218 wierszy krążących
w nieskończonej kolejce: `zapisz_wynik` dostawało wynik po dogrywce, nie umiało
go odczytać i **odrzucało go w całości**, więc wpis wracał do kolejki następnego
dnia. Objaw wyglądał jak brak danych po stronie źródła; źródło działało.

Tutaj są cztery warianty tego samego kształtu, każdy z innym skutkiem:

  `oblicz_tip_correct`           format wyniku bez obsługi → noga NIEROZLICZONA
  `data_jeszcze_osiagalna`       zła data → „poza zasięgiem", wynik nigdy nie
                                  zostanie pobrany
  `czeka_zbyt_dlugo`             zła data → alarm o zastoju NIE zobaczy kuponu
  `settle_active_coupons`        zła data → `too_old=False`, kupon NIGDY nie
                                  wygasa przez VOID i siedzi w ACTIVE

Ostatni jest najgroźniejszy, bo cisza pcha kupon w stan wieczny — dokładnie to,
co robiła pętla dziennika.
"""
from __future__ import annotations

import logging

import pytest

from footstats.core import coupon_settlement as cs
from footstats.utils.betting import oblicz_tip_correct


# ── daty kuponów ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("zla_data", ["", "brak", None, "2026-13-45"])
def test_niesparsowana_data_w_zasiegu_zrodel_jest_glosna(caplog, zla_data):
    with caplog.at_level(logging.WARNING):
        assert cs.data_jeszcze_osiagalna(zla_data) is False
    assert "nie do sparsowania" in caplog.text


@pytest.mark.parametrize("zla_data", ["", "brak", "2026-13-45"])
def test_niesparsowana_data_w_czekaniu_jest_glosna(caplog, zla_data):
    with caplog.at_level(logging.WARNING):
        assert cs.czeka_zbyt_dlugo(zla_data) is False
    assert "alarm o zastoju" in caplog.text


def test_poprawna_data_nie_generuje_szumu(caplog):
    """Kontrola. Ostrzeżenie przy każdym kuponie zabiłoby własny sygnał —
    a te funkcje chodzą w pętli po wszystkich aktywnych kuponach."""
    from datetime import date

    with caplog.at_level(logging.WARNING):
        cs.data_jeszcze_osiagalna("2026-08-25", dzis=date(2026, 8, 27))
        cs.czeka_zbyt_dlugo("2026-08-25", dzis=date(2026, 8, 27))

    assert caplog.text == ""


# ── formaty wyniku ──────────────────────────────────────────────────────────

def test_nieznany_format_wyniku_jest_glosny(caplog):
    """Cichy `pass` tutaj znaczył: „nie umiem tego przeczytać", i nikt się nie
    dowiadywał, że jakiś format wymaga obsługi."""
    with caplog.at_level(logging.WARNING):
        wynik = oblicz_tip_correct("1", "wynik-nieznany-format")

    assert wynik is None
    assert "NIEROZLICZONA" in caplog.text


def test_zepsuty_sufiks_HT_mowi_ze_traci_tylko_polowe(caplog):
    """Sufiks HT psuje TYLKO rynki pierwszej połowy — rynki FT liczą się dalej.
    Log ma to rozróżniać, inaczej brzmiałby jak utrata całego wyniku."""
    with caplog.at_level(logging.WARNING):
        wynik = oblicz_tip_correct("1", "2-1;HT:xx-yy")

    assert wynik == 1, "rynek FT ma sie rozliczyc mimo zepsutego HT"
    assert "pierwszej polowy" in caplog.text


def test_wynik_jako_krotka_o_zlym_ksztalcie_jest_glosny(caplog):
    with caplog.at_level(logging.WARNING):
        assert oblicz_tip_correct("1", (2,)) is None
    assert "dwoch elementow" in caplog.text


def test_zepsuty_TYP_wskazuje_na_nas_a_nie_na_dane(caplog):
    """Typ generujemy my. Nieczytelny próg w `OVER`/`UNDER` to błąd po NASZEJ
    stronie i log ma to mówić wprost — inaczej ktoś będzie szukał winy w danych.

    ZNALEZIONE PRZY PISANIU TEGO TESTU: cichy był nie `except`, tylko linia
    `if not val_match: return None` tuż nad nim. Audyt milczących handlerów jej
    NIE WIDZI, bo to zwykły `return`, nie handler — a to ona realnie przechwytuje
    ten przypadek. Handler poniżej jest przy obecnym wzorcu nieosiągalny."""
    with caplog.at_level(logging.WARNING):
        wynik = oblicz_tip_correct("OVER bez liczby", "2-1")

    assert wynik is None
    assert "NASZ typ" in caplog.text


def test_poprawny_wynik_nie_generuje_szumu(caplog):
    """Kontrola: `oblicz_tip_correct` woła się dla KAŻDEJ nogi każdej predykcji.
    Jedno zbędne ostrzeżenie na wywołanie utopiłoby log przy backfillu."""
    with caplog.at_level(logging.WARNING):
        assert oblicz_tip_correct("1", "2-1") == 1
        assert oblicz_tip_correct("OVER 2.5", "2-1") == 1
        assert oblicz_tip_correct("1", "2-1;HT:1-0") == 1

    assert caplog.text == ""
