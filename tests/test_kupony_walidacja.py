"""Walidacja liczb kuponów, kurs łączny liczony na serwerze, spójny zysk w trzech widokach.

Izolacja: place_coupon na atrapie połączenia (zero Neona), manual/ranking/user_stats
na plikowej SQLite z adapterem zgodnym z utils.db._Conn. Zero Telegrama.
"""
import logging
import sqlite3

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import footstats.api.routes.coupons as cr
import footstats.core.coupon_tracker as ct
from footstats.api.routes.coupons import (
    ManualCouponRequest,
    ManualLeg,
    PlaceCouponRequest,
    SelectionItem,
    get_leaderboard,
    manual_coupon,
    place_coupon,
)
from footstats.core.user_stats import get_progress_series, get_user_stats


# ── atrapa połączenia dla /coupon/place ──────────────────────────────────────
class _Cur:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _Fake:
    def __init__(self):
        self.inserty: list[tuple] = []

    def execute(self, sql, params=()):
        if "SELECT balance" in sql:
            return _Cur({"balance": 1000.0})
        if "INSERT INTO coupons" in sql:
            self.inserty.append(tuple(params))
            return _Cur({"id": 7})
        return _Cur(None)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def fake(monkeypatch):
    f = _Fake()
    monkeypatch.setattr(cr, "_connect", lambda: f)
    import footstats.core.response_cache as rc
    monkeypatch.setattr(rc, "clear_response_cache", lambda: None, raising=False)
    return f


def _sel(odds: float = 1.05) -> SelectionItem:
    return SelectionItem(match_id="1", home="A", away="B", tip="1", odds=odds, win_prob=60)


def _place(**kw):
    dane = {"selections": [_sel()], "total_odds": 1.05, "stake_pln": 10.0,
            "match_date": "2026-08-02"}
    dane.update(kw)
    return place_coupon(PlaceCouponRequest(**dane), user_id=1)


def _kod(exc) -> int:
    return exc.value.status_code


# ── /coupon/place ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("stawka", [float("nan"), float("inf"), "1e309", 100_001.0])
def test_place_zla_stawka_422(fake, stawka):
    with pytest.raises(HTTPException) as exc:
        _place(stake_pln=stawka)
    assert _kod(exc) == 422
    assert fake.inserty == []


@pytest.mark.parametrize("kurs", [float("nan"), float("inf"), 0.5, 1.0, 1001.0])
def test_place_zly_kurs_nogi_422(fake, kurs):
    with pytest.raises(HTTPException) as exc:
        _place(selections=[_sel(kurs)])
    assert _kod(exc) == 422
    assert fake.inserty == []


def test_place_kurs_laczny_inf_422(fake):
    # każdy kurs poprawny, ale iloczyn 1000^200 = inf
    with pytest.raises(HTTPException) as exc:
        _place(selections=[_sel(1000.0)] * 200)
    assert _kod(exc) == 422


def test_place_brak_kursu_nogi_odrzucony():
    with pytest.raises(ValidationError):  # FastAPI zamienia to na 422
        PlaceCouponRequest(
            selections=[{"match_id": "1", "home": "A", "away": "B", "tip": "1", "win_prob": 60}],
            stake_pln=10.0,
        )


def test_place_puste_selections_422(fake):
    with pytest.raises(HTTPException) as exc:
        _place(selections=[])
    assert _kod(exc) == 422


def test_place_total_odds_od_klienta_ignorowany(fake, caplog):
    with caplog.at_level(logging.WARNING):
        _place(total_odds=1000.0)
    assert fake.inserty[0][5] == 1.05
    assert any("total_odds" in r.getMessage() for r in caplog.records)


def test_place_total_odds_to_iloczyn_nog(fake):
    _place(selections=[_sel(1.5), _sel(2.0)], total_odds=None)
    assert fake.inserty[0][5] == 3.0


def test_place_total_odds_zgodny_nie_loguje_ostrzezenia(fake, caplog):
    with caplog.at_level(logging.WARNING):
        _place(total_odds=1.05)
    assert not any("total_odds" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("data", ["abc", "2026-13-40", "02.08.2026"])
def test_place_zla_data_422(fake, data):
    with pytest.raises(HTTPException) as exc:
        _place(match_date=data)
    assert _kod(exc) == 422


@pytest.mark.parametrize("data", ["2026-08-02", "2026-08-02T18:30:00", "2026-08-02 18:30:00"])
def test_place_poprawna_data_ok(fake, data):
    res = _place(match_date=data)
    assert res["ok"] is True
    assert fake.inserty[0][8] == "2026-08-02"


def test_place_poprawny_kupon_przechodzi(fake):
    assert _place()["coupon_id"] == 7


# ── SQLite dla manual / user_stats / ranking ─────────────────────────────────
class _SQLiteConn:
    def __init__(self, path: str) -> None:
        self._raw = sqlite3.connect(path)
        self._raw.row_factory = sqlite3.Row

    def execute(self, sql, params=()):
        return self._raw.execute(sql, params)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_):
        if exc_type:
            self._raw.rollback()
        else:
            self._raw.commit()
        self._raw.close()
        return False


_SCHEMA = """
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL DEFAULT 'x', leaderboard_opt_in BOOLEAN NOT NULL DEFAULT 1);
CREATE TABLE coupons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    phase TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'DRAFT',
    kupon_type TEXT NOT NULL DEFAULT '', legs_json TEXT NOT NULL DEFAULT '[]',
    total_odds REAL, stake_pln REAL, payout_pln REAL, roi_pct REAL,
    groq_reasoning TEXT, decision_score INTEGER, match_date_first TEXT,
    bookmaker TEXT, user_id INTEGER DEFAULT 1, shared BOOLEAN NOT NULL DEFAULT 0,
    settled_at TIMESTAMP);
"""


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = str(tmp_path / "t.db")
    raw = sqlite3.connect(path)
    raw.executescript(_SCHEMA)
    raw.execute("INSERT INTO users (id, username) VALUES (1, 'typer')")
    raw.commit()
    raw.close()
    monkeypatch.setattr(ct, "_connect", lambda: _SQLiteConn(path))
    monkeypatch.setattr(ct, "init_coupon_tables", lambda: None)
    monkeypatch.setattr(cr, "_connect", lambda: _SQLiteConn(path))
    monkeypatch.setattr(cr, "clear_response_cache", lambda: None, raising=False)
    return path


def _wstaw(db_path, status, stake, odds, payout, created="2026-08-01 10:00:00") -> None:
    raw = sqlite3.connect(db_path)
    raw.execute(
        "INSERT INTO coupons (created_at, status, kupon_type, total_odds, stake_pln, "
        "payout_pln, user_id) VALUES (?,?,?,?,?,?,1)",
        (created, status, "manual", odds, stake, payout),
    )
    raw.commit()
    raw.close()


def _leg(odds) -> ManualLeg:
    return ManualLeg(home="Legia", away="Lech", tip="1", odds=odds)


# ── /coupon/manual ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("stawka", [float("nan"), float("inf"), "1e309"])
def test_manual_zla_stawka_422(db, stawka):
    with pytest.raises(HTTPException) as exc:
        manual_coupon(ManualCouponRequest(legs=[_leg(1.85)], stake_pln=stawka), user_id=1)
    assert _kod(exc) == 422


@pytest.mark.parametrize("kurs", [float("nan"), float("inf"), "1e309", 0.5, 1.0, 1001.0])
def test_manual_zly_kurs_422(db, kurs):
    with pytest.raises(HTTPException) as exc:
        manual_coupon(ManualCouponRequest(legs=[_leg(kurs)], stake_pln=10.0), user_id=1)
    assert _kod(exc) == 422


def test_manual_nan_stawka_i_kurs_razem_422(db):
    with pytest.raises(HTTPException) as exc:
        manual_coupon(
            ManualCouponRequest(legs=[_leg(float("nan"))], stake_pln=float("nan")), user_id=1)
    assert _kod(exc) == 422


def test_kurs_laczny_inf_422_we_wspolnej_walidacji():
    # przy limicie 30 nóg manual nie dobije do inf, więc sprawdzamy wspólną funkcję
    with pytest.raises(HTTPException) as exc:
        cr._waliduj_liczby_kuponu(10.0, [1000.0] * 200)
    assert _kod(exc) == 422


def test_manual_granice_kursu_przechodza(db):
    res = manual_coupon(ManualCouponRequest(legs=[_leg(1.01)], stake_pln=10.0), user_id=1)
    assert res["total_odds"] == 1.01
    res = manual_coupon(ManualCouponRequest(legs=[_leg(1000.0)], stake_pln=10.0), user_id=1)
    assert res["total_odds"] == 1000.0


# ── user_stats: zysk z faktycznej wypłaty ────────────────────────────────────
def test_zysk_won_z_wyplata_to_wyplata_minus_stawka(db):
    _wstaw(db, "WON", 100.0, 2.0, 150.0)  # wypłata z buka (np. booster)
    assert get_user_stats(1).profit_units == pytest.approx(50.0)


def test_zysk_won_bez_wyplaty_netto_po_podatku(db):
    _wstaw(db, "WON", 100.0, 2.0, None)
    assert get_user_stats(1).profit_units == pytest.approx(76.0)  # 176 - 100


def test_zysk_lost_to_minus_stawka_niezaleznie_od_wyplaty(db):
    _wstaw(db, "LOST", 40.0, 2.0, 0.0)
    _wstaw(db, "LOST", 10.0, 2.0, None)
    assert get_user_stats(1).profit_units == pytest.approx(-50.0)


def test_won_bez_kursu_i_wyplaty_zero(db):
    _wstaw(db, "WON", 100.0, None, None)
    assert get_user_stats(1).profit_units == 0.0


def test_trzy_widoki_licza_ten_sam_zysk(db):
    _wstaw(db, "WON", 100.0, 2.0, 150.0, "2026-08-01 10:00:00")
    _wstaw(db, "WON", 50.0, 3.0, 120.0, "2026-08-02 10:00:00")
    _wstaw(db, "LOST", 30.0, 2.0, 0.0, "2026-08-03 10:00:00")
    me = get_user_stats(1).profit_units
    progress = get_progress_series(1)[-1].cumulative_profit
    ranking = get_leaderboard.__wrapped__(min_coupons=1, limit=10, sort="profit", days=0)
    assert me == pytest.approx(50.0 + 70.0 - 30.0)
    assert progress == pytest.approx(me)
    assert ranking[0]["profit_pln"] == pytest.approx(me)
