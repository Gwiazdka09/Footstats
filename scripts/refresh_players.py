#!/usr/bin/env python
"""
refresh_players.py — populacja bazy graczy (player_stats) z API-Football,
liga po lidze wg priorytetu (domyślnie: Liga Mistrzów → TOP5 → reszta).

Zasila goal_share dla Kontuzji v2 (`core.player_db`). Zapis do lokalnego SQLite
(`data/footstats_backtest.db`) — NIE prod Neon. Cache 24h + budżet klienta
APIFootball chronią przed przepalaniem limitu (free 100 req/dzień).

Użycie:
  python scripts/refresh_players.py                 # sezon bieżący, wszystkie ligi wg priorytetu
  python scripts/refresh_players.py --season 2024   # konkretny sezon (2024 = kampania 2024-25)
  python scripts/refresh_players.py --only 2,39,140 # tylko wybrane api_id lig
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from footstats.config import DB_PATH, ENV_APISPORTS  # noqa: E402
from footstats.scrapers.api_football import _APISPORTS_LIGI  # noqa: E402
from footstats.scrapers.player_stats import refresh_league_players  # noqa: E402
from footstats.core.player_db import team_goal_shares_recent  # noqa: E402

# Priorytet lig (api_id) — Liga Mistrzów pierwsza, potem TOP5, potem reszta.
_PRIORYTET: tuple[int, ...] = (
    2,    # UEFA Champions League
    39,   # Premier League
    140,  # La Liga
    135,  # Serie A
    78,   # Bundesliga
    61,   # Ligue 1
    88,   # Eredivisie
    94,   # Primeira Liga
    106,  # Ekstraklasa
    40,   # Championship
    71,   # Brasileirao
    253,  # MLS
    307,  # Saudi Pro League
    262,  # Liga MX
    144,  # Belgia Pro League
    179,  # Scottish Premiership
)


def _sezon_biezacy() -> int:
    now = datetime.now()
    return now.year if now.month > 6 else now.year - 1


def _kolejnosc(only: str | None) -> list[int]:
    if only:
        wybrane = [int(x) for x in only.split(",") if x.strip()]
        return [i for i in wybrane if i in _APISPORTS_LIGI]
    # priorytet najpierw, potem ewentualne nieujęte ligi z mapy
    reszta = [i for i in _APISPORTS_LIGI if i not in _PRIORYTET]
    return [i for i in _PRIORYTET if i in _APISPORTS_LIGI] + reszta


def main() -> int:
    ap = argparse.ArgumentParser(description="Populacja bazy graczy (goal_share) z API-Football.")
    ap.add_argument("--season", type=int, default=None, help="sezon (domyślnie bieżący)")
    ap.add_argument("--only", type=str, default=None, help="lista api_id po przecinku")
    args = ap.parse_args()

    key = (os.environ.get(ENV_APISPORTS) or "").strip()
    if not key:
        print(f"BŁĄD: brak {ENV_APISPORTS} w środowisku.", file=sys.stderr)
        return 1

    sezon = args.season if args.season is not None else _sezon_biezacy()
    ligi = _kolejnosc(args.only)
    print(f"Sezon {sezon} | DB {DB_PATH} | ligi: {len(ligi)} (priorytet: Liga Mistrzów pierwsza)\n")

    total = 0
    ok = puste = 0
    for api_id in ligi:
        info = _APISPORTS_LIGI[api_id]
        etykieta = f"{info['nazwa']} [{info['kod']}]"
        n = refresh_league_players(api_id, sezon, key, league_code=info["kod"])
        total += n
        if n:
            ok += 1
            print(f"  ✓ {etykieta:<34} +{n} graczy")
        else:
            puste += 1
            print(f"  · {etykieta:<34} 0 (pusto / 429 / brak sezonu)")

    print(f"\nRazem: {total} graczy | {ok} lig OK, {puste} pustych")

    # Sanity: goal_share dla topowych zespołów (lookup jak pipeline: fallback sezonowy)
    print("\nSanity goal_share:")
    for team in ("Real Madrid", "Liverpool", "Bayern Munich", "Paris Saint Germain", "Inter"):
        sh = team_goal_shares_recent(team, _sezon_biezacy(), lookback=2)
        if sh:
            top = sorted(sh.items(), key=lambda kv: kv[1], reverse=True)[:3]
            print(f"  {team:<20} {len(sh):>2} graczy | " + ", ".join(f"{n} {s:.0%}" for n, s in top))
        else:
            print(f"  {team:<20} BRAK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
