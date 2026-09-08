"""Zrodla pisza nazwiska INACZEJ i dlatego absencje sie nie dopasowuja.

STAN ZASTANY (2026-09-07, po backfillu pelnych skladow). `player_stats` ma
24 417 nazwisk na sezon 2025, z czego **16 093 (66%) w formie skroconej**:

    Liverpool:    'Hugo Ekitike', 'H. Ekitike', 'Cody Gakpo', 'C. Gakpo', ...
    Real Madrid:  'Kylian Mbappe-Lottin', 'Kylian Mbappé', 'J. Bellingham', ...

API-Football oddaje `H. Ekitike`, Understat oddawal `Hugo Ekitike`, a FotMob —
zrodlo absencji — pisze pelne imie. `_dopasuj` zna dwie reguly: dokladna rownosc
po normalizacji i prefiks (baza pelniejsza od zrodla). ZADNA z nich nie laczy
`hugo ekitike` z `h. ekitike`, bo skrot nie jest prefiksem pelnego imienia.

To jest realna przyczyna liczby z logu produkcji:

    udzialy absencji 3/24 dopasowane w player_db

Sam backfill jej nie naprawia — dokladal wiecej nazwisk w formie, ktora i tak
nie pasuje. Stad trzecia regula: porownanie po INICJALE I NAZWISKU, symetryczne,
wiec dziala niezaleznie od tego, ktore zrodlo skraca.

Regula zostaje ZACHOWAWCZA jak dwie poprzednie: wymaga co najmniej dwoch czlonow
i musi byc jednoznaczna. Przypisanie cudzego udzialu jest gorsze niz brak
udzialu — przy udziale 20% i capie 0.35 blad przesuwa lambda o kilkanascie
procent w zla strone.
"""
from __future__ import annotations

import pytest

from footstats.core.absencje import udzialy_absencji
from footstats.scrapers.teamnews.base import klucz_gracza, klucz_skrocony


# ── klucz_skrocony ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("pelne, skrocone", [
    ("Hugo Ekitike", "H. Ekitike"),
    ("Cody Gakpo", "C. Gakpo"),
    ("Virgil van Dijk", "V. van Dijk"),
    ("Jude Bellingham", "J. Bellingham"),
    ("Vinícius Júnior", "V. Junior"),
    ("Kylian Mbappé", "K. Mbappe"),
])
def test_pelne_i_skrocone_daja_ten_sam_klucz(pelne, skrocone):
    assert klucz_skrocony(pelne) == klucz_skrocony(skrocone)


def test_klucz_zachowuje_caly_czlon_nazwiska():
    """'van Dijk' to nazwisko dwuczlonowe — skracamy TYLKO imie."""
    assert klucz_skrocony("Virgil van Dijk") == "v van dijk"


def test_jednoczlonowe_zostaje_bez_zmian():
    """'Rodri' nie ma czego skracac; reguly rozmyte i tak go nie tykaja."""
    assert klucz_skrocony("Rodri") == "rodri"


def test_rozni_gracze_nie_zlewaja_sie():
    assert klucz_skrocony("Hugo Ekitike") != klucz_skrocony("Hugo Ekitiké Junior")
    assert klucz_skrocony("M. Salah") != klucz_skrocony("M. Sadio")


def test_puste_wejscie_nie_wybucha():
    assert klucz_skrocony("") == ""
    assert klucz_skrocony(None) == ""


def test_zgodne_z_klucz_gracza_na_pelnych_nazwiskach():
    """Obie funkcje normalizuja tak samo — roznia sie tylko skracaniem imienia."""
    assert klucz_gracza("Kylian Mbappé") == "kylian mbappe"
    assert klucz_skrocony("Kylian Mbappé") == "k mbappe"


# ── udzialy_absencji: trzecia regula ────────────────────────────────────────

def test_skrot_w_bazie_dopasowuje_pelne_imie_ze_zrodla():
    """RDZEN: FotMob mowi pelnym imieniem, baza skrotem."""
    udzialy, nietrafione = udzialy_absencji(
        ["Hugo Ekitiké"], {"H. Ekitike": 0.18, "M. Salah": 0.11})
    assert udzialy == [0.18]
    assert nietrafione == []


def test_pelne_w_bazie_dopasowuje_skrot_ze_zrodla():
    """Symetrycznie — nie zakladamy, ktore zrodlo skraca."""
    udzialy, nietrafione = udzialy_absencji(
        ["H. Ekitike"], {"Hugo Ekitike": 0.18})
    assert udzialy == [0.18]
    assert nietrafione == []


def test_niejednoznaczny_skrot_jest_ODRZUCANY():
    """Dwoch 'M. Diallo' w kadrze — cudzy udzial gorszy niz brak udzialu."""
    udzialy, nietrafione = udzialy_absencji(
        ["Moussa Diallo"], {"M. Diallo": 0.10, "Mamadou Diallo": 0.25})
    assert udzialy == []
    assert nietrafione == ["Moussa Diallo"]


def test_jednoczlonowe_nazwisko_dalej_nie_przechodzi_rozmyte():
    """'Pedro' trafiloby w dowolnego Pedro — regula z `_MIN_CZLONOW` zostaje."""
    udzialy, nietrafione = udzialy_absencji(["Pedro"], {"Pedro Silva": 0.2})
    assert udzialy == []
    assert nietrafione == ["Pedro"]


def test_dokladne_dopasowanie_ma_pierwszenstwo():
    """Skrot nie moze przebic trafienia dokladnego."""
    udzialy, _ = udzialy_absencji(
        ["Hugo Ekitike"], {"Hugo Ekitike": 0.30, "H. Ekitike": 0.05})
    assert udzialy == [0.30]


def test_rozne_nazwiska_z_tym_samym_inicjalem_nie_lacza_sie():
    udzialy, nietrafione = udzialy_absencji(
        ["Mohamed Salah"], {"M. Sadio": 0.2})
    assert udzialy == []
    assert nietrafione == ["Mohamed Salah"]
