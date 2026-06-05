"""Resolve operator/admin account (default Admin_JG) for coupons and bankroll."""

from __future__ import annotations

import logging
import os
from functools import lru_cache

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
    except (OSError, ValueError, RuntimeError) as exc:
        log.warning("resolve_admin_user_id: %s - fallback user_id=%s", exc, fallback)
    return fallback


def clear_admin_user_cache() -> None:
    """Clear cache after migration or in tests."""
    resolve_admin_user_id.cache_clear()
