"""FlashScore: znajdowanie drużyny i budowa adresu wyników.

BUG (2026-08-08): `get_form_flashscore` zwracało None dla KAŻDEJ drużyny, także
lokalnie. Przyczyną nie były selektory — te działają — tylko martwe adresy:

    https://www.flashscore.pl/search/?q=...          -> HTTP 404
    https://www.flashscore.pl/team/{slug}/{id}/      -> HTTP 404
    https://www.flashscore.pl/druzyna/{slug}/{id}/   -> HTTP 200

Serwis przeszedł na osobne API wyszukiwarki i na polskie `/druzyna/`. Kod
chodził pod angielskie `/team/` i skrobał stronę wyszukiwania, której już nie ma.

Wyszukiwarka zwraca czysty JSON przez zwykłe `requests` (bez przeglądarki),
ale miesza dyscypliny i zespoły rezerw, a nazwy podaje w języku `lang-id` —
stąd `lang-id=1` (angielski, ASCII) i filtrowanie po sporcie.
"""
from __future__ import annotations

import pytest

from footstats.scrapers.form_scraper import (
    _najlepsza_druzyna,
    _url_wynikow_flashscore,
)


def _wpis(nazwa: str, slug: str, ident: str, typ: int = 2, sport: str = "Soccer") -> dict:
    return {
        "id": ident, "url": slug, "name": nazwa,
        "type": {"id": typ, "name": "Team"},
        "sport": {"id": 1, "name": sport},
    }


# ── wybor druzyny z odpowiedzi wyszukiwarki ────────────────────────────────

def test_dokladna_druzyna_wybrana() -> None:
    wyniki = [_wpis("Gornik Zabrze", "gornik-zabrze", "2LH3Ywq4")]
    assert _najlepsza_druzyna("Górnik Zabrze", wyniki)["id"] == "2LH3Ywq4"


def test_rezerwy_nie_sa_brane_za_pierwsza_druzyne() -> None:
    """"Gornik Zabrze II" ma TEN SAM slug co pierwsza drużyna, inne id."""
    wyniki = [
        _wpis("Gornik Zabrze II", "gornik-zabrze", "r98x6SL9"),
        _wpis("Gornik Zabrze", "gornik-zabrze", "2LH3Ywq4"),
    ]
    assert _najlepsza_druzyna("Górnik Zabrze", wyniki)["id"] == "2LH3Ywq4"


def test_inna_dyscyplina_odrzucona() -> None:
    """Wyszukiwarka zwraca też koszykówkę — "Gornik Walbrzych" to inny klub i sport."""
    wyniki = [_wpis("Gornik Walbrzych", "gornik-walbrzych", "YyVSUlkI", sport="Basketball")]
    assert _najlepsza_druzyna("Gornik Walbrzych", wyniki) is None


def test_zawodnik_i_turniej_odrzucone() -> None:
    wyniki = [
        _wpis("Radomiak Radom", "radomiak", "AAA", typ=1),   # zawodnik
        _wpis("Radomiak Radom", "radomiak", "BBB", typ=3),   # turniej
    ]
    assert _najlepsza_druzyna("Radomiak Radom", wyniki) is None


def test_inny_klub_nie_jest_dopasowany() -> None:
    """Bez tego forma jednej drużyny trafiłaby do predykcji o innej."""
    wyniki = [_wpis("Legia Warszawa", "legia-warszawa", "XXX")]
    assert _najlepsza_druzyna("Lech Poznan", wyniki) is None


def test_pusta_odpowiedz() -> None:
    assert _najlepsza_druzyna("Radomiak Radom", []) is None


def test_wpis_bez_id_lub_slugu_pomijany() -> None:
    wyniki = [
        {"name": "Radomiak Radom", "type": {"id": 2}, "sport": {"name": "Soccer"}},
        _wpis("Radomiak Radom", "radomiak-radom", "zD5nYhAT"),
    ]
    assert _najlepsza_druzyna("Radomiak Radom", wyniki)["id"] == "zD5nYhAT"


def test_najlepszy_z_kilku_kandydatow() -> None:
    wyniki = [
        _wpis("Wisla Plock", "wisla-plock", "PLO"),
        _wpis("Wisla Krakow", "wisla-krakow", "KRA"),
    ]
    assert _najlepsza_druzyna("Wisła Płock", wyniki)["id"] == "PLO"


# ── adres wynikow ──────────────────────────────────────────────────────────

def test_adres_uzywa_polskiej_sciezki() -> None:
    """Angielskie `/team/` zwraca 404 — to była druga połowa buga."""
    url = _url_wynikow_flashscore({"url": "radomiak-radom", "id": "zD5nYhAT"})
    assert url == "https://www.flashscore.pl/druzyna/radomiak-radom/zD5nYhAT/wyniki/"
    assert "/team/" not in url


@pytest.mark.parametrize("brak", [{"url": "x"}, {"id": "y"}, {}])
def test_adres_wymaga_kompletu(brak: dict) -> None:
    assert _url_wynikow_flashscore(brak) is None


# ── strona gospodarza w wynikach ───────────────────────────────────────────

def test_gospodarz_rozpoznany_po_podobienstwie() -> None:
    from footstats.scrapers.form_scraper import _ta_sama_druzyna

    assert _ta_sama_druzyna("Radomiak Radom", "Radomiak Radom", "Górnik Zabrze") is True
    assert _ta_sama_druzyna("Górnik Zabrze", "Radomiak Radom", "Górnik Zabrze") is False


def test_kluby_z_tego_samego_miasta_nie_myla_stron() -> None:
    """Prefiks pięciu znaków mylił "Wisla Krakow" z "Wisla Plock".

    Skutek był cichy i groźny: gole trafiały na złą stronę, więc forma
    wychodziła dokładnie odwrotna.
    """
    from footstats.scrapers.form_scraper import _ta_sama_druzyna

    assert _ta_sama_druzyna("Wisla Plock", "Wisla Krakow", "Wisla Plock") is False


# ── wylacznik po blokadzie IP ──────────────────────────────────────────────

def test_blokada_sofascore_zapamietana_w_procesie() -> None:
    """Po 403 kolejne drużyny nie mają po co uruchamiać przeglądarki."""
    from footstats.scrapers import form_scraper as fs

    class _Odpowiedz:
        status = 403

    class _Strona:
        @staticmethod
        def goto(*_a, **_k):
            return _Odpowiedz()

    pierwotny = fs._SOFA_ZABLOKOWANY
    try:
        fs._SOFA_ZABLOKOWANY = False
        assert fs.sofascore_zablokowany() is False
        fs._sofa_fetch(_Strona(), "/search/all?q=X")
        assert fs.sofascore_zablokowany() is True
    finally:
        fs._SOFA_ZABLOKOWANY = pierwotny


def test_brak_danych_nie_wlacza_wylacznika() -> None:
    """404 znaczy "nie ma tego meczu", nie "jestesmy zablokowani"."""
    from footstats.scrapers import form_scraper as fs

    class _Odpowiedz:
        status = 404

    class _Strona:
        @staticmethod
        def goto(*_a, **_k):
            return _Odpowiedz()

    pierwotny = fs._SOFA_ZABLOKOWANY
    try:
        fs._SOFA_ZABLOKOWANY = False
        fs._sofa_fetch(_Strona(), "/injuries")
        assert fs.sofascore_zablokowany() is False
    finally:
        fs._SOFA_ZABLOKOWANY = pierwotny
