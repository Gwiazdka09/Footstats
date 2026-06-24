"""tests/test_referee_db.py — SQLite-backed fixture (PostgreSQL DDL mocked)."""
from __future__ import annotations

import sqlite3
import pytest


class _SQLiteConn:
    """sqlite3 adapter matching footstats.utils.db._Conn interface."""

    def __init__(self, path: str) -> None:
        self._raw = sqlite3.connect(path)
        self._raw.row_factory = sqlite3.Row

    def execute(self, sql: str, params=()):
        return self._raw.execute(sql, params)

    def executemany(self, sql: str, seq):
        return self._raw.executemany(sql, seq)

    def executescript(self, script: str) -> None:
        self._raw.executescript(script)

    def commit(self) -> None:
        self._raw.commit()

    def rollback(self) -> None:
        self._raw.rollback()

    def close(self) -> None:
        self._raw.close()

    def __enter__(self) -> "_SQLiteConn":
        return self

    def __exit__(self, exc_type, *_) -> bool:
        if exc_type:
            self.rollback()
        else:
            self.commit()
        self.close()
        return False


_SCHEMA = """
CREATE TABLE IF NOT EXISTS referees (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
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


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test_referees.db")

    setup = sqlite3.connect(db_path)
    setup.executescript(_SCHEMA)
    setup.commit()
    setup.close()

    import footstats.scrapers.referee_db as rdb

    monkeypatch.setattr(rdb, "connect", lambda: _SQLiteConn(db_path))


def test_init_creates_table(tmp_path):
    # fixture already ran init via monkeypatched connect
    from footstats.scrapers.referee_db import init_referee_table
    init_referee_table()  # should be idempotent


def test_upsert_and_get_referee():
    from footstats.scrapers.referee_db import upsert_referee, get_referee
    upsert_referee("Szymon Marciniak", {
        "country": "Poland", "avg_yellow": 3.2, "avg_red": 0.1,
        "avg_goals": 2.8, "home_win_pct": 0.45, "n_matches": 120,
    })
    result = get_referee("Szymon Marciniak")
    assert result is not None
    assert abs(result["avg_yellow"] - 3.2) < 0.01
    assert result["country"] == "Poland"


def test_get_referee_returns_none_when_unknown():
    from footstats.scrapers.referee_db import get_referee
    assert get_referee("Nieznany Sędzia") is None


def test_upsert_updates_existing():
    from footstats.scrapers.referee_db import upsert_referee, get_referee
    upsert_referee("Test Ref", {"avg_yellow": 2.0, "avg_red": 0.0, "avg_goals": 2.5,
                                "home_win_pct": 0.40, "n_matches": 10})
    upsert_referee("Test Ref", {"avg_yellow": 6.0, "avg_red": 0.2, "avg_goals": 2.5,
                                "home_win_pct": 0.40, "n_matches": 20})
    result = get_referee("Test Ref")
    assert abs(result["avg_yellow"] - 6.0) < 0.01
    assert result["n_matches"] == 20


def test_referee_signal_kartkowy():
    from footstats.scrapers.referee_db import upsert_referee, referee_signal
    upsert_referee("Kartkowy", {"avg_yellow": 6.0, "avg_red": 0.3, "avg_goals": 2.5,
                                "home_win_pct": 0.45, "n_matches": 50})
    assert referee_signal("Kartkowy") == "KARTKOWY"


def test_referee_signal_bramkowy():
    from footstats.scrapers.referee_db import upsert_referee, referee_signal
    upsert_referee("Bramkowy", {"avg_yellow": 2.0, "avg_red": 0.0, "avg_goals": 3.5,
                                "home_win_pct": 0.48, "n_matches": 30})
    assert referee_signal("Bramkowy") == "BRAMKOWY"


def test_referee_signal_neutralny():
    from footstats.scrapers.referee_db import upsert_referee, referee_signal
    upsert_referee("Neutralny", {"avg_yellow": 3.0, "avg_red": 0.1, "avg_goals": 2.4,
                                 "home_win_pct": 0.45, "n_matches": 40})
    assert referee_signal("Neutralny") == "NEUTRALNY"


def test_referee_signal_nieznany():
    from footstats.scrapers.referee_db import referee_signal
    assert referee_signal("Nieznany XYZ") == "NIEZNANY"
