"""tests/test_coupon_preview_signal.py — J6 (Etap B): podgląd NASZEGO sygnału
(typ + pewność + prawd.) obok wyboru użytkownika w formularzu ręcznego kuponu.

Izolacja: `match_linker.link_leg` monkeypatchowany (zero DB, zero zewn. API),
`_connect` w routes.coupons zablokowany fixture'em — endpoint MUSI być
READ-ONLY (deleguje całą logikę dopasowania do link_leg, sam nie dotyka DB
bezpośrednio). Endpoint wołany wprost (bez FastAPI TestClient), wzorem
tests/test_coupon_manual.py.
"""
import pytest
from fastapi import HTTPException

import footstats.api.routes.coupons as routes
import footstats.core.match_linker as match_linker
from footstats.api.routes.coupons import PreviewLeg, PreviewSignalRequest, preview_signal
from footstats.core.match_linker import LinkResult


def _prediction(ai_tip: str = "1", ai_confidence: float = 72.0) -> dict:
    return {
        "id": 1,
        "team_home": "Legia",
        "team_away": "Lech",
        "match_date": "2026-07-21",
        "ai_tip": ai_tip,
        "ai_confidence": ai_confidence,
        "prob_home": 0.55,
        "prob_draw": 0.25,
        "prob_away": 0.20,
        "actual_result": None,
    }


def _leg(home: str = "Legia", away: str = "Lech", tip: str = "1") -> PreviewLeg:
    return PreviewLeg(home=home, away=away, tip=tip)


def _mock_link_leg(monkeypatch, result: LinkResult) -> None:
    monkeypatch.setattr(
        match_linker, "link_leg",
        lambda home, away, date, day_tolerance=1: result,
    )


@pytest.fixture(autouse=True)
def block_direct_db(monkeypatch):
    """Endpoint podglądu sygnału MUSI być read-only (deleguje do link_leg) —
    bezpośrednie wywołanie `_connect` w routes.coupons sygnalizuje regresję
    (zapis/odczyt poza kontraktem link_leg)."""
    def _boom():
        raise AssertionError("preview_signal nie powinien wołać _connect bezpośrednio")

    monkeypatch.setattr(routes, "_connect", _boom)


# ── matched ──────────────────────────────────────────────────────────────────

def test_matched_zwraca_nasz_typ_pewnosc_i_prawdopodobienstwa(monkeypatch):
    _mock_link_leg(monkeypatch, LinkResult(True, "exact", _prediction(ai_tip="1", ai_confidence=72.0), "Dopasowano"))
    req = PreviewSignalRequest(legs=[_leg(tip="1")], match_date="2026-07-21")

    res = preview_signal(req, user_id=1)

    assert len(res) == 1
    sig = res[0]
    assert sig["matched"] is True
    assert sig["our_tip"] == "1"
    assert sig["our_confidence_pct"] == 72  # kalibracja OFF (domyślnie) == identity
    assert sig["prob_home"] == pytest.approx(0.55)
    assert sig["prob_draw"] == pytest.approx(0.25)
    assert sig["prob_away"] == pytest.approx(0.20)
    assert sig["agrees"] is True


def test_agrees_false_gdy_user_wybral_inny_typ(monkeypatch):
    _mock_link_leg(monkeypatch, LinkResult(True, "exact", _prediction(ai_tip="1"), "ok"))
    req = PreviewSignalRequest(legs=[_leg(tip="X")], match_date="2026-07-21")

    res = preview_signal(req, user_id=1)

    assert res[0]["agrees"] is False


def test_agrees_case_insensitive_po_stripie(monkeypatch):
    _mock_link_leg(monkeypatch, LinkResult(True, "exact", _prediction(ai_tip="Over 2.5"), "ok"))
    req = PreviewSignalRequest(legs=[_leg(tip=" over 2.5 ")], match_date="2026-07-21")

    res = preview_signal(req, user_id=1)

    assert res[0]["agrees"] is True


def test_kalibracja_off_pewnosc_rowna_ai_confidence(monkeypatch):
    _mock_link_leg(monkeypatch, LinkResult(True, "exact", _prediction(ai_confidence=55.0), "ok"))
    req = PreviewSignalRequest(legs=[_leg()], match_date="2026-07-21")

    res = preview_signal(req, user_id=1)

    assert res[0]["our_confidence_pct"] == 55


# ── nie matched ──────────────────────────────────────────────────────────────

def test_nie_matched_zwraca_null_pola(monkeypatch):
    _mock_link_leg(monkeypatch, LinkResult(False, "none", None, "Brak dopasowania"))
    req = PreviewSignalRequest(legs=[_leg()], match_date="2026-07-21")

    res = preview_signal(req, user_id=1)

    assert res == [{
        "matched": False, "our_tip": None, "our_confidence_pct": None,
        "prob_home": None, "prob_draw": None, "prob_away": None, "agrees": None,
    }]


# ── walidacja (cap 30 nóg) ───────────────────────────────────────────────────

def test_wiecej_niz_30_nog_400(monkeypatch):
    _mock_link_leg(monkeypatch, LinkResult(False, "none", None, "x"))
    req = PreviewSignalRequest(legs=[_leg() for _ in range(31)], match_date="2026-07-21")

    with pytest.raises(HTTPException) as exc:
        preview_signal(req, user_id=1)
    assert exc.value.status_code == 400


def test_dokladnie_30_nog_ok(monkeypatch):
    _mock_link_leg(monkeypatch, LinkResult(False, "none", None, "x"))
    req = PreviewSignalRequest(legs=[_leg() for _ in range(30)], match_date="2026-07-21")

    res = preview_signal(req, user_id=1)

    assert len(res) == 30


def test_puste_legs_zwraca_puste_liste():
    req = PreviewSignalRequest(legs=[], match_date="2026-07-21")

    res = preview_signal(req, user_id=1)

    assert res == []
