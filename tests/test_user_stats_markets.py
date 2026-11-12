"""Statystyki wg rodzaju typu: klasyfikator, get_market_stats, GET /api/stats/markets."""
import json

import pytest
from fastapi.testclient import TestClient

from footstats.api.auth import require_auth
from footstats.api.main import app
from footstats.core.coupon_tracker import save_coupon, update_coupon_status
from footstats.core.user_stats import get_market_stats, klasyfikuj_rynek, skladniki_bb
from tests.test_user_stats import tmp_db  # noqa: F401  (fixture autouse, izolowana baza)


@pytest.mark.parametrize("tip,oczekiwany", [
    ("1", "Wynik 1X2"), ("x", "Wynik 1X2"), ("2", "Wynik 1X2"),
    ("1X", "Podwójna szansa"), ("x2", "Podwójna szansa"), ("12", "Podwójna szansa"),
    ("Over 2.5", "Gole w meczu"), ("under 3,5", "Gole w meczu"),
    ("BTTS", "Obie strzelą"), ("btts no", "Obie strzelą"),
    ("1 OVER 1.5", "Gole drużyny"), ("2 under 0.5", "Gole drużyny"),
    ("GOSPODARZ STRZELI", "Gole drużyny"), ("gość strzeli", "Gole drużyny"),
    ("CORNERS OVER 9.5", "Rzuty rożne"), ("1 corners over 4.5", "Rzuty rożne"),
    ("GOL: Haaland", "Zawodnik: gol"),
    ("SOT: Haaland OVER 1.5", "Zawodnik: celne strzały"),
    ("BB: 1 OVER 1.5 + CORNERS OVER 9.5", "Bet Builder"),
    ("bb 1 over 1.5", "Bet Builder"),
    ("HANDICAP +1 GOŚĆ", "Inne"), ("", "Inne"), (None, "Inne"),
    ("1 & OVER 2.5", "Inne"),
])
def test_klasyfikuj_rynek(tip, oczekiwany):
    assert klasyfikuj_rynek(tip) == oczekiwany


def test_skladniki_bb_unikalne_i_tylko_dla_bb():
    tip = "BB: 1 OVER 1.5 + 2 OVER 0.5 + CORNERS OVER 9.5"
    assert skladniki_bb(tip) == ["Gole drużyny", "Rzuty rożne"]
    assert skladniki_bb("Over 2.5") == []


def _kupon(legs, status="WON", user_id=1, typ="manual"):
    cid = save_coupon("final", typ, legs, total_odds=2.0, stake_pln=10.0, user_id=user_id)
    update_coupon_status(cid, "ACTIVE")
    if status != "ACTIVE":
        update_coupon_status(cid, status)
    return cid


def _leg(tip, odds, won):
    return {"home": "A", "away": "B", "tip": tip, "odds": odds, "leg_won": won}


def test_market_stats_agreguje_i_sortuje():
    _kupon([_leg("Over 2.5", 2.0, True), _leg("BTTS", 2.0, False)], status="LOST")
    _kupon([_leg("Over 2.5", 2.0, True), _leg("1", 1.5, True)])
    _kupon([_leg("Over 2.5", 4.0, False)], status="LOST")
    stats = {s.market: s for s in get_market_stats(1)}
    gole = stats["Gole w meczu"]
    assert (gole.n, gole.wins) == (3, 2)
    assert gole.hit_rate == pytest.approx(2 / 3)
    assert gole.implied_prob == pytest.approx((0.5 + 0.5 + 0.25) / 3)
    assert gole.edge_pp == pytest.approx((2 / 3 - 1.25 / 3) * 100)
    assert gole.se_pp == pytest.approx(((2 / 3) * (1 / 3) / 3) ** 0.5 * 100)
    assert gole.n_za_male is True
    assert get_market_stats(1)[0].market == "Gole w meczu"


def test_market_stats_pomija_nogi_bez_leg_won_void_active_manual_only_i_innych_userow():
    _kupon([_leg("Over 2.5", 2.0, False), _leg("BTTS", 2.0, None)], status="LOST")
    _kupon([{"tip": "1", "odds": 2.0}])  # brak leg_won (zamknięty ręcznie)
    _kupon([_leg("1", 2.0, True)], status="VOID")
    _kupon([_leg("1", 2.0, True)], status="ACTIVE")
    _kupon([_leg("1", 2.0, True)], user_id=2)
    _kupon([_leg("1", 2.0, True)], typ="final")
    stats = get_market_stats(1)
    assert [(s.market, s.n) for s in stats] == [("Gole w meczu", 1)]


def test_market_stats_bb_ma_skladniki_i_uszkodzony_json_nie_wywala():
    _kupon([_leg("BB: 1 OVER 1.5 + CORNERS OVER 9.5", 3.0, True)])
    cid = _kupon([_leg("1", 2.0, True)])
    import footstats.core.coupon_tracker as ct
    with ct._connect() as conn:
        conn.execute("UPDATE coupons SET legs_json = ? WHERE id = ?", ("{zepsute", cid))
    stats = get_market_stats(1)
    assert len(stats) == 1 and stats[0].market == "Bet Builder"
    assert stats[0].skladniki == ["Gole drużyny", "Rzuty rożne"]
    json.dumps(stats[0].skladniki)


def test_endpoint_wymaga_auth():
    assert TestClient(app).get("/api/stats/markets").status_code in (401, 403)


def test_endpoint_zwraca_liste():
    app.dependency_overrides[require_auth] = lambda: 1
    try:
        _kupon([_leg("Over 2.5", 2.0, True)])
        r = TestClient(app).get("/api/stats/markets")
    finally:
        app.dependency_overrides.pop(require_auth, None)
    assert r.status_code == 200
    body = r.json()
    assert body[0]["market"] == "Gole w meczu" and body[0]["n"] == 1
    assert body[0]["n_za_male"] is True
