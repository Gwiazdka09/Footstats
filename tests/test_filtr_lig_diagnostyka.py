"""Filtr lig ma mówić, KTÓRE ligi odrzucił — inaczej cisza wygląda jak brak meczów.

PO CO: 10-12.08.2026 job `footstats-final` kończył się sukcesem przez trzy dni
z rzędu, produkując ZERO predykcji:

    Bzzoiro: 44 kandydatów w oknie 72h
    Whitelist lig: odrzucono 44 kandydatów spoza whitelist
    daily_agent final: kandydaci=44, po filtrach=0

Przyczyna okazała się banalna — w połowie sierpnia kalendarz wypełniają puchary
europejskie (Conference League, Europa League, Champions League, Copa
Libertadores), a whitelist ich nie zawiera. Ale log podawał tylko LICZBĘ,
więc diagnoza wymagała grzebania w bazie i porównywania nazw ręcznie.

Reguła: gdy filtr wycina WSZYSTKO, to jest zdarzenie warte krzyku, nie notatki.
Nazwy odrzuconych lig w logu skracają diagnozę z godziny do pięciu sekund.
"""
from __future__ import annotations

import logging

import pytest

from footstats.core import daily_filters


@pytest.fixture
def whitelist_tylko_ekstraklasa(monkeypatch):
    monkeypatch.setattr("footstats.config.LIGI_WHITELIST", frozenset({"Ekstraklasa"}))
    monkeypatch.setattr("footstats.config.LIGA_WHITELIST_ENFORCE", True)
    monkeypatch.setattr("footstats.config.LIGI_BLACKLIST_KEYWORDS", ())
    monkeypatch.setattr("footstats.config.LIGI_SLABE", frozenset())


def _kandydaci(*ligi: str) -> list[dict]:
    return [{"liga": liga, "gospodarz": "A", "goscie": "B"} for liga in ligi]


def test_log_wymienia_odrzucone_ligi(whitelist_tylko_ekstraklasa, caplog):
    with caplog.at_level(logging.INFO):
        daily_filters._pre_filtruj_ligi(
            _kandydaci("Conference League", "Europa League", "Ekstraklasa")
        )

    tekst = " ".join(r.getMessage() for r in caplog.records)
    assert "Conference League" in tekst, "log nie mowi, ktora liga odpadla"
    assert "Europa League" in tekst


def test_odrzucenie_wszystkiego_jest_ostrzezeniem(whitelist_tylko_ekstraklasa, caplog):
    """Zero przepuszczonych przy niezerowym wejsciu to nie jest zwykla informacja."""
    with caplog.at_level(logging.INFO):
        daily_filters._pre_filtruj_ligi(_kandydaci("Conference League", "Europa League"))

    poziomy = [r.levelno for r in caplog.records]
    assert max(poziomy) >= logging.WARNING, (
        "filtr wyciał wszystko, a log został na INFO — tak wygląda cicha awaria"
    )


def test_czesciowe_odrzucenie_zostaje_na_info(whitelist_tylko_ekstraklasa, caplog):
    """Normalna praca nie ma spamowac ostrzezeniami."""
    with caplog.at_level(logging.INFO):
        wynik = daily_filters._pre_filtruj_ligi(
            _kandydaci("Conference League", "Ekstraklasa")
        )

    assert len(wynik) == 1
    assert all(r.levelno < logging.WARNING for r in caplog.records)


@pytest.fixture
def blacklista_towarzyskich(monkeypatch):
    monkeypatch.setattr("footstats.config.LIGI_WHITELIST", frozenset({"Ekstraklasa"}))
    monkeypatch.setattr("footstats.config.LIGA_WHITELIST_ENFORCE", True)
    monkeypatch.setattr("footstats.config.LIGI_BLACKLIST_KEYWORDS", ("friendl", "towarzysk"))
    monkeypatch.setattr("footstats.config.LIGI_SLABE", frozenset())


def test_blacklista_slow_kluczowych_tez_sie_tlumaczy(blacklista_towarzyskich, caplog):
    """LUKA znaleziona na produkcji 13.08: gałąź blacklisty milczała całkowicie.

    Realny przebieg `footstats-final-5dpcn`: `kandydaci=5, po filtrach=0`, a w logu
    ANI JEDNEJ nazwy ligi — bo diagnostyka pokrywała tylko whitelistę, natomiast
    blacklista słów kluczowych robi `continue` bez licznika i bez zapisu nazwy.
    Dokładnie ta sama cicha awaria, przed którą miał chronić ten plik.
    """
    with caplog.at_level(logging.INFO):
        daily_filters._pre_filtruj_ligi(
            _kandydaci("Club Friendlies", "Mecze towarzyskie", "Ekstraklasa")
        )

    tekst = " ".join(r.getMessage() for r in caplog.records)
    assert "Friendlies" in tekst or "towarzysk" in tekst.lower(), (
        f"blacklista wycieła ligi po cichu — log nic nie mowi: {tekst!r}"
    )


def test_blacklista_wycinajaca_wszystko_krzyczy(blacklista_towarzyskich, caplog):
    with caplog.at_level(logging.INFO):
        daily_filters._pre_filtruj_ligi(_kandydaci("Club Friendlies", "Mecze towarzyskie"))

    poziomy = [r.levelno for r in caplog.records] or [logging.NOTSET]
    assert max(poziomy) >= logging.WARNING, (
        "blacklista wycieła wszystko, a log milczy albo zostal na INFO"
    )


def test_lista_lig_nie_puchnie_bez_konca(whitelist_tylko_ekstraklasa, caplog):
    """Przy 40 roznych ligach log ma zostac czytelny, nie stac sie sciana tekstu."""
    with caplog.at_level(logging.INFO):
        daily_filters._pre_filtruj_ligi(_kandydaci(*[f"Liga {i}" for i in range(40)]))

    tekst = " ".join(r.getMessage() for r in caplog.records)
    assert len(tekst) < 400, f"log za dlugi ({len(tekst)} znakow)"


def test_pusta_lista_kandydatow_nie_krzyczy(whitelist_tylko_ekstraklasa, caplog):
    """Brak meczow to nie to samo co filtr wycinajacy wszystko."""
    with caplog.at_level(logging.INFO):
        assert daily_filters._pre_filtruj_ligi([]) == []

    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
