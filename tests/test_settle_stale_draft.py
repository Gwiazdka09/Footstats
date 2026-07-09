"""Test cleanup stale-DRAFT w settle_active_coupons.

DRAFT z przeszla data meczu nigdy nie awansowal do ACTIVE -> nigdy by sie nie
rozliczyl. Po VOID_AFTER_DAYS musi byc oznaczony VOID (nie zywy zaklad).
"""
import json
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
);
CREATE TABLE bankroll_state (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    balance    REAL,
    updated_at TEXT,
    user_id    INTEGER DEFAULT 1 UNIQUE
);
CREATE TABLE bankroll_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT,
    change_pln  REAL,
    new_balance REAL,
    type        TEXT,
    description TEXT,
    user_id     INTEGER DEFAULT 1
);
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


def test_stale_active_z_dostepnym_wynikiem_rozlicza_sie(wired, monkeypatch):
    # Regresja #2 (code-review): stary ACTIVE (>10d) którego wynik DOPIERO stał się
    # dostępny musi się ROZLICZYĆ (WON/LOST), nie zostać VOID-owany przedwcześnie.
    import footstats.core.coupon_settlement as cs
    old = (datetime.now().date() - timedelta(days=30)).isoformat()
    conn = sqlite3.connect(wired)
    conn.execute(
        "INSERT INTO coupons (status, match_date_first, legs_json, total_odds, stake_pln, user_id) "
        "VALUES ('ACTIVE', ?, ?, 2.0, 10.0, 1)",
        (old, json.dumps([{"home": "PSG", "away": "Lyon", "tip": "1"}])),
    )
    conn.execute("INSERT INTO bankroll_state (balance, user_id) VALUES (100.0, 1)")
    conn.commit(); conn.close()

    # Wynik dostępny dopiero teraz (wolne źródło) → gospodarz wygrał.
    monkeypatch.setattr(cs, "_find_leg_result", lambda *a, **k: "2-1")

    from footstats.core.coupon_settlement import settle_active_coupons
    settle_active_coupons(days_back=3, dry_run=False, verbose=False)

    conn = sqlite3.connect(wired)
    conn.row_factory = sqlite3.Row
    status = conn.execute("SELECT status FROM coupons WHERE id=4").fetchone()["status"]
    bal = conn.execute("SELECT balance FROM bankroll_state WHERE user_id=1").fetchone()["balance"]
    conn.close()
    assert status == "WON"          # rozliczony, NIE VOID
    assert bal == pytest.approx(120.0)  # 100 + 10*2.0 brutto do właściciela


def test_dry_run_nie_zmienia_statusow(wired):
    from footstats.core.coupon_settlement import settle_active_coupons

    settle_active_coupons(days_back=3, dry_run=True, verbose=False)

    st = _statuses(wired)
    assert st[1] == "DRAFT"   # dry_run nie mutuje
    assert st[2] == "DRAFT"
    assert st[3] == "DRAFT"


def _wstaw_active_won_kandydata(path):
    """Kupon ACTIVE (odds 2.0, stake 10, user 1) + bankroll 100."""
    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT INTO coupons (status, match_date_first, legs_json, total_odds, stake_pln, user_id) "
        "VALUES ('ACTIVE', ?, ?, 2.0, 10.0, 1)",
        ((datetime.now().date() - timedelta(days=2)).isoformat(),
         json.dumps([{"home": "PSG", "away": "Lyon", "tip": "1"}])),
    )
    conn.execute("INSERT INTO bankroll_state (balance, user_id) VALUES (100.0, 1)")
    conn.commit(); conn.close()


def test_rownolegle_settle_kredytuje_raz(wired, monkeypatch):
    # D3 (audyt 09-07): dwa procesy settle widzą ten sam kupon jako ACTIVE
    # (Scheduler 06:00/21:30 + evening). Drugi zapis NIE może skredytować
    # bankrollu drugi raz — UPDATE musi być CAS (WHERE ... AND status='ACTIVE').
    import footstats.core.coupon_settlement as cs
    _wstaw_active_won_kandydata(wired)

    def _wynik_i_konkurencyjny_settle(*a, **k):
        # Symulacja wyścigu: "drugi proces" rozlicza kupon i kredytuje bankroll
        # między naszym SELECT (ACTIVE) a naszym UPDATE.
        conn = sqlite3.connect(wired)
        conn.execute("UPDATE coupons SET status='WON', payout_pln=20.0 WHERE id=4")
        conn.execute("UPDATE bankroll_state SET balance=120.0 WHERE user_id=1")
        conn.commit(); conn.close()
        return "2-1"

    monkeypatch.setattr(cs, "_find_leg_result", _wynik_i_konkurencyjny_settle)
    cs.settle_active_coupons(days_back=3, dry_run=False, verbose=False)

    conn = sqlite3.connect(wired)
    conn.row_factory = sqlite3.Row
    bal = conn.execute("SELECT balance FROM bankroll_state WHERE user_id=1").fetchone()["balance"]
    status = conn.execute("SELECT status FROM coupons WHERE id=4").fetchone()["status"]
    conn.close()
    assert status == "WON"
    assert bal == pytest.approx(120.0)   # kredyt RAZ, nie 140 (podwójny)


def test_won_bez_bankroll_state_loguje_warning(wired, monkeypatch, caplog):
    # D7 (audyt 09-07): WON właściciela bez wiersza bankroll_state nie może
    # przejść w ciszy — wymagany log.warning (kredyt pominięty świadomie).
    import logging
    import footstats.core.coupon_settlement as cs
    conn = sqlite3.connect(wired)
    conn.execute(
        "INSERT INTO coupons (status, match_date_first, legs_json, total_odds, stake_pln, user_id) "
        "VALUES ('ACTIVE', ?, ?, 2.0, 10.0, 77)",   # user 77 bez bankroll_state
        ((datetime.now().date() - timedelta(days=2)).isoformat(),
         json.dumps([{"home": "PSG", "away": "Lyon", "tip": "1"}])),
    )
    conn.commit(); conn.close()
    monkeypatch.setattr(cs, "_find_leg_result", lambda *a, **k: "2-1")

    with caplog.at_level(logging.WARNING, logger="footstats.core.coupon_settlement"):
        cs.settle_active_coupons(days_back=3, dry_run=False, verbose=False)

    conn = sqlite3.connect(wired)
    conn.row_factory = sqlite3.Row
    status = conn.execute("SELECT status FROM coupons WHERE id=4").fetchone()["status"]
    conn.close()
    assert status == "WON"
    assert any("bankroll_state" in r.message for r in caplog.records)
