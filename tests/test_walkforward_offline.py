"""Prod-safety: core/walkforward.run_walkforward MUSI pisać do lokalnego SQLite,
nigdy do prod Neon (footstats.utils.db). Regression dla bugu z code-review:
backtest robił CREATE TABLE + INSERT do produkcji.
"""
import sqlite3

import pandas as pd

import footstats.core.walkforward as wf


def _df(n: int = 80) -> pd.DataFrame:
    rows = []
    teams = ["Bayern", "Dortmund", "Leipzig", "Leverkusen", "Stuttgart"]
    for i in range(n):
        hg, ag = i % 4, (i + 1) % 3
        result = "H" if hg > ag else ("D" if hg == ag else "A")
        rows.append({
            "date":   pd.Timestamp("2024-01-01") + pd.Timedelta(days=i * 3),
            "league": "GER-Bundesliga",
            "home":   teams[i % len(teams)],
            "away":   teams[(i + 1) % len(teams)],
            "hg":     hg,
            "ag":     ag,
            "result": result,
        })
    return pd.DataFrame(rows)


def test_run_walkforward_pisze_do_sqlite_nie_neon(tmp_path, monkeypatch):
    # Jakiekolwiek dotknięcie prod-DB = twardy błąd testu.
    import footstats.utils.db as prod_db

    def _boom(*a, **k):
        raise AssertionError("walk-forward dotknął prod Neon (footstats.utils.db)!")

    monkeypatch.setattr(prod_db, "connect", _boom)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    wf_db = tmp_path / "wf.db"
    monkeypatch.setattr(wf, "WF_DB_PATH", wf_db)

    out = wf.run_walkforward(_df(), verbose=False)

    # Zapis trafił do lokalnego SQLite, nie do Neon.
    assert wf_db.exists()
    con = sqlite3.connect(wf_db)
    try:
        n = con.execute("SELECT COUNT(*) FROM wf_results").fetchone()[0]
    finally:
        con.close()
    assert n > 0
    assert len(out) == n
