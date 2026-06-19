import sqlite3
from pathlib import Path

from footstats.core.wf_db import init_db, save_run, load_run


def test_save_and_load_run(tmp_path):
    db = tmp_path / "wf_test.db"
    init_db(db)
    rows = [
        {"run_tag": "baseline", "league": "TEST", "match_date": "2020-01-01",
         "home": "A", "away": "B", "actual_res": "H", "pred_tip": "1",
         "pred_conf": 0.62, "correct": 1, "no_odds": 0},
        {"run_tag": "baseline", "league": "TEST", "match_date": "2020-01-02",
         "home": "C", "away": "D", "actual_res": "A", "pred_tip": "1",
         "pred_conf": 0.55, "correct": 0, "no_odds": 0},
    ]
    save_run(db, rows)
    loaded = load_run(db, "baseline")
    assert len(loaded) == 2
    assert loaded[0]["home"] == "A"


def test_init_db_is_sqlite_not_neon(tmp_path):
    """Guard: harness pisze do pliku SQLite, nie do Neon."""
    db = tmp_path / "wf_test.db"
    init_db(db)
    assert db.exists()
    con = sqlite3.connect(db)
    names = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    con.close()
    assert "wf_runs" in names
