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
    # testy nigdy nie czytaja prawdziwego .env (ani prod DB)
    mod._ENV_PATH = str(Path(__file__).parent / 'nie_istnieje.env')
    mod._url_z_env_pliku.__defaults__ = (mod._ENV_PATH,)
    return mod


def test_sqlite_generuje_html(brain, tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    conn = sqlite3.connect(tmp_path / "data" / "footstats_backtest.db")
    conn.executescript(
        """
        CREATE TABLE predictions (id INTEGER PRIMARY KEY, team_home TEXT,
            team_away TEXT, actual_result TEXT, match_date TEXT, tip_correct INTEGER);
        CREATE TABLE ai_feedback (id INTEGER PRIMARY KEY, match_id INTEGER,
            reason_for_failure TEXT, created_at TEXT);
        INSERT INTO predictions VALUES (1,'Arsenal','Chelsea','1:0','2026-01-01',0);
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


def _sqlite_env(tmp_path, monkeypatch, powod="zly typ", tip=0):
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir(exist_ok=True)
    conn = sqlite3.connect(tmp_path / "data" / "footstats_backtest.db")
    conn.executescript(
        """
        CREATE TABLE predictions (id INTEGER PRIMARY KEY, team_home TEXT,
            team_away TEXT, actual_result TEXT, match_date TEXT, tip_correct INTEGER);
        CREATE TABLE ai_feedback (id INTEGER PRIMARY KEY, match_id INTEGER,
            reason_for_failure TEXT, created_at TEXT);
        INSERT INTO predictions VALUES (1,'A','B','1:0','2026-01-01',%d);
        """ % tip
    )
    conn.execute("INSERT INTO ai_feedback VALUES (1,1,?,'2026-01-02')", (powod,))
    conn.commit()
    conn.close()


def test_xss_script_nie_wychodzi_z_tagu(brain, tmp_path, monkeypatch):
    _sqlite_env(tmp_path, monkeypatch, "</script><script>alert(1)</script>")
    html = (tmp_path / brain.create_brain_graph()).read_text(encoding="utf-8")
    assert "</script><script>alert" not in html


def test_trafiony_typ_ma_inny_wezel(brain, tmp_path, monkeypatch):
    _sqlite_env(tmp_path, monkeypatch, tip=1)
    html = (tmp_path / brain.create_brain_graph()).read_text(encoding="utf-8")
    assert "TRAFIONY: A vs B" in html


def test_blad_pobierania_nie_nadpisuje_pliku(brain, tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "brain_graph.html").write_text("STARY", encoding="utf-8")
    monkeypatch.setattr(brain, "_connect", lambda: (_ for _ in ()).throw(OSError("x")))
    with pytest.raises(SystemExit) as e:
        brain.create_brain_graph()
    assert e.value.code == 1
    assert (tmp_path / "brain_graph.html").read_text(encoding="utf-8") == "STARY"


def test_url_z_pliku_env(brain, tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        'DATABASE_URL="postgresql://a"\n'
        "DATABASE_URL_SUPABASE='postgresql://b'\n"
    )
    assert brain._url_z_env_pliku(str(env)) == "postgresql://b"


def test_connect_timeout(brain, monkeypatch):
    import psycopg2

    kw_seen = {}

    class C:
        def set_session(self, **kw):
            pass

    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/db")
    monkeypatch.setattr(psycopg2, "connect", lambda url, **kw: kw_seen.update(kw) or C())
    brain._connect()
    assert kw_seen["connect_timeout"] == 10
