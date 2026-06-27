"""Prod-safety: /coupon/place validate_only=True waliduje BEZ zapisu do DB.

Regression dla bugu z code-review: operator smoke realnie INSERT-ował kupon
do prod Neon + zjadał bankroll. Tryb validate_only musi zwrócić zanim cokolwiek
zapisze.
"""
import footstats.api.routes.coupons as coupons
from footstats.api.routes.coupons import (
    PlaceCouponRequest,
    SelectionItem,
    place_coupon,
)


class _FakeCur:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _FakeConn:
    """Loguje SQL; SELECT balance zwraca bankroll, reszta None."""

    def __init__(self):
        self.sqls = []

    def execute(self, sql, params=()):
        self.sqls.append(sql)
        if "SELECT balance" in sql:
            return _FakeCur({"balance": 1000.0})
        return _FakeCur(None)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _req(validate_only: bool) -> PlaceCouponRequest:
    return PlaceCouponRequest(
        selections=[SelectionItem(match_id="1", home="A", away="B",
                                  tip="1", odds=1.5, win_prob=60)],
        total_odds=1.5,
        stake_pln=2.0,
        match_date="2099-01-01",
        validate_only=validate_only,
    )


def test_validate_only_nie_zapisuje(monkeypatch):
    fake = _FakeConn()
    monkeypatch.setattr(coupons, "_connect", lambda: fake)

    res = place_coupon(_req(validate_only=True), user_id=1)

    assert res["validated"] is True
    assert res["ok"] is True
    # ZERO writes — żadnego INSERT/UPDATE.
    joined = " ".join(fake.sqls).upper()
    assert "INSERT" not in joined
    assert "UPDATE" not in joined


def test_normalny_place_zapisuje(monkeypatch):
    """Kontrola: bez validate_only ścieżka pisze (INSERT do coupons)."""
    fake = _FakeConn()
    monkeypatch.setattr(coupons, "_connect", lambda: fake)
    monkeypatch.setattr(coupons, "clear_response_cache", lambda: None, raising=False)

    # INSERT ... RETURNING id → fetchone musi zwrócić id; rozszerz fake.
    def _execute(sql, params=()):
        fake.sqls.append(sql)
        if "SELECT balance" in sql:
            return _FakeCur({"balance": 1000.0})
        if "INSERT INTO coupons" in sql:
            return _FakeCur({"id": 42})
        return _FakeCur(None)

    fake.execute = _execute  # type: ignore[method-assign]

    res = place_coupon(_req(validate_only=False), user_id=1)

    assert res["coupon_id"] == 42
    joined = " ".join(fake.sqls).upper()
    assert "INSERT INTO COUPONS" in joined
