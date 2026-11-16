"""Testy scripts/visualize_brain.py: SQLite (fallback) i Postgres read-only."""

import importlib.util
import sqlite3
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "visualize_brain.py"


@pytest.fixture()
def brain():
    spec = importlib.util.spec_from_file_location("visualize_brain", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_sqlite_generuje_html(brain, tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    conn = sqlite3.connect(tmp_path / "data" / "footstats_backtest.db")
    conn.executescript(
        """
        CREATE TABLE predictions (id INTEGER PRIMARY KEY, team_home TEXT,
            team_away TEXT, actual_result TEXT, match_date TEXT);
        CREATE TABLE ai_feedback (id INTEGER PRIMARY KEY, match_id INTEGER,
            reason_for_failure TEXT, created_at TEXT);
        INSERT INTO predictions VALUES (1,'Arsenal','Chelsea','1:0','2026-01-01');
        INSERT INTO ai_feedback VALUES (1,1,'zly typ','2026-01-02');
        """
    )
    conn.commit()
    conn.close()

    out = brain.create_brain_graph()

    html = (tmp_path / out).read_text(encoding="utf-8")
    assert "LEKCJA: Arsenal vs Chelsea" in html


def test_postgres_polaczenie_readonly(brain, monkeypatch):
    import psycopg2

    calls = {}

    class FakeConn:
        def set_session(self, **kw):
            calls["session"] = kw

    def fake_connect(url, **kw):
        calls["url"] = url
        calls["kw"] = kw
        return FakeConn()

    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/db")
    monkeypatch.setattr(psycopg2, "connect", fake_connect)

    brain._connect()

    assert calls["url"] == "postgresql://u:p@h/db"
    assert calls["session"] == {"readonly": True}
    assert "cursor_factory" in calls["kw"]
