#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
preflight_footstats.py � sprawdzenie ?rodowiska przed operatorem / daily_agent.

U?ycie:
    python scripts/preflight_footstats.py
    python scripts/preflight_footstats.py --strict
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"

CHECKS = [
    ("GROQ_API_KEY", True, "Groq LLM", 10),
    ("JWT_SECRET", True, "JWT", 32),
    ("SECRET_KEY", False, "FastAPI secret", 16),
    ("TELEGRAM_BOT_TOKEN", False, "Telegram bot", 10),
    ("TELEGRAM_CHAT_ID", False, "Telegram chat", 3),
    ("BZZOIRO_KEY", False, "Bzzoiro ML", 8),
]

PLACEHOLDER_FRAGMENTS = ("your_", "example", "changeme", "placeholder")


def _check_var(key: str, required: bool, desc: str, min_len: int) -> tuple[str, str]:
    val = os.getenv(key, "").strip()
    if not val:
        return (RED if required else YELLOW, "BRAK")
    if len(val) < min_len:
        return (YELLOW, f"ZA KR�TKI ({len(val)} < {min_len})")
    if any(p in val.lower() for p in PLACEHOLDER_FRAGMENTS):
        return (YELLOW, "PLACEHOLDER")
    return (GREEN, "OK")


def _check_db() -> tuple[bool, str]:
    url = os.getenv("DATABASE_URL", "").strip()
    try:
        if url:
            import psycopg2

            conn = psycopg2.connect(url, connect_timeout=5)
            conn.close()
            return True, "PostgreSQL OK (DATABASE_URL)"
        from footstats.config import DB_PATH
        import sqlite3

        if not DB_PATH.exists():
            return False, f"Brak pliku DB: {DB_PATH}"
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("SELECT 1").fetchone()
        return True, f"SQLite OK ({DB_PATH.name})"
    except Exception as e:
        return False, str(e)[:80]


def _check_admin_user() -> tuple[bool, str]:
    try:
        from footstats.utils.admin_user import get_operator_admin_username, resolve_admin_user_id

        name = get_operator_admin_username()
        uid = resolve_admin_user_id()
        return True, f"{name} ? user_id={uid}"
    except Exception as e:
        return False, str(e)[:80]


def _check_groq() -> tuple[bool, str]:
    key = os.getenv("GROQ_API_KEY", "").strip()
    if not key or any(p in key.lower() for p in PLACEHOLDER_FRAGMENTS):
        return True, "Pomini?to (brak klucza)"
    try:
        from groq import Groq

        client = Groq(api_key=key)
        client.models.list()
        return True, "Klucz aktywny"
    except Exception as e:
        msg = str(e)[:80]
        if "401" in msg or "invalid" in msg.lower():
            return False, "Nieprawid?owy klucz"
        return False, msg


def _check_telegram() -> tuple[bool, str]:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token or any(p in token.lower() for p in PLACEHOLDER_FRAGMENTS):
        return True, "Pomini?to (opcjonalny)"
    try:
        import requests

        r = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=5)
        if r.ok:
            name = r.json().get("result", {}).get("username", "?")
            return True, f"@{name}"
        return False, f"HTTP {r.status_code}"
    except Exception as e:
        return False, str(e)[:60]


def main() -> int:
    parser = argparse.ArgumentParser(description="FootStats preflight (SQLite)")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    env_file = ROOT / ".env"
    print(f"\n{'='*60}\n  FootStats Preflight (SQLite)\n  .env: {'OK' if env_file.exists() else 'brak'}\n{'='*60}\n")

    errors = warnings = 0

    print("?? Zmienne ??")
    for key, req, desc, min_len in CHECKS:
        color, status = _check_var(key, req, desc, min_len)
        m = "?" if color == RED else ("?" if color == YELLOW else "?")
        print(f"  {color}{m}{RESET} {key:<22} {status:<28} {desc}")
        if color == RED:
            errors += 1
        elif color == YELLOW:
            warnings += 1

    print("\n-- Polaczenia --")
    ok, msg = _check_db()
    print(f"  {'OK' if ok else 'FAIL'} {'Database':<22} {msg}")
    if not ok:
        errors += 1

    ok, msg = _check_admin_user()
    print(f"  {'?' if ok else '?'} {'Admin user':<22} {msg}")
    if not ok:
        warnings += 1

    ok, msg = _check_groq()
    if os.getenv("GROQ_API_KEY", "").strip():
        print(f"  {'?' if ok else '?'} {'Groq API':<22} {msg}")
        if not ok:
            errors += 1

    ok, msg = _check_telegram()
    print(f"  {'?' if ok else '?'} {'Telegram':<22} {msg}")

    print(f"\n{'='*60}")
    if errors:
        print(f"  {RED}FAIL{RESET} � {errors} b??d�w, {warnings} ostrze?e?")
        return 1
    if warnings and args.strict:
        print(f"  {YELLOW}WARN{RESET} � --strict")
        return 1
    print(f"  {GREEN}PASS{RESET}")
    print(f"{'='*60}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
