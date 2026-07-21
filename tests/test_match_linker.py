"""tests/test_match_linker.py — dopasowanie wolnego wpisu (home, away, date) do
predykcji w DB (Etap A dziennika kuponów, J6/J4c).

Kluczowy anty-regres: `_norm_ascii` (STRICT) zamiast `normalize_team_name`
(mappingi z team_mappings.json kolidują — "Manchester City" i "Manchester
United" po mapowaniu potrafią wylądować na tym samym skrócie), co dawałoby
false-positive w settlemencie. link_leg musi wykryć brak dopasowania w takim
przypadku (test_kolizja_normalizacji_nie_daje_false_positive).

Izolacja: własna plikowa SQLite DB, `match_linker.connect` podmieniony
(monkeypatch) — wzorzec z tests/test_coupon_settlement.py. Zero sieci/prod
(zgodnie z .claude/rules/tests-no-prod.md).
"""
import sqlite3
from datetime import date, timedelta

import pytest

import footstats.core.match_linker as match_linker

_TODAY = date(2026, 3, 15)


class _SQLiteConn:
    """sqlite3 adapter zgodny z interfejsem footstats.utils.db._Conn."""

    def __init__(self, path: str) -> None:
        self._raw = sqlite3.connect(path)
        self._raw.row_factory = sqlite3.Row

    def execute(self, sql, params=()):
        return self._raw.execute(sql, params)

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


_SCHEMA = """
CREATE TABLE IF NOT EXISTS predictions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    match_date    TEXT NOT NULL,
    team_home     TEXT NOT NULL,
    team_away     TEXT NOT NULL,
    league        TEXT NOT NULL DEFAULT '',
    ai_tip        TEXT NOT NULL DEFAULT '',
    ai_confidence INTEGER NOT NULL DEFAULT 0,
    prob_home     REAL,
    prob_draw     REAL,
    prob_away     REAL,
    actual_result TEXT
);
CREATE TABLE IF NOT EXISTS coupons (
    id INTEGER PRIMARY KEY AUTOINCREMENT
);
"""


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Własna plikowa SQLite DB; match_linker.connect podmieniony na nią."""
    db_path = str(tmp_path / "test.db")
    setup = sqlite3.connect(db_path)
    setup.executescript(_SCHEMA)
    setup.commit()
    setup.close()

    monkeypatch.setattr(match_linker, "connect", lambda: _SQLiteConn(db_path))
    yield db_path


def _insert_prediction(
    db_path: str,
    team_home: str,
    team_away: str,
    match_date: str,
    ai_tip: str = "1",
    ai_confidence: int = 70,
    prob_home: float = 0.5,
    prob_draw: float = 0.3,
    prob_away: float = 0.2,
    actual_result: str | None = "2-1",
) -> int:
    conn = sqlite3.connect(db_path)
    cur = conn.execute(
        "INSERT INTO predictions (team_home, team_away, match_date, ai_tip, "
        "ai_confidence, prob_home, prob_draw, prob_away, actual_result) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (team_home, team_away, match_date, ai_tip, ai_confidence,
         prob_home, prob_draw, prob_away, actual_result),
    )
    conn.commit()
    pred_id = cur.lastrowid
    conn.close()
    return pred_id


def _row_counts(db_path: str) -> tuple[int, int]:
    conn = sqlite3.connect(db_path)
    pred_n = conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
    coupon_n = conn.execute("SELECT COUNT(*) FROM coupons").fetchone()[0]
    conn.close()
    return pred_n, coupon_n


def test_exact_match_zwraca_predykcje(tmp_db):
    _insert_prediction(
        tmp_db, "Legia", "Lech", _TODAY.isoformat(),
        ai_tip="1", ai_confidence=75, prob_home=0.6, prob_draw=0.25,
        prob_away=0.15, actual_result="2-1",
    )
    result = match_linker.link_leg("Legia", "Lech", _TODAY.isoformat())
    assert result.matched is True
    assert result.match_confidence == "exact"
    assert result.prediction["ai_tip"] == "1"
    assert result.prediction["ai_confidence"] == 75
    assert result.prediction["prob_home"] == 0.6
    assert result.prediction["actual_result"] == "2-1"


def test_kolizja_normalizacji_nie_daje_false_positive(tmp_db):
    # DB ma "Manchester United" — pytanie o "Manchester City" NIE może matchować,
    # nawet jeśli normalize_team_name (mappingi) sprowadza obie do wspólnego aliasu.
    _insert_prediction(tmp_db, "Manchester United", "Chelsea", _TODAY.isoformat())
    result = match_linker.link_leg("Manchester City", "Chelsea", _TODAY.isoformat())
    assert result.matched is False
    assert result.match_confidence == "none"


def test_swap_orientacji_nie_matchuje(tmp_db):
    _insert_prediction(tmp_db, "Legia", "Lech", _TODAY.isoformat())
    result = match_linker.link_leg("Lech", "Legia", _TODAY.isoformat())
    assert result.matched is False
    assert result.match_confidence == "none"


def test_brak_danych_matched_false(tmp_db):
    result = match_linker.link_leg("Legia", "Lech", _TODAY.isoformat())
    assert result.matched is False
    assert result.match_confidence == "none"


def test_dwa_rozne_mecze_w_oknie_ambiguous(tmp_db):
    # Te same drużyny, dwie różne daty w oknie tolerancji ±1 — nie da się
    # jednoznacznie rozstrzygnąć, który mecz to ten sam co wpis użytkownika.
    _insert_prediction(tmp_db, "Legia", "Lech", _TODAY.isoformat())
    _insert_prediction(tmp_db, "Legia", "Lech", (_TODAY + timedelta(days=1)).isoformat())
    result = match_linker.link_leg("Legia", "Lech", _TODAY.isoformat())
    assert result.matched is False
    assert result.match_confidence == "ambiguous"


def test_wiele_wierszy_ten_sam_mecz_bierze_max_confidence(tmp_db):
    _insert_prediction(tmp_db, "Legia", "Lech", _TODAY.isoformat(), ai_tip="1", ai_confidence=60)
    _insert_prediction(tmp_db, "Legia", "Lech", _TODAY.isoformat(), ai_tip="1X", ai_confidence=80)
    result = match_linker.link_leg("Legia", "Lech", _TODAY.isoformat())
    assert result.matched is True
    assert result.prediction["ai_confidence"] == 80


def test_tolerancja_daty_plus_minus_1(tmp_db):
    _insert_prediction(tmp_db, "Legia", "Lech", (_TODAY + timedelta(days=1)).isoformat())
    result = match_linker.link_leg("Legia", "Lech", _TODAY.isoformat())
    assert result.matched is True
    assert result.match_confidence == "exact"


def test_brak_daty_matched_false(tmp_db):
    result = match_linker.link_leg("Legia", "Lech", None)
    assert result.matched is False
    assert result.match_confidence == "none"


def test_diakrytyki_matchuja(tmp_db):
    # _norm_ascii: NFKD → ascii ignore → "München" traci diakrytyk, ale litera
    # bazowa "u" zostaje (combining mark jest odrzucany, nie cała litera).
    _insert_prediction(tmp_db, "Bayern München", "Union Berlin", _TODAY.isoformat())
    result = match_linker.link_leg("Bayern Munchen", "Union Berlin", _TODAY.isoformat())
    assert result.matched is True
    assert result.match_confidence == "exact"


def test_read_only_zero_writes(tmp_db):
    _insert_prediction(tmp_db, "Legia", "Lech", _TODAY.isoformat())
    before = _row_counts(tmp_db)
    match_linker.link_leg("Legia", "Lech", _TODAY.isoformat())
    match_linker.link_leg("Nieznana", "Druzyna", _TODAY.isoformat())
    after = _row_counts(tmp_db)
    assert before == after
