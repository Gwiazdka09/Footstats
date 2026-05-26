"""Testy scripts/accuracy_report.py — obliczenia hit-rate."""
import sqlite3
import pytest

from scripts.accuracy_report import _pct, report_overall, report_per_liga, report_per_typ


@pytest.fixture
def mem_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE predictions (
            id INTEGER PRIMARY KEY,
            league TEXT,
            ai_tip TEXT,
            ai_confidence REAL,
            kupon_type TEXT,
            tip_correct INTEGER
        )"""
    )
    conn.execute(
        """CREATE TABLE coupons (
            id INTEGER PRIMARY KEY,
            status TEXT,
            stake_pln REAL,
            payout_pln REAL
        )"""
    )
    rows = [
        ("Bundesliga", "1", 75.0, "akumulator", 1),
        ("Bundesliga", "1", 65.0, "akumulator", 0),
        ("Bundesliga", "1", 80.0, "akumulator", 1),
        ("Bundesliga", "2", 60.0, "akumulator", 1),
        ("Bundesliga", "X", 55.0, "akumulator", 0),
        ("Ligue 1",    "2", 70.0, "pojedynczy",  0),
        ("Ligue 1",    "X", 60.0, "pojedynczy",  1),
        ("Serie A",    "1", 55.0, "akumulator", 1),
        ("Serie A",    "1", 55.0, "akumulator", 1),
    ]
    conn.executemany(
        "INSERT INTO predictions (league, ai_tip, ai_confidence, kupon_type, tip_correct) VALUES (?,?,?,?,?)",
        rows,
    )
    conn.commit()
    return conn


# ── _pct ──────────────────────────────────────────────────────────────────

def test_pct_zero_total():
    assert _pct(0, 0) == "  —  "


def test_pct_full_hit():
    assert "100.0%" in _pct(5, 5)


def test_pct_partial():
    result = _pct(1, 4)
    assert "25.0%" in result


# ── report_overall ────────────────────────────────────────────────────────

def test_report_overall_runs(mem_conn, capsys):
    report_overall(mem_conn)
    out = capsys.readouterr().out
    assert "9" in out          # 9 settled predictions
    assert "6" in out          # 6 hits


# ── report_per_liga ───────────────────────────────────────────────────────

def test_report_per_liga_runs(mem_conn, capsys):
    report_per_liga(mem_conn)
    out = capsys.readouterr().out
    assert "Bundesliga" in out


def test_report_per_liga_min5_filter(mem_conn, capsys):
    # Ligue 1 has only 2 rows — should be filtered out (min 5)
    report_per_liga(mem_conn)
    out = capsys.readouterr().out
    assert "Ligue 1" not in out


# ── report_per_typ ────────────────────────────────────────────────────────

def test_report_per_typ_runs(mem_conn, capsys):
    report_per_typ(mem_conn)
    # Should not raise, prints something
    out = capsys.readouterr().out
    assert "=" in out
