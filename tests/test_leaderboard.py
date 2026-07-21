"""tests/test_leaderboard.py — dziennik kuponów (J5): leaderboard v2 (ROI/profit/sort/days).

Izolacja jak tests/test_coupon_manual.py: własna plikowa SQLite DB, `_connect`
w routes.coupons podmienione na adapter zgodny z footstats.utils.db._Conn.
Zero prod Neon/Supabase. Dane wstrzykiwane bezpośrednio przez surowe SQL (pełna
kontrola nad shared/status/stake/payout/created_at), endpoint wołany bezpośrednio
(bez FastAPI TestClient).
"""
import sqlite3

import pytest
from fastapi import HTTPException

from footstats.api.routes.coupons import get_leaderboard
from footstats.core.response_cache import clear_response_cache

# @cached_response opakowuje wynik w JSONResponse (nawet przy MISS) — wołamy
# surową funkcję przez __wrapped__ (functools.wraps), żeby testować logikę
# rankingu na zwykłej liście dictów, nie na obiekcie Response. Samo cachowanie
# (TTL/vary_by) ma osobne testy w test_response_cache.py.
_leaderboard = get_leaderboard.__wrapped__


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
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL
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
    user_id          INTEGER DEFAULT 1,
    shared           BOOLEAN NOT NULL DEFAULT 0
)
"""


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    """Każdy test dostaje własną plikową SQLite DB; routes._connect mockowany."""
    db_path = str(tmp_path / "test.db")

    setup = sqlite3.connect(db_path)
    setup.executescript(_SCHEMA)
    setup.commit()
    setup.close()

    import footstats.api.routes.coupons as routes

    monkeypatch.setattr(routes, "_connect", lambda: _SQLiteConn(db_path))
    # Cache globalny (@cached_response) trzeba czyścić między testami — inaczej
    # wynik jednego testu wycieka do kolejnego przez wspólny in-memory słownik.
    clear_response_cache()
    yield db_path
    clear_response_cache()


def _insert_user(db_path: str, username: str) -> int:
    conn = sqlite3.connect(db_path)
    cur = conn.execute("INSERT INTO users (username, password_hash) VALUES (?, 'x')", (username,))
    conn.commit()
    uid = cur.lastrowid
    conn.close()
    return uid


def _insert_coupon(
    db_path: str,
    user_id: int,
    status: str,
    stake: float,
    payout: float,
    shared: bool = True,
    created_at: str | None = None,
) -> int:
    conn = sqlite3.connect(db_path)
    if created_at is None:
        cur = conn.execute(
            "INSERT INTO coupons (status, stake_pln, payout_pln, user_id, shared)"
            " VALUES (?, ?, ?, ?, ?)",
            (status, stake, payout, user_id, shared),
        )
    else:
        cur = conn.execute(
            "INSERT INTO coupons (status, stake_pln, payout_pln, user_id, shared, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (status, stake, payout, user_id, shared, created_at),
        )
    conn.commit()
    cid = cur.lastrowid
    conn.close()
    return cid


def _typer_wysoki_winrate_niski_roi(db_path: str) -> int:
    """3 kupony niskokursowe: 2 WON @1.1, 1 LOST — win_rate wysoki, ROI ujemny."""
    uid = _insert_user(db_path, "highwinrate")
    _insert_coupon(db_path, uid, "WON", 10.0, 11.0)
    _insert_coupon(db_path, uid, "WON", 10.0, 11.0)
    _insert_coupon(db_path, uid, "LOST", 10.0, 0.0)
    return uid


def _typer_niski_winrate_wysoki_roi(db_path: str) -> int:
    """3 kupony: 1 WON @10.0, 2 LOST — win_rate niski, ROI bardzo wysoki."""
    uid = _insert_user(db_path, "highroi")
    _insert_coupon(db_path, uid, "WON", 10.0, 100.0)
    _insert_coupon(db_path, uid, "LOST", 10.0, 0.0)
    _insert_coupon(db_path, uid, "LOST", 10.0, 0.0)
    return uid


def test_ranking_po_roi_rozny_niz_po_win_rate(tmp_db):
    _typer_wysoki_winrate_niski_roi(tmp_db)
    _typer_niski_winrate_wysoki_roi(tmp_db)

    by_winrate = _leaderboard(min_coupons=3, sort="win_rate")
    by_roi = _leaderboard(min_coupons=3, sort="roi")

    assert by_winrate[0]["username"] == "highwinrate"
    assert by_winrate[1]["username"] == "highroi"
    # Ranking się odwraca przy sort=roi — mniejszy win_rate, ale dużo wyższy ROI.
    assert by_roi[0]["username"] == "highroi"
    assert by_roi[1]["username"] == "highwinrate"


def test_profit_i_roi_liczone_poprawnie(tmp_db):
    _typer_niski_winrate_wysoki_roi(tmp_db)

    result = _leaderboard(min_coupons=3, sort="roi")
    row = next(r for r in result if r["username"] == "highroi")

    assert row["staked"] == pytest.approx(30.0)
    assert row["payout"] == pytest.approx(100.0)
    assert row["profit_pln"] == pytest.approx(70.0)
    assert row["roi"] == pytest.approx(233.3, abs=0.1)
    assert row["win_rate"] == pytest.approx(33.3, abs=0.1)


def test_roi_zero_gdy_staked_zero_bez_zero_division(tmp_db):
    uid = _insert_user(tmp_db, "bezstawki")
    _insert_coupon(tmp_db, uid, "WON", 0.0, 0.0)
    _insert_coupon(tmp_db, uid, "LOST", 0.0, 0.0)
    _insert_coupon(tmp_db, uid, "LOST", 0.0, 0.0)

    result = _leaderboard(min_coupons=3, sort="roi")
    row = next(r for r in result if r["username"] == "bezstawki")
    assert row["roi"] == 0.0


def test_days_odcina_stare_kupony(tmp_db):
    uid_stary = _insert_user(tmp_db, "staryhistoric")
    _insert_coupon(tmp_db, uid_stary, "WON", 10.0, 20.0, created_at="2020-01-01 00:00:00")

    uid_nowy = _insert_user(tmp_db, "swiezy")
    _insert_coupon(tmp_db, uid_nowy, "WON", 10.0, 20.0)

    # Bez filtra czasu — obaj widoczni (min_coupons=1, bo po 1 kuponie).
    result_all = _leaderboard(min_coupons=1, days=0)
    usernames_all = {r["username"] for r in result_all}
    assert "staryhistoric" in usernames_all
    assert "swiezy" in usernames_all

    # Z filtrem 7 dni — stary kupon wypada z okna, user znika z rankingu.
    result_7d = _leaderboard(min_coupons=1, days=7)
    usernames_7d = {r["username"] for r in result_7d}
    assert "staryhistoric" not in usernames_7d
    assert "swiezy" in usernames_7d


def test_min_coupons_respektowane(tmp_db):
    uid = _insert_user(tmp_db, "malokuponow")
    _insert_coupon(tmp_db, uid, "WON", 10.0, 20.0)
    _insert_coupon(tmp_db, uid, "LOST", 10.0, 0.0)

    # Domyślne min_coupons=3 — user z 2 kuponami nie kwalifikuje się.
    result_default = _leaderboard()
    assert all(r["username"] != "malokuponow" for r in result_default)

    # Obniżony próg — user się kwalifikuje.
    result_low = _leaderboard(min_coupons=2)
    assert any(r["username"] == "malokuponow" for r in result_low)


def test_nieudostepnione_kupony_pominiete(tmp_db):
    uid = _insert_user(tmp_db, "prywatny")
    _insert_coupon(tmp_db, uid, "WON", 10.0, 20.0, shared=False)
    _insert_coupon(tmp_db, uid, "WON", 10.0, 20.0, shared=False)
    _insert_coupon(tmp_db, uid, "LOST", 10.0, 0.0, shared=False)

    result = _leaderboard(min_coupons=1)
    assert all(r["username"] != "prywatny" for r in result)


def test_nieznany_sort_zwraca_400(tmp_db):
    with pytest.raises(HTTPException) as exc:
        _leaderboard(sort="losowy_smiec")
    assert exc.value.status_code == 400
