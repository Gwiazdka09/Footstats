"""
espn_stats.py — statystyki meczu z ESPN (rzuty rożne, zawodnicy) dla dziennika kuponów.

Nieoficjalne API (site.api.espn.com), bez klucza i gwarancji. Każdy błąd sieci/JSON
daje `log.warning` i `None` (nigdy wyjątek) — brak statystyk = noga zostaje do ręcznego
rozliczenia. Używane TYLKO przez ścieżkę manual (`settle_manual_coupons`).

Zwracany kształt:
    {"corners": (gospodarz, gość) | None,
     "zawodnicy": {nazwa_znormalizowana: {"gole": int, "sot": int,
                                          "zagral": bool, "druzyna": "home"|"away"}}}

Gole zawodnika = `totalGoals` (samobóje ESPN raportuje osobno jako `ownGoals`
i nie wchodzą do `gole`).
"""
from __future__ import annotations

import logging
from datetime import date as _date, timedelta

import requests

from footstats.scrapers.sources.espn_source import _HEADERS, _STATUS_KONIEC, _URL, _nazwa
from footstats.utils.betting import normalizuj_nazwisko
from footstats.utils.normalize import team_similarity

log = logging.getLogger(__name__)

_URL_SUMMARY = "https://site.api.espn.com/apis/site/v2/sports/soccer/all/summary"
_PROG_DRUZYNY = 0.70  # ta sama reguła co `_znajdz_wynik_fdb` (min z pary, team_similarity)


def _pobierz(url: str, params: dict) -> dict | None:
    """GET + JSON; None (z ostrzeżeniem) przy każdym błędzie."""
    try:
        resp = requests.get(url, params=params, headers=_HEADERS, timeout=15)
        if resp.status_code != 200:
            log.warning("espn_stats: HTTP %s dla %s", resp.status_code, params)
            return None
        dane = resp.json()
        return dane if isinstance(dane, dict) else None
    except (requests.RequestException, ValueError) as e:
        log.warning("espn_stats: błąd pobierania %s (%s: %s)", params, type(e).__name__, e)
        return None


def _rozne(competitor: dict) -> int | None:
    """Wartość statystyki `wonCorners` drużyny albo None."""
    for st in competitor.get("statistics") or []:
        if isinstance(st, dict) and st.get("name") == "wonCorners":
            try:
                return int(float(str(st.get("displayValue", st.get("value")))))
            except (TypeError, ValueError) as e:
                log.warning("espn_stats: nieczytelne wonCorners (%s)", e)
                return None
    return None


def _opis_zdarzenia(ev: dict) -> dict | None:
    """Id, nazwy, rożne i status jednego zdarzenia scoreboardu; None gdy uszkodzone."""
    try:
        strony = {c["homeAway"]: c for c in ev["competitions"][0]["competitors"]}
        return {
            "id": str(ev["id"]),
            "koniec": ev["status"]["type"]["name"] == _STATUS_KONIEC,
            "home": _nazwa(strony["home"]["team"]["displayName"]),
            "away": _nazwa(strony["away"]["team"]["displayName"]),
            "rozne": (_rozne(strony["home"]), _rozne(strony["away"])),
        }
    except (KeyError, IndexError, TypeError, AttributeError) as e:
        log.warning("espn_stats: pominięto uszkodzone zdarzenie (%s: %s)",
                    type(e).__name__, e)
        return None


def _znajdz_zdarzenie(home: str, away: str, data: str) -> dict | None:
    """Najlepsze zakończone zdarzenie (min podobieństwa pary >= próg) z dni d-1..d+1."""
    try:
        dzien = _date.fromisoformat(data[:10])
    except ValueError:
        log.warning("espn_stats: niepoprawna data %r", data)
        return None
    najlepsze, wynik = 0.0, None
    for przes in (-1, 0, 1):
        klucz = (dzien + timedelta(days=przes)).strftime("%Y%m%d")
        dane = _pobierz(_URL, {"dates": klucz, "limit": 1000})
        for ev in (dane or {}).get("events") or []:
            opis = _opis_zdarzenia(ev) if isinstance(ev, dict) else None
            if not opis or not opis["koniec"]:
                continue
            ocena = min(team_similarity(home, opis["home"]),
                        team_similarity(away, opis["away"]))
            if ocena >= _PROG_DRUZYNY and ocena > najlepsze:
                najlepsze, wynik = ocena, opis
    return wynik


def _statystyka(zawodnik: dict, nazwa: str) -> int:
    for st in zawodnik.get("stats") or []:
        if isinstance(st, dict) and st.get("name") == nazwa:
            try:
                return int(float(st.get("value") or 0))
            except (TypeError, ValueError) as e:
                log.warning("espn_stats: nieczytelna statystyka %s (%s)", nazwa, e)
                return 0
    return 0


def _zawodnicy(summary: dict) -> dict:
    """Mapa zawodników z `rosters`; wpisy bez `athlete` są pomijane."""
    wynik: dict = {}
    for sklad in summary.get("rosters") or []:
        if not isinstance(sklad, dict) or sklad.get("homeAway") not in ("home", "away"):
            continue
        for z in sklad.get("roster") or []:
            athlete = z.get("athlete") if isinstance(z, dict) else None
            if not isinstance(athlete, dict) or not athlete.get("displayName"):
                continue
            wynik[normalizuj_nazwisko(athlete["displayName"])] = {
                "gole": _statystyka(z, "totalGoals"),
                "sot": _statystyka(z, "shotsOnTarget"),
                "zagral": _statystyka(z, "appearances") > 0,
                "druzyna": sklad["homeAway"],
            }
    return wynik


def statystyki_meczu(home: str, away: str, data: str) -> dict | None:
    """Statystyki zakończonego meczu (rożne + zawodnicy) albo None gdy brak/błąd."""
    ev = _znajdz_zdarzenie(home, away, data)
    if ev is None:
        log.warning("espn_stats: brak zakończonego meczu %s - %s (%s)", home, away, data)
        return None
    summary = _pobierz(_URL_SUMMARY, {"event": ev["id"]})
    if summary is None:
        return None
    rozne = ev["rozne"] if None not in ev["rozne"] else None
    return {"corners": rozne, "zawodnicy": _zawodnicy(summary)}
