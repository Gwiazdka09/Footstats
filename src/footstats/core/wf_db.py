"""core/wf_db.py — persystencja wyników walk-forward do SQLite (offline).

ŚWIADOMIE odseparowane od footstats.utils.db (Neon prod) — backtest nie może
zanieczyszczać produkcji. Domyślny plik: data/walkforward.db.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parents[3] / "data" / "walkforward.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS wf_runs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    run_tag    TEXT NOT NULL,
    league     TEXT,
    match_date TEXT,
    home       TEXT,
    away       TEXT,
    actual_res TEXT,
    pred_tip   TEXT,
    pred_conf  REAL,
    correct    INTEGER,
    no_odds    INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_wf_runs_tag ON wf_runs(run_tag);
"""

_COLS = ("run_tag", "league", "match_date", "home", "away",
         "actual_res", "pred_tip", "pred_conf", "correct", "no_odds")


def init_db(db_path: Path | str = DEFAULT_DB) -> None:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        con.executescript(_SCHEMA)
        con.commit()
    finally:
        con.close()


def save_run(db_path: Path | str, rows: list[dict]) -> int:
    con = sqlite3.connect(Path(db_path))
    try:
        con.executemany(
            f"INSERT INTO wf_runs ({','.join(_COLS)}) "  # nosec B608 — _COLS stała lista kolumn (kod), wartości przez ? param
            f"VALUES ({','.join('?' * len(_COLS))})",
            [tuple(r.get(c) for c in _COLS) for r in rows],
        )
        con.commit()
        return len(rows)
    finally:
        con.close()


def load_run(db_path: Path | str, run_tag: str) -> list[dict]:
    con = sqlite3.connect(Path(db_path))
    con.row_factory = sqlite3.Row
    try:
        cur = con.execute("SELECT * FROM wf_runs WHERE run_tag = ? ORDER BY id", (run_tag,))
        return [dict(r) for r in cur.fetchall()]
    finally:
        con.close()
