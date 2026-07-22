"""tests/test_settle_manual_coupons.py — auto-settle kuponów manual (Etap C, J4c).

Zasada "co mamy — my": noga rozliczalna TYLKO gdy `link_leg` matched="exact"
ORAZ zlinkowana predykcja ma niepusty `actual_result`. Jakakolwiek niepewna
noga → CAŁY kupon zostaje ACTIVE (konserwatywnie, bez partial). ZERO
zewnętrznych API (`_find_leg_result` nie może być wołane — różnica vs
`settle_active_coupons`). Bankroll-neutralne: dziennik nie rusza
bankroll_state/bankroll_history.

Izolacja: własna plikowa SQLite DB; `backtest._connect`/`init_db` oraz
`coupon_tracker._connect`/`init_coupon_tables` podmienione na tę samą bazę;
`match_linker.link_leg` zamockowany (zero DB predictions/sieci).
"""
import sqlite3

import pytest
from fastapi import HTTPException

import footstats.core.backtest as backtest
import footstats.core.coupon_settlement as settlement
import footstats.core.coupon_tracker as coupon_tracker
import footstats.core.match_linker as match_linker
from footstats.core.match_linker import LinkResult


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


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    """Każdy test dostaje własną plikową SQLite DB; zero sieci/zewn. API."""
    db_path = str(tmp_path / "test.db")

    setup = sqlite3.connect(db_path)
    setup.executescript(_SCHEMA)
    setup.commit()
    setup.close()

    monkeypatch.setattr(backtest, "_connect", lambda: _SQLiteConn(db_path))
    monkeypatch.setattr(backtest, "init_db", lambda: None)
    monkeypatch.setattr(coupon_tracker, "_connect", lambda: _SQLiteConn(db_path))
    monkeypatch.setattr(coupon_tracker, "init_coupon_tables", lambda: None)

    def _boom_find_leg_result(*_a, **_k):
        raise AssertionError(
            "settle_manual_coupons NIE MOŻE wołać _find_leg_result (zero zewn. API)"
        )

    monkeypatch.setattr(settlement, "_find_leg_result", _boom_find_leg_result)
    yield db_path


def _insert_coupon(
    db_path: str,
    legs: list,
    kupon_type: str = "manual",
    status: str = "ACTIVE",
    match_date: str = "2026-07-20",
    total_odds: float = 2.0,
    stake: float = 10.0,
) -> int:
    import json

    conn = sqlite3.connect(db_path)
    cur = conn.execute(
        "INSERT INTO coupons (kupon_type, status, legs_json, total_odds, stake_pln,"
        " match_date_first, user_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (kupon_type, status, json.dumps(legs, ensure_ascii=False), total_odds, stake, match_date, 1),
    )
    conn.commit()
    coupon_id = cur.lastrowid
    conn.close()
    return coupon_id


def _row(db_path: str, coupon_id: int) -> sqlite3.Row:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM coupons WHERE id=?", (coupon_id,)).fetchone()
    conn.close()
    return row


def _bankroll(db_path: str, user_id: int = 1) -> float:
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT balance FROM bankroll_state WHERE user_id=?", (user_id,)
    ).fetchone()
    conn.close()
    return row[0]


def _prediction(actual_result) -> dict:
    return {
        "id": 1,
        "team_home": "Legia",
        "team_away": "Lech",
        "match_date": "2026-07-20",
        "ai_tip": "1",
        "ai_confidence": 70,
        "prob_home": 0.5,
        "prob_draw": 0.3,
        "prob_away": 0.2,
        "actual_result": actual_result,
    }


def _mock_link_leg_single(monkeypatch, result: LinkResult) -> None:
    """Każde wywołanie link_leg (bez względu na home/away) zwraca ten sam wynik."""
    monkeypatch.setattr(match_linker, "link_leg", lambda *a, **k: result)


def test_pewna_noga_z_wynikiem_settluje_won(tmp_db, monkeypatch):
    _mock_link_leg_single(
        monkeypatch, LinkResult(True, "exact", _prediction("2-0"), "Dopasowano")
    )
    cid = _insert_coupon(
        tmp_db, [{"home": "Legia", "away": "Lech", "tip": "1"}], total_odds=2.0, stake=10.0
    )

    stats = settlement.settle_manual_coupons(dry_run=False, verbose=False)

    row = _row(tmp_db, cid)
    assert row["status"] == "WON"
    assert row["payout_pln"] == pytest.approx(20.0)
    assert stats["settled"] == 1
    assert stats["skipped"] == 0
    assert _bankroll(tmp_db) == pytest.approx(100.0)  # bankroll nietknięty


def test_pewna_noga_tip_chybiony_lost(tmp_db, monkeypatch):
    _mock_link_leg_single(
        monkeypatch, LinkResult(True, "exact", _prediction("0-2"), "Dopasowano")
    )
    cid = _insert_coupon(tmp_db, [{"home": "Legia", "away": "Lech", "tip": "1"}])

    stats = settlement.settle_manual_coupons(dry_run=False, verbose=False)

    row = _row(tmp_db, cid)
    assert row["status"] == "LOST"
    assert row["payout_pln"] == pytest.approx(0.0)
    assert stats["settled"] == 1


def test_niepewna_noga_zostaje_active(tmp_db, monkeypatch):
    _mock_link_leg_single(monkeypatch, LinkResult(False, "none", None, "Brak dopasowania"))
    cid = _insert_coupon(tmp_db, [{"home": "Legia", "away": "Lech", "tip": "1"}])

    stats = settlement.settle_manual_coupons(dry_run=False, verbose=False)

    row = _row(tmp_db, cid)
    assert row["status"] == "ACTIVE"
    assert stats["settled"] == 0
    assert stats["skipped"] >= 1


def test_brak_wyniku_zostaje_active(tmp_db, monkeypatch):
    _mock_link_leg_single(
        monkeypatch, LinkResult(True, "exact", _prediction(None), "Dopasowano")
    )
    cid = _insert_coupon(tmp_db, [{"home": "Legia", "away": "Lech", "tip": "1"}])

    stats = settlement.settle_manual_coupons(dry_run=False, verbose=False)

    row = _row(tmp_db, cid)
    assert row["status"] == "ACTIVE"
    assert stats["settled"] == 0


def test_mieszany_kupon_jedna_noga_niepewna_caly_zostaje(tmp_db, monkeypatch):
    def _fake_link_leg(home, away, date, day_tolerance=1):
        if home == "Legia":
            return LinkResult(True, "exact", _prediction("2-0"), "Dopasowano")
        return LinkResult(False, "none", None, "Brak dopasowania")

    monkeypatch.setattr(match_linker, "link_leg", _fake_link_leg)
    cid = _insert_coupon(
        tmp_db,
        [
            {"home": "Legia", "away": "Lech", "tip": "1"},
            {"home": "Wisła", "away": "Cracovia", "tip": "1"},
        ],
    )

    stats = settlement.settle_manual_coupons(dry_run=False, verbose=False)

    row = _row(tmp_db, cid)
    assert row["status"] == "ACTIVE"  # cały kupon, nie partial
    assert stats["settled"] == 0
    assert stats["skipped"] == 1


def test_tip_nieparsowalny_zostaje_active(tmp_db, monkeypatch):
    _mock_link_leg_single(
        monkeypatch, LinkResult(True, "exact", _prediction("2-0"), "Dopasowano")
    )
    cid = _insert_coupon(tmp_db, [{"home": "Legia", "away": "Lech", "tip": "NIEZNANY_RYNEK"}])

    stats = settlement.settle_manual_coupons(dry_run=False, verbose=False)

    row = _row(tmp_db, cid)
    assert row["status"] == "ACTIVE"
    assert stats["settled"] == 0


def test_dry_run_nie_pisze(tmp_db, monkeypatch):
    _mock_link_leg_single(
        monkeypatch, LinkResult(True, "exact", _prediction("2-0"), "Dopasowano")
    )
    cid = _insert_coupon(tmp_db, [{"home": "Legia", "away": "Lech", "tip": "1"}])

    stats = settlement.settle_manual_coupons(dry_run=True, verbose=False)

    row = _row(tmp_db, cid)
    assert row["status"] == "ACTIVE"  # brak zapisu
    assert stats["settled"] == 1  # ale policzone


def test_nie_rusza_bankrollu(tmp_db, monkeypatch):
    _mock_link_leg_single(
        monkeypatch, LinkResult(True, "exact", _prediction("2-0"), "Dopasowano")
    )
    _insert_coupon(tmp_db, [{"home": "Legia", "away": "Lech", "tip": "1"}])

    settlement.settle_manual_coupons(dry_run=False, verbose=False)

    assert _bankroll(tmp_db) == pytest.approx(100.0)


def test_nie_dotyka_kuponow_ai(tmp_db, monkeypatch):
    _mock_link_leg_single(
        monkeypatch, LinkResult(True, "exact", _prediction("2-0"), "Dopasowano")
    )
    cid = _insert_coupon(
        tmp_db, [{"home": "Legia", "away": "Lech", "tip": "1"}], kupon_type="accumulator"
    )

    stats = settlement.settle_manual_coupons(dry_run=False, verbose=False)

    row = _row(tmp_db, cid)
    assert row["status"] == "ACTIVE"
    assert stats["settled"] == 0
    assert stats["skipped"] == 0


def test_cas_guard_nie_nadpisuje_recznie_rozliczonego(tmp_db, monkeypatch):
    # Kupon już ręcznie rozliczony (WON) — SELECT bierze tylko ACTIVE, więc
    # settle_manual_coupons w ogóle go nie dotyka (CAS chroniony przez filtr
    # + expected_status="ACTIVE" w update_coupon_status).
    _mock_link_leg_single(
        monkeypatch, LinkResult(True, "exact", _prediction("2-0"), "Dopasowano")
    )
    cid = _insert_coupon(
        tmp_db, [{"home": "Legia", "away": "Lech", "tip": "1"}], status="WON"
    )

    stats = settlement.settle_manual_coupons(dry_run=False, verbose=False)

    row = _row(tmp_db, cid)
    assert row["status"] == "WON"
    assert stats["settled"] == 0


def test_zero_zewn_api(tmp_db, monkeypatch):
    # _find_leg_result zamockowany na wyjątek w fixture tmp_db — jeśli
    # settle_manual_coupons go wywoła, test padnie z AssertionError.
    _mock_link_leg_single(
        monkeypatch, LinkResult(True, "exact", _prediction("2-0"), "Dopasowano")
    )
    _insert_coupon(tmp_db, [{"home": "Legia", "away": "Lech", "tip": "1"}])

    stats = settlement.settle_manual_coupons(dry_run=False, verbose=False)

    assert stats["settled"] == 1


def test_cron_settle_manual_wymaga_sekretu(monkeypatch):
    from footstats.api.routes.coupons import cron_settle_manual

    monkeypatch.setenv("CRON_SECRET", "tajny-sekret")
    with pytest.raises(HTTPException) as exc:
        cron_settle_manual(x_cron_secret="zly-sekret")
    assert exc.value.status_code == 401
