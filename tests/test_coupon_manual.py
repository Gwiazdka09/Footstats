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
    shared           BOOLEAN NOT NULL DEFAULT 0,
    settled_at       TIMESTAMP
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


_DATA = "2026-11-08"


def _leg(home: str = "Legia", away: str = "Lech", tip: str = "1", odds: float = 1.85) -> ManualLeg:
    return ManualLeg(home=home, away=away, tip=tip, odds=odds)


def _row(db_path: str, coupon_id: int) -> sqlite3.Row:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM coupons WHERE id=?", (coupon_id,)).fetchone()
    conn.close()
    return row


def _saved_coupon(user_id: int = 1, stake: float = 10.0, odds: float = 2.5) -> int:
    req = ManualCouponRequest(legs=[_leg(odds=odds)], stake_pln=stake, match_date=_DATA)
    res = manual_coupon(req, user_id=user_id)
    return res["coupon_id"]


# ── POST /coupon/manual — zapis ──────────────────────────────────────────────

def test_manual_coupon_zapisuje_bookmaker_i_status_active(tmp_db):
    req = ManualCouponRequest(legs=[_leg()], stake_pln=20.0, bookmaker="STS", match_date=_DATA)
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
        match_date=_DATA,
    )
    res = manual_coupon(req, user_id=1)
    assert res["total_odds"] == pytest.approx(3.0)


def test_manual_coupon_mowi_ktore_nogi_rozliczysz_sam(tmp_db):
    """Typ spoza `oblicz_tip_correct` zostaje ACTIVE na zawsze — człowiek ma
    to wiedzieć PRZY ZAPISIE, nie z alarmu po tygodniu (decyzja 10.09)."""
    req = ManualCouponRequest(
        legs=[_leg(tip="1"), _leg(home="Ajax", away="PSV", tip="rzuty rożne powyżej 3.5"),
              _leg(home="Roma", away="Lazio", tip="Over 2.5")],
        stake_pln=10.0,
        match_date=_DATA,
    )
    res = manual_coupon(req, user_id=1)
    assert res["do_recznego_rozliczenia"] == [1]


def test_manual_coupon_bez_bookmakera_jest_opcjonalny(tmp_db):
    req = ManualCouponRequest(legs=[_leg()], stake_pln=10.0, match_date=_DATA)
    res = manual_coupon(req, user_id=1)
    row = _row(tmp_db, res["coupon_id"])
    assert row["bookmaker"] is None


# ── POST /coupon/manual — walidacja ─────────────────────────────────────────

def test_manual_coupon_puste_legs_400(tmp_db):
    req = ManualCouponRequest(legs=[], stake_pln=10.0, match_date=_DATA)
    with pytest.raises(HTTPException) as exc:
        manual_coupon(req, user_id=1)
    assert exc.value.status_code == 400


def test_manual_coupon_odds_1_lub_mniej_422(tmp_db):
    # kurs poza [1.01, 1000] to teraz 422 (wspólna walidacja liczb), nie 400
    req = ManualCouponRequest(legs=[_leg(odds=1.0)], stake_pln=10.0, match_date=_DATA)
    with pytest.raises(HTTPException) as exc:
        manual_coupon(req, user_id=1)
    assert exc.value.status_code == 422


def test_manual_coupon_stake_zero_lub_ujemna_400(tmp_db):
    req = ManualCouponRequest(legs=[_leg()], stake_pln=0.0, match_date=_DATA)
    with pytest.raises(HTTPException) as exc:
        manual_coupon(req, user_id=1)
    assert exc.value.status_code == 400


def test_manual_coupon_za_dlugi_string_400(tmp_db):
    req = ManualCouponRequest(legs=[_leg(home="X" * 121)], stake_pln=10.0, match_date=_DATA)
    with pytest.raises(HTTPException) as exc:
        manual_coupon(req, user_id=1)
    assert exc.value.status_code == 400


def test_manual_coupon_za_dlugi_bookmaker_400(tmp_db):
    req = ManualCouponRequest(legs=[_leg()], stake_pln=10.0, bookmaker="X" * 61, match_date=_DATA)
    with pytest.raises(HTTPException) as exc:
        manual_coupon(req, user_id=1)
    assert exc.value.status_code == 400


def test_manual_coupon_niepoprawny_format_daty_400(tmp_db):
    req = ManualCouponRequest(legs=[_leg()], stake_pln=10.0, match_date="21-07-2026")
    with pytest.raises(HTTPException) as exc:
        manual_coupon(req, user_id=1)
    assert exc.value.status_code == 400


def test_manual_coupon_smieciowa_data_400(tmp_db):
    req = ManualCouponRequest(legs=[_leg()], stake_pln=10.0, match_date="nie-data")
    with pytest.raises(HTTPException) as exc:
        manual_coupon(req, user_id=1)
    assert exc.value.status_code == 400


def test_manual_coupon_poprawna_data_ok(tmp_db):
    req = ManualCouponRequest(legs=[_leg()], stake_pln=10.0, match_date="2026-07-21")
    res = manual_coupon(req, user_id=1)
    assert res["ok"] is True


# ── PATCH /coupon/{id}/result ────────────────────────────────────────────────

def test_result_won_payout_netto_po_podatku(tmp_db):
    cid = _saved_coupon(stake=10.0, odds=2.5)
    res = set_coupon_result(cid, CouponResultRequest(result="WON"), user_id=1)
    assert res["status"] == "WON"
    assert res["payout_pln"] == pytest.approx(22.0)  # 10 * 0.88 * 2.5


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


def _saved_ai_coupon(user_id: int = 1, stake: float = 10.0, odds: float = 2.5) -> int:
    """Kupon AI (accumulator) ACTIVE — do testu, że dziennik nie rozlicza cudzych automatów."""
    from footstats.core.coupon_tracker import STATUS_ACTIVE, save_coupon, update_coupon_status

    cid = save_coupon(
        phase="final",
        kupon_type="accumulator",
        legs=[{"home": "Legia", "away": "Lech", "tip": "1", "odds": odds}],
        total_odds=odds,
        stake_pln=stake,
        user_id=user_id,
    )
    update_coupon_status(cid, STATUS_ACTIVE)
    return cid


def test_result_niemanual_kupon_400(tmp_db):
    """Guard: kupon AI (kupon_type != 'manual') nie może być ręcznie rozliczony —
    inaczej user obszedłby automat i wpisał sobie fake WON."""
    cid = _saved_ai_coupon(stake=10.0, odds=2.5)
    with pytest.raises(HTTPException) as exc:
        set_coupon_result(cid, CouponResultRequest(result="WON"), user_id=1)
    assert exc.value.status_code == 400
    row = _row(tmp_db, cid)
    assert row["status"] == "ACTIVE"


# ── integracja J1: get_user_stats liczy rozliczony ręczny kupon ─────────────

def test_won_manual_coupon_liczony_w_user_stats(tmp_db):
    from footstats.core.user_stats import get_user_stats

    cid = _saved_coupon(user_id=1, stake=10.0, odds=2.5)
    set_coupon_result(cid, CouponResultRequest(result="WON"), user_id=1)

    stats = get_user_stats(1)
    assert stats.settled_count == 1
    assert stats.wins == 1
    assert stats.losses == 0


# ── ręczna korekta wypłaty + data nogi ───────────────────────────────────────

def test_result_won_z_kwota_zapisuje_kwote(tmp_db):
    cid = _saved_coupon(stake=10.0, odds=2.5)
    res = set_coupon_result(cid, CouponResultRequest(result="WON", payout_pln=23.4), user_id=1)
    assert res["payout_pln"] == pytest.approx(23.4)
    assert _row(tmp_db, cid)["payout_pln"] == pytest.approx(23.4)


@pytest.mark.parametrize("wynik,kwota", [
    ("LOST", 5.0), ("VOID", 5.0), ("WON", -1.0), ("WON", 10_000_001.0),
    ("WON", float("nan")), ("WON", float("inf")),
])
def test_result_zla_kwota_odrzucona(tmp_db, wynik, kwota):
    cid = _saved_coupon()
    with pytest.raises(HTTPException) as exc:
        set_coupon_result(cid, CouponResultRequest(result=wynik, payout_pln=kwota), user_id=1)
    assert exc.value.status_code in (400, 422)
    assert _row(tmp_db, cid)["status"] == "ACTIVE"


def test_result_korekta_won_do_won_z_kwota(tmp_db):
    cid = _saved_coupon(stake=10.0, odds=2.5)
    set_coupon_result(cid, CouponResultRequest(result="WON"), user_id=1)
    res = set_coupon_result(cid, CouponResultRequest(result="WON", payout_pln=24.0), user_id=1)
    row = _row(tmp_db, cid)
    assert res["payout_pln"] == pytest.approx(24.0)
    assert row["status"] == "WON"
    assert row["payout_pln"] == pytest.approx(24.0)
    assert row["roi_pct"] == pytest.approx(140.0)


def test_result_won_do_won_bez_kwoty_409(tmp_db):
    cid = _saved_coupon()
    set_coupon_result(cid, CouponResultRequest(result="WON"), user_id=1)
    with pytest.raises(HTTPException) as exc:
        set_coupon_result(cid, CouponResultRequest(result="WON"), user_id=1)
    assert exc.value.status_code == 409


def test_result_korekta_cudzego_kuponu_403(tmp_db):
    cid = _saved_coupon(user_id=1)
    set_coupon_result(cid, CouponResultRequest(result="WON"), user_id=1)
    with pytest.raises(HTTPException) as exc:
        set_coupon_result(cid, CouponResultRequest(result="WON", payout_pln=30.0), user_id=2)
    assert exc.value.status_code == 403


def test_manual_coupon_zapisuje_date_nogi_tylko_gdy_podana(tmp_db):
    import json

    req = ManualCouponRequest(
        legs=[ManualLeg(home="A", away="B", tip="1", odds=1.5, match_date="2026-07-25"),
              _leg()],
        stake_pln=10.0,
    )
    legs = json.loads(_row(tmp_db, manual_coupon(req, user_id=1)["coupon_id"])["legs_json"])
    assert legs[0]["match_date"] == "2026-07-25"
    assert "match_date" not in legs[1]


def test_manual_coupon_zla_data_nogi_400(tmp_db):
    req = ManualCouponRequest(
        legs=[ManualLeg(home="A", away="B", tip="1", odds=1.5, match_date="25-07-2026")],
        stake_pln=10.0,
    )
    with pytest.raises(HTTPException) as exc:
        manual_coupon(req, user_id=1)
    assert exc.value.status_code == 400


# ── POST /coupon/manual — data wymagana ──────────────────────────────────────

def test_manual_coupon_bez_zadnej_daty_400(tmp_db):
    """Kupon bez daty (ani kuponu, ani żadnej nogi) nigdy się nie rozliczy ani
    nie zaalarmuje — odrzucamy go przy zapisie, z komunikatem po polsku."""
    req = ManualCouponRequest(legs=[_leg()], stake_pln=10.0)
    with pytest.raises(HTTPException) as exc:
        manual_coupon(req, user_id=1)
    assert exc.value.status_code == 400
    assert "datę meczu" in exc.value.detail


def test_manual_coupon_data_kuponu_wystarcza(tmp_db):
    req = ManualCouponRequest(legs=[_leg()], stake_pln=10.0, match_date="2026-11-08")
    assert manual_coupon(req, user_id=1)["ok"] is True


def test_manual_coupon_data_na_jednej_nodze_wystarcza(tmp_db):
    """Brak daty kuponu przechodzi, gdy KTÓRAKOLWIEK noga ma datę."""
    req = ManualCouponRequest(
        legs=[_leg(), ManualLeg(home="Ajax", away="PSV", tip="1", odds=1.5, match_date="2026-11-08")],
        stake_pln=10.0,
    )
    assert manual_coupon(req, user_id=1)["ok"] is True
