"""
test_telegram_link_nonce.py — FAZA 15.7 (D7): weryfikacja własności czatu Telegram
przez nonce `/start <nonce>` w webhooku bota.

Testy NIE wysyłają nic na prawdziwy Telegram — `_reply`/`requests` są zamockowane.
DB jest zamockowana (SQLite w pamięci, sqlite3-Conn pattern) — żadnego dotyku
prod Neon (DATABASE_URL).
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

import pytest


class _SQLiteConn:
    """sqlite3 adapter zgodny z interfejsem footstats.utils.db._Conn (testowy double)."""

    def __init__(self, raw: sqlite3.Connection) -> None:
        self._raw = raw

    def execute(self, sql: str, params=()):
        return self._raw.execute(sql, params)

    def commit(self) -> None:
        self._raw.commit()

    def rollback(self) -> None:
        self._raw.rollback()

    def close(self) -> None:
        pass  # współdzielone połączenie w pamięci — nie zamykaj między `with`

    def __enter__(self) -> "_SQLiteConn":
        return self

    def __exit__(self, exc_type, *_args) -> bool:
        if exc_type:
            self.rollback()
        else:
            self.commit()
        return False


_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    username                TEXT NOT NULL UNIQUE,
    password_hash           TEXT NOT NULL DEFAULT 'x',
    is_active               BOOLEAN NOT NULL DEFAULT TRUE,
    telegram_chat_id        TEXT,
    telegram_link_nonce     TEXT,
    telegram_link_nonce_exp TIMESTAMP
);
"""


@pytest.fixture
def db_conn(monkeypatch):
    """Połączenie SQLite w pamięci podłączone pod footstats.utils.db.connect."""
    raw = sqlite3.connect(":memory:")
    raw.row_factory = sqlite3.Row
    raw.executescript(_SCHEMA)
    raw.commit()

    import footstats.utils.db as dbmod
    monkeypatch.setattr(dbmod, "connect", lambda: _SQLiteConn(raw))
    return raw


def _insert_user(raw: sqlite3.Connection, username: str = "kuba") -> int:
    cur = raw.execute(
        "INSERT INTO users (username, password_hash) VALUES (?, 'x')", (username,)
    )
    raw.commit()
    return cur.lastrowid


# ── Endpoint generujący nonce (api/auth.py) ────────────────────────────────────


class TestTelegramLinkStartEndpoint:
    """POST /api/telegram/link/start — generuje nonce dla zalogowanego usera."""

    @pytest.mark.unit
    def test_generuje_nonce_i_zapisuje_w_db(self, db_conn):
        from footstats.api.auth import telegram_link_start

        user_id = _insert_user(db_conn, "kuba")
        result = telegram_link_start(user_id=user_id)

        assert "nonce" in result
        assert len(result["nonce"]) >= 8
        assert result["expires_in"] == 900
        assert "instructions" in result

        row = db_conn.execute(
            "SELECT telegram_link_nonce, telegram_link_nonce_exp FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        assert row["telegram_link_nonce"] == result["nonce"]
        assert row["telegram_link_nonce_exp"] is not None

    @pytest.mark.unit
    def test_nonce_jest_unikalny_per_wywolanie(self, db_conn):
        from footstats.api.auth import telegram_link_start

        user_id = _insert_user(db_conn, "kuba")
        r1 = telegram_link_start(user_id=user_id)
        r2 = telegram_link_start(user_id=user_id)
        assert r1["nonce"] != r2["nonce"]

    @pytest.mark.unit
    def test_nie_ujawnia_nonce_innych_userow(self, db_conn):
        """Nonce zwrocony userowi A nie pokrywa siê z zapisanym dla usera B."""
        from footstats.api.auth import telegram_link_start

        user_a = _insert_user(db_conn, "alice")
        user_b = _insert_user(db_conn, "bob")
        result_a = telegram_link_start(user_id=user_a)
        telegram_link_start(user_id=user_b)

        row_b = db_conn.execute(
            "SELECT telegram_link_nonce FROM users WHERE id = ?", (user_b,)
        ).fetchone()
        assert row_b["telegram_link_nonce"] != result_a["nonce"]


# ── Webhook /start <nonce> (telegram_bot.py) ───────────────────────────────────


class TestTelegramStartWebhook:
    """Webhook `/start <nonce>` wiąże chat_id z kontem PRZED gate'em allowed-chat."""

    @pytest.mark.unit
    def test_valid_nonce_wiaze_chat_id_i_czysci_nonce(self, db_conn, monkeypatch):
        from footstats import telegram_bot as bot

        user_id = _insert_user(db_conn, "kuba")
        future = (datetime.now() + timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S")
        db_conn.execute(
            "UPDATE users SET telegram_link_nonce = ?, telegram_link_nonce_exp = ? WHERE id = ?",
            ("validnonce123", future, user_id),
        )
        db_conn.commit()

        # Bot nie skonfigurowany (brak admina) — /start musi działać mimo to.
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "")
        sent = {}
        monkeypatch.setattr(bot, "_reply", lambda chat_id, text: sent.update(chat_id=chat_id, text=text))

        bot._handle({"chat": {"id": 555444333}, "text": "/start validnonce123"})

        row = db_conn.execute(
            "SELECT telegram_chat_id, telegram_link_nonce FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        assert row["telegram_chat_id"] == "555444333"
        assert row["telegram_link_nonce"] is None
        assert "kuba" in sent["text"]
        assert "✅" in sent["text"]

    @pytest.mark.unit
    def test_invalid_nonce_nie_wiaze(self, db_conn, monkeypatch):
        from footstats import telegram_bot as bot

        monkeypatch.setenv("TELEGRAM_CHAT_ID", "")
        sent = {}
        monkeypatch.setattr(bot, "_reply", lambda chat_id, text: sent.update(chat_id=chat_id, text=text))

        bot._handle({"chat": {"id": 999}, "text": "/start totally-bogus-nonce"})

        rows = db_conn.execute("SELECT telegram_chat_id FROM users").fetchall()
        assert all(r["telegram_chat_id"] is None for r in rows)
        assert "text" in sent  # odpowiedź z błędem wysłana

    @pytest.mark.unit
    def test_expired_nonce_nie_wiaze(self, db_conn, monkeypatch):
        from footstats import telegram_bot as bot

        user_id = _insert_user(db_conn, "kuba")
        past = (datetime.now() - timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
        db_conn.execute(
            "UPDATE users SET telegram_link_nonce = ?, telegram_link_nonce_exp = ? WHERE id = ?",
            ("expirednonce", past, user_id),
        )
        db_conn.commit()

        monkeypatch.setenv("TELEGRAM_CHAT_ID", "")
        sent = {}
        monkeypatch.setattr(bot, "_reply", lambda chat_id, text: sent.update(chat_id=chat_id, text=text))

        bot._handle({"chat": {"id": 777}, "text": "/start expirednonce"})

        row = db_conn.execute(
            "SELECT telegram_chat_id, telegram_link_nonce FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        assert row["telegram_chat_id"] is None
        assert row["telegram_link_nonce"] == "expirednonce"  # nie wyczyszczony, bo nie zużyty

    @pytest.mark.unit
    def test_nonce_jednorazowy_drugie_uzycie_odrzucone(self, db_conn, monkeypatch):
        from footstats import telegram_bot as bot

        user_id = _insert_user(db_conn, "kuba")
        future = (datetime.now() + timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S")
        db_conn.execute(
            "UPDATE users SET telegram_link_nonce = ?, telegram_link_nonce_exp = ? WHERE id = ?",
            ("onceonly", future, user_id),
        )
        db_conn.commit()

        monkeypatch.setenv("TELEGRAM_CHAT_ID", "")
        monkeypatch.setattr(bot, "_reply", lambda chat_id, text: None)

        bot._handle({"chat": {"id": 111}, "text": "/start onceonly"})
        # Drugi atakujący próbuje tym samym (już zużytym) nonce z innego chat_id.
        sent2 = {}
        monkeypatch.setattr(bot, "_reply", lambda chat_id, text: sent2.update(chat_id=chat_id, text=text))
        bot._handle({"chat": {"id": 222}, "text": "/start onceonly"})

        row = db_conn.execute(
            "SELECT telegram_chat_id FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        assert row["telegram_chat_id"] == "111"  # nie nadpisany przez drugi atak
        assert "111" not in str(sent2)

    @pytest.mark.unit
    def test_start_dziala_przed_gate_em_allowed_chat(self, db_conn, monkeypatch):
        """Nowy user nie jest jeszcze `allowed` (TELEGRAM_CHAT_ID = admin) — /start musi przejść."""
        from footstats import telegram_bot as bot

        user_id = _insert_user(db_conn, "kuba")
        future = (datetime.now() + timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S")
        db_conn.execute(
            "UPDATE users SET telegram_link_nonce = ?, telegram_link_nonce_exp = ? WHERE id = ?",
            ("gateskip", future, user_id),
        )
        db_conn.commit()

        # Admin chat to inny chat_id niż ten, co wysyła /start.
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "999999")
        sent = {}
        monkeypatch.setattr(bot, "_reply", lambda chat_id, text: sent.update(chat_id=chat_id, text=text))

        bot._handle({"chat": {"id": 123123}, "text": "/start gateskip"})

        row = db_conn.execute(
            "SELECT telegram_chat_id FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        assert row["telegram_chat_id"] == "123123"
        assert sent.get("chat_id") == "123123"

    @pytest.mark.unit
    def test_inne_komendy_wciaz_za_gate_em_admina(self, db_conn, monkeypatch):
        """Komendy poza /start (np. /status) muszą zostać odrzucone dla nieautoryzowanego chat_id."""
        from footstats import telegram_bot as bot

        monkeypatch.setenv("TELEGRAM_CHAT_ID", "999999")
        called = {"reply": False}
        monkeypatch.setattr(bot, "_reply", lambda chat_id, text: called.update(reply=True))

        bot._handle({"chat": {"id": 123123}, "text": "/status"})

        assert called["reply"] is False
