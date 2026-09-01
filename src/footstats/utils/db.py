"""PostgreSQL connection factory — drop-in replacement for sqlite3 usage."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import psycopg2.pool

_pool: "psycopg2.pool.ThreadedConnectionPool | None" = None


def _get_pool() -> "psycopg2.pool.ThreadedConnectionPool":
    global _pool
    if _pool is None:
        import psycopg2.pool as _pg_pool
        url = os.environ.get("DATABASE_URL")
        if not url:
            try:
                from dotenv import load_dotenv
                from pathlib import Path
                load_dotenv(Path(__file__).parents[3] / ".env")
                url = os.environ.get("DATABASE_URL")
            except ImportError:
                pass
        if not url:
            raise RuntimeError("DATABASE_URL env var not set — dodaj connection string Supabase do Cloud Run")
        # Keepalives zapobiegają zrywaniu idle connections przez pooler Supabase/firewall.
        _pool = _pg_pool.ThreadedConnectionPool(
            minconn=1, maxconn=10, dsn=url,
            keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=5,
        )
    return _pool


def _natywna(v):
    """Skalar numpy → odpowiednik natywny Pythona. Reszta bez zmian.

    `numpy.float64` jest PODKLASĄ Pythonowego `float`, więc psycopg2 adaptuje ją
    swoim adapterem dla floatów — a ten używa `repr()`. Do NumPy 1.x
    `repr(np.float64(0.5))` dawało `'0.5'`; NumPy 2.x zmienił to na
    `'np.float64(0.5)'` i taki literał lądował w SQL, gdzie Postgres czyta `np`
    jako nazwę schematu:

        [AI] Nie udalo sie zapisac predykcji ...: schema "np" does not exist

    Zmierzone 01.09 na produkcji — przebieg zapisał ZERO predykcji. Awaria była
    nieregularna, bo zależała od tego, czy prawdopodobieństwa przyszły z Poissona
    (numpy) czy z Bzzoiro-ML (czyste floaty).

    Sprawdzamy `__module__`, a nie `isinstance`, żeby nie wciągać numpy do importu
    warstwy bazy — i żeby objąć wszystkie typy skalarne naraz.
    """
    if type(v).__module__ == "numpy" and hasattr(v, "item"):
        return v.item()
    return v


def _czysc_params(params):
    """Parametry zapytania z wartościami natywnymi. `None` przechodzi bez zmian."""
    if not params:
        return params
    return tuple(_natywna(p) for p in params)


class _Conn:
    """sqlite3-compatible psycopg2 connection wrapper."""

    def __init__(self) -> None:
        import psycopg2
        pool = _get_pool()
        raw = pool.getconn()
        if raw.closed:
            # Martwa conn z puli (Neon idle timeout) — wymień na świeżą
            try:
                pool.putconn(raw, close=True)
            except Exception:  # noqa: BLE001 — best-effort cleanup martwej conn
                pass
            raw = pool.getconn()
        self._raw = raw
        # Neon pooler (PgBouncer transaction-pooling) nie gwarantuje session
        # search_path → losowo "no schema has been selected" na unqualified
        # CREATE TABLE/SELECT (flaky start _init_db). Startup-options są odrzucane
        # przez pooler, więc ustawiamy per-połączenie jako SQL — w tej samej
        # transakcji co kolejne zapytania (ten sam backend → search_path trzyma).
        try:
            with raw.cursor() as _cur:
                _cur.execute("SET search_path TO public")
        except psycopg2.Error:
            # SET padło (na wpół-martwa conn z poolera) — oddaj ZAMKNIĘTĄ do puli,
            # inaczej conn nigdy nie wraca → wyciek → wyczerpanie puli (maxconn=10).
            try:
                pool.putconn(raw, close=True)
            except psycopg2.Error:
                pass
            raise

    @staticmethod
    def _fix(sql: str) -> str:
        return sql.replace("?", "%s")

    def execute(self, sql: str, params: tuple = ()):
        import psycopg2.extras as _extras
        cur = self._raw.cursor(cursor_factory=_extras.RealDictCursor)
        cur.execute(self._fix(sql), _czysc_params(params) or None)
        return cur

    def executemany(self, sql: str, seq):
        cur = self._raw.cursor()
        cur.executemany(self._fix(sql), (_czysc_params(p) for p in seq))
        return cur

    def executescript(self, script: str) -> None:
        """Execute multiple ;-separated DDL statements (PostgreSQL-compatible)."""
        cur = self._raw.cursor()
        for stmt in script.split(";"):
            stmt = stmt.strip()
            if stmt:
                cur.execute(stmt)

    def commit(self) -> None:
        self._raw.commit()

    def rollback(self) -> None:
        self._raw.rollback()

    def close(self) -> None:
        _get_pool().putconn(self._raw)  # type: ignore[arg-type]

    def __enter__(self) -> "_Conn":
        return self

    def __exit__(self, exc_type, *_) -> bool:
        if exc_type:
            self.rollback()
        else:
            self.commit()
        self.close()
        return False


def connect(wal: bool = True, foreign_keys: bool = True) -> _Conn:
    """Return a PostgreSQL connection. wal/foreign_keys ignored (PG handles natively)."""
    return _Conn()
