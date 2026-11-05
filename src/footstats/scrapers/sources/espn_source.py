"""
espn_source.py — adapter ESPN (scoreboard) jako ResultsSource, TYLKO wyniki.

UWAGA: to NIEOFICJALNE, nieudokumentowane API (site.api.espn.com). Bez klucza,
bez gwarancji stabilności — może zmienić kształt lub zniknąć bez uprzedzenia.
Dlatego każdy błąd daje `log.warning` i `[]` (nigdy wyjątek), a źródło służy
wyłącznie do rozliczania wyników, nie do kursów ani predykcji.

Powód istnienia: API-Football jest wyłączone na stałe (APISPORTS_ENABLED=0),
a kupony bez wyniku wypadały na VOID. ESPN oddaje wyniki ligowe z całego świata
jednym zapytaniem na dzień (`dates=YYYYMMDD`; zakres dat zwraca HTTP 400).

Zasady:
- wynik TYLKO ze STATUS_FULL_TIME; AET/PEN/AGT niosą wynik po dogrywce, a
  rozliczamy po 90 minutach, więc tam ma być brak wyniku,
- gospodarz/gość po polu `homeAway`, nigdy po kolejności tablicy,
- granica dnia po stronie ESPN jest nieznana: pobieramy d-1..d+1 i zostawiamy
  zdarzenia z datą UTC == d albo (d-1 i godzina UTC >= 22) — późne mecze trafiają
  do dnia, który mają w Polsce (bez zoneinfo).
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import date as _date, datetime, timedelta
from pathlib import Path

import requests

from footstats.scrapers.sources.base import MatchData
from footstats.utils.paths import katalog_cache

log = logging.getLogger(__name__)

_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard"
_HEADERS = {"User-Agent": "footstats-results/1.0"}
CACHE_DIR = katalog_cache(
    "espn_source",
    domyslny=Path(__file__).parent.parent.parent.parent.parent / "cache" / "espn_source",
)
CACHE_TTL_SEKUNDY = 6 * 3600  # 6h — wyniki dnia mogą jeszcze dochodzić
_STATUS_KONIEC = "STATUS_FULL_TIME"
_KROPKOWANY_PREFIKS = re.compile(r"\b([A-Za-z])\.([A-Za-z])\.")
_GODZINA_GRANICZNA_UTC = 22  # od tej godziny UTC mecz d-1 jest już w Polsce dniem d


def _nazwa(surowa: object) -> str:
    """displayName ESPN; "F.C. København" -> "FC København" (inaczej normalizacja
    daje "f c kobenhavn" i para nie pasuje do kuponowego "FC København")."""
    return _KROPKOWANY_PREFIKS.sub(r"\1\2", str(surowa)).strip()


class EspnSource:
    """Adapter ESPN do wspólnego interfejsu ResultsSource (tylko FT po 90 minutach)."""

    name: str = "espn"

    def fetch(self, date: str) -> list[MatchData]:
        """Mecze dnia `date` (YYYY-MM-DD). Graceful: każdy błąd -> pusta lista + warning."""
        try:
            dzien = _date.fromisoformat(date[:10])
        except ValueError:
            log.warning("espn: niepoprawna data %r", date)
            return []

        wynik: list[MatchData] = []
        widziane: set[str] = set()
        for przesuniecie in (-1, 0, 1):
            for ev in self._zdarzenia(dzien + timedelta(days=przesuniecie)):
                mecz = self._mapuj(ev, dzien)
                ident = str(ev.get("id", "")) if isinstance(ev, dict) else ""
                if mecz is None or (ident and ident in widziane):
                    continue
                if ident:
                    widziane.add(ident)
                wynik.append(mecz)
        return wynik

    def _zdarzenia(self, dzien: _date) -> list:
        """Surowe zdarzenia jednego koszyka dnia ESPN; cache tylko dla odpowiedzi niepustych."""
        klucz = dzien.strftime("%Y%m%d")
        sciezka = CACHE_DIR / f"{klucz}.json"
        try:
            if sciezka.exists() and time.time() - sciezka.stat().st_mtime < CACHE_TTL_SEKUNDY:
                return json.loads(sciezka.read_text(encoding="utf-8"))
            resp = requests.get(
                _URL, params={"dates": klucz, "limit": 1000},
                headers=_HEADERS, timeout=15,
            )
            if resp.status_code != 200:
                log.warning("espn: HTTP %s dla %s", resp.status_code, klucz)
                return []
            events = resp.json().get("events")
            if not isinstance(events, list):
                log.warning("espn: brak listy 'events' dla %s", klucz)
                return []
            if events:
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                sciezka.write_text(json.dumps(events), encoding="utf-8")
            return events
        except (requests.RequestException, OSError, ValueError, AttributeError) as e:
            log.warning("espn: błąd pobierania/parsowania %s (%s: %s)",
                        klucz, type(e).__name__, e)
            return []

    def _mapuj(self, ev: object, dzien: _date) -> MatchData | None:
        """Zdarzenie ESPN -> MatchData; None gdy poza dniem, uszkodzone lub score nieliczbowy."""
        try:
            utc = datetime.fromisoformat(str(ev["date"]).replace("Z", "+00:00"))  # type: ignore[index]
            if not (utc.date() == dzien or (
                utc.date() == dzien - timedelta(days=1)
                and utc.hour >= _GODZINA_GRANICZNA_UTC
            )):
                return None
            status = ev["status"]["type"]["name"]  # type: ignore[index]
            strony = {c["homeAway"]: c for c in ev["competitions"][0]["competitors"]}  # type: ignore[index]
            gosp, gosc = strony["home"], strony["away"]
            home = _nazwa(gosp["team"]["displayName"])
            away = _nazwa(gosc["team"]["displayName"])
            if not home or not away:
                return None
            if status != _STATUS_KONIEC:
                return MatchData(self.name, home, away, dzien.isoformat(),
                                 "unknown", None, None, None, None)
            return MatchData(self.name, home, away, dzien.isoformat(), "finished",
                             int(str(gosp["score"]).strip()),
                             int(str(gosc["score"]).strip()), None, None)
        except (KeyError, IndexError, TypeError, ValueError, AttributeError) as e:
            log.warning("espn: pominięto uszkodzone zdarzenie (%s: %s)", type(e).__name__, e)
            return None
