"""test_system_paper_build.py — writer single-leg kuponów System (pętla DB).

Hartuje ścieżkę zbierania danych walidacyjnych: rozwiązanie usera, dedup
idempotentny, save_coupon + status ACTIVE. Fake-DB (bez Neon)."""
import footstats.core.system_paper as sp
from footstats.core.coupon_tracker import STATUS_ACTIVE


class _FakeCur:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _FakeConn:
    """Kontekst-manager udający połączenie; execute().fetchone() → exists_row."""
    def __init__(self, exists_row=None):
        self._row = exists_row

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, *a, **k):
        return _FakeCur(self._row)


def _patch(monkeypatch, exists_row=None):
    calls = {"save": [], "status": []}
    monkeypatch.setattr("footstats.core.coupon_tracker.init_coupon_tables", lambda: None)
    monkeypatch.setattr("footstats.core.coupon_tracker.save_coupon",
                        lambda **k: (calls["save"].append(k) or 100))
    monkeypatch.setattr("footstats.core.coupon_tracker.update_coupon_status",
                        lambda cid, st: calls["status"].append((cid, st)))
    monkeypatch.setattr("footstats.utils.db.connect", lambda: _FakeConn(exists_row))
    return calls


def _wyn():
    return [{"gospodarz": "A", "goscie": "B", "data": "2026-08-01",
             "odds": {"home": 1.8}, "pw": 60}]


def test_happy_path_tworzy_kupon(monkeypatch):
    calls = _patch(monkeypatch, exists_row=None)
    n = sp.build_single_leg_coupons(_wyn(), user_id=42)
    assert n == 1
    assert len(calls["save"]) == 1
    k = calls["save"][0]
    assert k["phase"] == "system" and k["shared"] is False and k["user_id"] == 42
    assert k["legs"][0]["tip"] == "1" and k["legs"][0]["odds"] == 1.8
    assert calls["status"] == [(100, STATUS_ACTIVE)]


def test_idempotencja_pomija_istniejacy(monkeypatch):
    calls = _patch(monkeypatch, exists_row=(1,))   # System ma już kupon na ten mecz/datę
    n = sp.build_single_leg_coupons(_wyn(), user_id=42)
    assert n == 0 and calls["save"] == []


def test_brak_usera_zwraca_zero(monkeypatch):
    _patch(monkeypatch)
    monkeypatch.setattr(sp, "_resolve_system_user_id", lambda: None)
    n = sp.build_single_leg_coupons(_wyn(), user_id=None)
    assert n == 0


def test_brak_legalnego_typu_pomija(monkeypatch):
    calls = _patch(monkeypatch, exists_row=None)
    # kurs longshot 8.0 (>MAX_KURS) → najlepszy_typ None → brak kuponu
    wyn = [{"gospodarz": "A", "goscie": "B", "data": "2026-08-01",
            "odds": {"home": 8.0}, "pw": 60}]
    n = sp.build_single_leg_coupons(wyn, user_id=42)
    assert n == 0 and calls["save"] == []


def test_brak_nazw_druzyn_pomija(monkeypatch):
    calls = _patch(monkeypatch, exists_row=None)
    wyn = [{"gospodarz": "", "goscie": "B", "data": "2026-08-01",
            "odds": {"home": 1.8}, "pw": 60}]
    n = sp.build_single_leg_coupons(wyn, user_id=42)
    assert n == 0 and calls["save"] == []
