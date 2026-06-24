"""
af_source.py — adapter API-Football jako pierwsze źródło ResultsSource.

Reużywa istniejącego klienta APIFootball (cache + budżet) — fetch() woła
/fixtures raz na dzień (cache'owane przez mechanizm AF), nigdy nie rzuca.
"""
from __future__ import annotations

from footstats.config import ENV_APISPORTS, _czytaj_wszystkie_klucze
from footstats.scrapers.api_football import APIFootball
from footstats.scrapers.sources.base import MatchData
from footstats.utils.helpers import _s

# Statusy API-Football oznaczające zakończony mecz (zgodnie z evening_agent._wynik_z_fixture)
_STATUSY_ZAKONCZONE = ("FT", "AET", "PEN")


class APIFootballSource:
    """Adapter API-Football do wspólnego interfejsu ResultsSource."""

    name: str = "api-football"

    def __init__(self, klient: APIFootball | None = None) -> None:
        if klient is None:
            klucz = _czytaj_wszystkie_klucze().get(ENV_APISPORTS)
            klient = APIFootball(klucz or "")
        self._klient = klient

    def _get(self, endpoint: str, params: dict | None = None) -> dict | None:
        """Pośredni wrapper na klienta — ułatwia mockowanie w testach."""
        return self._klient._get(endpoint, params or {})

    def fetch(self, date: str) -> list[MatchData]:
        """
        Pobiera mecze danego dnia z API-Football i mapuje na MatchData.
        Graceful: brak klucza/danych/błąd parsowania -> [].
        """
        try:
            dane = self._get("/fixtures", {"date": date[:10]})
            if not dane:
                return []
            mecze: list[MatchData] = []
            for fixture in dane.get("response", []):
                match = self._mapuj_fixture(fixture, date)
                if match is not None:
                    mecze.append(match)
            return mecze
        except (KeyError, TypeError, ValueError):
            return []

    def _mapuj_fixture(self, fixture: dict, date: str) -> MatchData | None:
        """Mapuje pojedynczy fixture API-Football na MatchData. None gdy brak drużyn."""
        teams = fixture.get("teams", {})
        home = _s(teams.get("home", {}).get("name", ""))
        away = _s(teams.get("away", {}).get("name", ""))
        if not home or not away:
            return None

        status_short = fixture.get("fixture", {}).get("status", {}).get("short", "")
        zakonczony = status_short in _STATUSY_ZAKONCZONE
        status = "finished" if zakonczony else (
            "scheduled" if status_short in ("NS", "TBD") else "unknown"
        )

        goals = fixture.get("goals", {})
        ft_home, ft_away = goals.get("home"), goals.get("away")
        if not zakonczony or ft_home is None or ft_away is None:
            ft_home = ft_away = None

        halftime = fixture.get("score", {}).get("halftime", {})
        ht_home, ht_away = halftime.get("home"), halftime.get("away")

        return MatchData(
            source=self.name,
            home=home,
            away=away,
            date=date[:10],
            status=status,
            ft_home=ft_home,
            ft_away=ft_away,
            ht_home=ht_home,
            ht_away=ht_away,
        )
