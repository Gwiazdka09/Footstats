"""tests/test_coupon_manual.py — dziennik kuponów (J4a): ręczny wpis + ręczne rozliczenie.

Izolacja jak tests/test_coupon_tracker.py: własna plikowa SQLite DB, `_connect`
w coupon_tracker ORAZ w routes.coupons podmienione na adapter zgodny z
footstats.utils.db._Conn. Zero prod Neon/Supabase, zero Telegram — endpointy
wywoływane bezpośrednio (bez FastAPI TestClient), user_id przekazywany wprost.
"""
import sqlite3

import pytest
from fastapi import HTTPException

from footstats.api.routes.coupons import (
    CouponResultRequest,
    ManualCouponRequest,
    ManualLeg,
    manual_coupon,
    set_coupon_result,
)


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
    kupon_type       TEXT NOT NULL DEFAULT '',
    legs_json        TEXT NOT NULL DEFAULT '[]',
    total_odds       REAL,
    stake_pln        REAL,
    payout_pln       REAL,
    roi_pct          REAL,
    groq_reasoning   TEXT,
    decision_score   INTEGER,
    match_date_first TEXT,
    bookmaker        TEXT,
    user_id          INTEGER DEFAULT 1,
    shared           BOOLEAN NOT NULL DEFAULT 0
)
"""


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    """Każdy test dostaje własną plikową SQLite DB; _connect w obu modułach mockowane."""
    db_path = str(tmp_path / "test.db")

    setup = sqlite3.connect(db_path)
    setup.executescript(_SCHEMA)
    setup.commit()
    setup.close()

    import footstats.api.routes.coupons as routes
    import footstats.core.coupon_tracker as ct

    monkeypatch.setattr(ct, "_connect", lambda: _SQLiteConn(db_path))
    monkeypatch.setattr(ct, "init_coupon_tables", lambda: None)
    monkeypatch.setattr(routes, "_connect", lambda: _SQLiteConn(db_path))
    monkeypatch.setattr(routes, "clear_response_cache", lambda: None, raising=False)
    yield db_path


def _leg(home: str = "Legia", away: str = "Lech", tip: str = "1", odds: float = 1.85) -> ManualLeg:
    return ManualLeg(home=home, away=away, tip=tip, odds=odds)


def _row(db_path: str, coupon_id: int) -> sqlite3.Row:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM coupons WHERE id=?", (coupon_id,)).fetchone()
    conn.close()
    return row


def _saved_coupon(user_id: int = 1, stake: float = 10.0, odds: float = 2.5) -> int:
    req = ManualCouponRequest(legs=[_leg(odds=odds)], stake_pln=stake)
    res = manual_coupon(req, user_id=user_id)
    return res["coupon_id"]


# ── POST /coupon/manual — zapis ──────────────────────────────────────────────

def test_manual_coupon_zapisuje_bookmaker_i_status_active(tmp_db):
    req = ManualCouponRequest(legs=[_leg()], stake_pln=20.0, bookmaker="STS")
    res = manual_coupon(req, user_id=1)

    assert res["ok"] is True
    assert res["status"] == "ACTIVE"
    row = _row(tmp_db, res["coupon_id"])
    assert row["bookmaker"] == "STS"
    assert row["status"] == "ACTIVE"


def test_manual_coupon_total_odds_to_iloczyn(tmp_db):
    req = ManualCouponRequest(
        legs=[_leg(odds=1.5), _leg(home="Ajax", away="PSV", odds=2.0)],
        stake_pln=10.0,
    )
    res = manual_coupon(req, user_id=1)
    assert res["total_odds"] == pytest.approx(3.0)


def test_manual_coupon_bez_bookmakera_jest_opcjonalny(tmp_db):
    req = ManualCouponRequest(legs=[_leg()], stake_pln=10.0)
    res = manual_coupon(req, user_id=1)
    row = _row(tmp_db, res["coupon_id"])
    assert row["bookmaker"] is None


# ── POST /coupon/manual — walidacja ─────────────────────────────────────────

def test_manual_coupon_puste_legs_400(tmp_db):
    req = ManualCouponRequest(legs=[], stake_pln=10.0)
    with pytest.raises(HTTPException) as exc:
        manual_coupon(req, user_id=1)
    assert exc.value.status_code == 400


def test_manual_coupon_odds_1_lub_mniej_400(tmp_db):
    req = ManualCouponRequest(legs=[_leg(odds=1.0)], stake_pln=10.0)
    with pytest.raises(HTTPException) as exc:
        manual_coupon(req, user_id=1)
    assert exc.value.status_code == 400


def test_manual_coupon_stake_zero_lub_ujemna_400(tmp_db):
    req = ManualCouponRequest(legs=[_leg()], stake_pln=0.0)
    with pytest.raises(HTTPException) as exc:
        manual_coupon(req, user_id=1)
    assert exc.value.status_code == 400


def test_manual_coupon_za_dlugi_string_400(tmp_db):
    req = ManualCouponRequest(legs=[_leg(home="X" * 121)], stake_pln=10.0)
    with pytest.raises(HTTPException) as exc:
        manual_coupon(req, user_id=1)
    assert exc.value.status_code == 400


def test_manual_coupon_za_dlugi_bookmaker_400(tmp_db):
    req = ManualCouponRequest(legs=[_leg()], stake_pln=10.0, bookmaker="X" * 61)
    with pytest.raises(HTTPException) as exc:
        manual_coupon(req, user_id=1)
    assert exc.value.status_code == 400


# ── PATCH /coupon/{id}/result ────────────────────────────────────────────────

def test_result_won_payout_stake_x_odds(tmp_db):
    cid = _saved_coupon(stake=10.0, odds=2.5)
    res = set_coupon_result(cid, CouponResultRequest(result="WON"), user_id=1)
    assert res["status"] == "WON"
    assert res["payout_pln"] == pytest.approx(25.0)


def test_result_lost_payout_zero(tmp_db):
    cid = _saved_coupon(stake=10.0, odds=2.5)
    res = set_coupon_result(cid, CouponResultRequest(result="LOST"), user_id=1)
    assert res["status"] == "LOST"
    assert res["payout_pln"] == 0.0


def test_result_void_payout_stake_neutralny(tmp_db):
    cid = _saved_coupon(stake=10.0, odds=2.5)
    res = set_coupon_result(cid, CouponResultRequest(result="VOID"), user_id=1)
    assert res["status"] == "VOID"
    assert res["payout_pln"] == pytest.approx(10.0)


def test_result_owner_check_inny_user_403(tmp_db):
    cid = _saved_coupon(user_id=1)
    with pytest.raises(HTTPException) as exc:
        set_coupon_result(cid, CouponResultRequest(result="WON"), user_id=2)
    assert exc.value.status_code == 403


def test_result_nieistniejacy_kupon_404(tmp_db):
    with pytest.raises(HTTPException) as exc:
        set_coupon_result(9999, CouponResultRequest(result="WON"), user_id=1)
    assert exc.value.status_code == 404


def test_result_re_settle_guard_409(tmp_db):
    cid = _saved_coupon(stake=10.0, odds=2.5)
    set_coupon_result(cid, CouponResultRequest(result="WON"), user_id=1)
    with pytest.raises(HTTPException) as exc:
        set_coupon_result(cid, CouponResultRequest(result="LOST"), user_id=1)
    assert exc.value.status_code == 409
    # nietknięty przez drugie wywołanie
    row = _row(tmp_db, cid)
    assert row["status"] == "WON"


def test_result_nieprawidlowa_wartosc_400(tmp_db):
    cid = _saved_coupon()
    with pytest.raises(HTTPException) as exc:
        set_coupon_result(cid, CouponResultRequest(result="GARBAGE"), user_id=1)
    assert exc.value.status_code == 400


# ── integracja J1: get_user_stats liczy rozliczony ręczny kupon ─────────────

def test_won_manual_coupon_liczony_w_user_stats(tmp_db):
    from footstats.core.user_stats import get_user_stats

    cid = _saved_coupon(user_id=1, stake=10.0, odds=2.5)
    set_coupon_result(cid, CouponResultRequest(result="WON"), user_id=1)

    stats = get_user_stats(1)
    assert stats.settled_count == 1
    assert stats.wins == 1
    assert stats.losses == 0
