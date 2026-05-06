"""Unit tests for core/backtest.py — SQLite-backed mock."""
import sqlite3
import pytest
from datetime import datetime, timedelta


_SCHEMA = """
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
    coupon_id            INTEGER
);
CREATE TABLE IF NOT EXISTS ai_feedback (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    content    TEXT NOT NULL DEFAULT ''
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
def tmp_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "backtest.db")
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA)
    conn.commit()
    conn.close()

    import footstats.core.backtest as bt
    monkeypatch.setattr(bt, "_connect", lambda: _SQLiteConn(db_path))
    monkeypatch.setattr(bt, "init_db", lambda: None)
    yield db_path


from footstats.core.backtest import save_prediction, get_stats, get_pending_results


def _today():
    return datetime.now().strftime("%Y-%m-%d")


def _insert_prediction(team_home="PSG", team_away="Lyon", ai_tip="1",
                       ai_confidence=70, odds=1.85, actual_result=None,
                       tip_correct=None, league="Ligue 1", kupon_type="A"):
    return save_prediction(
        match_date=_today(),
        team_home=team_home,
        team_away=team_away,
        league=league,
        ai_tip=ai_tip,
        ai_confidence=ai_confidence,
        ai_reasoning="test reason",
        odds=odds,
        kupon_type=kupon_type,
    )


class TestSavePrediction:
    def test_returns_positive_id(self):
        mid = _insert_prediction()
        assert isinstance(mid, int)
        assert mid > 0

    def test_multiple_saves_unique_ids(self):
        id1 = _insert_prediction("A", "B")
        id2 = _insert_prediction("C", "D")
        assert id1 != id2

    def test_saves_all_fields(self, tmp_path):
        mid = _insert_prediction("Bayern", "Dortmund", "1X", 80, 1.40, league="Bundesliga")
        conn = sqlite3.connect(str(tmp_path / "backtest.db"))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM predictions WHERE id=?", (mid,)).fetchone()
        conn.close()
        assert row["team_home"] == "Bayern"
        assert row["team_away"] == "Dortmund"
        assert row["ai_tip"] == "1X"
        assert row["ai_confidence"] == 80


class TestUpdateResult:
    def test_update_sets_tip_correct(self):
        from footstats.core.backtest import update_result
        mid = _insert_prediction(ai_tip="1")
        update_result(mid, "2-1")
        from footstats.core.backtest import get_pending_results
        pending = get_pending_results()
        assert not any(p["id"] == mid for p in pending)

    def test_update_win_returns_correct(self):
        from footstats.core.backtest import update_result
        mid = _insert_prediction(ai_tip="1")
        result = update_result(mid, "2-1")
        assert result.get("tip_correct") == 1

    def test_update_loss_returns_incorrect(self):
        from footstats.core.backtest import update_result
        mid = _insert_prediction(ai_tip="1")
        result = update_result(mid, "0-2")
        assert result.get("tip_correct") == 0


class TestGetStats:
    def test_empty_db_returns_zero_total_tips(self):
        stats = get_stats(days=30)
        assert stats["total_tips"] == 0

    def test_counts_resolved_predictions(self):
        from footstats.core.backtest import update_result
        mid1 = _insert_prediction("A", "B", ai_tip="1")
        mid2 = _insert_prediction("C", "D", ai_tip="2")
        update_result(mid1, "2-1")
        update_result(mid2, "0-1")
        stats = get_stats(days=30)
        assert stats["total_tips"] >= 2

    def test_accuracy_computed(self):
        from footstats.core.backtest import update_result
        mid = _insert_prediction(ai_tip="1")
        update_result(mid, "2-1")
        stats = get_stats(days=30)
        assert "accuracy_pct" in stats

    def test_returns_dict(self):
        assert isinstance(get_stats(), dict)


class TestGetPendingResults:
    def test_empty_db_returns_empty_list(self):
        assert get_pending_results() == []

    def test_unresolved_prediction_is_pending(self):
        _insert_prediction("PSG", "Lyon")
        pending = get_pending_results()
        assert len(pending) >= 1

    def test_resolved_not_pending(self):
        from footstats.core.backtest import update_result
        mid = _insert_prediction("Bayern", "Dortmund")
        update_result(mid, "1-0")
        pending = get_pending_results()
        assert not any(p["id"] == mid for p in pending)


class TestGetWeaknessReport:
    def test_empty_returns_dict(self):
        from footstats.core.backtest import get_weakness_report
        result = get_weakness_report()
        assert isinstance(result, dict)

    def test_report_with_data(self):
        from footstats.core.backtest import update_result, get_weakness_report
        for i in range(5):
            mid = _insert_prediction(f"Team{i}", f"Opp{i}", ai_tip="1",
                                     ai_confidence=65, odds=2.0)
            update_result(mid, "0-1")  # all lose
        report = get_weakness_report(min_samples=3)
        assert isinstance(report, dict)
