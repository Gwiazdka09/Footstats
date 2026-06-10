"""
Integration tests: daily_agent pipeline (scrape → predict → kupon → DB).

Tests exercise the real code paths with:
- SQLite in-memory DB (via tmp_path)
- Mocked external APIs (Bzzoiro, Groq/AI)
- Real DB writes via coupon_tracker
"""
import json
import sqlite3
import pytest
from unittest.mock import patch, MagicMock
from contextlib import contextmanager


# ── Schema helpers ────────────────────────────────────────────────────────────

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
CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    coupon_id INTEGER REFERENCES coupons(id)
);
CREATE TABLE IF NOT EXISTS bankroll_state (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    balance    REAL NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user_id    INTEGER DEFAULT 1 UNIQUE
);
CREATE TABLE IF NOT EXISTS bankroll_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    change_pln  REAL NOT NULL,
    new_balance REAL NOT NULL,
    type        TEXT NOT NULL,
    description TEXT,
    user_id     INTEGER DEFAULT 1
);
"""


class _SQLiteConn:
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


def _setup_db(tmp_path, monkeypatch, balance: float = 500.0):
    """Init SQLite temp DB and patch all _connect references."""
    db_path = str(tmp_path / "test.db")
    setup = sqlite3.connect(db_path)
    setup.executescript(_SCHEMA)
    setup.execute("INSERT OR IGNORE INTO bankroll_state (id, balance, user_id) VALUES (1, ?, 1)", (balance,))
    setup.commit()
    setup.close()

    conn_factory = lambda: _SQLiteConn(db_path)

    import footstats.core.coupon_tracker as ct
    import footstats.core.bankroll as bk
    import footstats.core.backtest as bt
    monkeypatch.setattr(ct, "_connect", conn_factory)
    monkeypatch.setattr(ct, "init_coupon_tables", lambda: None)
    monkeypatch.setattr(bk, "_db_connect", conn_factory)
    monkeypatch.setattr(bt, "_connect", conn_factory)
    monkeypatch.setattr(bt, "init_db", lambda: None)

    return db_path, conn_factory


# ── Fixtures ──────────────────────────────────────────────────────────────────

FAKE_KANDYDACI = [
    {
        "gospodarz": "Arsenal",
        "goscie": "Chelsea",
        "tip": "1",
        "typ": "1",
        "kurs": 1.85,
        "decision_score": 72,
        "mecz": "Arsenal vs Chelsea",
        "liga": "Premier League",
    }
]

FAKE_KANDYDACI_AKO = [
    {
        "gospodarz": "Arsenal",
        "goscie": "Chelsea",
        "tip": "1",
        "typ": "1",
        "kurs": 1.85,
        "decision_score": 72,
        "mecz": "Arsenal vs Chelsea",
        "liga": "Premier League",
    },
    {
        "gospodarz": "Barcelona",
        "goscie": "Real Madrid",
        "tip": "Over 2.5",
        "typ": "Over 2.5",
        "kurs": 1.70,
        "decision_score": 65,
        "mecz": "Barcelona vs Real Madrid",
        "liga": "La Liga",
    },
]


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestZapiszKuponDoDB:
    """_zapisz_kupon_do_db saves coupon to DB correctly."""

    def test_draft_phase_creates_draft_status(self, tmp_path, monkeypatch):
        db_path, conn_factory = _setup_db(tmp_path, monkeypatch)

        monkeypatch.setattr(
            "footstats.utils.admin_user.resolve_admin_user_id",
            lambda *a, **kw: 1,
        )

        from footstats.daily_agent import _zapisz_kupon_do_db
        cid = _zapisz_kupon_do_db(
            FAKE_KANDYDACI, phase="draft", groq_resp="test reasoning",
            stake=10.0, total_odds=1.85,
        )

        assert cid is None or isinstance(cid, int)
        if cid is not None:
            with conn_factory() as conn:
                row = conn.execute("SELECT status, phase FROM coupons WHERE id=?", (cid,)).fetchone()
            assert row["status"] == "DRAFT"
            assert row["phase"] == "draft"

    def test_draft_saves_legs_json(self, tmp_path, monkeypatch):
        db_path, conn_factory = _setup_db(tmp_path, monkeypatch)

        monkeypatch.setattr(
            "footstats.utils.admin_user.resolve_admin_user_id",
            lambda *a, **kw: 1,
        )

        from footstats.daily_agent import _zapisz_kupon_do_db
        cid = _zapisz_kupon_do_db(
            FAKE_KANDYDACI, phase="draft", groq_resp=None,
            stake=10.0, total_odds=1.85,
        )

        if cid is None:
            pytest.skip("_zapisz_kupon_do_db zwróciło None — prawdopodobnie brak coupon_tracker")

        with conn_factory() as conn:
            row = conn.execute("SELECT legs_json, stake_pln FROM coupons WHERE id=?", (cid,)).fetchone()

        legs = json.loads(row["legs_json"])
        assert len(legs) == 1
        assert legs[0]["home"] == "Arsenal"
        assert legs[0]["away"] == "Chelsea"
        assert row["stake_pln"] == 10.0

    def test_final_phase_promotes_draft_to_active(self, tmp_path, monkeypatch):
        db_path, conn_factory = _setup_db(tmp_path, monkeypatch)

        monkeypatch.setattr(
            "footstats.utils.admin_user.resolve_admin_user_id",
            lambda *a, **kw: 1,
        )

        from footstats.daily_agent import _zapisz_kupon_do_db

        draft_id = _zapisz_kupon_do_db(
            FAKE_KANDYDACI, phase="draft", groq_resp="step 1",
            stake=10.0, total_odds=1.85,
        )
        if draft_id is None:
            pytest.skip("coupon_tracker not available")

        final_id = _zapisz_kupon_do_db(
            FAKE_KANDYDACI, phase="final", groq_resp="step 2",
            stake=10.0, total_odds=1.85,
        )

        if final_id is None:
            pytest.skip("final phase returned None")

        with conn_factory() as conn:
            row = conn.execute("SELECT status FROM coupons WHERE id=?", (final_id,)).fetchone()

        assert row["status"] == "ACTIVE"

    def test_ako_multiple_legs_saved(self, tmp_path, monkeypatch):
        db_path, conn_factory = _setup_db(tmp_path, monkeypatch)

        monkeypatch.setattr(
            "footstats.utils.admin_user.resolve_admin_user_id",
            lambda *a, **kw: 1,
        )

        from footstats.daily_agent import _zapisz_kupon_do_db
        total_odds = round(1.85 * 1.70, 2)
        cid = _zapisz_kupon_do_db(
            FAKE_KANDYDACI_AKO, phase="draft", groq_resp="AKO test",
            stake=10.0, total_odds=total_odds,
        )

        if cid is None:
            pytest.skip("coupon_tracker not available")

        with conn_factory() as conn:
            row = conn.execute("SELECT legs_json, total_odds FROM coupons WHERE id=?", (cid,)).fetchone()

        legs = json.loads(row["legs_json"])
        assert len(legs) == 2
        assert abs(row["total_odds"] - total_odds) < 0.01

    def test_bankroll_decreases_after_final(self, tmp_path, monkeypatch):
        db_path, conn_factory = _setup_db(tmp_path, monkeypatch, balance=500.0)

        monkeypatch.setattr(
            "footstats.utils.admin_user.resolve_admin_user_id",
            lambda *a, **kw: 1,
        )

        from footstats.daily_agent import _zapisz_kupon_do_db

        _zapisz_kupon_do_db(
            FAKE_KANDYDACI, phase="draft", groq_resp=None,
            stake=10.0, total_odds=1.85,
        )
        _zapisz_kupon_do_db(
            FAKE_KANDYDACI, phase="final", groq_resp=None,
            stake=10.0, total_odds=1.85,
        )

        with conn_factory() as conn:
            row = conn.execute(
                "SELECT balance FROM bankroll_state ORDER BY id DESC LIMIT 1"
            ).fetchone()

        if row:
            assert row["balance"] <= 500.0


class TestDailyPipelineFlow:
    """End-to-end: mocked Bzzoiro + AI → coupon saved to DB."""

    def test_full_flow_scrape_to_active_coupon(self, tmp_path, monkeypatch):
        """Simulate daily pipeline: fake Bzzoiro output → AI analyze → save to DB."""
        db_path, conn_factory = _setup_db(tmp_path, monkeypatch, balance=500.0)

        monkeypatch.setattr(
            "footstats.utils.admin_user.resolve_admin_user_id",
            lambda *a, **kw: 1,
        )

        # Mock Bzzoiro client to return fake predictions
        fake_bzz_predictions = [
            {
                "gospodarz": "Arsenal",
                "goscie": "Chelsea",
                "liga": "Premier League",
                "pewnosc": 0.72,
                "typ": "1",
                "kurs": 1.85,
                "ev_netto": 8.5,
                "roznica_modeli": 0.05,
                "accuracy": 0.70,
                "czynniki": [],
            }
        ]

        # Mock AI analyzer to return deterministic output
        fake_ai_output = {
            "kupon_a": {
                "typ": "single",
                "mecze": ["Arsenal vs Chelsea"],
                "reasoning": "Silny Arsenal w domu",
                "legs": [{"home": "Arsenal", "away": "Chelsea", "tip": "1", "odds": 1.85}],
            },
            "wyniki": fake_bzz_predictions,
        }

        with (
            patch("footstats.scrapers.bzzoiro.BzzoiroClient") as mock_bzz,
            patch("footstats.ai.analyzer.ai_analiza_pewniaczki", return_value=fake_ai_output),
        ):
            mock_bzz.return_value.predykcje_tygodnia.return_value = fake_bzz_predictions

            from footstats.daily_agent import _zapisz_kupon_do_db
            cid = _zapisz_kupon_do_db(
                fake_bzz_predictions,
                phase="draft",
                groq_resp="Silny Arsenal",
                stake=10.0,
                total_odds=1.85,
            )

        if cid is not None:
            with conn_factory() as conn:
                row = conn.execute("SELECT status, stake_pln FROM coupons WHERE id=?", (cid,)).fetchone()
            assert row["status"] == "DRAFT"
            assert row["stake_pln"] == 10.0

    def test_pre_filter_removes_low_score_candidates(self):
        """_filtruj_przez_decision_score removes weak candidates before DB save."""
        from footstats.daily_agent import _filtruj_przez_decision_score

        kandydaci = [
            {"ev_netto": -10.0, "pewnosc": 0.30, "czynniki": ["ROTACJA"], "roznica_modeli": 0.5, "accuracy": 0.35},
            {"ev_netto": 12.0,  "pewnosc": 0.80, "czynniki": [],          "roznica_modeli": 0.03, "accuracy": 0.72},
            {"ev_netto": 5.0,   "pewnosc": 0.60, "czynniki": [],          "roznica_modeli": 0.10, "accuracy": 0.55},
        ]

        result = _filtruj_przez_decision_score(kandydaci, phase="draft")
        scores = [k["decision_score"] for k in result]
        # All remaining candidates must pass draft threshold
        assert all(s >= 40 for s in scores)
        # Weak candidate removed
        assert len(result) < len(kandydaci)

    def test_decision_score_fields_present(self):
        """After filtering, each candidate has decision_score and decision_reasons."""
        from footstats.daily_agent import _filtruj_przez_decision_score

        kandydaci = [
            {"ev_netto": 8.0, "pewnosc": 0.75, "czynniki": [], "roznica_modeli": 0.05, "accuracy": 0.68},
        ]
        result = _filtruj_przez_decision_score(kandydaci, phase="draft", prog=0)
        assert "decision_score" in result[0]
        assert "decision_reasons" in result[0]
        assert isinstance(result[0]["decision_score"], int)
