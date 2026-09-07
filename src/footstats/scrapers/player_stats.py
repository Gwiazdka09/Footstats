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


def parse_players_page(payload: dict | None) -> list[dict]:
    """Strona `/players` → [{name, team, goals, assists, minutes}].

    Różnica wobec `parse_topscorers` jest jedna, ale zasadnicza: **nie odrzucamy
    graczy z zerem goli**. `goal_share` dzieli przez sumę graczy zapisanych, więc
    kompletność tabeli JEST mianownikiem — a `player_db.MIN_SKLAD` odróżnia skład
    od czołówki strzelców właśnie po ich liczbie.

    Gracz po transferze ma kilka wpisów w `statistics`, po jednym na klub.
    Bierzemy każdy: gole strzelone w innym klubie nie mogą wejść do udziału
    w tym.
    """
    if not payload:
        return []
    out: list[dict] = []
    for entry in payload.get("response") or []:
        name = ((entry.get("player") or {}).get("name") or "").strip()
        if not name:
            continue
        for st in entry.get("statistics") or []:
            st = st or {}
            team = ((st.get("team") or {}).get("name") or "").strip()
            if not team:
                continue
            goals = st.get("goals") or {}
            games = st.get("games") or {}
            out.append({
                "name": name,
                "team": team,
                "goals": int(goals.get("total") or 0),
                "assists": int(goals.get("assists") or 0),
                "minutes": int(games.get("minutes") or 0),
            })
    return out


# Sufit stron na ligę. `paging.total` przychodzi z zewnątrz, a jedna absurdalna
# wartość zjadłaby dzienny budżet zapytań. Premier League 2025 ma 34 strony,
# więc 60 zostawia zapas na największe ligi i dalej mieści się w limicie.
_MAX_STRON = 60


def fetch_league_squad(
    league_api_id: int, season: int, api_key: str,
    max_stron: int = _MAX_STRON, _klient=None,
) -> list[dict]:
    """Pełne kadry ligi z `/players`, strona po stronie. [] gdy brak klucza/danych.

    PO CO, skoro `fetch_league_players` już istnieje: tamta funkcja pyta
    `/players/topscorers`, który oddaje **20 nazwisk na całą ligę**, czyli 1-4 na
    drużynę. Na takim mianowniku `goal_share` jednego zawodnika wychodził 100%
    (pomiar 07.09: 62% drużyn z realnego ruchu). Understat, jedyne dotychczasowe
    źródło pełnych składów, jest martwy od tego samego dnia.

    KOSZT: Premier League 2025 to 34 strony po 20 graczy. Przy 16 śledzonych
    ligach daje to około 550 zapytań wobec 7500/dzień na planie Pro.

    Dziura w środku (strona bez odpowiedzi) NIE kończy ligi — przerwanie na niej
    dawałoby po cichu obciętą kadrę, czyli dokładnie ten zafałszowany mianownik,
    który ta funkcja usuwa.
    """
    if not api_key and _klient is None:
        return []
    if _klient is None:
        from footstats.scrapers.api_football import APIFootball
        _klient = APIFootball(api_key)

    wiersze: list[dict] = []
    strona, ostatnia = 1, 1
    while strona <= min(ostatnia, max_stron):
        payload = _klient._get(
            "/players",
            params={"league": league_api_id, "season": season, "page": strona},
            # Odpowiedź i tak ląduje w `player_stats`, więc disk cache trzymałby
            # te same dane drugi raz — i to bardzo drogo: jeden plik JSON,
            # czytany i zapisywany W CAŁOŚCI przy każdym żądaniu, urósł do 30 MB.
            # Przy ~550 stronach backfillu to ~33 GB dysku i ~7 minut na ligę.
            bez_cache=True,
        )
        if strona == 1 and not (payload or {}).get("response"):
            # Pusta PIERWSZA strona = liga nie ma danych na ten sezon. Dalsze
            # strony byłyby wtedy zapytaniami w ciemno.
            return []
        wiersze.extend(parse_players_page(payload))
        ostatnia = max(ostatnia, int(((payload or {}).get("paging") or {}).get("total") or 1))
        strona += 1
    return wiersze


def refresh_league_squad(
    league_api_id: int,
    season: int,
    api_key: str,
    db_path: Path | str = DB_PATH,
    league_code: str | None = None,
) -> int:
    """Pełna kadra ligi → upsert do `player_db`. Zwraca liczbę zapisanych wierszy."""
    rows = fetch_league_squad(league_api_id, season, api_key)
    if not rows:
        return 0
    for r in rows:
        r["season"] = season
        r["league"] = league_code
    return player_db.upsert_players(rows, db_path=db_path)


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
