#!/usr/bin/env python3
"""PreToolUse guard — blokuje LOKALNE odpalenie LIVE pipeline'u.

Cel: pipeline produkcyjny (kupony na Telegram + zapis do prod Neon) działa
w Cloud Run Jobs (patrz docs/cloud_migration.md). Ręczne odpalenie live agenta
z lokalnej maszyny grozi podwójnymi kuponami na Telegram i zapisem do prod DB.

Mechanizm: Claude Code przekazuje payload hooka jako JSON na stdin. Jeśli komenda
Bash uruchamia live agenta, skrypt wypisuje powód na stderr i zwraca exit 2 →
Claude Code blokuje wywołanie. Escape hatch: ustaw FOOTSTATS_ALLOW_LIVE=1.

Blokowane są WYŁĄCZNIE realne uruchomienia modułów (anchor na `footstats.<modul>`),
nie testy (`tests/test_evening_agent.py`) ani faza draft (paper, bez prod-write).
"""
from __future__ import annotations

import json
import os
import re
import sys

# Anchor na `footstats.<modul>` (kropka) → NIE łapie `tests/test_evening_agent.py`.
_LIVE_PATTERNS: tuple[str, ...] = (
    # daily_agent tylko w fazie final (draft = paper, dozwolony)
    r"footstats\.daily_agent\b.*--faza[ =]+final",
    r"footstats[/\\]daily_agent\.py\b.*--faza[ =]+final",
    # evening_agent zawsze pisze do prod (settlement + Telegram)
    r"-m[ =]+footstats\.evening_agent\b",
    r"footstats[/\\]evening_agent\.py\b",
)

_MSG = (
    "BLOKADA (guard_live_ops): komenda uruchamia LIVE pipeline lokalnie "
    "(prod Neon + Telegram).\n"
    "Pipeline produkcyjny działa w Cloud Run Jobs — patrz docs/cloud_migration.md.\n"
    "Jeśli naprawdę musisz odpalić lokalnie: dodaj FOOTSTATS_ALLOW_LIVE=1 przed komendą.\n"
)


def main() -> int:
    # Windows: stderr bywa cp1250 → polskie znaki w komunikacie się psują.
    try:
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

    # Świadomy override — użytkownik wie co robi.
    if os.environ.get("FOOTSTATS_ALLOW_LIVE") == "1":
        return 0

    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # nie umiem sparsować → nie blokuj (fail-open, brak fałszywych alarmów)

    command = (payload.get("tool_input") or {}).get("command", "")
    if not command:
        return 0

    for pattern in _LIVE_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            sys.stderr.write(_MSG)
            return 2  # exit 2 → Claude Code blokuje tool call

    return 0


if __name__ == "__main__":
    sys.exit(main())
