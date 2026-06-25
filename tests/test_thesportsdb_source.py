"""
test_thesportsdb_source.py — testy TheSportsDBSource (darmowe JSON API).

Wszystkie testy mockują requests.get — zero realnych wywołań sieciowych.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from footstats.scrapers.sources import thesportsdb_source
from footstats.scrapers.sources.thesportsdb_source import TheSportsDBSource, _parsuj_int

# Przykładowa odpowiedź: 1 zakończony (FT), 1 zaplanowany (NS), 1 bez drużyn.
_JSON_PRZYKLAD = json.dumps({
    "events": [
        {
            "strHomeTeam": "Morocco", "strAwayTeam": "Haiti",
            "intHomeScore": "4", "intAwayScore": "2",
            "intHomeScoreHT": None, "intAwayScoreHT": None,
            "strStatus": "FT", "dateEvent": "2026-06-24",
        },
        {
            "strHomeTeam": "Poland", "strAwayTeam": "Germany",
            "intHomeScore": None, "intAwayScore": None,
            "strStatus": "NS", "dateEvent": "2026-06-24",
        },
        {
            "strHomeTeam": "", "strAwayTeam": "Spain",
            "intHomeScore": "1", "intAwayScore": "0",
            "strStatus": "FT", "dateEvent": "2026-06-24",
        },
    ]
})


def _mock_response(text: str, status_code: int = 200):
    """Fałszywy obiekt odpowiedzi requests (TheSportsDBSource czyta .text → json.loads)."""
    mock = type("MockResponse", (), {})()
    mock.text = text
    mock.status_code = status_code
    mock.raise_for_status = lambda: None
    return mock


@pytest.fixture(autouse=True)
def _izolowany_cache(tmp_path, monkeypatch) -> None:
    """Izolowany katalog cache — testy nie czytają/piszą prawdziwego cache/thesportsdb_source."""
    monkeypatch.setattr(thesportsdb_source, "CACHE_DIR", tmp_path / "thesportsdb_source")


class TestParsujInt:
    @pytest.mark.parametrize("wejscie,oczekiwane", [
        ("4", 4), (3, 3), ("0", 0), (None, None), ("", None), ("abc", None), ("  2 ", 2),
    ])
    def test_parsuj_int(self, wejscie, oczekiwane) -> None:
        assert _parsuj_int(wejscie) == oczekiwane


class TestFetch:
    def test_parsuje_zakonczony_mecz(self) -> None:
        with patch("footstats.scrapers.sources.thesportsdb_source.requests.get",
                   return_value=_mock_response(_JSON_PRZYKLAD)):
            mecze = TheSportsDBSource(api_key="3").fetch("2026-06-24")

        finished = [m for m in mecze if m.status == "finished"]
        assert len(finished) == 1
        m = finished[0]
        assert (m.home, m.away) == ("Morocco", "Haiti")
        assert (m.ft_home, m.ft_away) == (4, 2)
        assert m.source == "thesportsdb"
        assert m.to_result_str() == "4-2"  # HT brak → bez sufiksu

    def test_niezakonczony_ma_ft_none(self) -> None:
        with patch("footstats.scrapers.sources.thesportsdb_source.requests.get",
                   return_value=_mock_response(_JSON_PRZYKLAD)):
            mecze = TheSportsDBSource(api_key="3").fetch("2026-06-24")

        ns = [m for m in mecze if (m.home, m.away) == ("Poland", "Germany")]
        assert len(ns) == 1
        assert ns[0].status == "scheduled"
        assert ns[0].ft_home is None and ns[0].ft_away is None
        assert ns[0].to_result_str() is None

    def test_pomija_brak_druzyn(self) -> None:
        with patch("footstats.scrapers.sources.thesportsdb_source.requests.get",
                   return_value=_mock_response(_JSON_PRZYKLAD)):
            mecze = TheSportsDBSource(api_key="3").fetch("2026-06-24")
        assert all(m.home and m.away for m in mecze)
        assert not any(m.away == "Spain" for m in mecze)  # brak home → pominięty

    def test_blad_sieci_zwraca_pusta_liste(self) -> None:
        import requests
        with patch("footstats.scrapers.sources.thesportsdb_source.requests.get",
                   side_effect=requests.RequestException("boom")):
            assert TheSportsDBSource(api_key="3").fetch("2026-06-24") == []

    def test_brak_klucza_events_zwraca_pusta_liste(self) -> None:
        with patch("footstats.scrapers.sources.thesportsdb_source.requests.get",
                   return_value=_mock_response(json.dumps({"events": None}))):
            assert TheSportsDBSource(api_key="3").fetch("2026-06-24") == []

    def test_cache_unika_drugiego_zapytania(self) -> None:
        """Drugi fetch tego samego dnia czyta cache — bez ponownego requests.get."""
        with patch("footstats.scrapers.sources.thesportsdb_source.requests.get",
                   return_value=_mock_response(_JSON_PRZYKLAD)) as mock_get:
            src = TheSportsDBSource(api_key="3")
            src.fetch("2026-06-24")
            src.fetch("2026-06-24")
            assert mock_get.call_count == 1


class TestRejestracjaAggregator:
    def test_thesportsdb_w_get_sources(self) -> None:
        from footstats.scrapers.sources import aggregator
        nazwy = {s.name for s in aggregator.get_sources()}
        assert "thesportsdb" in nazwy
