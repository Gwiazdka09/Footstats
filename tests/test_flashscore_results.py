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


# ── dopasowywanie nazw: margines bezpieczenstwa ─────────────────────────────
#
# `_parse_mobi_html` liczy podobienstwo i przepuszcza przy > 0.85.
# Ponizsze testy pilnuja, ze prog realnie oddziela kluby o wspolnej bazie nazwy.

def _mecz(gosp, gosc, wynik="2:1", klasa="fin"):
    return (f'<span>19:00</span>{gosp} - {gosc} '
            f'<a href="match/x" class="{klasa}">{wynik}</a><br />')


def test_dopasowuje_dokladna_nazwe():
    assert _parse_mobi_html(_mecz("Legia Warszawa", "Lech Poznan"),
                            "Legia Warszawa", "Lech Poznan") == "2-1"


def test_nie_myli_manchesterow():
    """Kupon na United nie moze zostac rozliczony wynikiem City.

    Ochrona jest tu WASKA: surowe podobienstwo tej pary wynosi 0.83 przy progu
    0.85, czyli margines to 0.02. Ten test istnieje, zeby kazde ruszenie progu
    albo funkcji podobienstwa od razu to ujawnilo.
    """
    html = _mecz("Manchester City", "Arsenal", "4:0")
    assert _parse_mobi_html(html, "Manchester United", "Arsenal") is None


def test_nie_myli_klubow_dundee():
    html = _mecz("Dundee FC", "Celtic", "0:3")
    assert _parse_mobi_html(html, "Dundee United", "Celtic") is None


def test_wynik_z_dwukropkiem_normalizowany():
    assert _parse_mobi_html(_mecz("Norway", "Senegal", "3:2"),
                            "Norway", "Senegal") == "3-2"


def test_placeholder_wyniku_odrzucany():
    """'-:-' to brak wyniku, nie remis."""
    assert _parse_mobi_html(_mecz("Norway", "Senegal", "-:-"),
                            "Norway", "Senegal") is None


def test_kartki_w_nazwie_nie_psuja_dopasowania():
    """FlashScore wstawia <img class="rcard-1"> przy czerwonych kartkach."""
    html = ('<span>19:00</span>Norway <img class="rcard-1"> - Senegal '
            '<a href="match/x" class="fin">1:0</a><br />')
    assert _parse_mobi_html(html, "Norway", "Senegal") == "1-0"


def test_wybiera_najlepsze_dopasowanie_z_wielu():
    html = _mecz("Brazil", "Haiti", "5:0") + _mecz("Norway", "Senegal", "1:1")
    assert _parse_mobi_html(html, "Norway", "Senegal") == "1-1"


def test_pusty_html_nie_wywala():
    assert _parse_mobi_html("", "Norway", "Senegal") is None
