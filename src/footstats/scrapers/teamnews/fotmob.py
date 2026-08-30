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
from dataclasses import dataclass, replace

import requests

from footstats.scrapers.teamnews.base import (
    Absencja, TeamNews, absencja_pewna, klucz_gracza,
)
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


# Grupy składu FotMoba → kody, których oczekuje `core/lambda_optimizer`
# (`_POZ_ATAK = ("F", "M")`, `_POZ_OBRONA = ("D", "G")`). Mapowanie jest 1:1
# i pilnuje go `test_kody_sa_dokladnie_tymi_ktorych_oczekuje_model` — rozjazd
# liter cicho zwróciłby korektę λ do (1.0, 1.0), czyli do stanu sprzed naprawy.
_GRUPY_POZYCJI = {
    "keepers": "G",
    "defenders": "D",
    "midfielders": "M",
    "attackers": "F",
}


def parsuj_pozycje(dane: dict) -> dict[str, str]:
    """
    Skład drużyny → `{znormalizowane_nazwisko: "G"|"D"|"M"|"F"}`.

    FotMob grupuje skład po pozycji, więc pozycja nie wymaga zgadywania.
    Grupa `coach` i wszystko spoza `_GRUPY_POZYCJI` (np. `loaned_out`) odpada:
    zawodnik wypożyczony i tak nie zagra, a trener nie jest zawodnikiem.

    Klucze są normalizowane (bez diakrytyków, casefold), bo nazwiska rozjeżdżają
    się między źródłami — `Moisés` w jednym, `Moises` w drugim.
    """
    grupy = ((dane or {}).get("squad") or {}).get("squad") or []
    out: dict[str, str] = {}
    for grupa in grupy:
        if not isinstance(grupa, dict):
            continue
        kod = _GRUPY_POZYCJI.get(str(grupa.get("title") or "").strip().lower())
        if kod is None:
            continue
        for czlonek in grupa.get("members") or []:
            if not isinstance(czlonek, dict):
                continue
            nazwisko = (czlonek.get("name") or "").strip()
            if nazwisko:
                out[klucz_gracza(nazwisko)] = kod
    return out


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

    def __init__(self) -> None:
        # Cache na przebieg, nie globalny: sklad zmienia sie rzadko, ale trzymanie
        # go miedzy przebiegami dawaloby zawodnikow sprzed transferu.
        self._pozycje: dict[int, dict[str, str]] = {}

    def pozycje_druzyny(self, team_id: int | None) -> dict[str, str]:
        """
        `{znormalizowane_nazwisko: "G"|"D"|"M"|"F"}` dla druzyny.

        Odblokowuje dwustronna korekte lambda w `_apply_injury_corrections`,
        ktora klasyfikuje absencje po pozycji. Jedynym zrodlem pozycji byl
        SofaScore — zmierzony 30.08 jako HTTP 403 na kazde zapytanie, i z Cloud
        Runa, i lokalnie przez `requests`.

        Awaria degraduje do korekty jednostronnej (`availability_edge`), a nie
        zatrzymuje potoku: pusty slownik znaczy "bez pozycji", i tak jest
        traktowany przez `injury_lambda_factors`.
        """
        if not team_id:
            return {}
        if team_id in self._pozycje:
            return self._pozycje[team_id]
        try:
            dane = _pobierz("teams", id=team_id)
        except (requests.RequestException, ValueError) as e:
            log.debug("FotMob sklad druzyny %s pominiety: %s", team_id, e)
            self._pozycje[team_id] = {}
            return {}
        poz = parsuj_pozycje(dane)
        self._pozycje[team_id] = poz
        return poz

    def _dodaj_pozycje(self, tn: TeamNews, szczegoly: dict) -> TeamNews:
        """
        Dokleja absencjom pozycję ze składu drużyny.

        Skład to DWA dodatkowe requesty na mecz, więc pobieramy go WYŁĄCZNIE
        wtedy, gdy jest kogo klasyfikować. Mecz bez absencji nie płaci nic.

        Awaria zapytania o skład zostawia absencje bez pozycji — korekta
        degraduje do jednostronnej (`availability_edge`), zamiast zniknąć.
        """
        if not tn.absencje_home and not tn.absencje_away:
            return tn

        lineup = (szczegoly.get("content") or {}).get("lineup") or {}
        poz_h = self.pozycje_druzyny((lineup.get("homeTeam") or {}).get("id"))
        poz_a = self.pozycje_druzyny((lineup.get("awayTeam") or {}).get("id"))
        if not poz_h and not poz_a:
            return tn

        def _z_pozycja(absencje, pozycje):
            return tuple(
                replace(a, pozycja=pozycje.get(klucz_gracza(a.nazwisko)))
                for a in absencje
            )

        return replace(
            tn,
            absencje_home=_z_pozycja(tn.absencje_home, poz_h),
            absencje_away=_z_pozycja(tn.absencje_away, poz_a),
        )

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
            tn = self._dodaj_pozycje(tn, szczegoly)
            if tn.home and tn.away:
                wynik.append(tn)
            if _PRZERWA_S:
                time.sleep(_PRZERWA_S)
        return wynik
