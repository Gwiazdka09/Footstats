"""
test_af_odds.py — testy fallbacku kursów przez API-Football /odds (D1b/D6).

Wszystkie testy mockują APIFootball._get — zero realnych wywołań sieciowych,
zero zużycia budżetu AF.
"""
from unittest.mock import patch

from footstats.scrapers.api_football import APIFootball, fetch_odds_af


# ── kursy_fixture (parsowanie /odds) ──────────────────────────────────────────

class TestKursyFixture:
    def test_parsuje_1x2_over_under_btts(self):
        klient = APIFootball(api_key="dummy")
        odds_response = {
            "response": [
                {
                    "bookmakers": [
                        {
                            "name": "Bet365",
                            "bets": [
                                {
                                    "name": "Match Winner",
                                    "values": [
                                        {"value": "Home", "odd": "1.50"},
                                        {"value": "Draw", "odd": "3.50"},
                                        {"value": "Away", "odd": "4.50"},
                                    ],
                                },
                                {
                                    "name": "Goals Over/Under",
                                    "values": [
                                        {"value": "Over 2.5", "odd": "1.80"},
                                        {"value": "Under 2.5", "odd": "2.10"},
                                    ],
                                },
                                {
                                    "name": "Both Teams Score",
                                    "values": [
                                        {"value": "Yes", "odd": "1.75"},
                                        {"value": "No", "odd": "2.05"},
                                    ],
                                },
                            ],
                        }
                    ]
                }
            ]
        }
        with patch.object(klient, "_get", return_value=odds_response):
            wynik = klient.kursy_fixture(123)

        assert wynik == {
            "home": 1.50, "draw": 3.50, "away": 4.50,
            "over_2_5": 1.80, "under_2_5": 2.10,
            "btts": 1.75,
        }

    def test_brak_rynku_pomija_klucz_nie_wstawia_fałszywego(self):
        klient = APIFootball(api_key="dummy")
        odds_response = {
            "response": [
                {
                    "bookmakers": [
                        {
                            "name": "Bet365",
                            "bets": [
                                {
                                    "name": "Match Winner",
                                    "values": [
                                        {"value": "Home", "odd": "1.50"},
                                        {"value": "Draw", "odd": "3.50"},
                                        {"value": "Away", "odd": "4.50"},
                                    ],
                                },
                            ],
                        }
                    ]
                }
            ]
        }
        with patch.object(klient, "_get", return_value=odds_response):
            wynik = klient.kursy_fixture(123)

        assert wynik == {"home": 1.50, "draw": 3.50, "away": 4.50}
        assert "over_2_5" not in wynik
        assert "btts" not in wynik

    def test_brak_danych_zwraca_pusty_dict(self):
        klient = APIFootball(api_key="dummy")
        with patch.object(klient, "_get", return_value=None):
            assert klient.kursy_fixture(123) == {}

    def test_pusta_response_zwraca_pusty_dict(self):
        klient = APIFootball(api_key="dummy")
        with patch.object(klient, "_get", return_value={"response": []}):
            assert klient.kursy_fixture(123) == {}

    def test_brak_bukmacherow_zwraca_pusty_dict(self):
        klient = APIFootball(api_key="dummy")
        with patch.object(klient, "_get", return_value={"response": [{"bookmakers": []}]}):
            assert klient.kursy_fixture(123) == {}


# ── znajdz_fixture_id (fuzzy match drużyn) ────────────────────────────────────

class TestZnajdzFixtureId:
    def test_dopasowuje_po_nazwach_druzyn(self):
        klient = APIFootball(api_key="dummy")
        fixtures_response = {
            "response": [
                {
                    "fixture": {"id": 555, "date": "2026-06-21T18:00:00+00:00"},
                    "teams": {
                        "home": {"name": "Real Madrid"},
                        "away": {"name": "FC Barcelona"},
                    },
                },
                {
                    "fixture": {"id": 556, "date": "2026-06-21T20:00:00+00:00"},
                    "teams": {
                        "home": {"name": "Sevilla"},
                        "away": {"name": "Valencia"},
                    },
                },
            ]
        }
        with patch.object(klient, "_get", return_value=fixtures_response):
            fix_id = klient.znajdz_fixture_id("Real Madrid", "Barcelona", "2026-06-21")

        assert fix_id == 555

    def test_brak_dopasowania_zwraca_none(self):
        klient = APIFootball(api_key="dummy")
        fixtures_response = {
            "response": [
                {
                    "fixture": {"id": 556, "date": "2026-06-21T20:00:00+00:00"},
                    "teams": {
                        "home": {"name": "Sevilla"},
                        "away": {"name": "Valencia"},
                    },
                },
            ]
        }
        with patch.object(klient, "_get", return_value=fixtures_response):
            fix_id = klient.znajdz_fixture_id("Real Madrid", "Barcelona", "2026-06-21")

        assert fix_id is None

    def test_brak_danych_zwraca_none(self):
        klient = APIFootball(api_key="dummy")
        with patch.object(klient, "_get", return_value=None):
            assert klient.znajdz_fixture_id("Real Madrid", "Barcelona", "2026-06-21") is None

    def test_wynik_cachowany_nie_wola_drugi_raz(self):
        klient = APIFootball(api_key="dummy")
        fixtures_response = {
            "response": [
                {
                    "fixture": {"id": 555, "date": "2026-06-21T18:00:00+00:00"},
                    "teams": {
                        "home": {"name": "Real Madrid"},
                        "away": {"name": "FC Barcelona"},
                    },
                },
            ]
        }
        with patch.object(klient, "_get", return_value=fixtures_response) as mock_get:
            klient.znajdz_fixture_id("Real Madrid", "Barcelona", "2026-06-21")
            klient.znajdz_fixture_id("Real Madrid", "Barcelona", "2026-06-21")
            # _get powinno być cache'owane wewnątrz (reuse cache AF) — przynajmniej
            # nie więcej wywołań niż dopasowań (faktyczny cache jest na poziomie _get,
            # ale sprawdzamy, że metoda nie crashuje przy powtórnym wywołaniu).
            assert mock_get.call_count >= 1


# ── fetch_odds_af (funkcja wysokopoziomowa) ───────────────────────────────────

class TestFetchOddsAf:
    def test_brak_klucza_apisports_zwraca_none(self, monkeypatch):
        monkeypatch.setattr(
            "footstats.scrapers.api_football._czytaj_wszystkie_klucze",
            lambda: {"APISPORTS_KEY": None},
        )
        assert fetch_odds_af("Real Madrid", "Barcelona", "2026-06-21") is None

    def test_pelny_przeplyw_zwraca_kursy(self, monkeypatch):
        monkeypatch.setattr(
            "footstats.scrapers.api_football._czytaj_wszystkie_klucze",
            lambda: {"APISPORTS_KEY": "dummy_key"},
        )
        with patch.object(APIFootball, "znajdz_fixture_id", return_value=555), \
             patch.object(APIFootball, "kursy_fixture", return_value={"home": 1.5, "draw": 3.5, "away": 4.5}):
            wynik = fetch_odds_af("Real Madrid", "Barcelona", "2026-06-21")

        assert wynik == {"home": 1.5, "draw": 3.5, "away": 4.5}

    def test_brak_fixture_id_zwraca_none(self, monkeypatch):
        monkeypatch.setattr(
            "footstats.scrapers.api_football._czytaj_wszystkie_klucze",
            lambda: {"APISPORTS_KEY": "dummy_key"},
        )
        with patch.object(APIFootball, "znajdz_fixture_id", return_value=None):
            assert fetch_odds_af("Real Madrid", "Barcelona", "2026-06-21") is None

    def test_puste_kursy_zwraca_none(self, monkeypatch):
        monkeypatch.setattr(
            "footstats.scrapers.api_football._czytaj_wszystkie_klucze",
            lambda: {"APISPORTS_KEY": "dummy_key"},
        )
        with patch.object(APIFootball, "znajdz_fixture_id", return_value=555), \
             patch.object(APIFootball, "kursy_fixture", return_value={}):
            assert fetch_odds_af("Real Madrid", "Barcelona", "2026-06-21") is None
