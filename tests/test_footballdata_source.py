"""
test_footballdata_source.py — testy FootballDataSource (football-data.co.uk CSV).

Wszystkie testy mockują requests.get — zero realnych wywołań sieciowych
(poza jednym opcjonalnym testem oznaczonym jako live smoke).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from footstats.scrapers.sources import footballdata_source
from footstats.scrapers.sources.footballdata_source import FootballDataSource


@pytest.fixture(autouse=True)
def _izolowany_cache(tmp_path, monkeypatch) -> None:
    """Każdy test używa izolowanego katalogu cache — żaden test nie czyta/pisze
    do prawdziwego `cache/footballdata` ani nie przecieka między testami."""
    monkeypatch.setattr(footballdata_source, "CACHE_DIR", tmp_path / "footballdata")


_CSV_PRZYKLAD = (
    "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,HTR,B365H,B365D,B365A\n"
    "E0,15/08/2025,Liverpool,Bournemouth,4,2,H,2,0,H,1.25,6.0,11.0\n"
    "E0,16/08/2025,Arsenal,Chelsea,1,1,D,0,0,D,2.0,3.3,3.8\n"
)


def _mock_response(text: str, status_code: int = 200):
    """Pomocniczy fałszywy obiekt odpowiedzi requests."""
    mock = type("MockResponse", (), {})()
    mock.text = text
    mock.status_code = status_code
    mock.raise_for_status = lambda: None
    return mock


class TestParsowanieCsv:
    def test_mapuje_wiersz_na_matchdata_z_ft_i_ht(self) -> None:
        src = FootballDataSource()
        with patch.object(src, "_pobierz_csv", return_value=_CSV_PRZYKLAD):
            mecze = src._fetch_liga("E0", "2526", "2025-08-15")

        assert len(mecze) == 1
        m = mecze[0]
        assert m.home == "Liverpool"
        assert m.away == "Bournemouth"
        assert m.ft_home == 4
        assert m.ft_away == 2
        assert m.ht_home == 2
        assert m.ht_away == 0
        assert m.status == "finished"
        assert m.source == "football-data.co.uk"
        assert m.to_result_str() == "4-2;HT:2-0"

    def test_kursy_b365_mapowane_do_odds(self) -> None:
        src = FootballDataSource()
        with patch.object(src, "_pobierz_csv", return_value=_CSV_PRZYKLAD):
            mecze = src._fetch_liga("E0", "2526", "2025-08-15")

        m = mecze[0]
        assert m.odds.get("home") == 1.25
        assert m.odds.get("draw") == 6.0
        assert m.odds.get("away") == 11.0


class TestFiltrPoDacie:
    def test_zwraca_tylko_mecze_z_danego_dnia(self) -> None:
        src = FootballDataSource()
        with patch.object(src, "_pobierz_csv", return_value=_CSV_PRZYKLAD):
            mecze = src._fetch_liga("E0", "2526", "2025-08-16")

        assert len(mecze) == 1
        assert mecze[0].home == "Arsenal"
        assert mecze[0].away == "Chelsea"

    def test_brak_meczow_danego_dnia_zwraca_puste(self) -> None:
        src = FootballDataSource()
        with patch.object(src, "_pobierz_csv", return_value=_CSV_PRZYKLAD):
            mecze = src._fetch_liga("E0", "2526", "2025-08-20")

        assert mecze == []


class TestParsowanieDaty:
    def test_format_dd_mm_yy(self) -> None:
        csv_yy = (
            "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,HTHG,HTAG\n"
            "E0,15/08/25,Liverpool,Bournemouth,4,2,2,0\n"
        )
        src = FootballDataSource()
        with patch.object(src, "_pobierz_csv", return_value=csv_yy):
            mecze = src._fetch_liga("E0", "2526", "2025-08-15")

        assert len(mecze) == 1
        assert mecze[0].home == "Liverpool"

    def test_format_dd_mm_yyyy(self) -> None:
        src = FootballDataSource()
        with patch.object(src, "_pobierz_csv", return_value=_CSV_PRZYKLAD):
            mecze = src._fetch_liga("E0", "2526", "2025-08-15")

        assert len(mecze) == 1


class TestGraceful:
    def test_blad_sieci_zwraca_puste(self) -> None:
        src = FootballDataSource()
        with patch("requests.get", side_effect=ConnectionError("brak sieci")):
            mecze = src.fetch("2025-08-15")

        assert mecze == []

    def test_pusty_csv_zwraca_puste(self) -> None:
        src = FootballDataSource()
        with patch("requests.get", return_value=_mock_response("")):
            mecze = src.fetch("2025-08-15")

        assert mecze == []

    def test_status_blad_http_zwraca_puste(self) -> None:
        def _raise():
            raise ConnectionError("404")

        resp = _mock_response("", status_code=404)
        resp.raise_for_status = _raise
        src = FootballDataSource()
        with patch("requests.get", return_value=resp):
            mecze = src.fetch("2025-08-15")

        assert mecze == []


class TestWyliczanieSezonu:
    def test_sezon_z_daty_sierpien(self) -> None:
        src = FootballDataSource()
        assert src._sezon_z_daty("2025-08-15") == "2526"

    def test_sezon_z_daty_styczen(self) -> None:
        src = FootballDataSource()
        # Styczeń 2026 jest jeszcze częścią sezonu 25/26 (rozpoczętego w 2025).
        assert src._sezon_z_daty("2026-01-15") == "2526"

    def test_sezon_z_daty_czerwiec(self) -> None:
        src = FootballDataSource()
        # Czerwiec to koniec sezonu rozpoczętego rok wcześniej.
        assert src._sezon_z_daty("2026-06-22") == "2526"

    def test_sezon_z_daty_lipiec_nowy_sezon(self) -> None:
        src = FootballDataSource()
        # Lipiec to już nowy sezon (zwykle start sierpień, ale CSV nazewnictwo
        # przełącza się latem).
        assert src._sezon_z_daty("2026-07-15") == "2627"


@pytest.mark.skip(reason="live smoke — odkomentuj manualnie do weryfikacji realnego CSV")
class TestLiveSmoke:
    def test_realny_csv_premier_league(self) -> None:
        """Smoke: realne pobranie CSV (E0) — wymaga sieci, pominięte w CI."""
        src = FootballDataSource()
        mecze = src.fetch("2025-08-15")
        assert isinstance(mecze, list)
