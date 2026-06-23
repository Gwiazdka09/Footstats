"""
flashscore_source.py — adapter FlashScore (flashscore.mobi) jako ResultsSource.

Reużywa podejścia z `scrapers/flashscore_results.py` (requests, NIE Playwright,
lekki HTML mobi z offsetem dnia ?d=X) — ale w wersji "cały dzień": parsuje
WSZYSTKIE zakończone mecze ze strony mobi danego dnia (a nie pojedynczy mecz
po fuzzy-matchu nazw drużyn), zwracając listę `MatchData`.

WAŻNE: tylko mecze z `class="fin"` są traktowane jako zakończone — live
(inna klasa, np. minuta gry) lub zaplanowane są pomijane (patrz fix #242
w `flashscore_results.py`: live score ≠ wynik końcowy).

Mobi nie udostępnia półczasu w prostym widoku listy dnia -> ht_*=None.
FlashScore w tym frameworku jest redundancją FT (AF dostarcza HT).
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from pathlib import Path

import requests

from footstats.scrapers.sources.base import MatchData

log = logging.getLogger(__name__)

FLASHSCORE_MOBI_URL = "https://www.flashscore.mobi"
CACHE_DIR = Path(__file__).parent.parent.parent.parent.parent / "cache" / "flashscore_source"
CACHE_TTL_SEKUNDY = 6 * 3600  # 6h — wyniki dnia mogą jeszcze dochodzić (mecze trwające)
ZASIEG_DNI_MOBI = 7  # flashscore.mobi obsługuje ~7 dni wstecz/przód

_USER_AGENT = "Mozilla/5.0 (iPhone; CPU iPhone OS 13_5 like Mac OS X) AppleWebKit/605.1.15"

# Wzorzec linii mobi: <span>19:00</span>Home - Away <a ...>2:1</a>
_WZORZEC_MECZU = re.compile(r"</span>(.*?)\s*<a\s([^>]*)>(.*?)</a>")
_WZORZEC_TAGOW = re.compile(r"<[^>]+>")


class FlashScoreSource:
    """Adapter flashscore.mobi do wspólnego interfejsu ResultsSource (finished-only)."""

    name: str = "flashscore"

    def fetch(self, date: str) -> list[MatchData]:
        """
        Pobiera wszystkie zakończone mecze danego dnia (YYYY-MM-DD) z flashscore.mobi.
        Graceful: błąd sieci/parsowania/poza zasięgiem mobi -> [].
        """
        try:
            html = self._pobierz_html(date)
            if not html:
                return []
            return self._parsuj_mobi_html(html, date)
        except (requests.RequestException, OSError, ValueError, KeyError):
            log.debug("flashscore.mobi: błąd pobierania/parsowania dla %s", date)
            return []

    def _pobierz_html(self, date: str) -> str:
        """Pobiera HTML mobi dla dnia (z cache, krótkie TTL) -> "" gdy poza zasięgiem."""
        try:
            date_obj = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            log.warning("flashscore.mobi: niepoprawny format daty: %s", date)
            return ""

        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        offset = (date_obj - today).days
        if abs(offset) > ZASIEG_DNI_MOBI:
            log.info("flashscore.mobi: data %s poza zasięgiem (offset %d).", date, offset)
            return ""

        cache_path = self._cache_path(date)
        if cache_path.exists():
            wiek = time.time() - cache_path.stat().st_mtime
            if wiek < CACHE_TTL_SEKUNDY:
                return cache_path.read_text(encoding="utf-8", errors="ignore")

        url = f"{FLASHSCORE_MOBI_URL}/?d={offset}&s=1"
        headers = {"User-Agent": _USER_AGENT}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        html = resp.text

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(html, encoding="utf-8")
        return html

    def _cache_path(self, date: str) -> Path:
        """Ścieżka pliku cache HTML mobi dla danego dnia."""
        return CACHE_DIR / f"{date}.html"

    def _parsuj_mobi_html(self, html: str, date: str) -> list[MatchData]:
        """
        Parsuje HTML mobi i zwraca WSZYSTKIE zakończone mecze (class="fin") danego dnia.
        Struktura: <span>19:00</span>Home - Away <a ...class="fin"...>2:1</a><br />
        """
        mecze: list[MatchData] = []
        for linia in html.split("<br />"):
            if "match/" not in linia:
                continue
            m = _WZORZEC_MECZU.search(linia)
            if m is None:
                continue

            a_attrs = m.group(2)
            # Tylko zakończone mecze: live/zaplanowane mają inną klasę -> pomijamy.
            if "fin" not in a_attrs:
                continue

            teams_raw = _WZORZEC_TAGOW.sub("", m.group(1))
            wynik_raw = m.group(3).strip()
            if " - " not in teams_raw:
                continue

            home, away = (t.strip() for t in teams_raw.split(" - ", 1))
            if not home or not away:
                continue

            ft_home, ft_away = self._parsuj_wynik(wynik_raw)
            if ft_home is None or ft_away is None:
                continue

            mecze.append(MatchData(
                source=self.name,
                home=home,
                away=away,
                date=date,
                status="finished",
                ft_home=ft_home,
                ft_away=ft_away,
                ht_home=None,
                ht_away=None,
            ))
        return mecze

    @staticmethod
    def _parsuj_wynik(wynik_raw: str) -> tuple[int | None, int | None]:
        """Parsuje wynik mobi "2:1"/"2-1" -> (2, 1). (None, None) gdy niepoprawny."""
        norm = wynik_raw.replace(":", "-").strip()
        m = re.match(r"^(\d+)-(\d+)$", norm)
        if m is None:
            return None, None
        return int(m.group(1)), int(m.group(2))
