"""
thesportsdb_source.py — adapter TheSportsDB (darmowe JSON API) jako ResultsSource.

TheSportsDB udostępnia wyniki dnia przez endpoint `eventsday.php?d=YYYY-MM-DD&s=Soccer`
(JSON, requests, BEZ anti-bot). Wartość w tym frameworku: pokrycie meczów
REPREZENTACJI / TOWARZYSKICH / turniejów, które ligowe źródła (football-data.co.uk
CSV, częściowo API-Football) gubią — to dokładnie mecze, które dziś nie settlują
(orphan predykcje MŚ/friendly, patrz D1a w TODO).

Półczas: free endpoint zwykle nie podaje HT (`intHomeScoreHT`=None) -> ht_*=None,
to redundancja FT (HT dostarcza API-Football). Klucz: domyślnie darmowy test-key "3",
nadpisywalny przez env `THESPORTSDB_KEY` (bez wymogu .env).

Graceful: błąd sieci/parsowania/limit -> [] (kontrakt ResultsSource).
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

import requests

from footstats.scrapers.sources.base import MatchData
from footstats.utils.helpers import _s

log = logging.getLogger(__name__)

_BASE_URL = "https://www.thesportsdb.com/api/v1/json"
CACHE_DIR = Path(__file__).parent.parent.parent.parent.parent / "cache" / "thesportsdb_source"
CACHE_TTL_SEKUNDY = 6 * 3600  # 6h — wyniki dnia mogą jeszcze dochodzić (mecze trwające)

# strStatus oznaczające zakończony mecz (TheSportsDB bywa niespójny w nazewnictwie).
_STATUSY_ZAKONCZONE = ("FT", "AET", "PEN", "Match Finished")
_STATUSY_PRZED = ("NS", "Not Started", "")


def _parsuj_int(wartosc: object) -> int | None:
    """TheSportsDB zwraca score jako string ("4") lub None -> int|None, nigdy nie rzuca."""
    if wartosc is None:
        return None
    try:
        return int(str(wartosc).strip())
    except (ValueError, TypeError):
        return None


class TheSportsDBSource:
    """Adapter TheSportsDB do wspólnego interfejsu ResultsSource (FT, szerokie reprezentacje)."""

    name: str = "thesportsdb"

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.getenv("THESPORTSDB_KEY", "3")

    def fetch(self, date: str) -> list[MatchData]:
        """
        Pobiera mecze piłkarskie danego dnia (YYYY-MM-DD) i mapuje na MatchData.
        Graceful: błąd sieci/parsowania/limit -> [].
        """
        try:
            dane = self._pobierz_json(date)
            if not dane:
                return []
            events = dane.get("events") or []
            mecze: list[MatchData] = []
            for ev in events:
                match = self._mapuj_event(ev, date)
                if match is not None:
                    mecze.append(match)
            return mecze
        except (requests.RequestException, OSError, ValueError, KeyError, TypeError):
            log.debug("thesportsdb: błąd pobierania/parsowania dla %s", date)
            return []

    def _pobierz_json(self, date: str) -> dict | None:
        """Pobiera JSON wyników dnia (z cache, krótkie TTL). None gdy brak/błąd."""
        cache_path = self._cache_path(date)
        if cache_path.exists():
            wiek = time.time() - cache_path.stat().st_mtime
            if wiek < CACHE_TTL_SEKUNDY:
                return json.loads(cache_path.read_text(encoding="utf-8", errors="ignore"))

        url = f"{_BASE_URL}/{self._api_key}/eventsday.php"
        resp = requests.get(url, params={"d": date[:10], "s": "Soccer"}, timeout=12)
        resp.raise_for_status()
        tekst = resp.text

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(tekst, encoding="utf-8")
        return json.loads(tekst)

    def _cache_path(self, date: str) -> Path:
        """Ścieżka pliku cache JSON dla danego dnia."""
        return CACHE_DIR / f"{date[:10]}.json"

    def _mapuj_event(self, ev: dict, date: str) -> MatchData | None:
        """Mapuje pojedynczy event TheSportsDB na MatchData. None gdy brak drużyn."""
        home = _s(ev.get("strHomeTeam") or "")
        away = _s(ev.get("strAwayTeam") or "")
        # _s() zwraca "-" dla pustych/None/nan — traktuj placeholder jako brak drużyny.
        if home == "-" or away == "-":
            return None

        status_raw = (ev.get("strStatus") or "").strip()
        zakonczony = status_raw in _STATUSY_ZAKONCZONE

        ft_home = _parsuj_int(ev.get("intHomeScore"))
        ft_away = _parsuj_int(ev.get("intAwayScore"))
        if not zakonczony or ft_home is None or ft_away is None:
            zakonczony = False
            ft_home = ft_away = None

        status = "finished" if zakonczony else (
            "scheduled" if status_raw in _STATUSY_PRZED else "unknown"
        )

        return MatchData(
            source=self.name,
            home=home,
            away=away,
            date=date[:10],
            status=status,
            ft_home=ft_home,
            ft_away=ft_away,
            ht_home=_parsuj_int(ev.get("intHomeScoreHT")),
            ht_away=_parsuj_int(ev.get("intAwayScoreHT")),
        )
