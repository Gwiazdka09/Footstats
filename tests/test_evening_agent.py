"""tests/test_evening_agent.py"""
import sqlite3
import pytest
from unittest.mock import patch


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
    bookmaker        TEXT,
    user_id          INTEGER DEFAULT 1,
    shared           BOOLEAN NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS predictions (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    match_date           TEXT NOT NULL DEFAULT '',
    team_home            TEXT NOT NULL DEFAULT '',
    team_away            TEXT NOT NULL DEFAULT '',
    league               TEXT NOT NULL DEFAULT '',
    ai_tip               TEXT NOT NULL DEFAULT '',
    ai_confidence        INTEGER NOT NULL DEFAULT 0,
    ai_reasoning         TEXT NOT NULL DEFAULT '',
    odds                 REAL,
    actual_result        TEXT,
    tip_correct          INTEGER,
    kupon_type           TEXT DEFAULT '',
    kodeks_rules_checked TEXT NOT NULL DEFAULT '[]',
    prompt_version       TEXT NOT NULL DEFAULT '',
    factors              TEXT NOT NULL DEFAULT '[]',
    match_stats          TEXT,
    coupon_id            INTEGER REFERENCES coupons(id)
);
CREATE TABLE IF NOT EXISTS ai_feedback (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    content    TEXT NOT NULL DEFAULT ''
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
)
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


@pytest.fixture(autouse=True)
def patch_db(tmp_path, monkeypatch):
    """All DB modules get a shared SQLite file; DDL init calls no-op'd."""
    db_path = str(tmp_path / "test.db")

    setup = sqlite3.connect(db_path)
    setup.executescript(_SCHEMA)
    setup.execute("INSERT OR IGNORE INTO bankroll_state (id, balance) VALUES (1, 1000.0)")
    setup.commit()
    setup.close()

    conn_factory = lambda: _SQLiteConn(db_path)

    import footstats.core.coupon_tracker as ct
    import footstats.core.backtest as bt
    import footstats.core.bankroll as bk

    monkeypatch.setattr(ct, "_connect", conn_factory)
    monkeypatch.setattr(bt, "_connect", conn_factory)
    monkeypatch.setattr(bk, "_db_connect", conn_factory)
    monkeypatch.setattr(ct, "init_coupon_tables", lambda: None)
    monkeypatch.setattr(bt, "init_db", lambda: None)

    import footstats.evening_agent as ea
    monkeypatch.setattr(ea, "init_coupon_tables", lambda: None)
    monkeypatch.setattr(ea, "init_db", lambda: None)

    yield db_path


# ── Pure helpers ────────────────────────────────────────────────────────────

from footstats.evening_agent import (
    _wynik_z_fixture,
    _find_result,
    _status_kuponu,
)


@pytest.fixture
def sample_fixture_psg_lyon():
    return {
        "fixture": {"status": {"short": "FT"}},
        "teams": {
            "home": {"name": "Paris Saint-Germain"},
            "away": {"name": "Olympique Lyonnais"},
        },
        "goals": {"home": 2, "away": 1},
    }


@pytest.fixture
def sample_fixture_inprogress():
    return {
        "fixture": {"status": {"short": "1H"}},
        "teams": {
            "home": {"name": "Bayern Munich"},
            "away": {"name": "Borussia Dortmund"},
        },
        "goals": {"home": 1, "away": 0},
    }


def test_wynik_z_fixture_finished(sample_fixture_psg_lyon):
    result = _wynik_z_fixture(sample_fixture_psg_lyon)
    assert result == ("Paris Saint-Germain", "Olympique Lyonnais", "2-1")


def test_wynik_z_fixture_inprogress_returns_none(sample_fixture_inprogress):
    assert _wynik_z_fixture(sample_fixture_inprogress) is None


def test_wynik_z_fixture_z_halftime_dodaje_sufiks_ht():
    fixture = {
        "fixture": {"status": {"short": "FT"}},
        "teams": {
            "home": {"name": "Paris Saint-Germain"},
            "away": {"name": "Olympique Lyonnais"},
        },
        "goals": {"home": 2, "away": 1},
        "score": {"halftime": {"home": 1, "away": 0}},
    }
    result = _wynik_z_fixture(fixture)
    assert result == ("Paris Saint-Germain", "Olympique Lyonnais", "2-1;HT:1-0")


def test_wynik_z_fixture_bez_halftime_samo_ft(sample_fixture_psg_lyon):
    # fixture bez klucza "score" → brak HT, samo FT (jak dotychczas)
    result = _wynik_z_fixture(sample_fixture_psg_lyon)
    assert result == ("Paris Saint-Germain", "Olympique Lyonnais", "2-1")


def test_find_result_fuzzy_match(sample_fixture_psg_lyon):
    wynik = _find_result("PSG", "Lyon", [sample_fixture_psg_lyon])
    assert wynik == "2-1"


def test_find_result_no_match():
    fixture = {
        "fixture": {"status": {"short": "FT"}},
        "teams": {"home": {"name": "Juventus"}, "away": {"name": "Inter"}},
        "goals": {"home": 1, "away": 1},
    }
    assert _find_result("Arsenal", "Chelsea", [fixture]) is None


def test_status_kuponu_all_win():
    assert _status_kuponu(["WIN", "WIN", "WIN"]) == "WON"


def test_status_kuponu_any_loss():
    assert _status_kuponu(["WIN", "LOSS", "WIN"]) == "LOST"


def test_status_kuponu_pending_stays_active():
    assert _status_kuponu(["WIN", "PENDING"]) == "ACTIVE"


def test_status_kuponu_all_void():
    assert _status_kuponu(["VOID", "VOID"]) == "VOID"


def test_status_kuponu_empty():
    assert _status_kuponu([]) == "VOID"


# ── Integration: run_evening_agent ──────────────────────────────────────────

def test_run_evening_agent_marks_coupon_won(sample_fixture_psg_lyon):
    from footstats.core.coupon_tracker import save_coupon, get_active_coupons
    from footstats.evening_agent import run_evening_agent

    legs = [{"gospodarz": "PSG", "goscie": "Lyon", "typ": "1", "kurs": 1.45}]
    save_coupon("final", "A", legs, total_odds=1.45, stake_pln=10.0)

    with patch("footstats.evening_agent._fetch_results_today",
               return_value=[sample_fixture_psg_lyon]), \
         patch("footstats.evening_agent._send_telegram_summary"), \
         patch.dict("os.environ", {"APISPORTS_KEY": "test_key"}):
        summary = run_evening_agent("2026-04-09")

    assert summary["won"] == 1
    assert len(get_active_coupons()) == 0


def test_run_evening_agent_marks_coupon_lost(sample_fixture_psg_lyon):
    from footstats.core.coupon_tracker import save_coupon
    from footstats.evening_agent import run_evening_agent

    legs = [{"gospodarz": "PSG", "goscie": "Lyon", "typ": "2", "kurs": 3.20}]
    save_coupon("final", "A", legs, total_odds=3.20, stake_pln=10.0)

    with patch("footstats.evening_agent._fetch_results_today",
               return_value=[sample_fixture_psg_lyon]), \
         patch("footstats.evening_agent._send_telegram_summary"), \
         patch.dict("os.environ", {"APISPORTS_KEY": "test_key"}):
        summary = run_evening_agent("2026-04-09")

    assert summary["lost"] == 1


def test_run_evening_agent_pending_when_no_result():
    from footstats.core.coupon_tracker import save_coupon, get_active_coupons
    from footstats.evening_agent import run_evening_agent

    legs = [{"gospodarz": "Bayern", "goscie": "Dortmund", "typ": "1", "kurs": 1.60}]
    save_coupon("final", "A", legs, total_odds=1.60, stake_pln=10.0)

    with patch("footstats.evening_agent._fetch_results_today", return_value=[]), \
         patch("footstats.evening_agent._send_telegram_summary"), \
         patch.dict("os.environ", {"APISPORTS_KEY": "test_key"}):
        summary = run_evening_agent("2026-04-09")

    assert summary["active"] == 1
    assert len(get_active_coupons()) == 1


def test_run_evening_agent_triggers_auto_trainer():
    from footstats.core.coupon_tracker import save_coupon, promote_to_active
    from footstats.evening_agent import run_evening_agent

    fixtures = []
    for i in range(20):
        home = f"HomeTeam{i}"
        away = f"AwayTeam{i}"
        legs = [{"home": home, "away": away, "typ": "1"}]
        cid = save_coupon("draft", "A", legs, stake_pln=10.0, total_odds=1.5)
        promote_to_active(cid)
        fixtures.append({
            "fixture": {"status": {"short": "FT"}},
            "teams": {"home": {"name": home}, "away": {"name": away}},
            "goals": {"home": 1, "away": 0},
        })

    with patch("footstats.evening_agent._fetch_results_today", return_value=fixtures), \
         patch("footstats.evening_agent._send_telegram_summary"), \
         patch("subprocess.Popen") as mock_popen, \
         patch.dict("os.environ", {"APISPORTS_KEY": "test_key"}):
        run_evening_agent("2026-04-09")

    mock_popen.assert_called_once()
    call_args = mock_popen.call_args[0][0]
    assert "footstats.ai.trainer" in call_args
