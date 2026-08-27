"""`uzupelnij_tip_correct` — naprawa wierszy, ktore maja wynik, a nigdy sie nie rozlicza.

PO CO: `get_pending_results` pyta WYLACZNIE `WHERE actual_result IS NULL`. Wiersz,
ktoremu `update_result` wpisal wynik, a `oblicz_tip_correct` przy tym zwrocil `None`
(typ wtedy nieobslugiwany albo wynik nierozliczalny), dostaje `tip_correct = NULL`
i od tej chwili jest dla pipeline'u NIEWIDOCZNY NA ZAWSZE — ma juz wynik, wiec zaden
kolejny przebieg juz go nie odwiedzi.

Zmierzone na produkcji 27.08: 3 z 161 wierszy z wynikiem mialy taka dziure. Dwa z nich
(typ "Handicap +1 Gość") parser rozumie JUZ DZIS, ale zostaly zapisane jako NULL,
zanim wsparcie dla tego typu powstalo — i nic ich nigdy nie odwiedzilo ponownie.
`uzupelnij_tip_correct` to reczny przebieg naprawczy uruchamiany po kazdej zmianie
`oblicz_tip_correct`, nie czesc automatycznego pipeline'u.

Baza: SQLite w pliku tymczasowym (jak `tests/test_backtest_db.py`) — zero prod.
"""
from __future__ import annotations

import sqlite3

import pytest

_SCHEMA = """
CREATE TABLE IF NOT EXISTS predictions (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    match_date           TEXT NOT NULL DEFAULT '',
    team_home            TEXT NOT NULL DEFAULT '',
    team_away            TEXT NOT NULL DEFAULT '',
    ai_tip               TEXT NOT NULL DEFAULT '',
    actual_result        TEXT,
    tip_correct          INTEGER
)
"""


class _SQLiteConn:
    """Cienki adapter ujednolicajacy API polaczenia jak w `footstats.utils.db`."""

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


@pytest.fixture
def baza(tmp_path, monkeypatch):
    """Prawdziwa (tymczasowa) baza SQLite — WHERE dziala naprawde, nie na atrapie."""
    db_path = str(tmp_path / "backfill.db")
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA)
    conn.commit()
    conn.close()

    import footstats.core.backtest as bt
    monkeypatch.setattr(bt, "_connect", lambda: _SQLiteConn(db_path))
    monkeypatch.setattr(bt, "init_db", lambda: None)
    return db_path


def _wstaw(db_path: str, ai_tip: str, actual_result, tip_correct=None) -> int:
    conn = sqlite3.connect(db_path)
    cur = conn.execute(
        "INSERT INTO predictions (match_date, team_home, team_away, ai_tip,"
        " actual_result, tip_correct) VALUES ('2026-08-01', 'A', 'B', ?, ?, ?)",
        (ai_tip, actual_result, tip_correct),
    )
    conn.commit()
    rid = cur.lastrowid
    conn.close()
    return rid


def _wiersz(db_path: str, rid: int) -> sqlite3.Row:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM predictions WHERE id = ?", (rid,)).fetchone()
    conn.close()
    return row


# ── zachowanie na sucho i na mokro ───────────────────────────────────────────

def test_dry_run_niczego_nie_zapisuje_ale_raportuje(baza):
    from footstats.core.backtest import uzupelnij_tip_correct

    rid = _wstaw(baza, "2 (wygrana gościa)", "0-3")

    stat = uzupelnij_tip_correct(dry_run=True)

    assert stat["kandydaci"] == 1
    assert stat["uzupelnione"] == 1
    assert stat["pominiete"] == 0
    assert _wiersz(baza, rid)["tip_correct"] is None, "suchy przebieg zapisal do bazy"


def test_dry_run_false_wypelnia_policzalny_wiersz(baza):
    from footstats.core.backtest import uzupelnij_tip_correct

    rid = _wstaw(baza, "2 (wygrana gościa)", "0-3")

    stat = uzupelnij_tip_correct(dry_run=False)

    assert stat == {"kandydaci": 1, "uzupelnione": 1, "pominiete": 0}
    assert _wiersz(baza, rid)["tip_correct"] == 1


# ── wynik nierozliczalny zostaje NULL ────────────────────────────────────────

def test_wynik_nierozliczalny_zostaje_null_i_liczy_sie_jako_pominiete(baza):
    from footstats.core.backtest import uzupelnij_tip_correct

    rid = _wstaw(baza, "2 (wygrana gościa)", "1-1 (Pen- 4-5)")

    stat = uzupelnij_tip_correct(dry_run=False)

    assert stat == {"kandydaci": 1, "uzupelnione": 0, "pominiete": 1}
    assert _wiersz(baza, rid)["tip_correct"] is None


# ── antyregresja: juz oceniony wiersz zostaje nietkniety ─────────────────────

def test_wiersz_z_juz_ustawionym_zerem_nie_jest_ruszany(baza):
    """`tip_correct = 0` nie moze zniknac jako "falszywe" — WHERE tip_correct IS
    NULL ma go w ogole nie widziec."""
    from footstats.core.backtest import uzupelnij_tip_correct

    rid_gotowy   = _wstaw(baza, "1", "0-2", tip_correct=0)
    rid_kandydat = _wstaw(baza, "2 (wygrana gościa)", "0-3")

    stat = uzupelnij_tip_correct(dry_run=False)

    assert stat["kandydaci"] == 1, "juz oceniony wiersz nie powinien byc kandydatem"
    assert _wiersz(baza, rid_gotowy)["tip_correct"] == 0
    assert _wiersz(baza, rid_kandydat)["tip_correct"] == 1


# ── idempotencja ──────────────────────────────────────────────────────────

def test_drugie_uruchomienie_po_udanym_backfillu_nie_znajduje_kandydatow(baza):
    """Po zapisaniu `tip_correct` wiersz przestaje spelniac `WHERE tip_correct
    IS NULL" — kolejny przebieg nie ma juz czego robic."""
    from footstats.core.backtest import uzupelnij_tip_correct

    _wstaw(baza, "2 (wygrana gościa)", "0-3")

    pierwszy = uzupelnij_tip_correct(dry_run=False)
    drugi    = uzupelnij_tip_correct(dry_run=False)

    assert pierwszy == {"kandydaci": 1, "uzupelnione": 1, "pominiete": 0}
    assert drugi == {"kandydaci": 0, "uzupelnione": 0, "pominiete": 0}
