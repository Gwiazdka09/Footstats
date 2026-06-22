"""
test_scrapers_sources.py — testy fundamentu multi-source scraperów
(MatchData, ResultsSource, aggregator compare/consensus, adapter API-Football).

Wszystkie testy mockują źródła/API-Football — zero realnych wywołań sieciowych.
"""
from unittest.mock import patch

from footstats.scrapers.sources.base import MatchData
from footstats.scrapers.sources.af_source import APIFootballSource
from footstats.scrapers.sources import aggregator


# ── MatchData.to_result_str ───────────────────────────────────────────────────

class TestMatchDataToResultStr:
    def test_ft_only(self):
        m = MatchData(
            source="x", home="A", away="B", date="2026-01-01", status="finished",
            ft_home=2, ft_away=1, ht_home=None, ht_away=None,
        )
        assert m.to_result_str() == "2-1"

    def test_ft_i_ht(self):
        m = MatchData(
            source="x", home="A", away="B", date="2026-01-01", status="finished",
            ft_home=2, ft_away=1, ht_home=1, ht_away=0,
        )
        assert m.to_result_str() == "2-1;HT:1-0"

    def test_brak_ft_zwraca_none(self):
        m = MatchData(
            source="x", home="A", away="B", date="2026-01-01", status="scheduled",
            ft_home=None, ft_away=None, ht_home=None, ht_away=None,
        )
        assert m.to_result_str() is None

    def test_domyslne_odds_to_puste_dict(self):
        m = MatchData(
            source="x", home="A", away="B", date="2026-01-01", status="finished",
            ft_home=1, ft_away=1, ht_home=None, ht_away=None,
        )
        assert m.odds == {}


# ── aggregator.match_key ──────────────────────────────────────────────────────

class TestMatchKey:
    def test_te_same_zespoly_inna_pisownia_ten_sam_klucz(self):
        k1 = aggregator.match_key("FC Barcelona", "Real Madrid")
        k2 = aggregator.match_key("Barcelona", "RC Real Madrid")
        assert k1 == k2

    def test_inne_zespoly_inny_klucz(self):
        k1 = aggregator.match_key("Barcelona", "Real Madrid")
        k2 = aggregator.match_key("Liverpool", "Chelsea")
        assert k1 != k2


# ── aggregator.compare ────────────────────────────────────────────────────────

class TestCompare:
    def test_dwa_zgodne_zrodla_ft_zgodne_true(self):
        src_a = MatchData(
            source="a", home="Barcelona", away="Real Madrid", date="2026-01-01",
            status="finished", ft_home=2, ft_away=1, ht_home=1, ht_away=0,
        )
        src_b = MatchData(
            source="b", home="FC Barcelona", away="Real Madrid", date="2026-01-01",
            status="finished", ft_home=2, ft_away=1, ht_home=1, ht_away=0,
        )
        with patch.object(
            aggregator, "fetch_all",
            return_value={"a": [src_a], "b": [src_b]},
        ):
            wynik = aggregator.compare("2026-01-01")

        assert len(wynik) == 1
        mecz = wynik[0]
        assert mecz["ft_zgodne"] is True
        assert mecz["ht_zgodne"] is True
        assert mecz["rozjazdy"] == []
        assert len(mecz["sources"]) == 2

    def test_rozjazd_wyniku_flagowany(self):
        src_a = MatchData(
            source="a", home="Barcelona", away="Real Madrid", date="2026-01-01",
            status="finished", ft_home=2, ft_away=1, ht_home=None, ht_away=None,
        )
        src_b = MatchData(
            source="b", home="FC Barcelona", away="Real Madrid", date="2026-01-01",
            status="finished", ft_home=2, ft_away=2, ht_home=None, ht_away=None,
        )
        with patch.object(
            aggregator, "fetch_all",
            return_value={"a": [src_a], "b": [src_b]},
        ):
            wynik = aggregator.compare("2026-01-01")

        assert len(wynik) == 1
        mecz = wynik[0]
        assert mecz["ft_zgodne"] is False
        assert mecz["rozjazdy"] != []


# ── aggregator.consensus_result ───────────────────────────────────────────────

class TestConsensusResult:
    def test_zwraca_wynik_z_dostepnego_zrodla(self):
        src_a = MatchData(
            source="a", home="Barcelona", away="Real Madrid", date="2026-01-01",
            status="finished", ft_home=2, ft_away=1, ht_home=None, ht_away=None,
        )
        with patch.object(aggregator, "fetch_all", return_value={"a": [src_a]}):
            wynik = aggregator.consensus_result("Barcelona", "Real Madrid", "2026-01-01")

        assert wynik == "2-1"

    def test_preferuje_zrodlo_z_ht(self):
        src_a = MatchData(
            source="a", home="Barcelona", away="Real Madrid", date="2026-01-01",
            status="finished", ft_home=2, ft_away=1, ht_home=None, ht_away=None,
        )
        src_b = MatchData(
            source="b", home="Barcelona", away="Real Madrid", date="2026-01-01",
            status="finished", ft_home=2, ft_away=1, ht_home=1, ht_away=0,
        )
        with patch.object(
            aggregator, "fetch_all",
            return_value={"a": [src_a], "b": [src_b]},
        ):
            wynik = aggregator.consensus_result("Barcelona", "Real Madrid", "2026-01-01")

        assert wynik == "2-1;HT:1-0"

    def test_brak_meczu_zwraca_none(self):
        with patch.object(aggregator, "fetch_all", return_value={"a": []}):
            wynik = aggregator.consensus_result("Nieznany", "Klub", "2026-01-01")

        assert wynik is None


# ── APIFootballSource.fetch ────────────────────────────────────────────────────

class TestAPIFootballSourceFetch:
    def test_mapuje_fixture_z_halftime(self):
        fixtures_response = {
            "response": [
                {
                    "fixture": {"status": {"short": "FT"}},
                    "teams": {
                        "home": {"name": "Barcelona"},
                        "away": {"name": "Real Madrid"},
                    },
                    "goals": {"home": 2, "away": 1},
                    "score": {"halftime": {"home": 1, "away": 0}},
                },
            ]
        }
        src = APIFootballSource()
        with patch.object(src, "_get", return_value=fixtures_response):
            mecze = src.fetch("2026-01-01")

        assert len(mecze) == 1
        m = mecze[0]
        assert m.source == "api-football"
        assert m.home == "Barcelona"
        assert m.away == "Real Madrid"
        assert m.ft_home == 2
        assert m.ft_away == 1
        assert m.ht_home == 1
        assert m.ht_away == 0
        assert m.status == "finished"

    def test_brak_klucza_lub_blad_zwraca_puste(self):
        src = APIFootballSource()
        with patch.object(src, "_get", return_value=None):
            mecze = src.fetch("2026-01-01")

        assert mecze == []

    def test_mecz_nieskonczony_status_scheduled(self):
        fixtures_response = {
            "response": [
                {
                    "fixture": {"status": {"short": "NS"}},
                    "teams": {
                        "home": {"name": "Barcelona"},
                        "away": {"name": "Real Madrid"},
                    },
                    "goals": {"home": None, "away": None},
                    "score": {"halftime": {"home": None, "away": None}},
                },
            ]
        }
        src = APIFootballSource()
        with patch.object(src, "_get", return_value=fixtures_response):
            mecze = src.fetch("2026-01-01")

        assert len(mecze) == 1
        assert mecze[0].status == "scheduled"
        assert mecze[0].ft_home is None
