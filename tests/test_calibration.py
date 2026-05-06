"""Testy jednostkowe modułu calibration (Etap 6) — SQLite mock."""
import sqlite3
import pytest

from footstats.core.calibration import (
    MULTIPLIER_HIGH, MULTIPLIER_LOW, MULTIPLIER_NEUTRAL,
    FORMA_WIN_MULTIPLIER, FORMA_LOSE_MULTIPLIER,
    calibration_summary, get_stake_multiplier, get_forma_multiplier,
)


class _SQLiteConn:
    def __init__(self, path: str) -> None:
        self._raw = sqlite3.connect(path)
        self._raw.row_factory = sqlite3.Row

    def execute(self, sql: str, params=()):
        return self._raw.execute(sql, params)

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


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "cal.db")
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE coupons (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT DEFAULT (datetime('now')),
            status     TEXT,
            stake_pln  REAL,
            payout_pln REAL,
            roi_pct    REAL
        )
    """)
    conn.commit()
    conn.close()

    import footstats.core.calibration as cal_mod
    monkeypatch.setattr(cal_mod, "_connect", lambda: _SQLiteConn(db_path))
    yield db_path


def _insert(db_path, rows):
    """rows: list of (status, stake_pln, roi_pct)"""
    conn = sqlite3.connect(db_path)
    conn.executemany(
        "INSERT INTO coupons (status, stake_pln, roi_pct) VALUES (?,?,?)", rows
    )
    conn.commit()
    conn.close()


# ── get_stake_multiplier ───────────────────────────────────────────────────────

def test_multiplier_high_form(tmp_db):
    """9/10 WON but last-3 = W,L,W → Forma neutral → hit-rate 1.2."""
    rows = [("WON", 10, 80)] * 8 + [("LOST", 10, -100), ("WON", 10, 80)]
    _insert(tmp_db, rows)
    assert get_stake_multiplier() == MULTIPLIER_HIGH


def test_multiplier_low_form(tmp_db):
    """4/10 WON, last-3 = L,W,L → Forma neutral → hit-rate 0.5."""
    rows = [("WON", 10, 80)] * 3 + [("LOST", 10, -100)] * 5 + [("WON", 10, 80), ("LOST", 10, -100)]
    _insert(tmp_db, rows)
    assert get_stake_multiplier() == MULTIPLIER_LOW


def test_multiplier_neutral_form(tmp_db):
    """6/10 WON, last-3 mixed → neutral."""
    rows = [("LOST", 10, -100)] * 3 + [("WON", 10, 80)] * 6 + [("LOST", 10, -100)]
    _insert(tmp_db, rows)
    assert get_stake_multiplier() == MULTIPLIER_NEUTRAL


def test_multiplier_no_history(tmp_db):
    """No resolved coupons → neutral."""
    _insert(tmp_db, [("ACTIVE", 10, None), ("DRAFT", 10, None)])
    assert get_stake_multiplier() == MULTIPLIER_NEUTRAL


def test_multiplier_boundary_high(tmp_db):
    """Exactly 80% (not > 80%) → neutral. last-3 = L,L,W → mix."""
    rows = [("WON", 10, 80)] * 8 + [("LOST", 10, -100)] * 2
    _insert(tmp_db, rows)
    assert get_stake_multiplier() == MULTIPLIER_NEUTRAL


# ── get_forma_multiplier ───────────────────────────────────────────────────────

def test_forma_3x_win(tmp_db):
    rows = [("LOST", 10, -100)] * 5 + [("WON", 10, 80)] * 3
    _insert(tmp_db, rows)
    assert get_forma_multiplier() == FORMA_WIN_MULTIPLIER


def test_forma_3x_lose(tmp_db):
    rows = [("WON", 10, 80)] * 5 + [("LOST", 10, -100)] * 3
    _insert(tmp_db, rows)
    assert get_forma_multiplier() == FORMA_LOSE_MULTIPLIER


def test_forma_mixed(tmp_db):
    _insert(tmp_db, [("WON", 10, 80), ("LOST", 10, -100), ("WON", 10, 80)])
    assert get_forma_multiplier() == MULTIPLIER_NEUTRAL


def test_forma_takes_priority_over_hitrate(tmp_db):
    _insert(tmp_db, [("WON", 10, 80)] * 10)
    assert get_stake_multiplier() == FORMA_WIN_MULTIPLIER


def test_forma_lose_takes_priority_over_hitrate(tmp_db):
    _insert(tmp_db, [("LOST", 10, -100)] * 10)
    assert get_stake_multiplier() == FORMA_LOSE_MULTIPLIER


# ── calibration_summary ────────────────────────────────────────────────────────

def test_summary_fields(tmp_db):
    rows = [("WON", 10, 50)] * 7 + [("LOST", 10, -100)] * 3
    _insert(tmp_db, rows)
    s = calibration_summary()
    assert {"n", "won", "lost", "hit_rate", "avg_roi_pct", "multiplier", "note"} <= s.keys()
    assert s["n"] == 10
    assert s["won"] == 7
    assert s["hit_rate"] == pytest.approx(0.7, abs=0.01)
