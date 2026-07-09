"""
Integration tests: evening_agent pipeline (fetch results → settle → feedback → RAG).

Tests exercise real settlement logic with:
- SQLite temp DB pre-seeded with ACTIVE coupons
- Mocked API-Football / FlashScore calls
- Real coupon_settlement.settle_active_coupons() execution
"""
import json
import sqlite3
import pytest
from datetime import datetime
from unittest.mock import patch


# ── Schema ────────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS coupons (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    phase            TEXT NOT NULL DEFAULT 'final',
    status           TEXT NOT NULL DEFAULT 'ACTIVE',
    kupon_type       TEXT NOT NULL DEFAULT 'AKO',
    legs_json        TEXT NOT NULL DEFAULT '[]',
    total_odds       REAL NOT NULL DEFAULT 1.0,
    stake_pln        REAL NOT NULL DEFAULT 10.0,
    payout_pln       REAL,
    roi_pct          REAL,
    groq_reasoning   TEXT,
    decision_score   INTEGER DEFAULT 70,
    match_date_first TEXT,
    user_id          INTEGER DEFAULT 1,
    shared           BOOLEAN NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS predictions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    match_date     TEXT NOT NULL DEFAULT '',
    team_home      TEXT NOT NULL DEFAULT '',
    team_away      TEXT NOT NULL DEFAULT '',
    league         TEXT NOT NULL DEFAULT '',
    ai_tip         TEXT NOT NULL DEFAULT '',
    ai_confidence  INTEGER NOT NULL DEFAULT 0,
    ai_reasoning   TEXT NOT NULL DEFAULT '',
    odds           REAL,
    actual_result  TEXT,
    tip_correct    INTEGER,
    kupon_type     TEXT DEFAULT '',
    kodeks_rules_checked TEXT NOT NULL DEFAULT '[]',
    prompt_version TEXT NOT NULL DEFAULT '',
    factors        TEXT NOT NULL DEFAULT '[]',
    match_stats    TEXT,
    coupon_id      INTEGER REFERENCES coupons(id)
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
CREATE TABLE IF NOT EXISTS ai_feedback (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    match_id   INTEGER,
    content    TEXT NOT NULL DEFAULT '',
    reason_for_failure TEXT
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
    db_path = str(tmp_path / "test.db")
    raw = sqlite3.connect(db_path)
    raw.executescript(_SCHEMA)
    raw.execute(
        "INSERT OR IGNORE INTO bankroll_state (id, balance, user_id) VALUES (1, ?, 1)",
        (balance,),
    )
    raw.commit()
    raw.close()

    conn_factory = lambda: _SQLiteConn(db_path)

    import footstats.core.backtest as bt
    import footstats.core.bankroll as bk
    monkeypatch.setattr(bt, "_connect", conn_factory)
    monkeypatch.setattr(bt, "init_db", lambda: None)
    monkeypatch.setattr(bk, "_db_connect", conn_factory)

    return db_path, conn_factory


def _insert_active_coupon(
    conn_factory,
    legs: list[dict],
    total_odds: float = 1.85,
    stake: float = 10.0,
    match_date: str | None = None,
) -> int:
    mdate = match_date or datetime.now().strftime("%Y-%m-%d")
    with conn_factory() as conn:
        cur = conn.execute(
            """INSERT INTO coupons
               (status, legs_json, total_odds, stake_pln, match_date_first)
               VALUES ('ACTIVE', ?, ?, ?, ?)""",
            (json.dumps(legs), total_odds, stake, mdate),
        )
        return cur.lastrowid


# ── Fake API-Football fixture ─────────────────────────────────────────────────

def _make_api_fixture(home: str, away: str, home_goals: int, away_goals: int) -> dict:
    return {
        "fixture": {"id": 999, "status": {"short": "FT"}},
        "teams": {
            "home": {"name": home},
            "away": {"name": away},
        },
        "goals": {"home": home_goals, "away": away_goals},
    }


# ── Tests: settle_active_coupons ──────────────────────────────────────────────

class TestSettleActiveCoupons:

    def test_single_leg_win_updates_status(self, tmp_path, monkeypatch):
        """Single-leg AKO: correct result → status=WIN, payout>0."""
        db_path, conn_factory = _setup_db(tmp_path, monkeypatch)

        today = datetime.now().strftime("%Y-%m-%d")
        legs = [{"home": "Arsenal", "away": "Chelsea", "tip": "1", "odds": 1.85}]
        cid = _insert_active_coupon(conn_factory, legs, total_odds=1.85, stake=10.0, match_date=today)

        with (
            patch("footstats.core.coupon_settlement._get_fixtures_api", return_value=[
                _make_api_fixture("Arsenal", "Chelsea", 2, 0),
            ]),
            patch("footstats.scrapers.flashscore_results.get_match_result", return_value=None),
            patch("footstats.core.coupon_settlement._send_to_rag_feedback"),
        ):
            from footstats.core.coupon_settlement import settle_active_coupons
            stats = settle_active_coupons(days_back=3, dry_run=False, verbose=False)

        with conn_factory() as conn:
            row = conn.execute("SELECT status, payout_pln FROM coupons WHERE id=?", (cid,)).fetchone()

        assert row["status"] == "WON"
        assert row["payout_pln"] == pytest.approx(10.0 * 1.85, rel=0.01)
        assert stats["settled"] >= 1

    def test_single_leg_lose_updates_status(self, tmp_path, monkeypatch):
        """Single-leg AKO: wrong result → status=LOSE, payout=0."""
        db_path, conn_factory = _setup_db(tmp_path, monkeypatch)

        today = datetime.now().strftime("%Y-%m-%d")
        legs = [{"home": "Arsenal", "away": "Chelsea", "tip": "1", "odds": 1.85}]
        cid = _insert_active_coupon(conn_factory, legs, total_odds=1.85, stake=10.0, match_date=today)

        with (
            patch("footstats.core.coupon_settlement._get_fixtures_api", return_value=[
                _make_api_fixture("Arsenal", "Chelsea", 0, 2),  # Chelsea wins, tip was "1"
            ]),
            patch("footstats.scrapers.flashscore_results.get_match_result", return_value=None),
            patch("footstats.core.coupon_settlement._send_to_rag_feedback"),
        ):
            from footstats.core.coupon_settlement import settle_active_coupons
            settle_active_coupons(days_back=3, dry_run=False, verbose=False)

        with conn_factory() as conn:
            row = conn.execute("SELECT status, payout_pln FROM coupons WHERE id=?", (cid,)).fetchone()

        assert row["status"] == "LOST"
        assert row["payout_pln"] == 0.0

    def test_ako_first_leg_lose_settles_immediately(self, tmp_path, monkeypatch):
        """AKO rule: first losing leg causes immediate LOSE, second leg not evaluated."""
        db_path, conn_factory = _setup_db(tmp_path, monkeypatch)

        today = datetime.now().strftime("%Y-%m-%d")
        legs = [
            {"home": "Arsenal",   "away": "Chelsea",    "tip": "1",         "odds": 1.85},
            {"home": "Barcelona", "away": "Real Madrid", "tip": "Over 2.5", "odds": 1.70},
        ]
        cid = _insert_active_coupon(conn_factory, legs, total_odds=3.14, stake=10.0, match_date=today)

        api_fixtures = [
            _make_api_fixture("Arsenal",   "Chelsea",    0, 2),  # Arsenal loses → tip "1" WRONG
            _make_api_fixture("Barcelona", "Real Madrid", 3, 1),  # would be win, but doesn't matter
        ]

        with (
            patch("footstats.core.coupon_settlement._get_fixtures_api", return_value=api_fixtures),
            patch("footstats.scrapers.flashscore_results.get_match_result", return_value=None),
            patch("footstats.core.coupon_settlement._send_to_rag_feedback") as mock_rag,
        ):
            from footstats.core.coupon_settlement import settle_active_coupons
            settle_active_coupons(days_back=3, dry_run=False, verbose=False)

        with conn_factory() as conn:
            row = conn.execute("SELECT status FROM coupons WHERE id=?", (cid,)).fetchone()

        assert row["status"] == "LOST"
        mock_rag.assert_called_once()

    def test_missing_results_stays_partial(self, tmp_path, monkeypatch):
        """No API result for match → coupon stays ACTIVE (partial)."""
        db_path, conn_factory = _setup_db(tmp_path, monkeypatch)

        today = datetime.now().strftime("%Y-%m-%d")
        legs = [{"home": "Arsenal", "away": "Chelsea", "tip": "1", "odds": 1.85}]
        cid = _insert_active_coupon(conn_factory, legs, total_odds=1.85, stake=10.0, match_date=today)

        # Wszystkie źródła wyników puste → kupon zostaje PARTIAL. Trzeba zamockować
        # KOMPLET źródeł sieciowych (inne testy zwracają matching fixture ze źródła 1 →
        # nie spadają niżej). Bez tego consensus/football-data biją realną sieć → na CI
        # (bez DATABASE_URL) network-guard → RuntimeError.
        with (
            patch("footstats.core.coupon_settlement._get_fixtures_api", return_value=[]),
            patch("footstats.core.coupon_settlement._get_matches_fdb", return_value=[]),
            patch("footstats.scrapers.flashscore_results.get_match_result", return_value=None),
            patch("footstats.scrapers.sources.aggregator.consensus_result", return_value=None),
        ):
            from footstats.core.coupon_settlement import settle_active_coupons
            stats = settle_active_coupons(days_back=3, dry_run=False, verbose=False)

        with conn_factory() as conn:
            row = conn.execute("SELECT status FROM coupons WHERE id=?", (cid,)).fetchone()

        assert row["status"] == "ACTIVE"
        assert stats["partial"] >= 1

    def test_win_updates_bankroll(self, tmp_path, monkeypatch):
        """WIN settlement adds payout to bankroll_state."""
        db_path, conn_factory = _setup_db(tmp_path, monkeypatch, balance=500.0)

        today = datetime.now().strftime("%Y-%m-%d")
        legs = [{"home": "Arsenal", "away": "Chelsea", "tip": "1", "odds": 2.0}]
        cid = _insert_active_coupon(conn_factory, legs, total_odds=2.0, stake=10.0, match_date=today)

        with (
            patch("footstats.core.coupon_settlement._get_fixtures_api", return_value=[
                _make_api_fixture("Arsenal", "Chelsea", 2, 1),
            ]),
            patch("footstats.scrapers.flashscore_results.get_match_result", return_value=None),
            patch("footstats.core.coupon_settlement._send_to_rag_feedback"),
        ):
            from footstats.core.coupon_settlement import settle_active_coupons
            settle_active_coupons(days_back=3, dry_run=False, verbose=False)

        with conn_factory() as conn:
            row = conn.execute(
                "SELECT balance FROM bankroll_state ORDER BY id DESC LIMIT 1"
            ).fetchone()

        assert row["balance"] == pytest.approx(520.0, rel=0.01)  # 500 + 10*2.0

    def test_dry_run_does_not_modify_db(self, tmp_path, monkeypatch):
        """dry_run=True: coupon status unchanged after settlement run."""
        db_path, conn_factory = _setup_db(tmp_path, monkeypatch)

        today = datetime.now().strftime("%Y-%m-%d")
        legs = [{"home": "Arsenal", "away": "Chelsea", "tip": "1", "odds": 1.85}]
        cid = _insert_active_coupon(conn_factory, legs, total_odds=1.85, stake=10.0, match_date=today)

        with (
            patch("footstats.core.coupon_settlement._get_fixtures_api", return_value=[
                _make_api_fixture("Arsenal", "Chelsea", 3, 0),
            ]),
            patch("footstats.scrapers.flashscore_results.get_match_result", return_value=None),
        ):
            from footstats.core.coupon_settlement import settle_active_coupons
            stats = settle_active_coupons(days_back=3, dry_run=True, verbose=False)

        with conn_factory() as conn:
            row = conn.execute("SELECT status FROM coupons WHERE id=?", (cid,)).fetchone()

        assert row["status"] == "ACTIVE"
        assert stats["settled"] >= 1  # dry_run counts as settled

    def test_rag_feedback_called_on_lose(self, tmp_path, monkeypatch):
        """LOSE coupon triggers _send_to_rag_feedback for learning."""
        db_path, conn_factory = _setup_db(tmp_path, monkeypatch)

        today = datetime.now().strftime("%Y-%m-%d")
        legs = [{"home": "Arsenal", "away": "Chelsea", "tip": "1", "odds": 1.85}]
        _insert_active_coupon(conn_factory, legs, total_odds=1.85, stake=10.0, match_date=today)

        with (
            patch("footstats.core.coupon_settlement._get_fixtures_api", return_value=[
                _make_api_fixture("Arsenal", "Chelsea", 0, 1),
            ]),
            patch("footstats.scrapers.flashscore_results.get_match_result", return_value=None),
            patch("footstats.core.coupon_settlement._send_to_rag_feedback") as mock_rag,
        ):
            from footstats.core.coupon_settlement import settle_active_coupons
            settle_active_coupons(days_back=3, dry_run=False, verbose=False)

        mock_rag.assert_called_once()
        call_args = mock_rag.call_args
        assert "PRZEGRANY" in call_args.kwargs.get("reason", call_args.args[3] if len(call_args.args) > 3 else "")


# ── Tests: run_evening_agent helpers ─────────────────────────────────────────

class TestEveningAgentHelpers:

    def test_wynik_z_fixture_parses_ft_result(self):
        from footstats.evening_agent import _wynik_z_fixture
        fixture = {
            "fixture": {"status": {"short": "FT"}},
            "teams": {"home": {"name": "Arsenal"}, "away": {"name": "Chelsea"}},
            "goals": {"home": 2, "away": 1},
        }
        result = _wynik_z_fixture(fixture)
        assert result == ("Arsenal", "Chelsea", "2-1")

    def test_wynik_z_fixture_ignores_live_match(self):
        from footstats.evening_agent import _wynik_z_fixture
        fixture = {
            "fixture": {"status": {"short": "1H"}},
            "teams": {"home": {"name": "A"}, "away": {"name": "B"}},
            "goals": {"home": 0, "away": 0},
        }
        assert _wynik_z_fixture(fixture) is None

    def test_find_result_fuzzy_match(self):
        from footstats.evening_agent import _find_result
        fixtures = [
            {
                "fixture": {"status": {"short": "FT"}},
                "teams": {"home": {"name": "Arsenal FC"}, "away": {"name": "Chelsea FC"}},
                "goals": {"home": 3, "away": 1},
            }
        ]
        result = _find_result("Arsenal", "Chelsea", fixtures)
        assert result == "3-1"

    def test_find_result_returns_none_no_match(self):
        from footstats.evening_agent import _find_result
        result = _find_result("Arsenal", "Chelsea", [])
        assert result is None

    def test_status_kuponu_all_win(self):
        from footstats.evening_agent import _status_kuponu
        assert _status_kuponu(["WIN", "WIN", "WIN"]) == "WON"

    def test_status_kuponu_any_loss(self):
        from footstats.evening_agent import _status_kuponu
        assert _status_kuponu(["WIN", "LOSS", "WIN"]) == "LOST"

    def test_status_kuponu_pending(self):
        from footstats.evening_agent import _status_kuponu
        from footstats.core.coupon_tracker import STATUS_ACTIVE
        assert _status_kuponu(["WIN", "PENDING"]) == STATUS_ACTIVE

    def test_status_kuponu_empty(self):
        from footstats.evening_agent import _status_kuponu
        assert _status_kuponu([]) == "VOID"


class TestRunEveningAgentIntegration:

    def test_run_evening_agent_settles_active_coupon(self, tmp_path, monkeypatch):
        """run_evening_agent with mocked API settles an ACTIVE coupon."""
        monkeypatch.setenv("APISPORTS_KEY", "fake-key")

        fake_legs = [{"gospodarz": "Arsenal", "goscie": "Chelsea", "typ": "1"}]
        fake_coupon = {
            "id": 1,
            "stake_pln": 10.0,
            "total_odds": 1.85,
            "user_id": 7,
            "legs": fake_legs,
        }

        api_fixtures = [
            {
                "fixture": {"id": 111, "status": {"short": "FT"}},
                "teams": {"home": {"name": "Arsenal"}, "away": {"name": "Chelsea"}},
                "goals": {"home": 2, "away": 0},
            }
        ]

        fake_leg_db = [
            {
                "gospodarz": "Arsenal",
                "goscie": "Chelsea",
                "typ": "1",
                "home": "Arsenal",
                "away": "Chelsea",
                "ai_tip": "1",
                "prediction_id": None,
            }
        ]

        with (
            patch("footstats.evening_agent._fetch_results_today", return_value=api_fixtures),
            patch("footstats.evening_agent.get_active_coupons", return_value=[fake_coupon]),
            patch("footstats.evening_agent.get_coupon_legs", return_value=fake_leg_db),
            patch("footstats.evening_agent.update_coupon_status") as mock_update,
            patch("footstats.evening_agent.credit_win") as mock_win,
            patch("footstats.evening_agent.init_coupon_tables"),
            patch("footstats.evening_agent.init_db"),
            patch("footstats.evening_agent._save_coupon_legs"),
            patch("footstats.evening_agent._send_telegram_summary"),
            patch("footstats.utils.telegram_notify.check_and_alert_agent_down"),
        ):
            from footstats.evening_agent import run_evening_agent
            summary = run_evening_agent("2026-06-05")

        assert summary["checked"] == 1
        mock_update.assert_called_once()
        call_args = mock_update.call_args
        new_status = call_args.args[1] if len(call_args.args) > 1 else call_args.kwargs.get("new_status", "WON")
        assert new_status == "WON"
        mock_win.assert_called_once()
        # Wygrana BRUTTO (stake*odds, bez ×0.88) do WŁAŚCICIELA (user_id=7)
        assert mock_win.call_args.args[0] == pytest.approx(18.5)  # 10 * 1.85
        assert mock_win.call_args.args[1] == 7

    def test_run_evening_agent_cas_przegrany_bez_kredytu(self, tmp_path, monkeypatch):
        """D3: gdy CAS w update_coupon_status zwraca False (kupon rozliczony
        równolegle przez settle_active_coupons), credit_win NIE może być wywołany
        — inaczej podwójny kredyt bankrollu."""
        monkeypatch.setenv("APISPORTS_KEY", "fake-key")

        fake_coupon = {
            "id": 1, "stake_pln": 10.0, "total_odds": 1.85, "user_id": 7,
            "legs": [{"gospodarz": "Arsenal", "goscie": "Chelsea", "typ": "1"}],
        }
        api_fixtures = [
            {
                "fixture": {"id": 111, "status": {"short": "FT"}},
                "teams": {"home": {"name": "Arsenal"}, "away": {"name": "Chelsea"}},
                "goals": {"home": 2, "away": 0},
            }
        ]
        fake_leg_db = [
            {"gospodarz": "Arsenal", "goscie": "Chelsea", "typ": "1",
             "home": "Arsenal", "away": "Chelsea", "ai_tip": "1", "prediction_id": None}
        ]

        with (
            patch("footstats.evening_agent._fetch_results_today", return_value=api_fixtures),
            patch("footstats.evening_agent.get_active_coupons", return_value=[fake_coupon]),
            patch("footstats.evening_agent.get_coupon_legs", return_value=fake_leg_db),
            patch("footstats.evening_agent.update_coupon_status", return_value=False) as mock_update,
            patch("footstats.evening_agent.credit_win") as mock_win,
            patch("footstats.evening_agent.init_coupon_tables"),
            patch("footstats.evening_agent.init_db"),
            patch("footstats.evening_agent._save_coupon_legs"),
            patch("footstats.evening_agent._send_telegram_summary"),
            patch("footstats.utils.telegram_notify.check_and_alert_agent_down"),
        ):
            from footstats.evening_agent import run_evening_agent
            run_evening_agent("2026-06-05")

        mock_update.assert_called_once()
        mock_win.assert_not_called()   # przegrany CAS = zero kredytu

    def test_run_evening_agent_lose_no_bankroll_update(self, tmp_path, monkeypatch):
        """LOSE coupon does not trigger process_win."""
        monkeypatch.setenv("APISPORTS_KEY", "fake-key")

        fake_coupon = {"id": 1, "stake_pln": 10.0, "total_odds": 1.85}
        api_fixtures = [
            {
                "fixture": {"id": 112, "status": {"short": "FT"}},
                "teams": {"home": {"name": "Arsenal"}, "away": {"name": "Chelsea"}},
                "goals": {"home": 0, "away": 2},
            }
        ]
        fake_leg_db = [
            {"gospodarz": "Arsenal", "goscie": "Chelsea", "typ": "1", "ai_tip": "1", "prediction_id": None}
        ]

        with (
            patch("footstats.evening_agent._fetch_results_today", return_value=api_fixtures),
            patch("footstats.evening_agent.get_active_coupons", return_value=[fake_coupon]),
            patch("footstats.evening_agent.get_coupon_legs", return_value=fake_leg_db),
            patch("footstats.evening_agent.update_coupon_status") as mock_update,
            patch("footstats.evening_agent.credit_win") as mock_win,
            patch("footstats.evening_agent.init_coupon_tables"),
            patch("footstats.evening_agent.init_db"),
            patch("footstats.evening_agent._save_coupon_legs"),
            patch("footstats.evening_agent._send_telegram_summary"),
            patch("footstats.utils.telegram_notify.check_and_alert_agent_down"),
        ):
            from footstats.evening_agent import run_evening_agent
            run_evening_agent("2026-06-05")

        mock_win.assert_not_called()
        call_args = mock_update.call_args
        new_status = call_args.args[1] if len(call_args.args) > 1 else "LOST"
        assert new_status == "LOST"

    def test_run_evening_agent_no_api_key_returns_empty(self, monkeypatch):
        """Missing APISPORTS_KEY → empty dict returned immediately."""
        monkeypatch.setenv("APISPORTS_KEY", "")
        with patch("footstats.evening_agent.load_dotenv"):
            from footstats.evening_agent import run_evening_agent
            result = run_evening_agent("2026-06-05")
        assert result == {}
