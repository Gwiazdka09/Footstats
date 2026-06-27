"""Startup-safety: migracje DDL muszą izolować błąd pojedynczego statementu.

Na PostgreSQL błędne zapytanie (np. kolumna już istnieje przy idempotentnym
re-runie) abortuje CAŁĄ transakcję → następny INSERT do schema_migrations padłby
→ crash startupu. SAVEPOINT per-statement izoluje błąd. Dodatkowo except musi
łapać psycopg2.Error (nie tylko RuntimeError/ValueError/KeyError).
"""
import pytest

import footstats.db.migrations as mig


class _FakeConn:
    def __init__(self, fail_on=None, exc=ValueError):
        self.calls: list[str] = []
        self.fail_on = fail_on
        self.exc = exc

    def execute(self, sql, params=()):
        s = sql.strip()
        self.calls.append(s)
        if self.fail_on is not None and s == self.fail_on:
            raise self.exc("kolumna już istnieje")
        return None


def test_savepoint_izoluje_blad_i_kontynuuje():
    conn = _FakeConn(fail_on="BAD SQL")
    mig._exec_statements(conn, ["GOOD 1", "BAD SQL", "GOOD 2"], "postgresql")
    # 3 niepuste statementy → 3 SAVEPOINT
    assert conn.calls.count("SAVEPOINT mig_stmt") == 3
    # błędny → ROLLBACK TO SAVEPOINT (recover transakcji)
    assert "ROLLBACK TO SAVEPOINT mig_stmt" in conn.calls
    # kontynuuje PO błędzie (nie przerywa migracji)
    assert "GOOD 2" in conn.calls


def test_pomija_puste_i_komentarze():
    conn = _FakeConn()
    mig._exec_statements(conn, ["", "  ", "-- komentarz", "REAL SQL"], "sqlite")
    assert conn.calls.count("SAVEPOINT mig_stmt") == 1
    assert "REAL SQL" in conn.calls


def test_lapie_psycopg2_error():
    psycopg2 = pytest.importorskip("psycopg2")
    conn = _FakeConn(fail_on="BAD", exc=psycopg2.Error)
    # NIE rzuca (psycopg2.Error w _DB_ERRORS)
    mig._exec_statements(conn, ["BAD"], "postgresql")
    assert "ROLLBACK TO SAVEPOINT mig_stmt" in conn.calls


def test_nieoczekiwany_blad_propaguje():
    # Błąd spoza _DB_ERRORS (np. TypeError) NIE jest cicho połykany.
    conn = _FakeConn(fail_on="BOOM", exc=TypeError)
    with pytest.raises(TypeError):
        mig._exec_statements(conn, ["BOOM"], "postgresql")
