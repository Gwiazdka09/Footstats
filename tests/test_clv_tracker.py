"""Testy core/clv_tracker.py — Closing Line Value."""
from unittest.mock import patch, MagicMock

import pytest

from footstats.core.clv_tracker import (
    calculate_clv,
    record_closing_odds,
    get_clv_report,
    batch_record_closing_odds,
)


# ── calculate_clv ─────────────────────────────────────────────────────────

def test_clv_positive_value():
    # bet 2.0, closing 1.8 → zakład lepszy niż rynek
    assert calculate_clv(2.0, 1.8) == pytest.approx(11.11, abs=0.01)


def test_clv_negative_value():
    # bet 1.8, closing 2.0 → rynek się otworzył
    assert calculate_clv(1.8, 2.0) == pytest.approx(-10.0, abs=0.01)


def test_clv_no_movement():
    assert calculate_clv(2.0, 2.0) == pytest.approx(0.0)


def test_clv_invalid_closing_below_one():
    assert calculate_clv(2.0, 0.9) is None


def test_clv_invalid_bet_below_one():
    assert calculate_clv(0.5, 2.0) is None


def test_clv_none_inputs():
    assert calculate_clv(None, 2.0) is None
    assert calculate_clv(2.0, None) is None


# ── record_closing_odds ───────────────────────────────────────────────────

def _make_mock_conn(odds: float | None):
    """Fake connection: SELECT zwraca odds, UPDATE działa."""
    row = {"odds": odds}
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = row
    conn.__enter__ = lambda s: conn
    conn.__exit__ = MagicMock(return_value=False)
    return conn


def test_record_closing_odds_returns_clv():
    mock_conn = _make_mock_conn(2.0)
    with patch("footstats.core.clv_tracker._connect", return_value=mock_conn), \
         patch("footstats.core.clv_tracker._ensure_clv_column"):
        result = record_closing_odds(1, closing_odds=1.8)
    assert result == pytest.approx(11.11, abs=0.01)


def test_record_closing_odds_no_bet_odds():
    mock_conn = _make_mock_conn(None)
    with patch("footstats.core.clv_tracker._connect", return_value=mock_conn), \
         patch("footstats.core.clv_tracker._ensure_clv_column"):
        result = record_closing_odds(99, closing_odds=2.0)
    assert result is None


# ── batch_record_closing_odds ─────────────────────────────────────────────

def test_batch_skips_incomplete_records():
    with patch("footstats.core.clv_tracker.record_closing_odds", return_value=5.0) as mock_rec, \
         patch("footstats.core.clv_tracker._ensure_clv_column"):
        n = batch_record_closing_odds([
            {"prediction_id": 1, "closing_odds": 1.9},
            {"closing_odds": 2.0},          # brak prediction_id
            {"prediction_id": 2},            # brak closing_odds
            {"prediction_id": 3, "closing_odds": 1.7},
        ])
    assert n == 2
    assert mock_rec.call_count == 2


def test_batch_empty():
    with patch("footstats.core.clv_tracker._ensure_clv_column"):
        assert batch_record_closing_odds([]) == 0


# ── get_clv_report ────────────────────────────────────────────────────────

def _make_rows(data: list[tuple]) -> list:
    """data: [(league, odds, clv_closing_odds, tip_correct), ...]"""
    rows = []
    for league, odds, closing, correct in data:
        r = MagicMock()
        r.__getitem__ = lambda s, k, _l=league, _o=odds, _c=closing, _tc=correct: {
            "league": _l, "odds": _o, "clv_closing_odds": _c, "tip_correct": _tc
        }[k]
        rows.append(r)
    return rows


def test_get_clv_report_no_data():
    conn = MagicMock()
    conn.execute.return_value.fetchall.return_value = []
    conn.__enter__ = lambda s: conn
    conn.__exit__ = MagicMock(return_value=False)
    with patch("footstats.core.clv_tracker._connect", return_value=conn), \
         patch("footstats.core.clv_tracker._ensure_clv_column"):
        result = get_clv_report()
    assert result["overall"] is None
    assert result["per_liga"] == []


def test_clv_report_overall():
    # 4 zakłady: 2 z CLV+, 2 z CLV-
    records = [
        ("Bundesliga", 2.0, 1.8, 1),   # CLV +11%
        ("Bundesliga", 2.0, 1.8, 1),   # CLV +11%
        ("Bundesliga", 1.8, 2.0, 0),   # CLV -10%
        ("Bundesliga", 1.8, 2.0, 0),   # CLV -10%
        ("Bundesliga", 2.0, 1.9, 1),   # CLV +5.3%
    ]

    conn = MagicMock()
    conn.__enter__ = lambda s: conn
    conn.__exit__ = MagicMock(return_value=False)

    class FakeRow:
        def __init__(self, league, odds, closing, correct):
            self._d = {"league": league, "odds": odds,
                       "clv_closing_odds": closing, "tip_correct": correct}
        def __getitem__(self, k):
            return self._d[k]

    conn.execute.return_value.fetchall.return_value = [
        FakeRow(*r) for r in records
    ]

    with patch("footstats.core.clv_tracker._connect", return_value=conn), \
         patch("footstats.core.clv_tracker._ensure_clv_column"):
        result = get_clv_report(min_samples=3)

    assert result["overall"] is not None
    assert result["overall"]["n"] == 5
    assert result["overall"]["positive_pct"] == pytest.approx(60.0)


# ── CLV liczone na kursie od Groqa mierzyłoby halucynację ──────────────────

class _FakeKursor:
    def __init__(self, wiersze):
        self._w = wiersze
    def fetchall(self):
        return self._w
    def fetchone(self):
        return self._w[0] if self._w else None


class _FakeConn:
    """Połączenie zwracające zaplanowane odpowiedzi po kolei, zapamiętuje SQL."""
    def __init__(self, odpowiedzi):
        self.odpowiedzi = list(odpowiedzi)
        self.zapytania = []
    def execute(self, sql, params=()):
        self.zapytania.append(sql)
        return _FakeKursor(self.odpowiedzi.pop(0) if self.odpowiedzi else [])
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def test_clv_report_pomija_niezweryfikowane_kursy():
    """Kurs zapisany w KROKU 3 pochodzi od Groqa — CLV z niego nic nie mierzy."""
    conn = _FakeConn([[], [{"n": 0}]])
    with patch("footstats.core.clv_tracker._connect", return_value=conn), \
         patch("footstats.core.clv_tracker._ensure_clv_column"):
        get_clv_report()
    assert "odds_verified" in conn.zapytania[0]


def test_clv_report_ostrzega_o_odrzuconej_probie(caplog):
    """Pusty raport z powodu braku weryfikacji to NIE to samo, co brak danych."""
    import logging
    conn = _FakeConn([[], [{"n": 42}]])
    with patch("footstats.core.clv_tracker._connect", return_value=conn), \
         patch("footstats.core.clv_tracker._ensure_clv_column"):
        with caplog.at_level(logging.WARNING, logger="footstats.core.clv_tracker"):
            wynik = get_clv_report()
    assert wynik["overall"] is None
    assert "pominieto 42" in caplog.text


def test_clv_report_milczy_gdy_nie_ma_czego_pomijac(caplog):
    import logging
    conn = _FakeConn([[], [{"n": 0}]])
    with patch("footstats.core.clv_tracker._connect", return_value=conn), \
         patch("footstats.core.clv_tracker._ensure_clv_column"):
        with caplog.at_level(logging.WARNING, logger="footstats.core.clv_tracker"):
            get_clv_report()
    assert "pominieto" not in caplog.text
