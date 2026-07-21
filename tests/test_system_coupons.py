"""Testy core.system_coupons — automatyczne propozycje dnia konta 'System'."""
import json
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
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL DEFAULT '',
    is_active     BOOLEAN NOT NULL DEFAULT 1,
    is_admin      BOOLEAN NOT NULL DEFAULT 0
);
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
    user_id          INTEGER,
    shared           BOOLEAN NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS predictions (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    coupon_id INTEGER REFERENCES coupons(id)
)
"""


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test.db")
    setup = sqlite3.connect(path)
    setup.executescript(_SCHEMA)
    setup.execute(
        "INSERT INTO users (username, password_hash, is_active, is_admin) "
        "VALUES ('System', 'system-no-login', 1, 0)"
    )
    setup.commit()
    setup.close()
    return path


@pytest.fixture
def wired(db_path, monkeypatch):
    """Wire _connect used by coupon_tracker, system_coupons, admin_user to tmp SQLite DB."""
    import footstats.core.coupon_tracker as ct
    import footstats.core.system_coupons as sc
    import footstats.utils.db as dbmod
    from footstats.utils.admin_user import clear_system_user_cache

    conn_factory = lambda: _SQLiteConn(db_path)
    monkeypatch.setattr(ct, "_connect", conn_factory)
    monkeypatch.setattr(ct, "init_coupon_tables", lambda: None)
    monkeypatch.setattr(sc, "_connect", conn_factory)
    monkeypatch.setattr(sc, "init_coupon_tables", lambda: None)
    monkeypatch.setattr(dbmod, "connect", conn_factory)

    clear_system_user_cache()
    yield
    clear_system_user_cache()


def _match(mid, prob_home, odds_home, prob_over=55.0, odds_over=1.8):
    return {
        "id": mid,
        "gosp": f"Dom{mid}",
        "gosc": f"Gosc{mid}",
        "liga": "Test League",
        "data": "2026-06-15",
        "godzina": "18:00",
        "pred_ml": {
            "prob_home_win": prob_home,
            "prob_draw": (1 - prob_home) * 0.4,
            "prob_away_win": (1 - prob_home) * 0.6,
            "prob_over_25": prob_over / 100.0,
            "prob_btts_yes": 0.5,
        },
        "odds": {"home": odds_home, "over_2_5": odds_over},
    }


_PREDICTIONS = [
    _match("m1", 0.70, 1.3),   # → low
    _match("m2", 0.50, 2.0),   # → medium
    _match("m3", 0.20, 4.0),   # → high
]


class TestGenerateSystemCoupons:
    def test_creates_coupon_per_nonempty_tier(self, wired):
        from footstats.core.system_coupons import generate_system_coupons

        ids = generate_system_coupons(_PREDICTIONS, date_str="2026-06-15")
        assert len(ids) == 3

    def test_created_coupons_are_shared_and_owned_by_system(self, wired, db_path):
        from footstats.core.system_coupons import generate_system_coupons

        ids = generate_system_coupons(_PREDICTIONS, date_str="2026-06-15")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        for cid in ids:
            row = conn.execute(
                "SELECT c.shared, u.username, c.kupon_type, c.legs_json, c.match_date_first "
                "FROM coupons c JOIN users u ON u.id = c.user_id WHERE c.id = ?",
                (cid,),
            ).fetchone()
            assert row["shared"] == 1
            assert row["username"] == "System"
            assert row["kupon_type"].startswith("risk_")
            assert row["match_date_first"] == "2026-06-15"
            assert json.loads(row["legs_json"])
        conn.close()

    def test_idempotent_on_rerun(self, wired):
        from footstats.core.system_coupons import generate_system_coupons

        first = generate_system_coupons(_PREDICTIONS, date_str="2026-06-15")
        second = generate_system_coupons(_PREDICTIONS, date_str="2026-06-15")
        assert len(first) == 3
        assert second == []

    def test_returns_empty_when_system_account_missing(self, db_path, monkeypatch):
        import sqlite3 as _sqlite3

        conn = _sqlite3.connect(db_path)
        conn.execute("DELETE FROM users WHERE username = 'System'")
        conn.commit()
        conn.close()

        import footstats.core.coupon_tracker as ct
        import footstats.core.system_coupons as sc
        import footstats.utils.db as dbmod
        from footstats.utils.admin_user import clear_system_user_cache
        from footstats.core.system_coupons import generate_system_coupons

        conn_factory = lambda: _SQLiteConn(db_path)
        monkeypatch.setattr(ct, "_connect", conn_factory)
        monkeypatch.setattr(ct, "init_coupon_tables", lambda: None)
        monkeypatch.setattr(sc, "_connect", conn_factory)
        monkeypatch.setattr(sc, "init_coupon_tables", lambda: None)
        monkeypatch.setattr(dbmod, "connect", conn_factory)
        clear_system_user_cache()

        assert generate_system_coupons(_PREDICTIONS, date_str="2026-06-15") == []
        clear_system_user_cache()

    def test_empty_predictions_returns_empty(self, wired):
        from footstats.core.system_coupons import generate_system_coupons

        assert generate_system_coupons([], date_str="2026-06-15") == []
