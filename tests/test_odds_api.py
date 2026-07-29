"""test_odds_api.py — The Odds API jako źródło kursów (requests-only, bez anti-bota).

Po co: dotychczasowy łańcuch to Bzzoiro → API-Football → SofaScore. SofaScore
oddaje 403 i wymaga Playwrighta, więc w cloud draft (requests-only) nie istnieje.
The Odds API zwraca WSZYSTKIE mecze ligi w jednym zapytaniu — dużo taniej niż AF,
gdzie jeden mecz kosztuje 2 zapytania (znajdz_fixture_id + kursy_fixture).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from footstats.scrapers.odds_api import (
    OddsAPIClient,
    dolacz_kursy_odds_api,
    mapuj_wydarzenie,
)

# ── kształt realnej odpowiedzi /v4/sports/{sport}/odds ──────────────────────

_EVENT = {
    "id": "abc123",
    "sport_key": "soccer_epl",
    "commence_time": "2026-08-01T16:30:00Z",
    "home_team": "Arsenal",
    "away_team": "Chelsea",
    "bookmakers": [
        {
            "key": "pinnacle",
            "markets": [
                {
                    "key": "h2h",
                    "outcomes": [
                        {"name": "Arsenal", "price": 1.80},
                        {"name": "Chelsea", "price": 4.20},
                        {"name": "Draw", "price": 3.60},
                    ],
                },
                {
                    "key": "totals",
                    "outcomes": [
                        {"name": "Over", "price": 1.95, "point": 2.5},
                        {"name": "Under", "price": 1.85, "point": 2.5},
                    ],
                },
            ],
        },
        {
            "key": "betfair",
            "markets": [
                {
                    "key": "h2h",
                    "outcomes": [
                        {"name": "Arsenal", "price": 1.90},
                        {"name": "Chelsea", "price": 4.00},
                        {"name": "Draw", "price": 3.50},
                    ],
                }
            ],
        },
    ],
}


# ── mapowanie wydarzenia na schemat projektu ────────────────────────────────


def test_mapuje_h2h_na_home_draw_away():
    """1X2 musi trafić pod klucze, których używa system_paper.najlepszy_typ."""
    odds = mapuj_wydarzenie(_EVENT)
    assert set(("home", "draw", "away")).issubset(odds)
    # Mediana po bukmacherach: home = median(1.80, 1.90) = 1.85
    assert odds["home"] == pytest.approx(1.85)
    assert odds["draw"] == pytest.approx(3.55)


def test_mapuje_totals_tylko_dla_linii_2_5():
    """Rynek totals ma wiele linii — bierzemy wyłącznie 2.5, inaczej mieszamy jabłka z gruszkami."""
    odds = mapuj_wydarzenie(_EVENT)
    assert odds["over_2_5"] == pytest.approx(1.95)
    assert odds["under_2_5"] == pytest.approx(1.85)


def test_ignoruje_inne_linie_totals():
    """Linia 3.5 nie może podszyć się pod 2.5."""
    ev = {
        "home_team": "A", "away_team": "B",
        "bookmakers": [{"key": "x", "markets": [{"key": "totals", "outcomes": [
            {"name": "Over", "price": 2.5, "point": 3.5},
            {"name": "Under", "price": 1.5, "point": 3.5},
        ]}]}],
    }
    odds = mapuj_wydarzenie(ev)
    assert "over_2_5" not in odds and "under_2_5" not in odds


def test_mediana_nie_maksimum():
    """
    Świadoma decyzja: mediana, nie max. Max po bukmacherach zawyża EV kursem,
    którego user u swojego bukmachera nie dostanie → fałszywe value-bety.
    """
    ev = {
        "home_team": "A", "away_team": "B",
        "bookmakers": [
            {"key": "b1", "markets": [{"key": "h2h", "outcomes": [{"name": "A", "price": 2.0}]}]},
            {"key": "b2", "markets": [{"key": "h2h", "outcomes": [{"name": "A", "price": 2.1}]}]},
            {"key": "b3", "markets": [{"key": "h2h", "outcomes": [{"name": "A", "price": 9.9}]}]},
        ],
    }
    assert mapuj_wydarzenie(ev)["home"] == pytest.approx(2.1)


def test_smieciowe_wydarzenie_nie_rzuca():
    """Brak drużyn / pusty dict → pusty wynik, nie wyjątek."""
    assert mapuj_wydarzenie({}) == {}
    assert mapuj_wydarzenie({"bookmakers": None}) == {}


# ── klient ──────────────────────────────────────────────────────────────────


def test_brak_klucza_jest_graceful():
    klient = OddsAPIClient(api_key="")
    ok, msg = klient.waliduj()
    assert ok is False and "ODDS_API_KEY" in msg
    assert klient.kursy_ligi("soccer_epl") == []


def test_kursy_ligi_jedno_zapytanie_na_lige():
    """Cała liga w jednym requeście — to jest przewaga nad AF (2 zapytania/mecz)."""
    resp = MagicMock(status_code=200, headers={"x-requests-remaining": "480"})
    resp.json.return_value = [_EVENT]
    with patch("footstats.scrapers.odds_api.requests.get", return_value=resp) as mock_get:
        klient = OddsAPIClient(api_key="k")
        eventy = klient.kursy_ligi("soccer_epl")

    assert len(eventy) == 1
    assert mock_get.call_count == 1
    params = mock_get.call_args.kwargs["params"]
    assert params["apiKey"] == "k"
    assert params["oddsFormat"] == "decimal"


def test_blad_http_jest_graceful():
    resp = MagicMock(status_code=401, headers={})
    with patch("footstats.scrapers.odds_api.requests.get", return_value=resp):
        assert OddsAPIClient(api_key="k").kursy_ligi("soccer_epl") == []


def test_wyjatek_sieci_jest_graceful():
    with patch("footstats.scrapers.odds_api.requests.get", side_effect=OSError("timeout")):
        assert OddsAPIClient(api_key="k").kursy_ligi("soccer_epl") == []


# ── dołączanie do kandydatów ────────────────────────────────────────────────


def test_dolacza_kursy_po_nazwach_druzyn():
    wyniki = [{"gospodarz": "Arsenal", "goscie": "Chelsea", "odds": {}}]
    klient = MagicMock()
    klient.waliduj.return_value = (True, "ok")
    klient.kursy_ligi.return_value = [_EVENT]

    n = dolacz_kursy_odds_api(wyniki, sport_keys=["soccer_epl"], klient=klient)
    assert n == 1
    assert wyniki[0]["odds"]["home"] == pytest.approx(1.85)


def test_nie_nadpisuje_istniejacych_kursow():
    """Kursy Bzzoiro/AF mają pierwszeństwo — uzupełniamy tylko braki."""
    wyniki = [{"gospodarz": "Arsenal", "goscie": "Chelsea", "odds": {"home": 1.5}}]
    klient = MagicMock()
    klient.waliduj.return_value = (True, "ok")
    klient.kursy_ligi.return_value = [_EVENT]

    dolacz_kursy_odds_api(wyniki, sport_keys=["soccer_epl"], klient=klient)
    assert wyniki[0]["odds"]["home"] == 1.5
    # ale brakujące klucze dochodzą
    assert wyniki[0]["odds"]["draw"] == pytest.approx(3.55)


def test_nie_myli_swapniętych_druzyn():
    """Arsenal-Chelsea to nie Chelsea-Arsenal — zły kierunek zabiłby settlement."""
    wyniki = [{"gospodarz": "Chelsea", "goscie": "Arsenal", "odds": {}}]
    klient = MagicMock()
    klient.waliduj.return_value = (True, "ok")
    klient.kursy_ligi.return_value = [_EVENT]

    assert dolacz_kursy_odds_api(wyniki, sport_keys=["soccer_epl"], klient=klient) == 0
    assert wyniki[0]["odds"] == {}


def test_klient_nieaktywny_nic_nie_robi():
    wyniki = [{"gospodarz": "Arsenal", "goscie": "Chelsea", "odds": {}}]
    klient = MagicMock()
    klient.waliduj.return_value = (False, "brak ODDS_API_KEY")

    assert dolacz_kursy_odds_api(wyniki, sport_keys=["soccer_epl"], klient=klient) == 0
    klient.kursy_ligi.assert_not_called()


def test_brak_meczow_bez_kursow_nie_pyta_api():
    """Zero braków → zero zapytań, żeby nie palić limitu 500/miesiąc."""
    wyniki = [{"gospodarz": "A", "goscie": "B", "odds": {"home": 2.0, "draw": 3.0, "away": 4.0}}]
    klient = MagicMock()
    klient.waliduj.return_value = (True, "ok")

    assert dolacz_kursy_odds_api(wyniki, sport_keys=["soccer_epl"], klient=klient) == 0
    klient.kursy_ligi.assert_not_called()
