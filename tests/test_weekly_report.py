import sqlite3
import pytest


class _SQLiteConn:
    def __init__(self, path: str) -> None:
        self._raw = sqlite3.connect(path)
        self._raw.row_factory = sqlite3.Row

    def execute(self, sql: str, params=()):
        return self._raw.execute(sql, params)

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
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    phase      TEXT NOT NULL DEFAULT '',
    status     TEXT NOT NULL DEFAULT 'DRAFT',
    kupon_type TEXT NOT NULL DEFAULT '',
    legs_json  TEXT NOT NULL DEFAULT '[]',
    total_odds REAL,
    stake_pln  REAL,
    payout_pln REAL,
    roi_pct    REAL,
    groq_reasoning   TEXT,
    decision_score   INTEGER,
    match_date_first TEXT
)
"""


@pytest.fixture
def db_with_coupons(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA)
    conn.execute(
        "INSERT INTO coupons (phase,status,kupon_type,legs_json,total_odds,stake_pln,payout_pln,roi_pct)"
        " VALUES ('final','WON','A','[]',3.20,10.0,28.16,181.6)"
    )
    conn.execute(
        "INSERT INTO coupons (phase,status,kupon_type,legs_json,total_odds,stake_pln,payout_pln,roi_pct)"
        " VALUES ('final','LOST','A','[]',2.10,10.0,0.0,-100.0)"
    )
    conn.commit()
    conn.close()

    import footstats.weekly_report as wr
    monkeypatch.setattr(wr, "_connect", lambda: _SQLiteConn(db_path))
    yield db_path


def test_get_stats_7_dni_returns_dict(db_with_coupons):
    from footstats.weekly_report import get_stats_7_dni
    stats = get_stats_7_dni()
    assert isinstance(stats, dict)
    assert "total" in stats
    assert "won" in stats
    assert "lost" in stats


def test_get_stats_7_dni_counts_correctly(db_with_coupons):
    from footstats.weekly_report import get_stats_7_dni
    stats = get_stats_7_dni()
    assert stats["total"] >= 2
    assert stats["won"] >= 1
    assert stats["lost"] >= 1


def test_build_raport_prompt_contains_stats():
    from footstats.weekly_report import build_raport_prompt
    stats = {"total": 5, "won": 3, "lost": 2, "accuracy_pct": 60.0, "roi_pct": 12.5,
             "total_stake": 50.0, "total_payout": 56.25}
    prompt = build_raport_prompt(stats)
    assert "60" in prompt or "accuracy" in prompt.lower()
    assert isinstance(prompt, str)
    assert len(prompt) > 50


def test_run_weekly_report_without_groq(db_with_coupons, monkeypatch):
    import footstats.weekly_report as wr
    monkeypatch.setattr(wr, "_connect", lambda: _SQLiteConn(db_with_coupons))
    from footstats.weekly_report import run_weekly_report
    result = run_weekly_report(api_key_groq=None, send_telegram=False)
    assert isinstance(result, dict)
    assert "total" in result
