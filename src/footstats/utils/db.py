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
            raise RuntimeError("DATABASE_URL env var not set — add Neon.tech connection string to Cloud Run")
        # Keepalives zapobiegają zrywaniu idle connections przez Neon/firewall
        _pool = _pg_pool.ThreadedConnectionPool(
            minconn=1, maxconn=10, dsn=url,
            keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=5,
        )
    return _pool


class _Conn:
    """sqlite3-compatible psycopg2 connection wrapper."""

    def __init__(self) -> None:
        pool = _get_pool()
        raw = pool.getconn()
        if raw.closed:
            # Martwa conn z puli (Neon idle timeout) — wymień na świeżą
            try:
                pool.putconn(raw, close=True)
            except Exception:
                pass
            raw = pool.getconn()
        self._raw = raw

    @staticmethod
    def _fix(sql: str) -> str:
        return sql.replace("?", "%s")

    def execute(self, sql: str, params: tuple = ()):
        import psycopg2.extras as _extras
        cur = self._raw.cursor(cursor_factory=_extras.RealDictCursor)
        cur.execute(self._fix(sql), params or None)
        return cur

    def executemany(self, sql: str, seq):
        cur = self._raw.cursor()
        cur.executemany(self._fix(sql), seq)
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
