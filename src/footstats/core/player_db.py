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
    rating       REAL,
    xg           REAL,
    updated_at   TEXT,
    PRIMARY KEY (name, team_norm, season)
)
"""

# Kolumny dokładane migracyjnie do istniejących tabel (ALTER ADD COLUMN)
_OPTIONAL_COLS = {"rating": "REAL", "xg": "REAL"}


def _connect(db_path: Path | str = DB_PATH) -> sqlite3.Connection:
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    return con


def init_player_table(db_path: Path | str = DB_PATH) -> None:
    """Tworzy tabelę player_stats + dokłada brakujące kolumny (migracja rating/xg)."""
    with _connect(db_path) as con:
        con.execute(_DDL)
        existing = {r["name"] for r in con.execute("PRAGMA table_info(player_stats)")}
        for col, typ in _OPTIONAL_COLS.items():
            if col not in existing:
                con.execute(f"ALTER TABLE player_stats ADD COLUMN {col} {typ}")


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
            rating = r.get("rating")
            xg = r.get("xg")
            con.execute(
                """
                INSERT INTO player_stats
                    (name, team_norm, team_display, league, season, goals, assists,
                     minutes, rating, xg, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name, team_norm, season) DO UPDATE SET
                    team_display = excluded.team_display,
                    league       = excluded.league,
                    goals        = excluded.goals,
                    assists      = excluded.assists,
                    minutes      = excluded.minutes,
                    rating       = COALESCE(excluded.rating, player_stats.rating),
                    xg           = COALESCE(excluded.xg, player_stats.xg),
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
                    float(rating) if rating is not None else None,
                    float(xg) if xg is not None else None,
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


def get_team_players(
    team: str, season: int, db_path: Path | str = DB_PATH
) -> list[dict]:
    """
    Pełne wiersze graczy drużyny w sezonie (name, goals, assists, minutes, rating, xg),
    posortowane malejąco po golach. Pusta lista gdy brak/błąd. Rating = ocena 1-10
    (Sofascore, gdy dostępna), xg = expected goals.
    """
    if not team:
        return []
    tn = normalize_team_name(team)
    try:
        with _connect(db_path) as con:
            rows = con.execute(
                "SELECT name, goals, assists, minutes, rating, xg FROM player_stats "
                "WHERE team_norm = ? AND season = ? ORDER BY goals DESC",
                (tn, int(season)),
            ).fetchall()
    except sqlite3.Error:
        return []
    return [dict(r) for r in rows]


def team_goal_shares_recent(
    team: str, season: int, lookback: int = 2, db_path: Path | str = DB_PATH
) -> dict[str, float]:
    """
    goal_shares dla drużyny z najświeższego dostępnego sezonu: próbuje `season`,
    potem season-1 ... season-lookback. Zwraca pierwszy niepusty (off-season /
    przerwa międzysezonowa → używa poprzedniej kampanii). {} gdy brak w oknie.
    """
    for s in range(int(season), int(season) - lookback - 1, -1):
        shares = team_goal_shares(team, s, db_path=db_path)
        if shares:
            return shares
    return {}
