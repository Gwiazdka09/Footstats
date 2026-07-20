"""Resolve operator/admin account (default Admin_JG) for coupons and bankroll."""

from __future__ import annotations

import logging
import os
from functools import lru_cache

import psycopg2

log = logging.getLogger(__name__)


def get_operator_admin_username() -> str:
    """Username from OPERATOR_ADMIN_USERNAME env, default Admin_JG."""
    return (os.getenv("OPERATOR_ADMIN_USERNAME", "Admin_JG") or "Admin_JG").strip()


@lru_cache(maxsize=1)
def resolve_admin_user_id(fallback: int = 1) -> int:
    """
    Return user_id from users table.
    On missing user or DB error - fallback (default 1).
    """
    username = get_operator_admin_username()
    try:
        from footstats.utils.db import connect

        with connect() as conn:
            row = conn.execute(
                "SELECT id FROM users WHERE username = ? AND is_active = TRUE",
                (username,),
            ).fetchone()
        if row:
            return int(row["id"])
        log.warning(
            "User %s not found in DB - fallback user_id=%s",
            username,
            fallback,
        )
    except (OSError, ValueError, RuntimeError, psycopg2.Error) as exc:
        # psycopg2.Error: martwa DB (np. quota-block 18-20.07) nie może wywalać agenta
        log.warning("resolve_admin_user_id: %s - fallback user_id=%s", exc, fallback)
    return fallback


def clear_admin_user_cache() -> None:
    """Clear cache after migration or in tests."""
    resolve_admin_user_id.cache_clear()


@lru_cache(maxsize=1)
def resolve_system_user_id() -> int | None:
    """
    Return user_id for konto 'System' (auto-generowane propozycje dnia).
    None jeśli konto nie istnieje (np. migracja #5 nie była uruchomiona).
    """
    try:
        from footstats.utils.db import connect

        with connect() as conn:
            row = conn.execute(
                "SELECT id FROM users WHERE username = 'System' AND is_active = TRUE",
            ).fetchone()
        if row:
            return int(row["id"])
        log.warning("Konto 'System' nie znalezione w DB - propozycje dnia nie będą udostępnione")
    except (OSError, ValueError, RuntimeError, psycopg2.Error) as exc:
        log.warning("resolve_system_user_id: %s", exc)
    return None


def clear_system_user_cache() -> None:
    """Clear cache after migration or in tests."""
    resolve_system_user_id.cache_clear()
