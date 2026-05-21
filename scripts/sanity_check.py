#!/usr/bin/env python
"""
sanity_check.py — Sprawdza konfigurację przed uruchomieniem FootStats.

Użycie:
    python scripts/sanity_check.py
    python scripts/sanity_check.py --strict   # błąd na opcjonalnych też
"""
import argparse
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

load_dotenv()

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"

CHECKS = [
    # (klucz, wymagany, opis, min_len)
    ("DATABASE_URL",      False, "PostgreSQL (opcjonalnie; bez tego SQLite DB_PATH)", 20),
    ("GROQ_API_KEY",      True,  "Groq LLM (AI kupony)",            10),
    ("JWT_SECRET",        True,  "JWT podpisywanie tokenów",        32),
    ("SECRET_KEY",        True,  "FastAPI secret key",              32),
    ("FOOTBALL_API_KEY",  False, "football-data.org (wyniki)",      8),
    ("APISPORTS_KEY",     False, "api-sports.io (statystyki)",      8),
    ("BZZOIRO_KEY",       False, "Bzzoiro ML (kandydaci)",          8),
    ("TELEGRAM_BOT_TOKEN",False, "Telegram powiadomienia",         10),
    ("TELEGRAM_CHAT_ID",  False, "Telegram chat ID",                3),
    ("STS_LOGIN",         False, "STS konto (scraper)",             3),
    ("SUPERBET_LOGIN",    False, "Superbet konto (scraper)",        3),
]

PLACEHOLDER_FRAGMENTS = ("your_", "example", "changeme", "placeholder")


def _check_var(key: str, required: bool, desc: str, min_len: int) -> tuple[str, str]:
    val = os.getenv(key, "").strip()
    if not val:
        status = "BRAK"
        color = RED if required else YELLOW
        return color, status
    if len(val) < min_len:
        return YELLOW, f"ZA KRÓTKI ({len(val)} < {min_len})"
    if any(p in val.lower() for p in PLACEHOLDER_FRAGMENTS):
        return YELLOW, "PLACEHOLDER (nie uzupełniony)"
    return GREEN, "OK"


def _check_db() -> tuple[bool, str]:
    url = os.getenv("DATABASE_URL", "").strip()
    try:
        if url:
            import psycopg2
            conn = psycopg2.connect(url, connect_timeout=5)
            conn.close()
            return True, "PostgreSQL OK"
        root = Path(__file__).resolve().parent.parent
        db = root / "data" / "footstats_backtest.db"
        if not db.exists():
            return False, f"Brak SQLite: {db}"
        import sqlite3
        with sqlite3.connect(db) as conn:
            conn.execute("SELECT 1").fetchone()
        return True, f"SQLite OK ({db.name})"
    except Exception as e:
        return False, str(e)[:80]


def _check_groq() -> tuple[bool, str]:
    try:
        from groq import Groq
        client = Groq(api_key=os.getenv("GROQ_API_KEY", ""))
        client.models.list()
        return True, "Klucz aktywny"
    except Exception as e:
        msg = str(e)[:80]
        if "401" in msg or "invalid" in msg.lower():
            return False, "Nieprawidłowy klucz API"
        return False, msg


def _check_telegram() -> tuple[bool, str]:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token or any(p in token.lower() for p in PLACEHOLDER_FRAGMENTS):
        return True, "Pominięto (opcjonalny)"
    try:
        import requests
        r = requests.get(
            f"https://api.telegram.org/bot{token}/getMe", timeout=5
        )
        if r.ok:
            name = r.json().get("result", {}).get("username", "?")
            return True, f"Bot @{name} aktywny"
        return False, f"HTTP {r.status_code}"
    except Exception as e:
        return False, str(e)[:60]


def main() -> int:
    parser = argparse.ArgumentParser(description="FootStats Sanity Check")
    parser.add_argument("--strict", action="store_true",
                        help="Fail na opcjonalnych też")
    args = parser.parse_args()

    env_file = Path(__file__).parent.parent / ".env"
    print(f"\n{'='*60}")
    print("  FootStats — Sanity Check")
    print(f"  .env: {'znaleziony' if env_file.exists() else 'BRAK — używam zmiennych systemowych'}")
    print(f"{'='*60}\n")

    errors = 0
    warnings = 0

    print("── Zmienne środowiskowe ──────────────────────────────────")
    for key, required, desc, min_len in CHECKS:
        color, status = _check_var(key, required, desc, min_len)
        marker = "✖" if color == RED else ("⚠" if color == YELLOW else "✓")
        print(f"  {color}{marker}{RESET} {key:<25} {status:<30} {desc}")
        if color == RED:
            errors += 1
        elif color == YELLOW:
            warnings += 1

    print("\n── Połączenia sieciowe ───────────────────────────────────")

    ok, msg = _check_db()
    print(f"  {'✓' if ok else '✖'} {'Baza danych':<25} {msg}")
    if not ok:
        errors += 1

    ok, msg = _check_groq()
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    if groq_key and not any(p in groq_key.lower() for p in PLACEHOLDER_FRAGMENTS):
        print(f"  {'✓' if ok else '✖'} {'Groq API':<25} {msg}")
        if not ok:
            errors += 1
    else:
        print(f"  ⚠ {'Groq API':<25} Pominięto (brak klucza)")
        warnings += 1

    ok, msg = _check_telegram()
    print(f"  {'✓' if ok else '⚠'} {'Telegram Bot':<25} {msg}")
    if not ok:
        warnings += 1

    print(f"\n{'='*60}")
    if errors:
        print(f"  {RED}FAIL{RESET} — {errors} błęd{'y' if errors < 5 else 'ów'}, {warnings} ostrzeżeń")
        print("  Uzupełnij .env przed uruchomieniem bota.")
    elif warnings and args.strict:
        print(f"  {YELLOW}WARN{RESET} — 0 błędów, {warnings} ostrzeżeń (--strict)")
        print("  Uzupełnij opcjonalne zmienne dla pełnej funkcjonalności.")
        return 1
    else:
        status = f"{YELLOW}{warnings} ostrzeżeń{RESET}" if warnings else f"{GREEN}wszystko OK{RESET}"
        print(f"  {GREEN}PASS{RESET} — {status}")
    print(f"{'='*60}\n")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
