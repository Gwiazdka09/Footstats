"""test_flashscore_para.py — dopasowanie pary drużyn w wynikach FlashScore.

PO CO: FlashScore jest ostatnim źródłem wyników — działa dla lig, których nie ma
w football-data.org (POL/AUT/BEL/SCO), czyli dokładnie dla tych, w których gramy.
Złe dopasowanie tutaj rozlicza kupon wynikiem cudzego meczu.

`_parse_mobi_html` liczyło ŚREDNIĄ podobieństw obu drużyn przy progu 0.85:

    kupon "Standard – Cercle Brugge"  vs  mecz "Standard – Club Brugge"
    1.00 + 0.75 = średnia 0.88 > 0.85  ->  PRZECHODZIŁO

Cercle Brugge i Club Brugge to dwa różne kluby z Brugii, oba w belgijskiej
ekstraklasie. „Standard–Cercle" jest w tej chwili żywą nogą kuponu papierowego
100x B (mecz 08.08), więc to nie jest przypadek hipotetyczny.

Próg musiał zejść z 0.85 na 0.80, bo `min` przy 0.85 odciąłby dopasowania
POPRAWNE: „Mechelen" ↔ „KV Mechelen" to 0.80 (reguła token-prefix). 0.80 to ta
sama wartość, co `PROG_DOPASOWANIA_MECZU` w pozostałych modułach — przyjmujemy
wyłącznie dopasowania wynikające z reguły (dokładne / alias / skrót / inicjały),
nie z przypadkowego podobieństwa liter.
"""
from __future__ import annotations

import pytest

from footstats.scrapers.flashscore_results import _parse_mobi_html


def _html(*mecze: tuple[str, str, str], klasa: str = "fin") -> str:
    """HTML w formacie flashscore.mobi: linie rozdzielone `<br />`,
    wynik w linku z `class="fin"` (tylko zakończone mecze)."""
    return "<br />".join(
        f'<span>19:00</span>{g} - {a} '
        f'<a href="/match/x{i}/" class="{klasa}">{w}</a>'
        for i, (g, a, w) in enumerate(mecze)
    )


# ── sedno błędu ─────────────────────────────────────────────────────────────

def test_cercle_nie_rozlicza_sie_meczem_club_brugge():
    """REGRESJA: 1.00 + 0.75 = 0.88 > 0.85 przepuszczało INNY klub z Brugii.
    To żywa noga kuponu 100x B (Standard–Cercle, 08.08)."""
    html = _html(("Standard", "Club Brugge", "3-1"))

    assert _parse_mobi_html(html, "Standard", "Cercle Brugge") is None


def test_lech_nie_rozlicza_sie_meczem_lechii():
    html = _html(("Legia Warszawa", "Lechia Gdansk", "4-0"))

    assert _parse_mobi_html(html, "Legia Warszawa", "Lech Poznan") is None


def test_inny_rywal_tego_samego_klubu_odrzucony():
    html = _html(("Rapid Wien", "Austria Wien", "2-2"))

    assert _parse_mobi_html(html, "Rapid Wien", "Rheindorf Altach") is None


def test_derby_nie_myla_klubow():
    html = _html(("Manchester City", "Arsenal", "2-0"))

    assert _parse_mobi_html(html, "Manchester United", "Arsenal") is None


def test_rezerwy_nie_rozliczaja_pierwszego_zespolu():
    html = _html(("Legia II", "Lech II", "5-0"))

    assert _parse_mobi_html(html, "Legia", "Lech") is None


# ── poprawne dopasowania muszą przeżyć obniżenie progu ─────────────────────

def test_dokladne_nazwy_rozliczaja():
    html = _html(("Legia Warszawa", "Lech Poznan", "2-1"))

    assert _parse_mobi_html(html, "Legia Warszawa", "Lech Poznan") == "2-1"


def test_wariant_z_prefiksem_klubowym_rozlicza():
    """"Mechelen" ↔ "KV Mechelen" = 0.80 — to jest powód, dla którego próg
    musiał zejść z 0.85, a nie zostać przy nim z `min`."""
    html = _html(("Gent", "KV Mechelen", "1-0"))

    assert _parse_mobi_html(html, "Gent", "Mechelen") == "1-0"


def test_wynik_z_dwukropkiem_normalizowany():
    """FlashScore zwraca raz "1-0", raz "1:0"."""
    html = _html(("Legia Warszawa", "Lech Poznan", "3:2"))

    assert _parse_mobi_html(html, "Legia Warszawa", "Lech Poznan") == "3-2"


def test_wybiera_najlepsze_dopasowanie():
    html = _html(("Legia Warszawa", "Lechia Gdansk", "4-0"),
                 ("Legia Warszawa", "Lech Poznan", "2-1"))

    assert _parse_mobi_html(html, "Legia Warszawa", "Lech Poznan") == "2-1"


# ── dane niepełne ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("wynik", ["-:-", "--"])
def test_mecz_bez_wyniku_nie_rozlicza(wynik):
    """Mecz nierozegrany ma placeholder zamiast wyniku — to nie jest 0-0."""
    html = _html(("Legia Warszawa", "Lech Poznan", wynik))

    assert _parse_mobi_html(html, "Legia Warszawa", "Lech Poznan") is None


def test_mecz_w_trakcie_nie_jest_rozliczany():
    """REGRESJA #242: wynik LIVE brany za końcowy rozliczał kupon przedwcześnie
    (Norway–Senegal 0-0 w 15. minucie → BTTS=nie → cała akumulacja LOST)."""
    html = _html(("Legia Warszawa", "Lech Poznan", "0-0"), klasa="live")

    assert _parse_mobi_html(html, "Legia Warszawa", "Lech Poznan") is None


def test_pusty_html_nie_wywala():
    assert _parse_mobi_html("<html></html>", "Legia", "Lech") is None


def test_brak_dopasowania_to_none():
    html = _html(("Arka Gdynia", "Wisla Krakow", "1-1"))

    assert _parse_mobi_html(html, "Legia", "Lech") is None
