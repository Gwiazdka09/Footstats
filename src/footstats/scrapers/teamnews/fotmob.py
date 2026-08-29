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

KOSZT. Lista dnia to jeden request, ale szczegóły są per mecz, a FotMob pokrywa
147 lig — 30.08 dawało 482 mecze. Ściąganie wszystkiego kosztowałoby 483 requesty
na przebieg, żeby użyć kilkudziesięciu. Dlatego `fetch_dla` filtruje po nazwach
JUŻ NA LIŚCIE DNIA i schodzi po szczegóły wyłącznie dla naszych kandydatów.
`fetch` (pełny dzień) zostaje dla smoke'a i diagnostyki, nie dla potoku.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import requests

from footstats.scrapers.teamnews.base import Absencja, TeamNews, absencja_pewna
from footstats.scrapers.teamnews.sedzia import statystyki_sedziego
from footstats.utils.normalize import normalize_team_name, team_similarity

log = logging.getLogger(__name__)

_BASE = "https://www.fotmob.com/api/data"
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
_TIMEOUT = 25
_PRZERWA_S = 0.7    # throttle — 1 request na mecz; nie chcemy wyglądać na atak
_PROG_NAZW = 0.72   # próg podobieństwa nazw drużyn na liście dnia


@dataclass(frozen=True)
class MeczDnia:
    """Pozycja z listy dnia — tyle, ile trzeba, żeby zdecydować o pobraniu szczegółów."""
    id: int
    home: str
    away: str
    liga: str


def _pobierz(sciezka: str, **params) -> dict:
    """Surowy GET. Wyjątki NIE są tu łapane — o ich randze decyduje wywołujący."""
    odp = requests.get(f"{_BASE}/{sciezka}", params=params,
                       headers={"User-Agent": _UA}, timeout=_TIMEOUT)
    odp.raise_for_status()
    return odp.json()


def _nazwiska(gracze: list | None) -> tuple[str, ...]:
    """Lista graczy → krotka nazwisk. Wpis bez nazwiska to śmieć w danych,
    nie awaria źródła — odpada cicho."""
    if not gracze:
        return ()
    return tuple(
        (g.get("name") or "").strip()
        for g in gracze
        if isinstance(g, dict) and (g.get("name") or "").strip()
    )


def _absencje(surowe: list | None) -> tuple[Absencja, ...]:
    """`unavailable[]` → krotka `Absencja`. Reguła `pewna` mieszka w `base`."""
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
        powrot = powrot if isinstance(powrot, str) else None
        gole = (g.get("performance") or {}).get("seasonGoals")
        out.append(Absencja(
            nazwisko=nazwisko,
            typ=str(niedost.get("type") or "unknown"),
            powrot=powrot,
            pewna=absencja_pewna(powrot),
            gole_sezon=gole if isinstance(gole, int) else None,
        ))
    return tuple(out)


def parsuj_liste_dnia(dane: dict) -> list[MeczDnia]:
    """`matches?date=` → płaska lista meczów. Pozycje bez id lub nazw odpadają."""
    out: list[MeczDnia] = []
    for liga in dane.get("leagues") or []:
        nazwa_ligi = f"{(liga or {}).get('ccode') or '?'}/{(liga or {}).get('name') or '?'}"
        for mecz in (liga or {}).get("matches") or []:
            mid = (mecz or {}).get("id")
            home = ((mecz or {}).get("home") or {}).get("name") or ""
            away = ((mecz or {}).get("away") or {}).get("name") or ""
            if mid and home.strip() and away.strip():
                out.append(MeczDnia(id=int(mid), home=home.strip(),
                                    away=away.strip(), liga=nazwa_ligi))
    return out


def parsuj_mecz(szczegoly: dict, data: str,
                home: str = "", away: str = "") -> TeamNews:
    """
    `matchDetails` → `TeamNews`.

    Brak sekcji `lineup` to stan NORMALNY — FotMob pokrywa 147 lig, a prognozy
    składów robi dla części. Wychodzi wtedy DTO z pustym składem: nie wyjątek
    i nie zmyślony skład.

    `home`/`away` z listy dnia są używane, gdy `lineup` nie podaje nazw — bez
    tego mecz bez składu tracił tożsamość i wypadał z wyniku, mimo że mógł
    nieść samego sędziego.
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
        home=(gosp.get("name") or "").strip() or home.strip(),
        away=(gosc.get("name") or "").strip() or away.strip(),
        date=data,
        typ_skladu=lineup.get("lineupType"),
        xi_home=_nazwiska(gosp.get("starters")),
        xi_away=_nazwiska(gosc.get("starters")),
        absencje_home=_absencje(gosp.get("unavailable")),
        absencje_away=_absencje(gosc.get("unavailable")),
        sedzia=((sedzia_surowy or {}).get("text") or "").strip() or None,
        sedzia_stats=statystyki_sedziego(sedzia_surowy),
    )


def _pasuje(mecz: MeczDnia, pary_norm: list[tuple[str, str]]) -> bool:
    """Czy mecz z listy dnia odpowiada któremuś z naszych kandydatów."""
    mh, ma = normalize_team_name(mecz.home), normalize_team_name(mecz.away)
    for kh, ka in pary_norm:
        if (mh, ma) == (kh, ka):
            return True
        if min(team_similarity(kh, mh), team_similarity(ka, ma)) >= _PROG_NAZW:
            return True
    return False


class FotMobTeamNews:
    """Adapter `TeamNewsSource`. Graceful — ale awarię źródła krzyczy."""

    name = "fotmob"

    def fetch(self, date: str) -> list[TeamNews]:
        """
        WSZYSTKIE mecze dnia. Kosztuje 1 + N requestów (30.08: 483) — do smoke'a
        i diagnostyki, nie do potoku. W potoku używaj `fetch_dla`.
        """
        return self.fetch_dla(date, None)

    def fetch_dla(self, date: str,
                  pary: list[tuple[str, str]] | None) -> list[TeamNews]:
        """
        Team news dla meczów danego dnia. `date` w formacie YYYY-MM-DD.

        `pary` to lista (gospodarz, goście) naszych kandydatów. Filtr działa
        NA LIŚCIE DNIA, przed pobraniem szczegółów — dzięki temu płacimy za
        kilkadziesiąt requestów zamiast za 483. `None` = bez filtra.

        Dwie awarie, dwie rangi. Padnięcie listy dnia znaczy ZERO danych
        w całym przebiegu, więc jest ERROR. Padnięcie pojedynczego meczu to
        stan normalny przy 147 ligach — DEBUG, i lecimy dalej.
        """
        dzien = date.replace("-", "")
        try:
            surowe = _pobierz("matches", date=dzien)
        except (requests.RequestException, ValueError) as e:
            log.error(
                "FotMob nie oddal listy meczow na %s (%s) — ZERO team-news w tym "
                "przebiegu: brak skladow, absencji i sedziego. To zrodlo nieoficjalne, "
                "wiec taki blad moze znaczyc, ze przestalo istniec.", date, e)
            return []

        mecze = parsuj_liste_dnia(surowe)
        if pary is not None:
            pary_norm = [(normalize_team_name(h), normalize_team_name(a))
                         for h, a in pary]
            mecze = [m for m in mecze if _pasuje(m, pary_norm)]
            log.debug("FotMob: %d meczow dnia pasuje do %d kandydatow",
                      len(mecze), len(pary_norm))

        wynik: list[TeamNews] = []
        for m in mecze:
            try:
                szczegoly = _pobierz("matchDetails", matchId=m.id)
            except (requests.RequestException, ValueError) as e:
                log.debug("FotMob matchDetails %s pominiete: %s", m.id, e)
                continue
            tn = parsuj_mecz(szczegoly, date, home=m.home, away=m.away)
            if tn.home and tn.away:
                wynik.append(tn)
            if _PRZERWA_S:
                time.sleep(_PRZERWA_S)
        return wynik
