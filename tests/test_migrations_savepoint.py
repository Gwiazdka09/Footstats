"""Startup-safety: migracje DDL muszą izolować błąd pojedynczego statementu.

Na PostgreSQL błędne zapytanie (np. kolumna już istnieje przy idempotentnym
re-runie) abortuje CAŁĄ transakcję → następny INSERT do schema_migrations padłby
→ crash startupu. SAVEPOINT per-statement izoluje błąd. Dodatkowo except musi
łapać psycopg2.Error (nie tylko RuntimeError/ValueError/KeyError).
"""
import sqlite3
from pathlib import Path

import pytest

import footstats.db.migrations as mig
import footstats.utils.db as udb


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


class _ZamykajacyConn(sqlite3.Connection):
    """Połączenie SQLite zachowujące kontrakt `utils.db._Conn`: commit/rollback + close."""

    def __exit__(self, exc_type, *_) -> bool:
        if exc_type:
            self.rollback()
        else:
            self.commit()
        self.close()
        return False


@pytest.fixture
def baza_sqlite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Plik SQLite w tmp_path zamiast Postgresa; `connect` podmieniamy u źródła."""
    sciezka = tmp_path / "migracje.db"

    def _polacz(wal: bool = True, foreign_keys: bool = True) -> sqlite3.Connection:
        conn = sqlite3.connect(sciezka, factory=_ZamykajacyConn, timeout=5)
        conn.row_factory = sqlite3.Row
        return conn

    monkeypatch.setattr(udb, "connect", _polacz)
    monkeypatch.setattr(mig, "seed_admin_user", lambda: None)
    return sciezka


def _najwyzsza_wersja() -> int:
    return max(v for v, _, _ in mig._get_migrations_for_dialect("sqlite"))


def _liczba_wierszy_wersji(sciezka: Path, version: int) -> int:
    with sqlite3.connect(sciezka) as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version = ?", (version,)
        ).fetchone()[0]


def _usun_wiersz_wersji(sciezka: Path, version: int) -> None:
    with sqlite3.connect(sciezka) as conn:
        conn.execute("DELETE FROM schema_migrations WHERE version = ?", (version,))


def test_ponowny_start_po_usunieciu_wiersza_wersji_nie_rzuca(baza_sqlite: Path) -> None:
    # Arrange: pełna migracja, potem wiersz najwyższej wersji znika (ALTER już zrobiony)
    mig.run_migrations()
    najwyzsza = _najwyzsza_wersja()
    _usun_wiersz_wersji(baza_sqlite, najwyzsza)

    # Act: ponowny start nie może wywrócić procesu
    mig.run_migrations()

    # Assert: dokładnie jeden wiersz tej wersji
    assert _liczba_wierszy_wersji(baza_sqlite, najwyzsza) == 1


def test_wyscig_wpis_wersji_tuz_przed_insertem_nie_wywraca_startu(
    baza_sqlite: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange: najwyższa wersja nieukończona; drugi proces zapisze ją tuż po ALTER,
    # a przed INSERT-em tego procesu (symulacja wyścigu API vs job).
    mig.run_migrations()
    najwyzsza = _najwyzsza_wersja()
    _usun_wiersz_wersji(baza_sqlite, najwyzsza)
    statements_najwyzszej = next(
        s for v, _, s in mig._get_migrations_for_dialect("sqlite") if v == najwyzsza
    )
    oryginal_exec = mig._exec_statements

    def _exec_z_rywalem(conn, statements, dialect) -> None:
        oryginal_exec(conn, statements, dialect)
        if statements == statements_najwyzszej:
            with sqlite3.connect(baza_sqlite, timeout=5) as rywal:
                rywal.execute(
                    "INSERT INTO schema_migrations (version, description) VALUES (?, ?)",
                    (najwyzsza, "wpisane_przez_rywala"),
                )

    monkeypatch.setattr(mig, "_exec_statements", _exec_z_rywalem)

    # Act: nie może rzucić IntegrityError
    mig.run_migrations()

    # Assert: jeden wiersz, nadal wpis rywala (ON CONFLICT nie nadpisuje)
    assert _liczba_wierszy_wersji(baza_sqlite, najwyzsza) == 1
