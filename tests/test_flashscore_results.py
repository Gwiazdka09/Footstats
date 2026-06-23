"""Regresja 06-23: FlashScore zwracał LIVE score jako końcowy → kupon #242 rozliczony
przedwcześnie LOST (Norway-Senegal 0-0 @15min). Fix: tylko mecze class="fin" (zakończone)."""
from footstats.scrapers.flashscore_results import _parse_mobi_html


def _line(status_class, score):
    return (f'<span>15</span>Norway - Senegal '
            f'<a href="match/abc" class="{status_class}">{score}</a><br />')


def test_zakonczony_mecz_zwraca_wynik():
    html = _line("fin", "2:1")
    assert _parse_mobi_html(html, "Norway", "Senegal") == "2-1"


def test_live_mecz_NIE_zwraca_wyniku():
    # Mecz w trakcie (class != fin) — NIE wolno traktować jako końcowy.
    assert _parse_mobi_html(_line("live", "0:0"), "Norway", "Senegal") is None


def test_zaplanowany_mecz_nie_zwraca():
    # Zaplanowany (godzina zamiast wyniku, brak class fin).
    assert _parse_mobi_html(_line("sched", "-:-"), "Norway", "Senegal") is None


def test_inny_mecz_nie_dopasowany():
    html = _line("fin", "3:0").replace("Norway - Senegal", "Brazil - Haiti")
    assert _parse_mobi_html(html, "Norway", "Senegal") is None
