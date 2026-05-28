from __future__ import annotations

from datetime import datetime

from footstats.utils.db import connect

_DDL = """
CREATE TABLE IF NOT EXISTS referees (
    id           SERIAL PRIMARY KEY,
    name         TEXT    NOT NULL UNIQUE,
    country      TEXT,
    avg_yellow   REAL,
    avg_red      REAL,
    avg_goals    REAL,
    home_win_pct REAL,
    n_matches    INTEGER,
    updated_at   TEXT
)
"""

_KARTKOWY_THRESHOLD = 4.3
_BRAMKOWY_THRESHOLD = 3.0


def init_referee_table() -> None:
    with connect() as conn:
        conn.execute(_DDL)


def upsert_referee(name: str, stats: dict) -> None:
    init_referee_table()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO referees (name, country, avg_yellow, avg_red, avg_goals,
                                  home_win_pct, n_matches, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                country      = excluded.country,
                avg_yellow   = excluded.avg_yellow,
                avg_red      = excluded.avg_red,
                avg_goals    = excluded.avg_goals,
                home_win_pct = excluded.home_win_pct,
                n_matches    = excluded.n_matches,
                updated_at   = excluded.updated_at
            """,
            (
                name,
                stats.get("country"),
                stats.get("avg_yellow"),
                stats.get("avg_red"),
                stats.get("avg_goals"),
                stats.get("home_win_pct"),
                stats.get("n_matches"),
                datetime.now().isoformat(),
            ),
        )


def get_referee(name: str) -> dict | None:
    init_referee_table()
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM referees WHERE name = ?", (name,)
        ).fetchone()
    if row is None:
        return None
    return dict(row)


def referee_signal(name: str) -> str:
    """Return one of: KARTKOWY | BRAMKOWY | NEUTRALNY | NIEZNANY"""
    ref = get_referee(name)
    if ref is None:
        return "NIEZNANY"
    avg_y = ref.get("avg_yellow") or 0.0
    avg_g = ref.get("avg_goals") or 0.0
    if avg_y > _KARTKOWY_THRESHOLD:
        return "KARTKOWY"
    if avg_g > _BRAMKOWY_THRESHOLD:
        return "BRAMKOWY"
    return "NEUTRALNY"
