"""
player_db.py — Faza 1 bazy graczy: persystencja statystyk zawodników w SQLite
(`data/footstats_backtest.db`) + wyliczanie goal_share (udziału w golach drużyny).

goal_share zasila Kontuzje v2 (`injury_lambda_factors`): utrata strzelca o share 0.4
karze λ mocniej niż rezerwowy 0.02. Denominator = suma goli zapisanych graczy zespołu
(topscorers ≈ większość goli), więc share jest miarą względną, spójną per drużyna.

Zero prod Neon — świadomie lokalny SQLite (reference/cache), testowalny na tmp db.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from footstats.config import DB_PATH
from footstats.utils.normalize import normalize_team_name

_DDL = """
CREATE TABLE IF NOT EXISTS player_stats (
    name         TEXT    NOT NULL,
    team_norm    TEXT    NOT NULL,
    team_display TEXT,
    league       TEXT,
    season       INTEGER NOT NULL,
    goals        INTEGER DEFAULT 0,
    assists      INTEGER DEFAULT 0,
    minutes      INTEGER DEFAULT 0,
    updated_at   TEXT,
    PRIMARY KEY (name, team_norm, season)
)
"""


def _connect(db_path: Path | str = DB_PATH) -> sqlite3.Connection:
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    return con


def init_player_table(db_path: Path | str = DB_PATH) -> None:
    """Tworzy tabelę player_stats jeśli nie istnieje."""
    with _connect(db_path) as con:
        con.execute(_DDL)


def upsert_players(rows: list[dict], db_path: Path | str = DB_PATH) -> int:
    """
    Wstawia/aktualizuje statystyki graczy. Konflikt (name, team_norm, season) →
    nadpisuje (najnowszy fetch wygrywa). Zwraca liczbę przetworzonych wierszy.

    row: {name, team, league, season, goals, assists, minutes}
    """
    init_player_table(db_path)
    now = datetime.now().isoformat()
    n = 0
    with _connect(db_path) as con:
        for r in rows:
            name = (r.get("name") or "").strip()
            team = (r.get("team") or "").strip()
            if not name or not team:
                continue
            con.execute(
                """
                INSERT INTO player_stats
                    (name, team_norm, team_display, league, season, goals, assists, minutes, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name, team_norm, season) DO UPDATE SET
                    team_display = excluded.team_display,
                    league       = excluded.league,
                    goals        = excluded.goals,
                    assists      = excluded.assists,
                    minutes      = excluded.minutes,
                    updated_at   = excluded.updated_at
                """,
                (
                    name,
                    normalize_team_name(team),
                    team,
                    r.get("league"),
                    int(r.get("season") or 0),
                    int(r.get("goals") or 0),
                    int(r.get("assists") or 0),
                    int(r.get("minutes") or 0),
                    now,
                ),
            )
            n += 1
    return n


def team_goal_shares(
    team: str, season: int, db_path: Path | str = DB_PATH
) -> dict[str, float]:
    """
    Zwraca {nazwa_gracza: udział_w_golach 0-1} dla drużyny w sezonie.
    Udział = gole gracza / suma goli zapisanych graczy zespołu. Pusty dict gdy
    brak drużyny / suma goli = 0 (bezpieczny fallback → injury model używa flat).
    """
    if not team:
        return {}
    tn = normalize_team_name(team)
    try:
        with _connect(db_path) as con:
            rows = con.execute(
                "SELECT name, goals FROM player_stats WHERE team_norm = ? AND season = ?",
                (tn, int(season)),
            ).fetchall()
    except sqlite3.Error:
        return {}
    total = sum(int(r["goals"] or 0) for r in rows)
    if total <= 0:
        return {}
    return {r["name"]: int(r["goals"] or 0) / total for r in rows if r["goals"]}
