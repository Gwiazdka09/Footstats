"""tests/test_coupon_tracker.py — SQLite-backed fixture (PostgreSQL DDL mocked)."""
import sqlite3
import pytest


class _SQLiteConn:
    """sqlite3 adapter matching footstats.utils.db._Conn interface."""

    def __init__(self, path: str) -> None:
        self._raw = sqlite3.connect(path)
        self._raw.row_factory = sqlite3.Row

    def execute(self, sql: str, params=()):
        return self._raw.execute(sql, params)

    def executemany(self, sql: str, seq):
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
    user_id          INTEGER DEFAULT 1,
    shared           BOOLEAN NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_coupon_status  ON coupons(status);
CREATE INDEX IF NOT EXISTS idx_coupon_created ON coupons(created_at);
CREATE TABLE IF NOT EXISTS predictions (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    coupon_id INTEGER REFERENCES coupons(id)
)
"""


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    """Each test gets own SQLite DB; _connect + init_coupon_tables mocked."""
    db_path = str(tmp_path / "test.db")

    setup = sqlite3.connect(db_path)
    setup.executescript(_SCHEMA)
    setup.commit()
    setup.close()

    import footstats.core.coupon_tracker as ct

    monkeypatch.setattr(ct, "_connect", lambda: _SQLiteConn(db_path))
    monkeypatch.setattr(ct, "init_coupon_tables", lambda: None)
    yield db_path


from footstats.core.coupon_tracker import (
    save_coupon,
    update_coupon_status,
    get_active_coupons,
    get_coupon_legs,
)


def test_save_coupon_returns_positive_id():
    legs = [{"gospodarz": "PSG", "goscie": "Lyon", "typ": "1", "kurs": 1.45}]
    cid = save_coupon("draft", "A", legs, total_odds=1.45, stake_pln=10.0)
    assert isinstance(cid, int)
    assert cid > 0


def test_new_coupon_has_draft_status():
    save_coupon("draft", "A", [])
    active = get_active_coupons()
    assert len(active) == 1
    assert active[0]["status"] == "DRAFT"


def test_lost_coupon_not_in_active():
    cid = save_coupon("final", "A", [], stake_pln=10.0)
    update_coupon_status(cid, "LOST", payout_pln=0.0)
    active = get_active_coupons()
    assert all(c["id"] != cid for c in active)


def test_get_active_coupons_user_none_zwraca_wszystkich():
    # Regresja 06-21: evening_agent rozliczał 0 bo get_active_coupons() default user_id=1,
    # a kupony to user 408/2. user_id=None musi zwrócić kupony WSZYSTKICH userów.
    cid = save_coupon("final", "A", [], stake_pln=10.0, user_id=408)
    # filtr po user_id=1 NIE widzi kuponu usera 408
    assert all(c["id"] != cid for c in get_active_coupons(user_id=1))
    # user_id=None widzi (do rozliczeń evening)
    assert any(c["id"] == cid for c in get_active_coupons(user_id=None))


def _status_kuponu_z_db(db_path: str, cid: int) -> str:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    st = conn.execute("SELECT status FROM coupons WHERE id=?", (cid,)).fetchone()["status"]
    conn.close()
    return st


def test_update_coupon_status_cas_zgodny_zmienia(tmp_db):
    cid = save_coupon("final", "A", [], stake_pln=10.0)
    update_coupon_status(cid, "ACTIVE")
    zmienione = update_coupon_status(cid, "WON", payout_pln=20.0, expected_status="ACTIVE")
    assert zmienione is True
    assert _status_kuponu_z_db(tmp_db, cid) == "WON"


def test_update_coupon_status_cas_niezgodny_nie_zmienia(tmp_db):
    # D3 (audyt 09-07): drugi proces settle (evening vs settle_active_coupons)
    # nie może nadpisać już rozliczonego kuponu — CAS zwraca False, caller
    # pomija kredyt bankrollu (zero podwójnej wypłaty).
    cid = save_coupon("final", "A", [], stake_pln=10.0)
    update_coupon_status(cid, "ACTIVE")
    update_coupon_status(cid, "WON", payout_pln=20.0)   # pierwszy settle wygrał wyścig
    zmienione = update_coupon_status(cid, "LOST", expected_status="ACTIVE")
    assert zmienione is False
    assert _status_kuponu_z_db(tmp_db, cid) == "WON"    # nietknięty przez drugi proces


def test_update_coupon_status_bez_cas_dziala_jak_dotad(tmp_db):
    # Wsteczna kompatybilność: bez expected_status UPDATE bezwarunkowy.
    cid = save_coupon("final", "A", [], stake_pln=10.0)
    assert update_coupon_status(cid, "ACTIVE") is True
    assert _status_kuponu_z_db(tmp_db, cid) == "ACTIVE"


def test_won_coupon_roi_calculated():
    cid = save_coupon("final", "A", [], stake_pln=10.0)
    update_coupon_status(cid, "WON", payout_pln=110.0)
    from footstats.core.coupon_tracker import _connect
    with _connect() as conn:
        row = conn.execute("SELECT roi_pct FROM coupons WHERE id=?", (cid,)).fetchone()
    assert row["roi_pct"] == pytest.approx(1000.0, abs=1.0)


def test_get_coupon_legs_roundtrip():
    legs = [{"gospodarz": "Bayern", "goscie": "Dortmund", "typ": "1X", "kurs": 1.30}]
    cid = save_coupon("draft", "B", legs)
    assert get_coupon_legs(cid) == legs


def test_get_coupon_legs_unknown_id_returns_empty():
    assert get_coupon_legs(9999) == []


def test_init_coupon_tables_idempotent():
    """No-op mock called multiple times — must not raise."""
    import footstats.core.coupon_tracker as ct
    ct.init_coupon_tables()
    ct.init_coupon_tables()


def test_update_coupon_status_invalid_raises():
    cid = save_coupon("draft", "A", [])
    with pytest.raises(ValueError, match="Nieprawidłowy"):
        update_coupon_status(cid, "INVALID_STATUS")


def test_get_draft_today_returns_todays_draft():
    from footstats.core.coupon_tracker import get_draft_today
    cid = save_coupon("draft", "A", [])
    row = get_draft_today()
    assert row is not None
    assert row["id"] == cid


def test_get_draft_today_ignores_active_coupon():
    from footstats.core.coupon_tracker import get_draft_today
    cid = save_coupon("final", "A", [], stake_pln=10.0)
    update_coupon_status(cid, "ACTIVE")
    row = get_draft_today()
    assert row is None


def test_get_draft_today_none_when_empty():
    from footstats.core.coupon_tracker import get_draft_today
    assert get_draft_today() is None


def test_promote_to_active_changes_status_to_active():
    from footstats.core.coupon_tracker import promote_to_active
    cid = save_coupon("draft", "A", [])
    promote_to_active(cid)
    active = get_active_coupons()
    rows = [c for c in active if c["id"] == cid]
    assert rows, "Kupon powinien być w active_coupons po promocji"
    assert rows[0]["status"] == "ACTIVE"
    assert rows[0]["phase"] == "final"


def test_promote_to_active_updates_legs_and_reasoning():
    from footstats.core.coupon_tracker import promote_to_active
    cid = save_coupon("draft", "A", [{"home": "A", "away": "B"}])
    new_legs = [{"home": "X", "away": "Y", "tip": "1"}]
    promote_to_active(cid, legs=new_legs, groq_reasoning="test reason", decision_score=75)
    assert get_coupon_legs(cid) == new_legs


def test_promote_to_active_no_legs_keeps_old_legs():
    from footstats.core.coupon_tracker import promote_to_active
    original_legs = [{"home": "PSG", "away": "Lyon"}]
    cid = save_coupon("draft", "A", original_legs)
    promote_to_active(cid)
    assert get_coupon_legs(cid) == original_legs
