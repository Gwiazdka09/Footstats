"""
test_flashscore_source.py — testy FlashScoreSource (flashscore.mobi, finished-only).

Wszystkie testy mockują requests.get — zero realnych wywołań sieciowych
(poza jednym opcjonalnym testem oznaczonym jako live smoke).
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pytest

from footstats.scrapers.sources import flashscore_source
from footstats.scrapers.sources.flashscore_source import FlashScoreSource

# Data "dzisiejsza" względem zegara testowego — fetch() liczy offset mobi
# (±7 dni od `datetime.now()`), więc testy sieciowe muszą używać daty bieżącej.
_DZIS = datetime.now().strftime("%Y-%m-%d")

# Przykładowy HTML mobi: 2 mecze zakończone (class="fin") + 1 live (inna klasa).
_HTML_PRZYKLAD = (
    "<span>19:00</span>Liverpool - Bournemouth "
    '<a href="/match/abc#match-summary" class="fin">2:1</a><br />'
    "<span>20:00</span>Arsenal - Chelsea "
    '<a href="/match/def#match-summary" class="fin">1:1</a><br />'
    "<span>21:00</span>Real Madrid - Barcelona "
    '<a href="/match/ghi#match-summary" class="live">0:0</a><br />'
)


def _mock_response(text: str, status_code: int = 200):
    """Pomocniczy fałszywy obiekt odpowiedzi requests."""
    mock = type("MockResponse", (), {})()
    mock.text = text
    mock.status_code = status_code
    mock.raise_for_status = lambda: None
    return mock


@pytest.fixture(autouse=True)
def _izolowany_cache(tmp_path, monkeypatch) -> None:
    """Każdy test używa izolowanego katalogu cache — żaden test nie czyta/pisze
    do prawdziwego `cache/flashscore_source` ani nie przecieka między testami."""
    monkeypatch.setattr(flashscore_source, "CACHE_DIR", tmp_path / "flashscore_source")


class TestParsowanieMobi:
    def test_zwraca_tylko_zakonczone_mecze(self) -> None:
        src = FlashScoreSource()
        mecze = src._parsuj_mobi_html(_HTML_PRZYKLAD, "2025-08-15")

        nazwy = {(m.home, m.away) for m in mecze}
        assert ("Liverpool", "Bournemouth") in nazwy
        assert ("Arsenal", "Chelsea") in nazwy
        assert ("Real Madrid", "Barcelona") not in nazwy
        assert len(mecze) == 2

    def test_mecz_zakonczony_ma_ft_i_status_finished(self) -> None:
        src = FlashScoreSource()
        mecze = src._parsuj_mobi_html(_HTML_PRZYKLAD, "2025-08-15")

        m = next(m for m in mecze if m.home == "Liverpool")
        assert m.ft_home == 2
        assert m.ft_away == 1
        assert m.status == "finished"
        assert m.to_result_str() == "2-1"
        assert m.source == "flashscore"
        assert m.ht_home is None
        assert m.ht_away is None
        assert m.odds == {}

    def test_mecz_live_nie_jest_w_wyniku(self) -> None:
        src = FlashScoreSource()
        mecze = src._parsuj_mobi_html(_HTML_PRZYKLAD, "2025-08-15")

        assert all(m.home != "Real Madrid" for m in mecze)

    def test_pusty_html_zwraca_puste(self) -> None:
        src = FlashScoreSource()
        mecze = src._parsuj_mobi_html("", "2025-08-15")
        assert mecze == []


class TestGraceful:
    def test_blad_sieci_zwraca_puste(self) -> None:
        src = FlashScoreSource()
        with patch("requests.get", side_effect=ConnectionError("brak sieci")):
            mecze = src.fetch(_DZIS)

        assert mecze == []

    def test_blad_http_zwraca_puste(self) -> None:
        def _raise():
            raise ConnectionError("404")

        resp = _mock_response("", status_code=404)
        resp.raise_for_status = _raise
        src = FlashScoreSource()
        with patch("requests.get", return_value=resp):
            mecze = src.fetch(_DZIS)

        assert mecze == []

    def test_data_poza_zasiegiem_mobi_zwraca_puste(self) -> None:
        src = FlashScoreSource()
        # Mobi obsługuje ~7 dni — data odległa o 365 dni jest poza zasięgiem.
        mecze = src.fetch("2027-01-01")
        assert mecze == []

    def test_niepoprawny_format_daty_zwraca_puste(self) -> None:
        src = FlashScoreSource()
        mecze = src.fetch("nie-data")
        assert mecze == []


class TestFetchCalegoDnia:
    def test_fetch_pobiera_i_parsuje_html(self) -> None:
        src = FlashScoreSource()
        with patch("requests.get", return_value=_mock_response(_HTML_PRZYKLAD)):
            mecze = src.fetch(_DZIS)

        assert len(mecze) == 2
        assert {m.home for m in mecze} == {"Liverpool", "Arsenal"}
        assert all(m.date == _DZIS for m in mecze)

    def test_fetch_uzywa_offsetu_dnia_w_url(self) -> None:
        """fetch() powinien obliczyć offset (?d=X) jak flashscore_results."""
        src = FlashScoreSource()
        wywolane_url = []

        def _fake_get(url, headers=None, timeout=None):
            wywolane_url.append(url)
            return _mock_response(_HTML_PRZYKLAD)

        with patch("requests.get", side_effect=_fake_get):
            src.fetch(_DZIS)

        assert any("?d=" in u for u in wywolane_url)


class TestCache:
    def test_drugi_fetch_uzywa_cache_nie_woła_sieci(self) -> None:
        src = FlashScoreSource()
        with patch("requests.get", return_value=_mock_response(_HTML_PRZYKLAD)) as mock_get:
            src.fetch(_DZIS)
            src.fetch(_DZIS)

        assert mock_get.call_count == 1


@pytest.mark.skip(reason="live smoke — odkomentuj manualnie do weryfikacji realnego mobi")
class TestLiveSmoke:
    def test_realny_dzien_wczoraj(self) -> None:
        """Smoke: realne pobranie dnia (wczoraj) — wymaga sieci, pominięte w CI."""
        from datetime import datetime, timedelta

        src = FlashScoreSource()
        wczoraj = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        mecze = src.fetch(wczoraj)
        assert isinstance(mecze, list)
