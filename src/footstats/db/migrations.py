"""Database migration runner — multi-user support (Beta)."""
from __future__ import annotations

import logging
import os

_log = logging.getLogger(__name__)

# Each entry: (version, description, [sql_statements])
# All statements must be idempotent (IF NOT EXISTS / IF EXISTS guards).
MIGRATIONS: list[tuple[int, str, list[str]]] = [
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
            # seed default admin so FK backfill to user_id=1 succeeds
            "INSERT INTO users (id, username, password_hash) VALUES (1, 'admin', 'changeme') ON CONFLICT DO NOTHING",
            "SELECT setval(pg_get_serial_sequence('users', 'id'), COALESCE((SELECT MAX(id) FROM users), 1))",
            # coupons
            "ALTER TABLE coupons ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id)",
            "UPDATE coupons SET user_id = 1 WHERE user_id IS NULL",
            "CREATE INDEX IF NOT EXISTS idx_coupons_user ON coupons(user_id)",
            # bankroll_state: drop singleton check, add user_id
            "ALTER TABLE bankroll_state DROP CONSTRAINT IF EXISTS bankroll_state_id_check",
            "ALTER TABLE bankroll_state ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id)",
            "UPDATE bankroll_state SET user_id = 1 WHERE user_id IS NULL",
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_bankroll_state_user ON bankroll_state(user_id)",
            # bankroll_history
            "ALTER TABLE bankroll_history ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id)",
            "UPDATE bankroll_history SET user_id = 1 WHERE user_id IS NULL",
            "CREATE INDEX IF NOT EXISTS idx_bankroll_history_user ON bankroll_history(user_id)",
            # bot_settings: swap PK from (key) to (user_id, key)
            "ALTER TABLE bot_settings DROP CONSTRAINT IF EXISTS bot_settings_pkey",
            "ALTER TABLE bot_settings ADD COLUMN IF NOT EXISTS user_id INTEGER DEFAULT 1",
            "UPDATE bot_settings SET user_id = 1 WHERE user_id IS NULL",
            "ALTER TABLE bot_settings ALTER COLUMN user_id SET NOT NULL",
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_bot_settings_user_key ON bot_settings(user_id, key)",
        ],
    ),
]


def _ensure_migrations_table(conn) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS schema_migrations (
            version     INTEGER PRIMARY KEY,
            description TEXT,
            applied_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    conn.commit()


def run_migrations() -> None:
    """Apply pending migrations. Safe to call on every startup."""
    from footstats.utils.db import connect

    with connect() as conn:
        _ensure_migrations_table(conn)
        applied: set[int] = {
            r["version"]
            for r in conn.execute("SELECT version FROM schema_migrations").fetchall()
        }

    for version, description, statements in MIGRATIONS:
        if version in applied:
            continue
        _log.info("Migration %d: %s", version, description)
        with connect() as conn:
            for sql in statements:
                conn.execute(sql)
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
    """Insert admin user from FOOTSTATS_USER / FOOTSTATS_PASSWORD_HASH env vars if missing."""
    username = os.environ.get("FOOTSTATS_USER", "").strip()
    password_hash = os.environ.get("FOOTSTATS_PASSWORD_HASH", "").strip()
    if not username or not password_hash:
        return
    from footstats.utils.db import connect

    with connect() as conn:
        conn.execute(
            "INSERT INTO users (username, password_hash)"
            " VALUES (?, ?) ON CONFLICT (username) DO NOTHING",
            (username, password_hash),
        )
    _log.info("Admin user '%s' seeded.", username)
