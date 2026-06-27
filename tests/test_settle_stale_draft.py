"""Test cleanup stale-DRAFT w settle_active_coupons.

DRAFT z przeszla data meczu nigdy nie awansowal do ACTIVE -> nigdy by sie nie
rozliczyl. Po VOID_AFTER_DAYS musi byc oznaczony VOID (nie zywy zaklad).
"""
import sqlite3
from datetime import datetime, timedelta

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
CREATE TABLE coupons (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    status           TEXT NOT NULL DEFAULT 'DRAFT',
    legs_json        TEXT NOT NULL DEFAULT '[]',
    total_odds       REAL,
    stake_pln        REAL,
    payout_pln       REAL,
    roi_pct          REAL,
    match_date_first TEXT,
    user_id          INTEGER DEFAULT 1
)
"""


@pytest.fixture
def wired(tmp_path, monkeypatch):
    path = str(tmp_path / "settle.db")
    setup = sqlite3.connect(path)
    setup.executescript(_SCHEMA)
    today = datetime.now().date()
    old = (today - timedelta(days=30)).isoformat()      # poza oknem VOID
    recent = (today - timedelta(days=2)).isoformat()    # w oknie VOID
    future = (today + timedelta(days=3)).isoformat()    # przyszly draft (uzytkownik buduje)
    setup.executemany(
        "INSERT INTO coupons (status, match_date_first) VALUES (?, ?)",
        [
            ("DRAFT", old),       # id 1 -> VOID
            ("DRAFT", recent),    # id 2 -> zostaje DRAFT (w oknie)
            ("DRAFT", future),    # id 3 -> zostaje DRAFT (przyszly mecz)
        ],
    )
    setup.commit()
    setup.close()

    import footstats.core.coupon_settlement as cs

    monkeypatch.setattr(cs, "_connect", lambda: _SQLiteConn(path), raising=False)
    # settle importuje _connect/init_db z backtest wewnatrz funkcji
    import footstats.core.backtest as bt
    monkeypatch.setattr(bt, "_connect", lambda: _SQLiteConn(path))
    monkeypatch.setattr(bt, "init_db", lambda: None)
    return path


def _statuses(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT id, status FROM coupons ORDER BY id").fetchall()
    conn.close()
    return {r["id"]: r["status"] for r in rows}


def test_stale_draft_voided_recent_and_future_kept(wired):
    from footstats.core.coupon_settlement import settle_active_coupons

    stats = settle_active_coupons(days_back=3, dry_run=False, verbose=False)

    st = _statuses(wired)
    assert st[1] == "VOID"    # przeszly poza oknem -> VOID
    assert st[2] == "DRAFT"   # w oknie 10d -> jeszcze nie ruszamy
    assert st[3] == "DRAFT"   # przyszly mecz -> nietkniety
    assert stats["voided"] == 1


def test_stale_active_voided_po_oknie(wired):
    # Regresja #175: ACTIVE z nierozliczalną nogą (mecz spoza coverage) wisiał wiecznie —
    # wcześniej VOID był tylko dla DRAFT. Stary ACTIVE (>10d) musi pójść do VOID.
    from footstats.core.coupon_settlement import settle_active_coupons
    old = (datetime.now().date() - timedelta(days=30)).isoformat()
    conn = sqlite3.connect(wired)
    conn.execute(
        "INSERT INTO coupons (status, match_date_first, legs_json) VALUES ('ACTIVE', ?, '[]')",
        (old,),
    )
    conn.commit(); conn.close()

    stats = settle_active_coupons(days_back=3, dry_run=False, verbose=False)

    st = _statuses(wired)
    assert st[4] == "VOID"          # stary ACTIVE poza oknem 10d → VOID (stale-cleanup)
    assert stats["voided"] >= 2     # stale DRAFT (#1) + stale ACTIVE (#4)


def test_dry_run_nie_zmienia_statusow(wired):
    from footstats.core.coupon_settlement import settle_active_coupons

    settle_active_coupons(days_back=3, dry_run=True, verbose=False)

    st = _statuses(wired)
    assert st[1] == "DRAFT"   # dry_run nie mutuje
    assert st[2] == "DRAFT"
    assert st[3] == "DRAFT"
