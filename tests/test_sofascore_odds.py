"""
test_sofascore_odds.py – testy scrapera fallback kursów SofaScore (D6/D1b).

Wszystkie testy mockują Playwright/_sofa_fetch — zero realnych wywołań sieciowych.
"""
import shutil

import pytest

from footstats.scrapers import sofascore_odds as so


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    """Izoluje cache testów od cache/sofa_odds realnego projektu."""
    cache_dir = tmp_path / "sofa_odds_cache"
    monkeypatch.setattr(so, "CACHE_DIR", cache_dir)
    yield
    if cache_dir.exists():
        shutil.rmtree(cache_dir, ignore_errors=True)


# ── fractional_to_decimal ──────────────────────────────────────────────────────

class TestFractionalToDecimal:
    def test_5_2_daje_3_5(self):
        assert so.fractional_to_decimal("5/2") == 3.5

    def test_1_2_daje_1_5(self):
        assert so.fractional_to_decimal("1/2") == 1.5

    def test_1_1_daje_2_0(self):
        assert so.fractional_to_decimal("1/1") == 2.0

    def test_niepoprawny_format_zwraca_none(self):
        assert so.fractional_to_decimal("abc") is None

    def test_dzielenie_przez_zero_zwraca_none(self):
        assert so.fractional_to_decimal("5/0") is None


# ── parsowanie rynków ──────────────────────────────────────────────────────────

class TestParseMarkets:
    def test_parsuje_1x2(self):
        odds_json = {
            "markets": [
                {
                    "marketName": "Full time",
                    "choices": [
                        {"name": "1", "fractionalValue": "1/2"},
                        {"name": "X", "fractionalValue": "5/2"},
                        {"name": "2", "fractionalValue": "7/2"},
                    ],
                }
            ]
        }
        result = so._parse_markets(odds_json)
        assert result["home"] == 1.5
        assert result["draw"] == 3.5
        assert result["away"] == 4.5

    def test_parsuje_over_under(self):
        odds_json = {
            "markets": [
                {
                    "marketName": "Match goals",
                    "choices": [
                        {"name": "Over 2.5", "fractionalValue": "4/5"},
                        {"name": "Under 2.5", "fractionalValue": "11/10"},
                    ],
                }
            ]
        }
        result = so._parse_markets(odds_json)
        assert result["over_2_5"] == 1.8
        assert result["under_2_5"] == 2.1

    def test_parsuje_btts(self):
        odds_json = {
            "markets": [
                {
                    "marketName": "Both teams to score",
                    "choices": [
                        {"name": "Yes", "fractionalValue": "4/5"},
                        {"name": "No", "fractionalValue": "11/10"},
                    ],
                }
            ]
        }
        result = so._parse_markets(odds_json)
        assert result["btts"] == 1.8
        assert "no" not in result

    def test_brak_rynku_nie_wstawia_klucza(self):
        odds_json = {"markets": []}
        result = so._parse_markets(odds_json)
        assert result == {}

    def test_brak_markets_w_jsonie_nie_crashuje(self):
        assert so._parse_markets({}) == {}
        assert so._parse_markets(None) == {}


# ── fetch_odds (mockowane _sofa_fetch / find_team_id) ──────────────────────────

class TestFetchOdds:
    def test_brak_playwright_zwraca_none(self, monkeypatch):
        monkeypatch.setattr(so, "PLAYWRIGHT_OK", False)
        assert so.fetch_odds("Real Madrid", "Barcelona", "2026-06-21") is None

    def test_brak_team_id_zwraca_none(self, monkeypatch):
        monkeypatch.setattr(so, "PLAYWRIGHT_OK", True)
        monkeypatch.setattr(so, "find_team_id", lambda team, page: None)
        page = object()
        assert so.fetch_odds("Nieznana Druzyna", "Inna", "2026-06-21", page=page) is None

    def test_brak_eventu_zwraca_none(self, monkeypatch):
        monkeypatch.setattr(so, "PLAYWRIGHT_OK", True)
        monkeypatch.setattr(so, "find_team_id", lambda team, page: 123)
        monkeypatch.setattr(so, "_find_event_id", lambda page, tid, away, data: None)
        page = object()
        assert so.fetch_odds("Real Madrid", "Barcelona", "2026-06-21", page=page) is None

    def test_pelny_przeplyw_zwraca_kursy(self, monkeypatch):
        monkeypatch.setattr(so, "PLAYWRIGHT_OK", True)
        monkeypatch.setattr(so, "find_team_id", lambda team, page: 100)
        monkeypatch.setattr(so, "_find_event_id", lambda page, tid, away, data: 999)

        odds_json = {
            "markets": [
                {
                    "marketName": "Full time",
                    "choices": [
                        {"name": "1", "fractionalValue": "1/2"},
                        {"name": "X", "fractionalValue": "5/2"},
                        {"name": "2", "fractionalValue": "7/2"},
                    ],
                }
            ]
        }
        monkeypatch.setattr(so, "_sofa_fetch", lambda page, path: odds_json)

        page = object()
        result = so.fetch_odds("Real Madrid", "Barcelona", "2026-06-21", page=page)
        assert result == {"home": 1.5, "draw": 3.5, "away": 4.5}

    def test_brak_kursow_w_evencie_zwraca_none(self, monkeypatch):
        monkeypatch.setattr(so, "PLAYWRIGHT_OK", True)
        monkeypatch.setattr(so, "find_team_id", lambda team, page: 100)
        monkeypatch.setattr(so, "_find_event_id", lambda page, tid, away, data: 999)
        monkeypatch.setattr(so, "_sofa_fetch", lambda page, path: None)

        page = object()
        assert so.fetch_odds("Real Madrid", "Barcelona", "2026-06-21", page=page) is None

    def test_pusty_wynik_jest_cachowany_brak_ponownego_fetch(self, monkeypatch):
        """Brak rynków -> None, ale wynik (pusty dict) trafia do cache,
        więc druga próba dla tego samego eventu NIE odpytuje ponownie API."""
        monkeypatch.setattr(so, "PLAYWRIGHT_OK", True)
        monkeypatch.setattr(so, "find_team_id", lambda team, page: 100)
        monkeypatch.setattr(so, "_find_event_id", lambda page, tid, away, data: 999)

        calls = []

        def _fake_fetch(page, path):
            calls.append(path)
            return {"markets": []}

        monkeypatch.setattr(so, "_sofa_fetch", _fake_fetch)
        page = object()

        r1 = so.fetch_odds("Real Madrid", "Barcelona", "2026-06-21", page=page)
        assert r1 is None
        assert len(calls) == 1

        r2 = so.fetch_odds("Real Madrid", "Barcelona", "2026-06-21", page=page)
        assert r2 is None
        assert len(calls) == 1  # cache trafiony, brak drugiego fetcha

    def test_cache_zapisuje_i_odczytuje_wynik(self, monkeypatch):
        monkeypatch.setattr(so, "PLAYWRIGHT_OK", True)
        monkeypatch.setattr(so, "find_team_id", lambda team, page: 100)
        monkeypatch.setattr(so, "_find_event_id", lambda page, tid, away, data: 999)

        odds_json = {
            "markets": [
                {
                    "marketName": "Full time",
                    "choices": [{"name": "1", "fractionalValue": "1/1"}],
                }
            ]
        }
        calls = []

        def _fake_fetch(page, path):
            calls.append(path)
            return odds_json

        monkeypatch.setattr(so, "_sofa_fetch", _fake_fetch)
        page = object()

        r1 = so.fetch_odds("Real Madrid", "Barcelona", "2026-06-21", page=page)
        r2 = so.fetch_odds("Real Madrid", "Barcelona", "2026-06-21", page=page)
        assert r1 == r2 == {"home": 2.0}
        assert len(calls) == 1  # druga próba z cache, brak ponownego fetch


# ── fuzzy matching nazw / dat ──────────────────────────────────────────────────

class TestFindEventId:
    def test_dopasowuje_po_nazwie_i_dacie(self, monkeypatch):
        events_data = {
            "events": [
                {
                    "id": 1,
                    "homeTeam": {"name": "Real Madrid"},
                    "awayTeam": {"name": "FC Barcelona"},
                    "startTimestamp": 1750000000,
                },
                {
                    "id": 2,
                    "homeTeam": {"name": "Real Madrid"},
                    "awayTeam": {"name": "Sevilla"},
                    "startTimestamp": 1750100000,
                },
            ]
        }
        monkeypatch.setattr(so, "_sofa_fetch", lambda page, path: events_data)
        eid = so._find_event_id(page=object(), team_id=1, away="Barcelona", data="2026-06-21")
        assert eid == 1

    def test_brak_dopasowania_zwraca_none(self, monkeypatch):
        events_data = {
            "events": [
                {
                    "id": 1,
                    "homeTeam": {"name": "Real Madrid"},
                    "awayTeam": {"name": "Sevilla"},
                    "startTimestamp": 1750000000,
                },
            ]
        }
        monkeypatch.setattr(so, "_sofa_fetch", lambda page, path: events_data)
        eid = so._find_event_id(page=object(), team_id=1, away="Barcelona", data="2026-06-21")
        assert eid is None

    def test_brak_eventow_zwraca_none(self, monkeypatch):
        monkeypatch.setattr(so, "_sofa_fetch", lambda page, path: None)
        eid = so._find_event_id(page=object(), team_id=1, away="Barcelona", data="2026-06-21")
        assert eid is None
