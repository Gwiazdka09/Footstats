"""Testy współbieżnego dostępu do puli połączeń DB."""
import threading
import time
from unittest.mock import MagicMock, patch

import pytest


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_mock_pool(maxconn: int = 10):
    """Symuluje ThreadedConnectionPool z limitem połączeń."""
    semaphore = threading.Semaphore(maxconn)
    active = threading.local()

    mock_pool = MagicMock()

    def getconn():
        acquired = semaphore.acquire(timeout=2.0)
        if not acquired:
            raise Exception("Pool exhausted — timeout")
        mock_conn = MagicMock()
        mock_conn._semaphore = semaphore
        return mock_conn

    def putconn(conn):
        conn._semaphore.release()

    mock_pool.getconn = getconn
    mock_pool.putconn = putconn
    return mock_pool


# ── Testy ────────────────────────────────────────────────────────────────────

def test_concurrent_connections_no_deadlock():
    """10 wątków uzyskuje i zwalnia połączenia bez deadlocka."""
    mock_pool = _make_mock_pool(maxconn=5)
    errors: list[Exception] = []
    results: list[str] = []

    def worker(idx: int) -> None:
        try:
            conn = mock_pool.getconn()
            time.sleep(0.05)  # symulacja pracy
            mock_pool.putconn(conn)
            results.append(f"ok_{idx}")
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)

    assert not errors, f"Błędy: {errors}"
    assert len(results) == 10


def test_pool_exhaustion_raises_not_hangs():
    """Przy wyczerpaniu puli wątek dostaje błąd (nie wisi)."""
    mock_pool = _make_mock_pool(maxconn=2)
    conns = [mock_pool.getconn(), mock_pool.getconn()]  # zajmij wszystkie

    error_raised = threading.Event()

    def blocked_worker():
        try:
            mock_pool.getconn()
        except Exception:
            error_raised.set()

    t = threading.Thread(target=blocked_worker)
    t.start()
    t.join(timeout=3.0)

    assert error_raised.is_set(), "Pool exhaustion powinien podnieść wyjątek, nie wisieć"

    for c in conns:
        mock_pool.putconn(c)


def test_context_manager_releases_on_exception():
    """Połączenie wraca do puli nawet gdy wyjątek."""
    from footstats.utils.db import _Conn

    mock_raw_conn = MagicMock()
    mock_raw_conn.cursor.return_value.__enter__ = MagicMock()
    mock_raw_conn.cursor.return_value.__exit__ = MagicMock()

    mock_pool = MagicMock()
    mock_pool.getconn.return_value = mock_raw_conn
    putconn_calls: list = []
    mock_pool.putconn = lambda c: putconn_calls.append(c)

    with patch("footstats.utils.db._get_pool", return_value=mock_pool):
        try:
            with _Conn() as _conn:
                raise ValueError("Symulowany błąd")
        except ValueError:
            pass

    assert len(putconn_calls) == 1, "putconn powinien być wywołany mimo wyjątku"


def test_context_manager_commits_on_success():
    """Commit wywoływany przy normalnym wyjściu z context managera."""
    from footstats.utils.db import _Conn

    mock_raw_conn = MagicMock()
    mock_pool = MagicMock()
    mock_pool.getconn.return_value = mock_raw_conn
    mock_pool.putconn = MagicMock()

    with patch("footstats.utils.db._get_pool", return_value=mock_pool):
        with _Conn():
            pass

    mock_raw_conn.commit.assert_called_once()
    mock_raw_conn.rollback.assert_not_called()


def test_context_manager_rollbacks_on_exception():
    """Rollback wywoływany przy wyjątku."""
    from footstats.utils.db import _Conn

    mock_raw_conn = MagicMock()
    mock_pool = MagicMock()
    mock_pool.getconn.return_value = mock_raw_conn
    mock_pool.putconn = MagicMock()

    with patch("footstats.utils.db._get_pool", return_value=mock_pool):
        try:
            with _Conn():
                raise RuntimeError("crash")
        except RuntimeError:
            pass

    mock_raw_conn.rollback.assert_called_once()
    mock_raw_conn.commit.assert_not_called()


def test_pool_reuse_after_release():
    """Po zwolnieniu połączenia można je ponownie uzyskać."""
    mock_pool = _make_mock_pool(maxconn=1)

    conn1 = mock_pool.getconn()
    mock_pool.putconn(conn1)
    conn2 = mock_pool.getconn()  # nie powinno rzucić
    mock_pool.putconn(conn2)

    assert conn2 is not None
