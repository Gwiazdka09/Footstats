"""
fotmob.py — adapter team-news oparty o publiczne JSON-y FotMoba.

Zmierzone 29-30.08: `https://www.fotmob.com/api/data/*` odpowiada zwykłemu
`requests` (HTTP 200, bez Cloudflare, bez klucza). Na n=14 meczów w naszych
ligach: przewidywany XI 14/14, lista absencji 14/14, sędzia 14/14.

UWAGA: to NIE jest oficjalne API. Zniknie kiedyś bez ostrzeżenia — dokładnie
tak, jak zawieszone konto API-Football i wycofany model Groqa. Dlatego 403/429
i zmiana kształtu JSON-a lądują na ERROR, a nie w ciszy: to jedyny moment,
w którym możemy się o tym dowiedzieć, zanim ścieżka B po cichu przestanie
liczyć cokolwiek.

Stara ścieżka `/api/matches?date=` zwraca 404. Działa `/api/data/matches?date=`.
"""
from __future__ import annotations

import logging
import time

import requests

from footstats.scrapers.teamnews.base import Absencja, TeamNews, absencja_pewna
from footstats.scrapers.teamnews.sedzia import statystyki_sedziego

log = logging.getLogger(__name__)

_BASE = "https://www.fotmob.com/api/data"
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
_TIMEOUT = 25
_PRZERWA_S = 0.7   # throttle — 1 request na mecz; nie chcemy wyglądać na atak


def _pobierz(sciezka: str, **params) -> dict:
    """Surowy GET. Wyjątki NIE są tu łapane — o ich randze decyduje `fetch`."""
    odp = requests.get(f"{_BASE}/{sciezka}", params=params,
                       headers={"User-Agent": _UA}, timeout=_TIMEOUT)
    odp.raise_for_status()
    return odp.json()


def _nazwiska(gracze: list | None) -> tuple[str, ...]:
    """Lista graczy → krotka nazwisk. Wpisy bez nazwiska odpadają cicho:
    brakujące nazwisko to śmieć w danych, nie awaria źródła."""
    if not gracze:
        return ()
    return tuple(
        (g.get("name") or "").strip()
        for g in gracze
        if isinstance(g, dict) and (g.get("name") or "").strip()
    )


def _absencje(surowe: list | None) -> tuple[Absencja, ...]:
    """`unavailable[]` → krotka `Absencja`. Reguła `pewna` w `base`."""
    if not surowe:
        return ()
    out: list[Absencja] = []
    for g in surowe:
        if not isinstance(g, dict):
            continue
        nazwisko = (g.get("name") or "").strip()
        if not nazwisko:
            continue
        niedost = g.get("unavailability") or {}
        powrot = niedost.get("expectedReturn")
        gole = (g.get("performance") or {}).get("seasonGoals")
        out.append(Absencja(
            nazwisko=nazwisko,
            typ=str(niedost.get("type") or "unknown"),
            powrot=powrot if isinstance(powrot, str) else None,
            pewna=absencja_pewna(powrot if isinstance(powrot, str) else None),
            gole_sezon=gole if isinstance(gole, int) else None,
        ))
    return tuple(out)


def parsuj_mecz(szczegoly: dict, data: str) -> TeamNews:
    """
    `matchDetails` → `TeamNews`.

    Brak sekcji `lineup` to stan NORMALNY — FotMob pokrywa 147 lig, a prognozy
    składów robi dla części. Wychodzi wtedy puste DTO: nie wyjątek i nie
    zmyślony skład.
    """
    tresc = szczegoly.get("content") or {}
    lineup = tresc.get("lineup") or {}
    gosp = lineup.get("homeTeam") or {}
    gosc = lineup.get("awayTeam") or {}
    infobox = (tresc.get("matchFacts") or {}).get("infoBox") or {}

    sedzia_surowy = infobox.get("Referee")
    if not isinstance(sedzia_surowy, dict):
        sedzia_surowy = None

    return TeamNews(
        source="fotmob",
        home=(gosp.get("name") or "").strip(),
        away=(gosc.get("name") or "").strip(),
        date=data,
        typ_skladu=lineup.get("lineupType"),
        xi_home=_nazwiska(gosp.get("starters")),
        xi_away=_nazwiska(gosc.get("starters")),
        absencje_home=_absencje(gosp.get("unavailable")),
        absencje_away=_absencje(gosc.get("unavailable")),
        sedzia=((sedzia_surowy or {}).get("text") or "").strip() or None,
        sedzia_stats=statystyki_sedziego(sedzia_surowy),
    )


class FotMobTeamNews:
    """Adapter `TeamNewsSource`. Graceful — ale awarię źródła krzyczy."""

    name = "fotmob"

    def fetch(self, date: str) -> list[TeamNews]:
        """
        Team news dla meczów danego dnia. `date` w formacie YYYY-MM-DD.

        Koszt: 1 request na listę dnia + 1 na mecz.

        Dwie awarie, dwie rangi. Padnięcie listy dnia znaczy ZERO danych
        w całym przebiegu, więc jest ERROR. Padnięcie pojedynczego meczu to
        stan normalny przy 147 ligach — DEBUG, i lecimy dalej.
        """
        dzien = date.replace("-", "")
        try:
            dane = _pobierz("matches", date=dzien)
        except (requests.RequestException, ValueError) as e:
            log.error(
                "FotMob nie oddal listy meczow na %s (%s) — ZERO team-news w tym "
                "przebiegu: brak skladow, absencji i sedziego. To zrodlo nieoficjalne, "
                "wiec taki blad moze znaczyc, ze przestalo istniec.", date, e)
            return []

        wynik: list[TeamNews] = []
        for liga in dane.get("leagues") or []:
            for mecz in (liga or {}).get("matches") or []:
                mid = (mecz or {}).get("id")
                if not mid:
                    continue
                try:
                    szczegoly = _pobierz("matchDetails", matchId=mid)
                except (requests.RequestException, ValueError) as e:
                    log.debug("FotMob matchDetails %s pominiete: %s", mid, e)
                    continue
                tn = parsuj_mecz(szczegoly, date)
                if tn.home and tn.away:
                    wynik.append(tn)
                if _PRZERWA_S:
                    time.sleep(_PRZERWA_S)
        return wynik
