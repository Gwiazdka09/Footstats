"""Dowód że autouse guard sieci (conftest._block_network) działa w trybie unit.

Guard jest aktywny tylko gdy DATABASE_URL NIE jest ustawiony (tryb unit/CI).
Lokalnie .env + load_dotenv() ustawia DATABASE_URL w trakcie sesji → guard się
wyłącza (tryb integracyjny) → te testy się skipują. Pełna ochrona = CI (bez .env).
"""
import os
import socket

import pytest


def _skip_if_integracyjny():
    # Sprawdzane w RUNTIME (nie import-time) — inny test mógł zrobić load_dotenv().
    if os.environ.get("DATABASE_URL"):
        pytest.skip("guard wyłączony (DATABASE_URL ustawiony — tryb integracyjny)")


def test_blokuje_nielokalne_polaczenie():
    _skip_if_integracyjny()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(RuntimeError, match="sieci"):
            s.connect(("8.8.8.8", 53))
    finally:
        s.close()


def test_localhost_dozwolony():
    _skip_if_integracyjny()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.1)
    try:
        s.connect_ex(("127.0.0.1", 1))  # port zamknięty, ale guard NIE blokuje localhost
    except RuntimeError:
        pytest.fail("guard nie powinien blokować localhost")
    finally:
        s.close()
