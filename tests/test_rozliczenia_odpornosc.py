"""tests/test_rozliczenia_odpornosc.py — odporność rozliczeń kuponów (audyt 5.11).

Trzy znaleziska w `coupon_settlement.py`:

1. Błąd jednego kuponu (np. `total_odds=None` → TypeError przy `stake * total_odds`)
   przerywał cały przebieg `settle_active_coupons`; kupony pozostałych userów
   zostawały nierozliczone.
2. Źródło 4 w `_find_leg_result` dopasowywało mecz w `predictions` JEDNĄ stroną
   (`team_home LIKE OR team_away LIKE`), więc krótka nazwa „Inter" łapała „Inter Miami".
3. `settle_manual_coupons` zapisywał status bez wyników nóg — GUI pokazywało
   „0✓ / 0✗ / N⏳" na kuponie WON/LOST.

Izolacja: plikowa SQLite, `backtest._connect`/`coupon_tracker._connect` podmienione,
zero sieci i zero Telegrama (tests-no-prod.md).
"""
import json
import sqlite3
from datetime import date, timedelta

import pytest

import footstats.core.backtest as backtest
import footstats.core.coupon_settlement as settlement
import footstats.core.coupon_tracker as coupon_tracker
import footstats.core.match_linker as match_linker
from footstats.core.match_linker import LinkResult


class _SQLiteConn:
    """Adapter sqlite3 zgodny z interfejsem footstats.utils.db._Conn."""

    def __init__(self, path: str) -> None:
        self._raw = sqlite3.connect(path)
        self._raw.row_factory = sqlite3.Row

    def execute(self, sql, params=()):
        return self._raw.execute(sql, params)

    def executescript(self, script: str) -> None:
        self._raw.executescript(script)

    def __enter__(self) -> "_SQLiteConn":
        return self

    def __exit__(self, exc_type, *_) -> bool:
        if exc_type:
            self._raw.rollback()
        else:
            self._raw.commit()
        self._raw.close()
        return False


_SCHEMA = """
CREATE TABLE coupons (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    phase            TEXT NOT NULL DEFAULT '',
    status           TEXT NOT NULL DEFAULT 'DRAFT',
    kupon_type       TEXT,
    legs_json        TEXT NOT NULL DEFAULT '[]',
    total_odds       REAL,
    stake_pln        REAL,
    payout_pln       REAL,
    roi_pct          REAL,
    match_date_first TEXT,
    bookmaker        TEXT,
    user_id          INTEGER DEFAULT 1,
    settled_at       TIMESTAMP
);
CREATE TABLE bankroll_state (user_id INTEGER PRIMARY KEY, balance REAL NOT NULL, updated_at TEXT);
CREATE TABLE bankroll_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, change_pln REAL,
    new_balance REAL, type TEXT, description TEXT, user_id INTEGER
);
CREATE TABLE predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, match_date TEXT, team_home TEXT,
    team_away TEXT, actual_result TEXT
);
INSERT INTO bankroll_state (user_id, balance) VALUES (1, 100.0);
"""

_WCZORAJ = (date.today() - timedelta(days=1)).isoformat()


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = str(tmp_path / "test.db")
    setup = sqlite3.connect(path)
    setup.executescript(_SCHEMA)
    setup.commit()
    setup.close()

    monkeypatch.setattr(backtest, "_connect", lambda: _SQLiteConn(path))
    monkeypatch.setattr(backtest, "init_db", lambda: None)
    monkeypatch.setattr(coupon_tracker, "_connect", lambda: _SQLiteConn(path))
    monkeypatch.setattr(coupon_tracker, "init_coupon_tables", lambda: None)
    return path


def _kupon(db_path, legs, kupon_type=None, odds=2.0, stake=10.0, mdate=_WCZORAJ) -> int:
    conn = sqlite3.connect(db_path)
    cur = conn.execute(
        "INSERT INTO coupons (kupon_type, status, legs_json, total_odds, stake_pln,"
        " match_date_first, user_id) VALUES (?, 'ACTIVE', ?, ?, ?, ?, 1)",
        (kupon_type, json.dumps(legs), odds, stake, mdate),
    )
    conn.commit()
    cid = cur.lastrowid
    conn.close()
    return cid


def _wiersz(db_path, cid) -> sqlite3.Row:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM coupons WHERE id=?", (cid,)).fetchone()
    conn.close()
    return row


# ── 1. błąd jednego kuponu nie zatrzymuje przebiegu ─────────────────────────

def test_kupon_z_total_odds_none_nie_zatrzymuje_przebiegu(db, monkeypatch, caplog):
    import logging

    monkeypatch.setattr(settlement, "_find_leg_result", lambda *a, **k: "1-0")
    zepsuty = _kupon(db, [{"home": "Legia", "away": "Lech", "tip": "1"}], odds=None)
    dobry = _kupon(db, [{"home": "Cracovia", "away": "Pogon", "tip": "1"}])

    with caplog.at_level(logging.ERROR):
        stats = settlement.settle_active_coupons(dry_run=False, verbose=False)

    assert _wiersz(db, dobry)["status"] == "WON", "drugi kupon nie został rozliczony"
    assert _wiersz(db, zepsuty)["status"] == "ACTIVE"
    assert stats["settled"] == 1
    assert stats["errors"] == 1
    msg = " ".join(r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR)
    assert str(zepsuty) in msg and "TypeError" in msg


def test_uszkodzony_legs_json_nie_zatrzymuje_przebiegu(db, monkeypatch):
    monkeypatch.setattr(settlement, "_find_leg_result", lambda *a, **k: "1-0")
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO coupons (status, legs_json, total_odds, stake_pln, match_date_first,"
        " user_id) VALUES ('ACTIVE', '{nie-json', 2.0, 10.0, ?, 1)", (_WCZORAJ,))
    conn.commit()
    conn.close()
    dobry = _kupon(db, [{"home": "Legia", "away": "Lech", "tip": "1"}])

    stats = settlement.settle_active_coupons(dry_run=False, verbose=False)

    assert _wiersz(db, dobry)["status"] == "WON"
    assert stats["errors"] == 1


# ── 2. źródło 4: obie strony meczu ──────────────────────────────────────────

@pytest.fixture
def tylko_predictions(db, monkeypatch):
    """Wyłącza wszystkie źródła poza `predictions` (źródło 4)."""
    import footstats.scrapers.flashscore_results as fs
    import footstats.scrapers.results_updater as ru
    import footstats.scrapers.sources.aggregator as agg

    monkeypatch.setattr(settlement, "_get_matches_fdb", lambda key, d: [])
    monkeypatch.setattr(settlement, "_get_matches_espn", lambda d: [])
    monkeypatch.setattr(ru, "_znajdz_wynik", lambda *a, **k: None)
    monkeypatch.setattr(fs, "get_match_result", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(agg, "consensus_result", lambda *a, **k: None, raising=False)
    return db


def _pred(db_path, home, away, wynik, mdate="2026-08-02") -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO predictions (match_date, team_home, team_away, actual_result)"
        " VALUES (?, ?, ?, ?)", (mdate, home, away, wynik))
    conn.commit()
    conn.close()


def _szukaj(home, away, mdate="2026-08-02"):
    return settlement._find_leg_result(
        home, away, mdate, fixtures_cache={}, fdb_cache={}, api_key="", fdb_key="")


def test_zrodlo4_krotka_nazwa_nie_lapie_innego_klubu(tylko_predictions):
    _pred(tylko_predictions, "Inter Miami", "Orlando City", "3-0")

    assert _szukaj("Inter", "Chicago Fire") is None


def test_zrodlo4_poprawna_para_dostaje_wynik(tylko_predictions):
    _pred(tylko_predictions, "Inter Miami", "Orlando City", "3-0")

    assert _szukaj("Inter Miami", "Orlando City") == "3-0"


def test_zrodlo4_pasuje_tez_po_jednej_stronie_gdy_druga_rozni_sie(tylko_predictions):
    """Dawniej wystarczyło trafić gospodarza LUB gościa."""
    _pred(tylko_predictions, "Legia Warszawa", "Lech Poznan", "2-1")

    assert _szukaj("Cracovia", "Lech Poznan") is None


def test_zrodlo4_kilku_kandydatow_z_roznymi_wynikami_to_brak_wyniku(tylko_predictions):
    """Fail-closed: dwa pasujące mecze o różnym wyniku → nie zgadujemy."""
    _pred(tylko_predictions, "Legia Warszawa", "Lech Poznan", "2-1")
    _pred(tylko_predictions, "Legia", "Lech", "0-0")

    assert _szukaj("Legia", "Lech") is None


def test_zrodlo4_duplikaty_z_tym_samym_wynikiem_sa_ok(tylko_predictions):
    _pred(tylko_predictions, "Legia Warszawa", "Lech Poznan", "2-1")
    _pred(tylko_predictions, "Legia", "Lech", "2-1")

    assert _szukaj("Legia", "Lech") == "2-1"


def test_zrodlo4_pomija_wiersze_bez_wyniku(tylko_predictions):
    _pred(tylko_predictions, "Legia", "Lech", None)
    _pred(tylko_predictions, "Legia", "Lech", "")

    assert _szukaj("Legia", "Lech") is None


# ── 3. kupon manual zapisuje wyniki nóg ─────────────────────────────────────

def _link_wg_pary(monkeypatch, wyniki: dict) -> None:
    def _link(home, away, *_a, **_k):
        wynik = wyniki.get((home, away))
        if wynik is None:
            return LinkResult(False, "none", None, "brak")
        return LinkResult(True, "exact", {"actual_result": wynik}, "ok")

    monkeypatch.setattr(match_linker, "link_leg", _link)
    monkeypatch.setattr(match_linker, "wynik_z_model_log", lambda *a, **k: None)
    monkeypatch.setattr(settlement, "_find_leg_result",
                        lambda *a, **k: pytest.fail("zero zewnętrznych API"))


def test_manual_won_zapisuje_wyniki_nog(db, monkeypatch):
    _link_wg_pary(monkeypatch, {("Legia", "Lech"): "2-0", ("Wisla", "Gornik"): "1-0"})
    cid = _kupon(db, [
        {"home": "Legia", "away": "Lech", "tip": "1"},
        {"home": "Wisla", "away": "Gornik", "tip": "1"},
    ], kupon_type="manual")

    stats = settlement.settle_manual_coupons(dry_run=False, verbose=False)

    row = _wiersz(db, cid)
    assert row["status"] == "WON" and stats["settled"] == 1
    legs = json.loads(row["legs_json"])
    assert [lg["result"] for lg in legs] == ["2-0", "1-0"]
    assert [lg["leg_won"] for lg in legs] == [True, True]
    assert legs[0]["home"] == "Legia"  # pozostałe pola nóg nietknięte


def test_manual_lost_zapisuje_wyniki_nog_takze_niedokonczonych(db, monkeypatch):
    """Przegrana noga rozlicza kupon od razu; reszta zostaje bez wyniku (None)."""
    _link_wg_pary(monkeypatch, {("Legia", "Lech"): "0-2"})
    cid = _kupon(db, [
        {"home": "Legia", "away": "Lech", "tip": "1"},
        {"home": "Wisla", "away": "Gornik", "tip": "1"},
    ], kupon_type="manual")

    settlement.settle_manual_coupons(dry_run=False, verbose=False)

    row = _wiersz(db, cid)
    assert row["status"] == "LOST"
    legs = json.loads(row["legs_json"])
    assert legs[0]["result"] == "0-2" and legs[0]["leg_won"] is False
    assert legs[1]["result"] is None and legs[1]["leg_won"] is None


def test_manual_cas_nie_nadpisuje_nog_rozliczonego_recznie(db, monkeypatch):
    """Kupon zamknięty równolegle (nie ACTIVE) zachowuje swój legs_json."""
    _link_wg_pary(monkeypatch, {("Legia", "Lech"): "2-0"})
    cid = _kupon(db, [{"home": "Legia", "away": "Lech", "tip": "1"}], kupon_type="manual")
    oryginal = _wiersz(db, cid)["legs_json"]

    def _zamknij_przed_cas(coupon_id, status, **kw):
        conn = sqlite3.connect(db)
        conn.execute("UPDATE coupons SET status='VOID' WHERE id=?", (coupon_id,))
        conn.commit()
        conn.close()
        return orig(coupon_id, status, **kw)

    orig = coupon_tracker.update_coupon_status
    monkeypatch.setattr(coupon_tracker, "update_coupon_status", _zamknij_przed_cas)

    stats = settlement.settle_manual_coupons(dry_run=False, verbose=False)

    row = _wiersz(db, cid)
    assert row["status"] == "VOID" and row["legs_json"] == oryginal
    assert stats["settled"] == 0
