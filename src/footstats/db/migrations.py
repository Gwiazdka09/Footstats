"""Database migration runner — SQLite + PostgreSQL dual-dialect support."""
from __future__ import annotations

import logging
import os
from typing import Literal

_log = logging.getLogger(__name__)


def _detect_dialect(conn) -> Literal["sqlite", "postgresql"]:
    """Detect database type by attempting a PostgreSQL-specific query."""
    try:
        conn.execute("SELECT version()")
        return "postgresql"
    except Exception:  # noqa: broad-except — DB probe, driver-specific exceptions vary
        return "sqlite"


def _get_migrations_for_dialect(dialect: Literal["sqlite", "postgresql"]) -> list[tuple[int, str, list[str]]]:
    """Return migration SQL statements appropriate for the detected dialect."""

    if dialect == "sqlite":
        return [
            (
                1,
                "create_users_table",
                [
                    """CREATE TABLE IF NOT EXISTS users (
                        id            INTEGER PRIMARY KEY AUTOINCREMENT,
                        username      TEXT NOT NULL UNIQUE,
                        password_hash TEXT NOT NULL,
                        email         TEXT UNIQUE,
                        created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        is_active     BOOLEAN NOT NULL DEFAULT TRUE
                    )""",
                    "CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)",
                ],
            ),
            (
                2,
                "add_user_id_to_user_tables",
                [
                    "INSERT OR IGNORE INTO users (id, username, password_hash) VALUES (1, 'admin', 'changeme')",
                    "ALTER TABLE coupons ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id)",
                    "UPDATE coupons SET user_id = 1 WHERE user_id IS NULL",
                    "CREATE INDEX IF NOT EXISTS idx_coupons_user ON coupons(user_id)",
                    "ALTER TABLE bankroll_state ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id)",
                    "UPDATE bankroll_state SET user_id = 1 WHERE user_id IS NULL",
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_bankroll_state_user ON bankroll_state(user_id)",
                    "ALTER TABLE bankroll_history ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id)",
                    "UPDATE bankroll_history SET user_id = 1 WHERE user_id IS NULL",
                    "CREATE INDEX IF NOT EXISTS idx_bankroll_history_user ON bankroll_history(user_id)",
                    "ALTER TABLE bot_settings ADD COLUMN IF NOT EXISTS user_id INTEGER DEFAULT 1",
                    "UPDATE bot_settings SET user_id = 1 WHERE user_id IS NULL",
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_bot_settings_user_key ON bot_settings(user_id, key)",
                ],
            ),
            (
                3,
                "fix_bankroll_state_id_generation",
                ["-- SQLite auto-increments by default, no sequence needed"],
            ),
            (
                4,
                "add_is_admin_to_users",
                [
                    "ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT FALSE",
                    "UPDATE users SET is_admin = TRUE WHERE username = 'admin'",
                ],
            ),
        ]
    else:  # postgresql
        return [
            (
                1,
                "create_users_table",
                [
                    """CREATE TABLE IF NOT EXISTS users (
                        id            SERIAL PRIMARY KEY,
                        username      TEXT NOT NULL UNIQUE,
                        password_hash TEXT NOT NULL,
                        email         TEXT UNIQUE,
                        created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        is_active     BOOLEAN NOT NULL DEFAULT TRUE
                    )""",
                    "CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)",
                ],
            ),
            (
                2,
                "add_user_id_to_user_tables",
                [
                    "INSERT INTO users (id, username, password_hash) VALUES (1, 'admin', 'changeme') ON CONFLICT DO NOTHING",
                    "SELECT setval(pg_get_serial_sequence('users', 'id'), COALESCE((SELECT MAX(id) FROM users), 1))",
                    "ALTER TABLE coupons ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id)",
                    "UPDATE coupons SET user_id = 1 WHERE user_id IS NULL",
                    "CREATE INDEX IF NOT EXISTS idx_coupons_user ON coupons(user_id)",
                    "ALTER TABLE bankroll_state DROP CONSTRAINT IF EXISTS bankroll_state_id_check",
                    "ALTER TABLE bankroll_state ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id)",
                    "UPDATE bankroll_state SET user_id = 1 WHERE user_id IS NULL",
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_bankroll_state_user ON bankroll_state(user_id)",
                    "ALTER TABLE bankroll_history ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id)",
                    "UPDATE bankroll_history SET user_id = 1 WHERE user_id IS NULL",
                    "CREATE INDEX IF NOT EXISTS idx_bankroll_history_user ON bankroll_history(user_id)",
                    "ALTER TABLE bot_settings DROP CONSTRAINT IF EXISTS bot_settings_pkey",
                    "ALTER TABLE bot_settings ADD COLUMN IF NOT EXISTS user_id INTEGER DEFAULT 1",
                    "UPDATE bot_settings SET user_id = 1 WHERE user_id IS NULL",
                    "ALTER TABLE bot_settings ALTER COLUMN user_id SET NOT NULL",
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_bot_settings_user_key ON bot_settings(user_id, key)",
                ],
            ),
            (
                3,
                "fix_bankroll_state_id_generation",
                [
                    "CREATE SEQUENCE IF NOT EXISTS bankroll_state_id_seq",
                    "SELECT setval('bankroll_state_id_seq', COALESCE((SELECT MAX(id) FROM bankroll_state), 0) + 1)",
                    "ALTER TABLE bankroll_state ALTER COLUMN id SET DEFAULT nextval('bankroll_state_id_seq')",
                ],
            ),
            (
                4,
                "add_is_admin_to_users",
                [
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT FALSE",
                    "UPDATE users SET is_admin = TRUE WHERE username = 'admin'",
                ],
            ),
        ]


def _ensure_migrations_table(conn, dialect: Literal["sqlite", "postgresql"]) -> None:
    """Create schema_migrations table if not exists."""
    if dialect == "sqlite":
        sql = """CREATE TABLE IF NOT EXISTS schema_migrations (
            version     INTEGER PRIMARY KEY,
            description TEXT,
            applied_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )"""
    else:
        sql = """CREATE TABLE IF NOT EXISTS schema_migrations (
            version     INTEGER PRIMARY KEY,
            description TEXT,
            applied_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )"""
    conn.execute(sql)
    conn.commit()


def run_migrations() -> None:
    """Apply pending migrations for the detected DB dialect. Safe to call on every startup."""
    from footstats.utils.db import connect

    with connect() as conn:
        dialect = _detect_dialect(conn)
        _log.info("Detected dialect: %s", dialect)
        _ensure_migrations_table(conn, dialect)
        applied: set[int] = {
            r["version"]
            for r in conn.execute("SELECT version FROM schema_migrations").fetchall()
        }

    migrations = _get_migrations_for_dialect(dialect)
    for version, description, statements in migrations:
        if version in applied:
            continue
        _log.info("Migration %d (%s): %s", version, dialect, description)
        with connect() as conn:
            for sql in statements:
                if sql.strip() and not sql.strip().startswith("--"):
                    try:
                        conn.execute(sql)
                    except Exception as e:
                        _log.warning("SQL ignored in %s (idempotent): %s", dialect, e)
            conn.execute(
                "INSERT INTO schema_migrations (version, description) VALUES (?, ?)",
                (version, description),
            )
        _log.info("Migration %d done.", version)

        # CRITICAL: Seed the admin user immediately after creating the users table
        # so that subsequent migrations (like adding foreign keys) don't fail.
        if version == 1:
            seed_admin_user()

    _log.info("All migrations up to date.")


def seed_admin_user() -> None:
    """Upsert admin user from FOOTSTATS_USER / FOOTSTATS_PASSWORD_HASH env vars.

    Zawsze nadpisuje hash - env var jest source of truth dla hasla admina.
    Dzieki temu redeploy z nowym hashem natychmiast dziala.
    """
    username = os.environ.get("FOOTSTATS_USER", "").strip()
    password_hash = os.environ.get("FOOTSTATS_PASSWORD_HASH", "").strip()
    if not username or not password_hash:
        _log.warning(
            "seed_admin_user: FOOTSTATS_USER lub FOOTSTATS_PASSWORD_HASH nie ustawione — "
            "brak usera w DB, logowanie do /preview bedzie niemozliwe."
        )
        return
    import psycopg2.errors as _pg_errors
    from footstats.utils.db import connect

    with connect() as conn:
        try:
            conn.execute(
                "INSERT INTO users (username, password_hash, is_admin, is_active)"
                " VALUES (?, ?, TRUE, TRUE)"
                " ON CONFLICT (username)"
                " DO UPDATE SET password_hash = EXCLUDED.password_hash,"
                " is_admin = TRUE, is_active = TRUE",
                (username, password_hash),
            )
        except _pg_errors.UndefinedColumn:
            # is_admin column not yet added (pre-migration v4) — will be set by v4
            conn.rollback()
            conn.execute(
                "INSERT INTO users (username, password_hash, is_active)"
                " VALUES (?, ?, TRUE)"
                " ON CONFLICT (username)"
                " DO UPDATE SET password_hash = EXCLUDED.password_hash, is_active = TRUE",
                (username, password_hash),
            )
    _log.info("Admin user '%s' seeded/updated.", username)
