"""tests/test_bankroll.py — SQLite-backed fixture (PostgreSQL DDL mocked). TD-31."""
import json
import sqlite3

import pytest


class _SQLiteConn:
    """sqlite3 adapter matching footstats.utils.db._Conn interface."""

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


_SCHEMA = """
CREATE TABLE IF NOT EXISTS bankroll_state (
    user_id    INTEGER PRIMARY KEY,
    balance    REAL NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS bankroll_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    change_pln REAL NOT NULL,
    new_balance REAL NOT NULL,
    type       TEXT NOT NULL,
    description TEXT,
    timestamp  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS coupons (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status     TEXT NOT NULL DEFAULT 'DRAFT',
    user_id    INTEGER DEFAULT 1
);
"""


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    """Each test gets own SQLite DB; _connect + agent_state.json mocked."""
    db_path = str(tmp_path / "test.db")

    setup = sqlite3.connect(db_path)
    setup.executescript(_SCHEMA)
    setup.commit()
    setup.close()

    import footstats.core.bankroll as br

    monkeypatch.setattr(br, "_connect", lambda: _SQLiteConn(db_path))
    monkeypatch.setattr(br, "_STATE_FILE", tmp_path / "agent_state.json")
    yield db_path


import footstats.core.bankroll as br
from footstats.core.bankroll import (
    check_daily_stop_loss,
    get_current_bankroll,
    get_loss_streak,
    get_pause_state,
    get_stake_multiplier,
    is_agent_paused,
    kelly_fraction,
    process_bet,
    process_win,
    set_agent_paused,
    update_bankroll,
)


def test_init_and_get_current_bankroll_returns_default():
    balance = get_current_bankroll()
    from footstats.config import AGENT_BANKROLL
    assert balance == AGENT_BANKROLL


def test_update_bankroll_bet_and_win_adjust_balance():
    start = get_current_bankroll()

    after_bet = process_bet(10.0, "test bet")
    assert after_bet == pytest.approx(start - 10.0)

    after_win = process_win(50.0, "test win")
    # process_win reinwestuje 50% wygranej
    assert after_win == pytest.approx(after_bet + 25.0)


def test_update_bankroll_bet_never_goes_negative():
    start = get_current_bankroll()
    new_balance = update_bankroll(-(start + 1000), "BET", "huge bet")
    assert new_balance == 0


def test_kelly_fraction_zero_when_no_edge():
    # kurs odpowiada uczciwemu prawdopodobienstwu -> brak edge
    assert kelly_fraction(prob=0.5, kurs=2.0, bankroll=1000) == 0.0


def test_kelly_fraction_positive_edge_respects_caps():
    stake = kelly_fraction(prob=0.6, kurs=2.0, bankroll=1000, frac=0.25)
    assert 1.0 <= stake <= 100.0  # min 1 PLN, max 10% bankrolla


def test_loss_streak_and_stake_multiplier():
    # WON najstarszy, potem 3x LOST coraz nowsze -> streak=3 od najnowszego
    rows = [
        ("WON", "2026-06-10 12:00:00"),
        ("LOST", "2026-06-11 12:00:00"),
        ("LOST", "2026-06-12 12:00:00"),
        ("LOST", "2026-06-13 12:00:00"),
    ]
    with br._connect() as conn:
        for status, created_at in rows:
            conn.execute(
                "INSERT INTO coupons (status, user_id, created_at) VALUES (?, 1, ?)",
                (status, created_at),
            )

    assert get_loss_streak() == 3
    assert get_stake_multiplier() == 0.5


def test_check_daily_stop_loss_false_when_no_bets():
    assert check_daily_stop_loss() is False


def test_agent_pause_state_roundtrip():
    assert is_agent_paused() is False
    assert get_pause_state()["paused"] is False

    set_agent_paused(True, reason="test")
    assert is_agent_paused() is True
    assert get_pause_state()["reason"] == "test"

    set_agent_paused(False)
    assert is_agent_paused() is False
