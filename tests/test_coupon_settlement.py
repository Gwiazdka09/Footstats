"""tests/test_coupon_settlement.py — auto-settlement crona wyklucza kupony manual (J4a).

Regresja HIGH (code review 21.07): `settle_active_coupons` SELECT-ował WSZYSTKIE
kupony ACTIVE bez filtra kupon_type. Ręczne kupony z dziennika (kupon_type='manual')
były zgarniane przez cron → auto-settle nadpisywał ręcznie wpisany wynik usera
(fuzzy-match nazw drużyn, abuse zewnętrznych API). Fix: filtr NULL-safe
`kupon_type IS NULL OR kupon_type <> 'manual'` (legacy kupony bez kupon_type
muszą zostać w auto-settle).

Izolacja: własna plikowa SQLite DB, `backtest._connect`/`init_db` podmienione,
`_find_leg_result` zamockowany (zero sieci/zewnętrznych API — zgodnie z
.claude/rules/tests-no-prod.md).
"""
import json
import sqlite3
from datetime import date, timedelta

import pytest

import footstats.core.backtest as backtest
import footstats.core.coupon_settlement as settlement


class _SQLiteConn:
    """sqlite3 adapter matching footstats.utils.db._Conn interface."""

    def __init__(self, path: str) -> None:
        self._raw = sqlite3.connect(path)
        self._raw.row_factory = sqlite3.Row

    def execute(self, sql, params=()):
        return self._raw.execute(sql, params)

    def executemany(self, sql, seq):
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
    kupon_type       TEXT,
    legs_json        TEXT NOT NULL DEFAULT '[]',
    total_odds       REAL,
    stake_pln        REAL,
    payout_pln       REAL,
    roi_pct          REAL,
    match_date_first TEXT,
    bookmaker        TEXT,
    user_id          INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS bankroll_state (
    user_id    INTEGER PRIMARY KEY,
    balance    REAL NOT NULL,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS bankroll_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT,
    change_pln  REAL,
    new_balance REAL,
    type        TEXT,
    description TEXT,
    user_id     INTEGER
);
INSERT INTO bankroll_state (user_id, balance) VALUES (1, 100.0);
"""

_YESTERDAY = (date.today() - timedelta(days=1)).isoformat()


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    """Każdy test dostaje własną plikową SQLite DB; sieć (_find_leg_result) zamockowana."""
    db_path = str(tmp_path / "test.db")

    setup = sqlite3.connect(db_path)
    setup.executescript(_SCHEMA)
    setup.commit()
    setup.close()

    monkeypatch.setattr(backtest, "_connect", lambda: _SQLiteConn(db_path))
    monkeypatch.setattr(backtest, "init_db", lambda: None)
    # "1-0" = wygrana gospodarzy — zero sieci/zewnętrznych API (tests-no-prod.md).
    monkeypatch.setattr(settlement, "_find_leg_result", lambda *a, **k: "1-0")
    yield db_path


def _insert_coupon(
    db_path: str,
    kupon_type,
    status: str = "ACTIVE",
    match_date: str = _YESTERDAY,
    tip: str = "1",
    stake: float = 10.0,
    odds: float = 2.0,
) -> int:
    legs = json.dumps([{"home": "Legia", "away": "Lech", "tip": tip}], ensure_ascii=False)
    conn = sqlite3.connect(db_path)
    cur = conn.execute(
        "INSERT INTO coupons (kupon_type, status, legs_json, total_odds, stake_pln,"
        " match_date_first, user_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (kupon_type, status, legs, odds, stake, match_date, 1),
    )
    conn.commit()
    coupon_id = cur.lastrowid
    conn.close()
    return coupon_id


def _status_of(db_path: str, coupon_id: int) -> str:
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT status FROM coupons WHERE id=?", (coupon_id,)).fetchone()
    conn.close()
    return row[0]


def test_manual_coupon_nietkniety_przez_auto_settle(tmp_db):
    cid = _insert_coupon(tmp_db, kupon_type="manual")
    stats = settlement.settle_active_coupons(dry_run=False, verbose=False)
    assert _status_of(tmp_db, cid) == "ACTIVE"
    assert stats["settled"] == 0


def test_legacy_kupon_bez_typu_dalej_procesowany(tmp_db):
    # kupon_type NULL (stare kupony sprzed dodania kolumny) NIE mogą wypaść z auto-settle.
    cid = _insert_coupon(tmp_db, kupon_type=None)
    stats = settlement.settle_active_coupons(dry_run=False, verbose=False)
    assert _status_of(tmp_db, cid) == "WON"
    assert stats["settled"] == 1


def test_accumulator_kupon_dalej_procesowany(tmp_db):
    cid = _insert_coupon(tmp_db, kupon_type="accumulator")
    stats = settlement.settle_active_coupons(dry_run=False, verbose=False)
    assert _status_of(tmp_db, cid) == "WON"
    assert stats["settled"] == 1


def test_mieszany_zestaw_manual_zostaje_reszta_rozliczona(tmp_db):
    manual_id = _insert_coupon(tmp_db, kupon_type="manual")
    normal_id = _insert_coupon(tmp_db, kupon_type=None)
    settlement.settle_active_coupons(dry_run=False, verbose=False)
    assert _status_of(tmp_db, manual_id) == "ACTIVE"
    assert _status_of(tmp_db, normal_id) == "WON"
