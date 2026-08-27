"""
odds_snapshot.py — SUROWE kwoty per bukmacher z The Odds API.

Roznica wobec `odds_api.py`: tamten modul zbiera ceny wszystkich ksiazek do
`{outcome: [ceny]}`, gubi nazwe bukmachera i zwraca MEDIANE. Rozrzut miedzy
ksiazkami — dokladnie ta wielkosc, o ktora chodzi w pilocie — jest tam liczony
i wyrzucany przy kazdym zapytaniu. Ten modul niczego nie agreguje.

Spec: docs/superpowers/specs/2026-08-27-rozrzut-kursow-pilot-design.md
"""
from __future__ import annotations

import logging
import os

import requests

log = logging.getLogger(__name__)

ENV_ODDS_API = "ODDS_API_KEY"
_BASE = "https://api.the-odds-api.com/v4"
_TIMEOUT = 15

# Linia, na ktorej operuje model (Over/Under 2.5). Inne linie to inne rynki —
# zmieszanie ich zafalszowaloby devig.
LINIA_TOTALS = 2.5

# Prog bezpieczenstwa: pula 500 kredytow/mies. jest DZIELONA z produkcyjna
# sciezka kursow (`odds_api.py`). Eksperyment nie ma prawa jej zjesc.
KREDYTY_MINIMUM = 50

LIGI_PILOTA: dict[str, str] = {
    "soccer_epl": "Premier League",
    "soccer_china_superleague": "Chinese Super League",
    "soccer_japan_j_league": "J1 League",
}

# Ostatnia znana liczba pozostalych kredytow. None = jeszcze nie pytalismy,
# wiec pierwsze zapytanie zawsze przechodzi.
_ostatnie_kredyty: int | None = None


def zeruj_stan_kredytow() -> None:
    """Kasuje pamiec o kredytach. Do uzytku testow — stan modulowy przecieka
    miedzy testami i bezpiecznik zachowywalby sie zaleznie od kolejnosci."""
    global _ostatnie_kredyty
    _ostatnie_kredyty = None


def ostatnie_kredyty() -> int | None:
    """Ile kredytow zostalo wg ostatniej odpowiedzi (None = brak informacji)."""
    return _ostatnie_kredyty


def _zapamietaj_kredyty(odpowiedz) -> None:
    global _ostatnie_kredyty
    try:
        _ostatnie_kredyty = int(odpowiedz.headers.get("x-requests-remaining"))
    except (TypeError, ValueError, AttributeError):
        return
    log.info("The Odds API: pozostalo %s kredytow", _ostatnie_kredyty)


def _wiersze_z_wydarzenia(wydarzenie: dict, sport_key: str) -> list[dict]:
    """Splaszcza jedno wydarzenie do wierszy (bukmacher, rynek, wynik, cena).

    NIE agreguje. Kazda ksiazka daje wlasny wiersz — to jest cel tego modulu.
    """
    event_id = str(wydarzenie.get("id") or "").strip()
    home = str(wydarzenie.get("home_team") or "").strip()
    away = str(wydarzenie.get("away_team") or "").strip()
    if not (event_id and home and away):
        return []

    wiersze: list[dict] = []
    for bookmaker in (wydarzenie.get("bookmakers") or []):
        klucz_b = str(bookmaker.get("key") or "").strip()
        if not klucz_b:
            continue
        for market in (bookmaker.get("markets") or []):
            rynek = str(market.get("key") or "").strip()
            if rynek not in ("h2h", "totals"):
                continue
            for outcome in (market.get("outcomes") or []):
                nazwa = str(outcome.get("name") or "").strip()
                if not nazwa:
                    continue
                if rynek == "totals":
                    if outcome.get("point") != LINIA_TOTALS:
                        continue
                    linia = LINIA_TOTALS
                else:
                    # `line` jest NOT NULL w schemacie; 0 znaczy „rynek bez linii".
                    linia = 0.0
                try:
                    cena = float(outcome.get("price"))
                except (TypeError, ValueError):
                    continue
                if cena <= 1.0:
                    continue
                wiersze.append({
                    "sport_key": sport_key,
                    "event_id": event_id,
                    "commence_time": wydarzenie.get("commence_time"),
                    "team_home": home,
                    "team_away": away,
                    "market": rynek,
                    "line": linia,
                    "outcome": nazwa,
                    "bookmaker": klucz_b,
                    "price": cena,
                })
    return wiersze


def pobierz_migawke(
    sport_key: str,
    markets: str = "h2h,totals",
    regions: str = "eu",
    klucz: str | None = None,
) -> list[dict]:
    """
    Jedna liga, jedno zapytanie. Zwraca plaskie wiersze per bukmacher.

    Brak klucza albo blad HTTP → pusta lista i log, bez wyjatku. Kolektor jest
    eksperymentem wpietym w potok produkcyjny i nie ma prawa go zatrzymac.
    """
    api_key = klucz if klucz is not None else os.getenv(ENV_ODDS_API, "").strip()
    if not api_key:
        log.warning("odds_snapshot: brak %s — pomijam %s", ENV_ODDS_API, sport_key)
        return []

    try:
        odpowiedz = requests.get(
            f"{_BASE}/sports/{sport_key}/odds",
            params={
                "apiKey": api_key,
                "regions": regions,
                "markets": markets,
                "oddsFormat": "decimal",
            },
            timeout=_TIMEOUT,
        )
    except requests.RequestException as e:
        log.warning("odds_snapshot: %s nieosiagalne: %s", sport_key, e)
        return []

    _zapamietaj_kredyty(odpowiedz)

    if odpowiedz.status_code != 200:
        log.warning("odds_snapshot: %s → HTTP %s", sport_key, odpowiedz.status_code)
        return []

    try:
        dane = odpowiedz.json()
    except ValueError:
        log.warning("odds_snapshot: %s → odpowiedz nie jest JSON-em", sport_key)
        return []
    if not isinstance(dane, list):
        return []

    wiersze: list[dict] = []
    for wydarzenie in dane:
        if isinstance(wydarzenie, dict):
            wiersze.extend(_wiersze_z_wydarzenia(wydarzenie, sport_key))
    log.info("odds_snapshot: %s → %d wydarzen, %d wierszy",
             sport_key, len(dane), len(wiersze))
    return wiersze


def zamiataj_pilota(klucz: str | None = None) -> dict:
    """
    Obchodzi trzy ligi pilota. Staje, gdy kredytow zostalo mniej niz
    `KREDYTY_MINIMUM` — pula jest wspolna z produkcyjna sciezka kursow.
    """
    wiersze: list[dict] = []
    ligi = 0
    zatrzymany = False

    for sport_key in LIGI_PILOTA:
        if _ostatnie_kredyty is not None and _ostatnie_kredyty < KREDYTY_MINIMUM:
            log.warning(
                "odds_snapshot: zostalo %s kredytow (prog %s) — przerywam"
                " zamiatanie przed %s, zeby nie zjesc puli sciezce produkcyjnej",
                _ostatnie_kredyty, KREDYTY_MINIMUM, sport_key,
            )
            zatrzymany = True
            break
        wiersze.extend(pobierz_migawke(sport_key, klucz=klucz))
        ligi += 1

    return {
        "ligi": ligi,
        "wierszy": len(wiersze),
        "kredyty": _ostatnie_kredyty,
        "zatrzymany_przez_kredyty": zatrzymany,
        "wiersze": wiersze,
    }
