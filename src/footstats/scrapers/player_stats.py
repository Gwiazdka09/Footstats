"""
player_stats.py — Faza 1: pobranie statystyk graczy z API-Football
(/players/topscorers, 1 req/liga, cache+budżet klienta APIFootball) i zasilenie
`player_db`. Zwraca topowych strzelców ligi → goal_share dla Kontuzji v2.

Endpoint zwraca ~top 20 strzelców — wystarczy: injury model karze tylko utratę
realnego strzelca (gracz spoza bazy → flat fallback).
"""
from __future__ import annotations

from pathlib import Path

from footstats.config import DB_PATH
from footstats.core import player_db


def parse_topscorers(payload: dict | None) -> list[dict]:
    """
    Parsuje odpowiedź /players/topscorers → [{name, team, goals, assists, minutes}].
    Odporny na None/braki: gole/minuty None → 0. Pomija wpisy bez statystyk.
    """
    if not payload:
        return []
    out: list[dict] = []
    for entry in payload.get("response", []) or []:
        name = ((entry.get("player") or {}).get("name") or "").strip()
        stats = entry.get("statistics") or []
        if not name or not stats:
            continue
        st = stats[0] or {}
        goals = st.get("goals") or {}
        games = st.get("games") or {}
        team = ((st.get("team") or {}).get("name") or "").strip()
        if not team:
            continue
        out.append({
            "name": name,
            "team": team,
            "goals": int(goals.get("total") or 0),
            "assists": int(goals.get("assists") or 0),
            "minutes": int(games.get("minutes") or 0),
        })
    return out


def fetch_league_players(league_api_id: int, season: int, api_key: str) -> list[dict]:
    """
    Pobiera topowych strzelców ligi przez API-Football (cache+budżet).
    Zwraca listę wierszy (parse_topscorers) lub [] gdy brak danych/klucza.
    """
    if not api_key:
        return []
    from footstats.scrapers.api_football import APIFootball

    client = APIFootball(api_key)
    payload = client._get(
        "/players/topscorers", params={"league": league_api_id, "season": season}
    )
    return parse_topscorers(payload)


def refresh_league_players(
    league_api_id: int,
    season: int,
    api_key: str,
    db_path: Path | str = DB_PATH,
    league_code: str | None = None,
) -> int:
    """
    Fetch strzelców ligi → upsert do player_db. Zwraca liczbę zapisanych graczy.
    league_code: wewnętrzny kod ligi (np. "PL") zapisywany przy graczu.
    """
    rows = fetch_league_players(league_api_id, season, api_key)
    if not rows:
        return 0
    for r in rows:
        r["season"] = season
        r["league"] = league_code
    return player_db.upsert_players(rows, db_path=db_path)


def refresh_tracked_leagues(
    api_key: str, season: int | None = None, db_path: Path | str = DB_PATH
) -> int:
    """
    Odświeża strzelców wszystkich śledzonych lig (`_APISPORTS_LIGI`, ~16 req < budżet
    100/dzień). Zwraca łączną liczbę zapisanych graczy. season=None → sezon bieżący.
    """
    if not api_key:
        return 0
    from datetime import datetime

    from footstats.scrapers.api_football import _APISPORTS_LIGI

    if season is None:
        now = datetime.now()
        season = now.year if now.month > 6 else now.year - 1

    total = 0
    for api_id, info in _APISPORTS_LIGI.items():
        total += refresh_league_players(
            api_id, season, api_key, db_path=db_path, league_code=info.get("kod")
        )
    return total


def refresh_understat_leagues(
    season: int,
    db_path: Path | str = DB_PATH,
    only: list[str] | None = None,
) -> int:
    """
    Zbiera pełne składy TOP5 z Understat (scraper, bez klucza/budżetu API) → upsert
    do player_db. Pełen skład = prawdziwy denominator goal_share (bez zawyżenia
    z topscorers). Nadpisuje wpisy API-Football tym samym kluczem (name,team,season).
    only: lista kodów wewn. (np. ["PL","PD"]) — domyślnie wszystkie z UNDERSTAT_LIGI.
    """
    from footstats.scrapers.understat_xg import (
        UNDERSTAT_LIGI, fetch_league_players_understat,
    )

    total = 0
    for kod, ukey in UNDERSTAT_LIGI.items():
        if only and kod not in only:
            continue
        rows = fetch_league_players_understat(ukey, season)
        if not rows:
            continue
        for r in rows:
            r["season"] = season
            r["league"] = kod
        total += player_db.upsert_players(rows, db_path=db_path)
    return total
