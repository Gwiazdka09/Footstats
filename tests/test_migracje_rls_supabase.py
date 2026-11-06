"""Utwardzenie Supabase (audyt 5.11): RLS na public i brak grantow anon/authenticated."""
from __future__ import annotations

import logging
from contextlib import contextmanager

import pytest

import footstats.db.migrations as mig


class _Kursor:
    def __init__(self, sql_log: list[tuple[str, object]], exc: Exception | None) -> None:
        self._log, self._exc = sql_log, exc

    def execute(self, sql, params=None):
        self._log.append((sql, params))
        if self._exc is not None:
            raise self._exc


class _PgConn:
    """Atrapa polaczenia PG: zapisuje SQL i parametry, opcjonalnie rzuca blad."""

    def __init__(self, exc: Exception | None = None) -> None:
        self.calls: list[tuple[str, object]] = []
        self.rollbacks = 0
        self._exc = exc

    def execute(self, sql, params=()):
        s = sql.strip()
        if s.startswith("SELECT version()"):
            return _Wynik()
        if s.startswith("DO $$"):
            self.calls.append((sql, params))
            if self._exc is not None:
                raise self._exc
            return None
        if s.startswith("SELECT version FROM"):
            return _Wynik()
        return None

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        self.rollbacks += 1

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Wynik:
    def fetchall(self):
        return []


def _blok(conn: _PgConn) -> str:
    assert len(conn.calls) == 1, "blok DO ma isc jednym wywolaniem"
    return conn.calls[0][0]


def test_blok_zawiera_wymagane_instrukcje_i_nie_ma_force():
    conn = _PgConn()
    mig._utwardz_supabase(conn)
    sql = _blok(conn)
    assert "ENABLE ROW LEVEL SECURITY" in sql
    assert "format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY'" in sql
    assert "REVOKE ALL ON ALL TABLES IN SCHEMA public FROM" in sql
    assert "REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM" in sql
    assert "ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM" in sql
    assert "ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM" in sql
    assert "rolname = 'anon'" in sql
    assert "'authenticated'" in sql
    assert "FORCE" not in sql.upper()


def test_blok_ogranicza_alter_do_tabel_bez_rls():
    """ALTER bierze ACCESS EXCLUSIVE nawet przy włączonym RLS, więc tylko tabele bez RLS."""
    conn = _PgConn()
    mig._utwardz_supabase(conn)
    sql = _blok(conn)
    assert "relrowsecurity" in sql
    assert "NOT c.relrowsecurity" in sql


def test_blok_ustawia_lock_timeout_zanim_zrobi_alter():
    """Start API nie może czekać bez limitu na długie transakcje jobów."""
    conn = _PgConn()
    mig._utwardz_supabase(conn)
    sql = _blok(conn)
    assert "set_config('lock_timeout', '5s', true)" in sql
    assert sql.index("lock_timeout") < sql.index("ENABLE ROW LEVEL SECURITY")


def test_revoke_tylko_gdy_rola_ma_grant_na_tabele_public():
    conn = _PgConn()
    mig._utwardz_supabase(conn)
    sql = _blok(conn)
    assert "role_table_grants" in sql
    assert "table_schema = 'public'" in sql


def test_sql_bez_parametrow_i_bez_znaku_zapytania():
    """Wrapper zamienia '?' na '%s'; psycopg2 interpretuje '%' tylko przy params != None."""
    conn = _PgConn()
    mig._utwardz_supabase(conn)
    sql, params = conn.calls[0]
    assert not params
    assert "?" not in sql
    assert "%I" in sql


def test_przez_prawdziwy_wrapper_kursor_dostaje_sql_bez_podmiany(monkeypatch):
    """_Conn.execute z pustymi params -> cur.execute(sql, None): %I nietkniete."""
    import footstats.utils.db as udb

    log: list[tuple[str, object]] = []

    class _Raw:
        def cursor(self, cursor_factory=None):
            return _Kursor(log, None)

        def commit(self):
            pass

    wrapper = udb._Conn.__new__(udb._Conn)
    wrapper._raw = _Raw()
    monkeypatch.setattr("psycopg2.extras.RealDictCursor", object, raising=False)
    mig._utwardz_supabase(wrapper)
    sql, params = log[0]
    assert params is None
    assert "%I" in sql and "%s" not in sql


def test_blad_psycopg2_logowany_i_nie_przerywa(caplog):
    psycopg2 = pytest.importorskip("psycopg2")
    conn = _PgConn(exc=psycopg2.Error("brak uprawnien"))
    with caplog.at_level(logging.ERROR, logger=mig.__name__):
        mig._utwardz_supabase(conn)
    assert conn.rollbacks == 1
    assert any("utwardz_supabase" in r.getMessage() and "brak uprawnien" in r.getMessage()
              for r in caplog.records if r.levelno == logging.ERROR)


def test_run_migrations_pg_wywoluje_utwardzenie_na_koncu_nawet_gdy_blad(monkeypatch):
    psycopg2 = pytest.importorskip("psycopg2")
    conn = _PgConn(exc=psycopg2.Error("x"))
    monkeypatch.setattr("footstats.utils.db.connect", lambda *a, **k: conn)
    monkeypatch.setattr(mig, "_get_migrations_for_dialect", lambda d: [])
    mig.run_migrations()  # nie wolno rzucic
    assert len(conn.calls) == 1


def test_run_migrations_sqlite_nic_nie_wysyla(tmp_path, monkeypatch):
    import sqlite3

    wywolano: list[int] = []
    monkeypatch.setattr(mig, "_utwardz_supabase", lambda c: wywolano.append(1))

    @contextmanager
    def _ctx():
        c = sqlite3.connect(":memory:")
        c.row_factory = sqlite3.Row
        yield c
        c.close()

    monkeypatch.setattr("footstats.utils.db.connect", lambda *a, **k: _ctx())
    monkeypatch.setattr(mig, "_get_migrations_for_dialect", lambda d: [])
    mig.run_migrations()
    assert wywolano == []
