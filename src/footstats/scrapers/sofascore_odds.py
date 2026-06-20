"""
sofascore_odds.py – Fallback kursów bukmacherskich przez SofaScore (gdy Bzzoiro
nie ma kursów dla danego meczu, np. egzotyczne ligi / MŚ).

Reużywa wzorca z `footstats.scrapers.form_scraper`: Playwright (omija 403),
cache na dysku z TTL, `_sofa_fetch`/`_sofa_session`/`find_team_id`.

Przepływ:
    find_team_id(home) -> /team/{id}/events/next/0 -> fuzzy match (away, data)
    -> event_id -> /event/{event_id}/odds/1/all -> parsing rynków

Użycie:
    from footstats.scrapers.sofascore_odds import fetch_odds
    odds = fetch_odds("Real Madrid", "Barcelona", "2026-06-21")
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from footstats.scrapers.form_scraper import (
    PLAYWRIGHT_OK,
    SOFA_BASE,
    _sofa_fetch,
    _sofa_session,
    find_team_id,
)
from footstats.utils.normalize import normalize_team_name

logger = logging.getLogger(__name__)

CACHE_DIR = Path("cache/sofa_odds")
CACHE_TTL_HOURS = 2

# Mapowanie nazw rynków SofaScore -> nazw wewnetrznych (jak w system_paper._ODDS_KEY)
_MARKET_1X2 = {"Full time", "1X2", "Match winner"}
_MARKET_OU25 = {"Match goals", "Over/Under 2.5", "Total goals"}
_MARKET_BTTS = {"Both teams to score"}


# ── Cache ─────────────────────────────────────────────────────────────────────
def _cache_path(event_id: int) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"event_{event_id}.json"


def _load_cache(event_id: int) -> Optional[dict]:
    p = _cache_path(event_id)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        saved = datetime.fromisoformat(data.get("_cached_at", "2000-01-01T00:00:00"))
        if (datetime.now() - saved).total_seconds() / 3600 < CACHE_TTL_HOURS:
            return data.get("odds")
    except (OSError, ValueError) as e:
        logger.debug("Błąd odczytu cache sofascore_odds: %s", e)
    return None


def _save_cache(event_id: int, odds: dict) -> None:
    payload = {"odds": odds, "_cached_at": datetime.now().isoformat()}
    _cache_path(event_id).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ── Parsowanie ────────────────────────────────────────────────────────────────
def fractional_to_decimal(fractional: str) -> Optional[float]:
    """Konwertuje kurs fractional SofaScore (np. '5/2') na decimal (3.5)."""
    try:
        num_str, den_str = fractional.split("/")
        num, den = float(num_str), float(den_str)
        if den == 0:
            return None
        return round(num / den + 1, 3)
    except (ValueError, AttributeError, ZeroDivisionError):
        return None


def _parse_markets(odds_json: dict) -> dict:
    """Parsuje JSON odds SofaScore (/event/{id}/odds/1/all) do płaskiego dict."""
    result: dict = {}
    markets = odds_json.get("markets", []) if odds_json else []

    for market in markets:
        name = market.get("marketName", "")
        choices = market.get("choices", [])

        if name in _MARKET_1X2:
            for ch in choices:
                dec = fractional_to_decimal(ch.get("fractionalValue", ""))
                if dec is None:
                    continue
                label = ch.get("name", "")
                if label == "1":
                    result["home"] = dec
                elif label == "X":
                    result["draw"] = dec
                elif label == "2":
                    result["away"] = dec

        elif name in _MARKET_OU25:
            for ch in choices:
                dec = fractional_to_decimal(ch.get("fractionalValue", ""))
                if dec is None:
                    continue
                label = (ch.get("name", "") or "").lower()
                if "over" in label:
                    result["over_2_5"] = dec
                elif "under" in label:
                    result["under_2_5"] = dec

        elif name in _MARKET_BTTS:
            for ch in choices:
                if (ch.get("name", "") or "").lower() == "yes":
                    dec = fractional_to_decimal(ch.get("fractionalValue", ""))
                    if dec is not None:
                        result["btts"] = dec

    return result


# ── Wyszukiwanie meczu ────────────────────────────────────────────────────────
def _names_match(team_name: str, away: str) -> bool:
    """Fuzzy match nazw drużyn (po normalizacji)."""
    n1, n2 = normalize_team_name(team_name), normalize_team_name(away)
    if not n1 or not n2:
        return False
    return n1 == n2 or n1 in n2 or n2 in n1


def _find_event_id(page, team_id: int, away: str, data: str) -> Optional[int]:
    """Szuka nadchodzacego wydarzenia drużyny `team_id` przeciwko `away` blisko daty `data`."""
    events_data = _sofa_fetch(page, f"/team/{team_id}/events/next/0")
    if not events_data:
        return None

    try:
        target_date = datetime.fromisoformat(data).date()
    except (ValueError, TypeError):
        target_date = None

    best_id = None
    best_diff = None
    for ev in events_data.get("events", []):
        home_name = ev.get("homeTeam", {}).get("name", "")
        away_name = ev.get("awayTeam", {}).get("name", "")
        if not (_names_match(home_name, away) or _names_match(away_name, away)):
            continue

        eid = ev.get("id")
        if eid is None:
            continue

        if target_date is None:
            return eid

        ts = ev.get("startTimestamp")
        try:
            ev_date = datetime.fromtimestamp(ts).date()
            diff = abs((ev_date - target_date).days)
        except (TypeError, ValueError, OSError, OverflowError):
            diff = 99

        if best_diff is None or diff < best_diff:
            best_diff, best_id = diff, eid

    return best_id


# ── Główna funkcja ────────────────────────────────────────────────────────────
def fetch_odds(home: str, away: str, data: str, page=None) -> Optional[dict]:
    """
    Pobiera kursy DECIMAL dla meczu home vs away (blisko daty `data`) z SofaScore.

    Zwraca dict z podzbiorem kluczy {home, draw, away, over_2_5, under_2_5, btts}
    (tylko te rynki, które realnie znaleziono) lub None gdy mecz/kursy nie znalezione.
    """
    if not PLAYWRIGHT_OK:
        logger.info("[SofaScoreOdds] Playwright niedostępny — pomijam fallback kursów")
        return None

    own_session = page is None
    if own_session:
        sess = _sofa_session()
        if sess is None:
            return None
        p, browser, page = sess

    try:
        team_id = find_team_id(home, page)
        if team_id is None:
            logger.info(f"[SofaScoreOdds] Nie znaleziono drużyny: {home}")
            return None

        event_id = _find_event_id(page, team_id, away, data)
        if event_id is None:
            logger.info(f"[SofaScoreOdds] Nie znaleziono meczu: {home} vs {away} ({data})")
            return None

        cached = _load_cache(event_id)
        if cached is not None:
            return cached or None

        odds_json = _sofa_fetch(page, f"/event/{event_id}/odds/1/all")
        if not odds_json:
            logger.info(f"[SofaScoreOdds] Brak kursów dla event_id={event_id}")
            return None

        odds = _parse_markets(odds_json)
        _save_cache(event_id, odds)
        return odds or None
    finally:
        if own_session:
            browser.close()
            p.stop()
