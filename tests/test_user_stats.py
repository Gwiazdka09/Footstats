"""tests/test_user_stats.py — SQLite-backed fixture (PostgreSQL DDL mocked), jak test_coupon_tracker.py."""
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
CREATE TABLE IF NOT EXISTS coupons (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    phase            TEXT NOT NULL DEFAULT '',
    status           TEXT NOT NULL DEFAULT 'DRAFT',
    kupon_type       TEXT NOT NULL DEFAULT '',
    legs_json        TEXT NOT NULL DEFAULT '[]',
    total_odds       REAL,
    stake_pln        REAL,
    payout_pln       REAL,
    roi_pct          REAL,
    groq_reasoning   TEXT,
    decision_score   INTEGER,
    match_date_first TEXT,
    user_id          INTEGER DEFAULT 1,
    shared           BOOLEAN NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_coupon_status  ON coupons(status);
CREATE INDEX IF NOT EXISTS idx_coupon_created ON coupons(created_at);
CREATE TABLE IF NOT EXISTS predictions (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    coupon_id INTEGER REFERENCES coupons(id)
)
"""


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    """Każdy test dostaje własną izolowaną bazę SQLite (bez dotykania prod Neon/Supabase)."""
    db_path = str(tmp_path / "test.db")

    setup = sqlite3.connect(db_path)
    setup.executescript(_SCHEMA)
    setup.commit()
    setup.close()

    import footstats.core.coupon_tracker as ct

    monkeypatch.setattr(ct, "_connect", lambda: _SQLiteConn(db_path))
    monkeypatch.setattr(ct, "init_coupon_tables", lambda: None)
    yield db_path


from footstats.core.coupon_tracker import save_coupon, update_coupon_status
from footstats.core.user_stats import get_progress_series, get_user_stats


def _make_settled(status: str, stake: float, odds: float, user_id: int = 1) -> int:
    """Pomocnik testowy: tworzy kupon final -> ACTIVE -> status (WON/LOST) i zwraca id."""
    cid = save_coupon("final", "A", [], total_odds=odds, stake_pln=stake, user_id=user_id)
    update_coupon_status(cid, "ACTIVE")
    payout = round(stake * odds, 2) if status == "WON" else 0.0
    update_coupon_status(cid, status, payout_pln=payout)
    return cid


def test_empty_user_returns_zeros_no_crash():
    stats = get_user_stats(user_id=999)

    assert stats.total_coupons == 0
    assert stats.settled_count == 0
    assert stats.wins == 0
    assert stats.losses == 0
    assert stats.win_rate == 0.0
    assert stats.profit_units == 0.0
    assert stats.roi == 0.0
    assert stats.current_streak == 0
    assert stats.best_coupon is None
    assert stats.worst_coupon is None


def test_two_won_one_lost_win_rate_profit_roi():
    _make_settled("WON", stake=10.0, odds=2.0)
    _make_settled("WON", stake=10.0, odds=2.0)
    _make_settled("LOST", stake=10.0, odds=2.0)

    stats = get_user_stats(user_id=1)

    assert stats.total_coupons == 3
    assert stats.settled_count == 3
    assert stats.wins == 2
    assert stats.losses == 1
    assert stats.win_rate == pytest.approx(2 / 3)
    assert stats.profit_units == pytest.approx(10.0)  # +10 +10 -10
    assert stats.roi == pytest.approx(10.0 / 30.0)


def test_streak_counted_from_newest_not_total_wins():
    # Kolejność: W, W, L (L najnowszy) -> streak ujemny mimo przewagi wygranych.
    _make_settled("WON", stake=10.0, odds=2.0)
    _make_settled("WON", stake=10.0, odds=2.0)
    _make_settled("LOST", stake=10.0, odds=2.0)

    stats = get_user_stats(user_id=1)

    assert stats.current_streak == -1


def test_streak_positive_when_last_two_won():
    # Kolejność: L, W, W (W najnowszy) -> streak dodatni +2.
    _make_settled("LOST", stake=10.0, odds=2.0)
    _make_settled("WON", stake=10.0, odds=2.0)
    _make_settled("WON", stake=10.0, odds=2.0)

    stats = get_user_stats(user_id=1)

    assert stats.current_streak == 2


def test_best_and_worst_coupon():
    _make_settled("WON", stake=5.0, odds=1.5)          # +2.5
    id_big_win = _make_settled("WON", stake=10.0, odds=3.0)   # +20
    id_loss = _make_settled("LOST", stake=8.0, odds=2.0)      # -8

    stats = get_user_stats(user_id=1)

    assert stats.best_coupon is not None
    assert stats.best_coupon.coupon_id == id_big_win
    assert stats.best_coupon.profit_units == pytest.approx(20.0)
    assert stats.worst_coupon is not None
    assert stats.worst_coupon.coupon_id == id_loss
    assert stats.worst_coupon.profit_units == pytest.approx(-8.0)


def test_pending_coupons_do_not_count_towards_settled():
    save_coupon("draft", "A", [], stake_pln=10.0, user_id=1)  # DRAFT
    cid_active = save_coupon("final", "A", [], stake_pln=10.0, total_odds=2.0, user_id=1)
    update_coupon_status(cid_active, "ACTIVE")  # pending, nie wchodzi do win-rate

    stats = get_user_stats(user_id=1)

    assert stats.total_coupons == 2
    assert stats.settled_count == 0
    assert stats.win_rate == 0.0


def test_void_and_partial_do_not_count_towards_settled():
    # Regresja review LOW-2: VOID (terminarz/brak wyniku po VOID_AFTER_DAYS) i
    # PARTIAL (kupon czeka na częściowe wyniki, zob. coupon_settlement.py) nie są
    # "żywym" rozliczonym zakładem — nie mogą wpaść do settled/win_rate/roi/streak.
    _make_settled("WON", stake=10.0, odds=2.0)  # jedyny realnie rozliczony

    cid_void = save_coupon("final", "A", [], stake_pln=10.0, total_odds=2.0, user_id=1)
    update_coupon_status(cid_void, "ACTIVE")
    update_coupon_status(cid_void, "VOID")

    cid_partial = save_coupon("final", "A", [], stake_pln=10.0, total_odds=2.0, user_id=1)
    update_coupon_status(cid_partial, "ACTIVE")
    update_coupon_status(cid_partial, "PARTIAL")

    stats = get_user_stats(user_id=1)

    assert stats.total_coupons == 3
    assert stats.settled_count == 1
    assert stats.wins == 1
    assert stats.losses == 0
    assert stats.win_rate == pytest.approx(1.0)
    assert stats.profit_units == pytest.approx(10.0)  # tylko WON, VOID/PARTIAL pominięte
    assert stats.roi == pytest.approx(1.0)             # 10 / 10 (staked tylko z WON)
    assert stats.current_streak == 1


# ── get_progress_series (J3) ─────────────────────────────────────────────────


def test_progress_series_empty_user_returns_empty_list():
    assert get_progress_series(user_id=999) == []


def test_progress_series_three_coupons_cumulative_and_win_rate():
    _make_settled("WON", stake=10.0, odds=2.0)   # +10
    _make_settled("WON", stake=10.0, odds=2.0)   # +10
    _make_settled("LOST", stake=10.0, odds=2.0)  # -10

    series = get_progress_series(user_id=1)

    assert len(series) == 3
    assert all(isinstance(p.date, str) and p.date for p in series)

    assert series[0].settled_count == 1
    assert series[0].cumulative_profit == pytest.approx(10.0)
    assert series[0].running_win_rate == pytest.approx(1.0)

    assert series[1].settled_count == 2
    assert series[1].cumulative_profit == pytest.approx(20.0)
    assert series[1].running_win_rate == pytest.approx(1.0)

    assert series[2].settled_count == 3
    assert series[2].cumulative_profit == pytest.approx(10.0)  # +10 +10 -10
    assert series[2].running_win_rate == pytest.approx(2 / 3)


def test_progress_series_pending_coupons_ignored_and_sorted_chronologically():
    save_coupon("draft", "A", [], stake_pln=10.0, user_id=1)  # DRAFT, pomijany
    _make_settled("LOST", stake=10.0, odds=2.0)               # -10
    _make_settled("WON", stake=10.0, odds=3.0)                # +20

    series = get_progress_series(user_id=1)

    assert len(series) == 2
    assert series[0].settled_count == 1
    assert series[0].cumulative_profit == pytest.approx(-10.0)
    assert series[0].running_win_rate == pytest.approx(0.0)
    assert series[1].settled_count == 2
    assert series[1].cumulative_profit == pytest.approx(10.0)  # -10 + 20
    assert series[1].running_win_rate == pytest.approx(0.5)
