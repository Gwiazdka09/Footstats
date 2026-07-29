"""
odds_api.py — kursy z The Odds API (https://the-odds-api.com), requests-only.

Po co kolejne źródło kursów: łańcuch Bzzoiro → API-Football → SofaScore ma słabe
ogniwo — SofaScore oddaje 403 i wymaga Playwrighta, więc w cloud draft
(requests-only) po prostu nie istnieje. The Odds API jest czystym REST-em bez
anti-bota i agreguje wielu bukmacherów.

Ekonomia zapytań (to jest główna przewaga):
  - API-Football: 1 mecz = 2 zapytania (`znajdz_fixture_id` + `kursy_fixture`).
  - The Odds API: 1 zapytanie zwraca WSZYSTKIE nadchodzące mecze danej ligi.
Koszt kredytu = [liczba rynków] × [liczba regionów]. Domyślnie `h2h,totals` × `eu`
= 2 kredyty na ligę. Darmowy limit to 500 kredytów/miesiąc, więc lig pytamy tylko
tyle, ile realnie mamy meczów bez kursów.

Konfiguracja: `ODDS_API_KEY` w env (patrz `.env.example`). Brak klucza = źródło
nieaktywne, reszta łańcucha działa bez zmian.
"""
from __future__ import annotations

import logging
import os
from statistics import median

import requests

from footstats.utils.normalize import _norm_ascii

log = logging.getLogger(__name__)

ENV_ODDS_API = "ODDS_API_KEY"
_BASE = "https://api.the-odds-api.com/v4"
_TIMEOUT = 15

# Linia totals, na której operuje model (Over/Under 2.5).
_LINIA_TOTALS = 2.5

# Mapowanie lig projektu → sport_key The Odds API. Nazwy lig bywają różne
# w zależności od źródła, więc dopasowanie jest luźne (substring, lowercase).
SPORT_KEYS: dict[str, str] = {
    "premier league": "soccer_epl",
    "la liga": "soccer_spain_la_liga",
    "primera division": "soccer_spain_la_liga",
    "serie a": "soccer_italy_serie_a",
    "bundesliga": "soccer_germany_bundesliga",
    "ligue 1": "soccer_france_ligue_one",
    "eredivisie": "soccer_netherlands_eredivisie",
    "primeira liga": "soccer_portugal_primeira_liga",
    "ekstraklasa": "soccer_poland_ekstraklasa",
    "championship": "soccer_efl_champ",
    "champions league": "soccer_uefa_champs_league",
    "europa league": "soccer_uefa_europa_league",
}


def sport_key_dla_ligi(liga: str) -> str | None:
    """Nazwa ligi (dowolne źródło) → sport_key The Odds API. None gdy nieznana."""
    nazwa = (liga or "").strip().lower()
    if not nazwa:
        return None
    for wzorzec, key in SPORT_KEYS.items():
        if wzorzec in nazwa:
            return key
    return None


class OddsAPIClient:
    """Cienki klient REST. Nigdy nie rzuca — brak danych zwraca pustą listę."""

    def __init__(
        self,
        api_key: str | None = None,
        regions: str = "eu",
        markets: str = "h2h,totals",
    ) -> None:
        self._key = api_key if api_key is not None else os.getenv(ENV_ODDS_API, "")
        self._regions = regions
        self._markets = markets

    def waliduj(self) -> tuple[bool, str]:
        """Czy źródło jest w ogóle użyteczne. Nie bije po sieci — sam brak klucza wystarczy."""
        if not self._key:
            return False, f"brak {ENV_ODDS_API} — The Odds API nieaktywne"
        return True, "The Odds API gotowe"

    def kursy_ligi(self, sport_key: str) -> list[dict]:
        """Wszystkie nadchodzące mecze ligi wraz z kursami. Jedno zapytanie."""
        if not self._key:
            return []
        try:
            r = requests.get(
                f"{_BASE}/sports/{sport_key}/odds",
                params={
                    "apiKey": self._key,
                    "regions": self._regions,
                    "markets": self._markets,
                    "oddsFormat": "decimal",
                    "dateFormat": "iso",
                },
                timeout=_TIMEOUT,
            )
        except (OSError, ValueError) as e:
            log.warning("The Odds API %s nieosiągalne: %s", sport_key, e)
            return []

        if r.status_code != 200:
            log.warning("The Odds API %s → HTTP %s", sport_key, r.status_code)
            return []

        # Nagłówki limitu — bez nich nie zauważymy wyczerpania darmowej puli.
        pozostalo = (r.headers or {}).get("x-requests-remaining")
        if pozostalo is not None:
            log.info("The Odds API: pozostalo %s kredytow", pozostalo)

        try:
            dane = r.json()
        except ValueError:
            return []
        return dane if isinstance(dane, list) else []


def _ceny_rynku(wydarzenie: dict, market_key: str) -> dict[str, list[float]]:
    """Zbiera ceny per nazwa outcome'u ze wszystkich bukmacherów danego rynku."""
    zebrane: dict[str, list[float]] = {}
    for bookmaker in (wydarzenie.get("bookmakers") or []):
        for market in (bookmaker.get("markets") or []):
            if market.get("key") != market_key:
                continue
            for outcome in (market.get("outcomes") or []):
                nazwa = str(outcome.get("name") or "").strip()
                if not nazwa:
                    continue
                if market_key == "totals" and outcome.get("point") != _LINIA_TOTALS:
                    continue  # inna linia niż 2.5 — nie mieszamy rynków
                try:
                    cena = float(outcome.get("price"))
                except (TypeError, ValueError):
                    continue
                if cena > 1.0:
                    zebrane.setdefault(nazwa, []).append(cena)
    return zebrane


def mapuj_wydarzenie(wydarzenie: dict) -> dict:
    """
    Wydarzenie The Odds API → dict kursów w schemacie projektu
    ({home, draw, away, over_2_5, under_2_5}). Brak danych → pusty dict.

    Wiele bukmacherów agregujemy **medianą, nie maksimum**: max zawyżałby EV
    kursem, którego user u swojego bukmachera nie dostanie, i produkowałby
    fałszywe value-bety. Mediana to konsensus rynku — spójne z reweightem
    ensemble ku rynkowi (`ENSEMBLE_MARKET_WEIGHT`).
    """
    if not isinstance(wydarzenie, dict):
        return {}

    home = str(wydarzenie.get("home_team") or "").strip()
    away = str(wydarzenie.get("away_team") or "").strip()
    odds: dict[str, float] = {}

    h2h = _ceny_rynku(wydarzenie, "h2h")
    for nazwa, ceny in h2h.items():
        if home and nazwa == home:
            odds["home"] = round(median(ceny), 2)
        elif away and nazwa == away:
            odds["away"] = round(median(ceny), 2)
        elif nazwa.lower() == "draw":
            odds["draw"] = round(median(ceny), 2)

    totals = _ceny_rynku(wydarzenie, "totals")
    for nazwa, ceny in totals.items():
        low = nazwa.lower()
        if low == "over":
            odds["over_2_5"] = round(median(ceny), 2)
        elif low == "under":
            odds["under_2_5"] = round(median(ceny), 2)

    return odds


def _niepelne_1x2(w: dict) -> bool:
    """Czy mecz ma lukę w kursach 1X2. Ten sam warunek co `daily_phases._wzbogac_o_kursy_fallback`."""
    odds = w.get("odds") or {}
    return not all(odds.get(k) for k in ("home", "draw", "away"))


def _klucz(home: str, away: str) -> tuple[str, str]:
    """Klucz meczu. STRICT `_norm_ascii` — `normalize_team_name` zbija City==United."""
    return (_norm_ascii(home), _norm_ascii(away))


def dolacz_kursy_odds_api(
    wyniki: list[dict],
    sport_keys: list[str] | None = None,
    klient: OddsAPIClient | None = None,
) -> int:
    """
    Uzupełnia brakujące kursy kandydatów z The Odds API. Zwraca ile meczów ruszyło.

    Nie nadpisuje kursów już obecnych (Bzzoiro/AF mają pierwszeństwo) — dokłada
    wyłącznie brakujące klucze. Gdy żaden mecz nie ma braków, nie wykonuje ANI
    JEDNEGO zapytania (darmowa pula to 500 kredytów/miesiąc).

    Dopasowanie po nazwach jest konserwatywne (exact po `_norm_ascii`, bez swapu) —
    ten sam wybór co w `core/match_linker.py`: lepiej brak kursu niż kurs z innego meczu.
    """
    braki = [w for w in wyniki if _niepelne_1x2(w)]
    if not braki:
        return 0

    klient = klient or OddsAPIClient()
    ok, msg = klient.waliduj()
    if not ok:
        log.debug("The Odds API pominiete: %s", msg)
        return 0

    if sport_keys is None:
        sport_keys = sorted({
            k for w in braki
            if (k := sport_key_dla_ligi(str(w.get("liga") or ""))) is not None
        })
    if not sport_keys:
        return 0

    indeks: dict[tuple[str, str], dict] = {}
    for sport_key in sport_keys:
        for wydarzenie in klient.kursy_ligi(sport_key):
            odds = mapuj_wydarzenie(wydarzenie)
            if not odds:
                continue
            klucz = _klucz(
                str(wydarzenie.get("home_team") or ""),
                str(wydarzenie.get("away_team") or ""),
            )
            if all(klucz):
                indeks[klucz] = odds

    if not indeks:
        return 0

    uzupelnione = 0
    for w in braki:
        odds = indeks.get(_klucz(str(w.get("gospodarz") or ""), str(w.get("goscie") or "")))
        if not odds:
            continue
        istniejace = dict(w.get("odds") or {})
        for klucz_rynku, cena in odds.items():
            istniejace.setdefault(klucz_rynku, cena)
        w["odds"] = istniejace
        uzupelnione += 1

    return uzupelnione
