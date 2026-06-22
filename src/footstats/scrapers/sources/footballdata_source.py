"""
footballdata_source.py — adapter football-data.co.uk (CSV) jako ResultsSource.

football-data.co.uk udostępnia darmowe pliki CSV per liga+sezon (wyniki FT/HT
+ kursy bukmacherskie), bez anti-bota — niezawodna "kotwica" do cross-walidacji
gdy FlashScore/API-Football się rozjeżdżają. Pliki dochodzą z opóźnieniem
(bieżący sezon dopisywany na żywo), więc cache ma krótkie TTL.

UWAGA: to football-data.co.uk (CSV), NIE football-data.org (API) — różne serwisy.
"""
from __future__ import annotations

import csv
import io
import logging
import time
from datetime import datetime
from pathlib import Path

import requests

from footstats.scrapers.sources.base import MatchData

log = logging.getLogger(__name__)

# Kody lig football-data.co.uk pasujące do LIGI_WHITELIST projektu.
# Pomijamy ligi, których ten serwis nie pokrywa (np. polska Ekstraklasa, MŚ).
KODY_LIG: dict[str, str] = {
    "E0": "Premier League",
    "E1": "Championship",
    "SP1": "La Liga",
    "D1": "Bundesliga",
    "I1": "Serie A",
    "F1": "Ligue 1",
    "N1": "Eredivisie",
    "P1": "Primeira Liga",
    "B1": "Jupiler Pro League",
    "T1": "Super Lig",
}

BASE_URL = "https://www.football-data.co.uk/mmz4281"
CACHE_DIR = Path(__file__).parent.parent.parent.parent.parent / "cache" / "footballdata"
CACHE_TTL_SEKUNDY = 6 * 3600  # 6h — sezon w toku dochodzi, nie cache'ować na długo


class FootballDataSource:
    """Adapter football-data.co.uk (CSV) do wspólnego interfejsu ResultsSource."""

    name: str = "football-data.co.uk"

    def fetch(self, date: str) -> list[MatchData]:
        """
        Pobiera mecze danego dnia (YYYY-MM-DD) ze wszystkich śledzonych lig.
        Graceful: błąd sieci/parsowania pojedynczej ligi -> [] dla niej,
        reszta lig kontynuuje.
        """
        sezon = self._sezon_z_daty(date)
        mecze: list[MatchData] = []
        for kod_ligi in KODY_LIG:
            mecze.extend(self._fetch_liga(kod_liga=kod_ligi, sezon=sezon, date=date))
        return mecze

    def _fetch_liga(self, kod_liga: str, sezon: str, date: str) -> list[MatchData]:
        """Pobiera i parsuje CSV jednej ligi, filtruje po dacie. Graceful -> []."""
        try:
            tekst_csv = self._pobierz_csv(kod_liga, sezon)
            if not tekst_csv:
                return []
            return self._parsuj_csv(tekst_csv, date)
        except (requests.RequestException, OSError, ValueError, KeyError):
            log.debug("football-data.co.uk: błąd pobierania/parsowania %s", kod_liga)
            return []

    def _pobierz_csv(self, kod_liga: str, sezon: str) -> str:
        """Pobiera treść CSV (z cache plikowym, krótkie TTL) dla ligi+sezonu."""
        cache_path = self._cache_path(kod_liga, sezon)
        if cache_path.exists():
            wiek = time.time() - cache_path.stat().st_mtime
            if wiek < CACHE_TTL_SEKUNDY:
                return cache_path.read_text(encoding="utf-8", errors="ignore")

        url = f"{BASE_URL}/{sezon}/{kod_liga}.csv"
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        tekst = resp.text

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(tekst, encoding="utf-8")
        return tekst

    def _cache_path(self, kod_liga: str, sezon: str) -> Path:
        """Ścieżka pliku cache dla danej ligi+sezonu."""
        return CACHE_DIR / f"{kod_liga}_{sezon}.csv"

    def _parsuj_csv(self, tekst_csv: str, date: str) -> list[MatchData]:
        """Parsuje CSV football-data.co.uk i filtruje mecze danego dnia."""
        reader = csv.DictReader(io.StringIO(tekst_csv))
        mecze: list[MatchData] = []
        for wiersz in reader:
            match = self._mapuj_wiersz(wiersz, date)
            if match is not None:
                mecze.append(match)
        return mecze

    def _mapuj_wiersz(self, wiersz: dict, date: str) -> MatchData | None:
        """Mapuje pojedynczy wiersz CSV na MatchData. None gdy nie ten dzień/brak danych."""
        data_meczu = self._parsuj_date(wiersz.get("Date", ""))
        if data_meczu is None or data_meczu != date:
            return None

        home = (wiersz.get("HomeTeam") or "").strip()
        away = (wiersz.get("AwayTeam") or "").strip()
        if not home or not away:
            return None

        ft_home = self._parsuj_int(wiersz.get("FTHG"))
        ft_away = self._parsuj_int(wiersz.get("FTAG"))
        ht_home = self._parsuj_int(wiersz.get("HTHG"))
        ht_away = self._parsuj_int(wiersz.get("HTAG"))

        return MatchData(
            source=self.name,
            home=home,
            away=away,
            date=date,
            status="finished",
            ft_home=ft_home,
            ft_away=ft_away,
            ht_home=ht_home,
            ht_away=ht_away,
            odds=self._mapuj_odds(wiersz),
        )

    @staticmethod
    def _mapuj_odds(wiersz: dict) -> dict[str, float | None]:
        """Mapuje kursy Bet365 (B365H/D/A) na słownik odds, jeśli dostępne."""
        odds: dict[str, float | None] = {}
        mapowanie = {"home": "B365H", "draw": "B365D", "away": "B365A"}
        for klucz, kolumna in mapowanie.items():
            wartosc = FootballDataSource._parsuj_float(wiersz.get(kolumna))
            if wartosc is not None:
                odds[klucz] = wartosc
        return odds

    @staticmethod
    def _parsuj_int(wartosc: str | None) -> int | None:
        """Parsuje wartość liczbową z CSV (pusty/niepoprawny string -> None)."""
        if wartosc is None or wartosc.strip() == "":
            return None
        try:
            return int(float(wartosc))
        except ValueError:
            return None

    @staticmethod
    def _parsuj_float(wartosc: str | None) -> float | None:
        """Parsuje wartość zmiennoprzecinkową z CSV (pusty/niepoprawny string -> None)."""
        if wartosc is None or wartosc.strip() == "":
            return None
        try:
            return float(wartosc)
        except ValueError:
            return None

    @staticmethod
    def _parsuj_date(wartosc: str) -> str | None:
        """
        Parsuje datę football-data.co.uk (dd/mm/yy lub dd/mm/yyyy) -> YYYY-MM-DD.
        None gdy format niepoprawny.
        """
        wartosc = wartosc.strip()
        if not wartosc:
            return None
        for fmt in ("%d/%m/%Y", "%d/%m/%y"):
            try:
                return datetime.strptime(wartosc, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return None

    @staticmethod
    def _sezon_z_daty(date: str) -> str:
        """
        Wylicza kod sezonu football-data.co.uk (np. "2526" dla 25/26) z daty.
        Sezon zaczyna się latem (lipiec) i trwa do następnego lata.
        """
        dt = datetime.strptime(date, "%Y-%m-%d")
        if dt.month >= 7:
            rok_start = dt.year
        else:
            rok_start = dt.year - 1
        rok_koniec = rok_start + 1
        return f"{rok_start % 100:02d}{rok_koniec % 100:02d}"
