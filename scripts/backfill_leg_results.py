"""
backfill_leg_results.py – Uzupełnia per-leg result/leg_won dla historycznych kuponów.

Źródła (w kolejności):
  1. football-data.org (pełna historia)
  2. API-Football (tylko ≤3 dni wstecz na Free planie)

Użycie:
    python scripts/backfill_leg_results.py          # wszystkie nieuzupełnione
    python scripts/backfill_leg_results.py --dry-run
"""

import json
import logging
import os
import sys
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
load_dotenv()

from footstats.core.backtest import _connect
from footstats.utils.betting import oblicz_tip_correct
from footstats.utils.normalize import normalize_team_name

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

FDB_KEY  = os.getenv("FOOTBALL_API_KEY", "").strip()
AFOOTKEY = os.getenv("APISPORTS_KEY", "").strip()

# Cache: date_str → lista meczów
_fdb_cache: dict[str, list] = {}
_af_cache:  dict[str, list] = {}


def _fdb_matches(date_str: str) -> list[dict]:
    if date_str in _fdb_cache:
        return _fdb_cache[date_str]
    if not FDB_KEY:
        return []
    try:
        r = requests.get(
            "https://api.football-data.org/v4/matches",
            headers={"X-Auth-Token": FDB_KEY},
            params={"dateFrom": date_str, "dateTo": date_str, "status": "FINISHED"},
            timeout=15,
        )
        r.raise_for_status()
        result = r.json().get("matches", [])
    except (requests.RequestException, ValueError, KeyError) as e:
        log.debug("football-data.org %s: %s", date_str, e)
        result = []
    _fdb_cache[date_str] = result
    return result


def _af_matches(date_str: str) -> list[dict]:
    if date_str in _af_cache:
        return _af_cache[date_str]
    if not AFOOTKEY:
        return []
    try:
        r = requests.get(
            "https://v3.football.api-sports.io/fixtures",
            headers={"x-apisports-key": AFOOTKEY},
            params={"date": date_str},
            timeout=15,
        )
        data = r.json()
        if data.get("errors"):
            log.debug("API-Football %s plan limit: %s", date_str, data["errors"])
            result = []
        else:
            result = data.get("response", [])
    except (requests.RequestException, ValueError, KeyError) as e:
        log.debug("API-Football %s: %s", date_str, e)
        result = []
    _af_cache[date_str] = result
    return result


def _sim(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_team_name(a), normalize_team_name(b)).ratio()


def _find_fdb(home: str, away: str, matches: list[dict]) -> str | None:
    best_score, best = 0.0, None
    for m in matches:
        fh = m.get("homeTeam", {}).get("name", "")
        fa = m.get("awayTeam", {}).get("name", "")
        score = (_sim(home, fh) + _sim(away, fa)) / 2
        if score >= 0.6 and score > best_score:
            ft = m.get("score", {}).get("fullTime", {})
            hg, ag = ft.get("home"), ft.get("away")
            if hg is not None and ag is not None:
                best_score, best = score, f"{hg}-{ag}"
    return best


def _find_af(home: str, away: str, fixtures: list[dict]) -> str | None:
    best_score, best = 0.0, None
    for fix in fixtures:
        status = fix.get("fixture", {}).get("status", {}).get("short", "")
        if status not in ("FT", "AET", "PEN"):
            continue
        teams = fix.get("teams", {})
        fh = teams.get("home", {}).get("name", "")
        fa = teams.get("away", {}).get("name", "")
        goals = fix.get("goals", {})
        hg, ag = goals.get("home"), goals.get("away")
        if hg is None or ag is None:
            continue
        score = (_sim(home, fh) + _sim(away, fa)) / 2
        if score >= 0.6 and score > best_score:
            best_score, best = score, f"{hg}-{ag}"
    return best


def backfill(dry_run: bool = False) -> dict:
    stats = {"updated": 0, "partial": 0, "skipped": 0, "errors": 0}

    with _connect() as conn:
        rows = conn.execute(
            """SELECT id, status, match_date_first, legs_json
               FROM coupons
               WHERE match_date_first IS NOT NULL
                 AND match_date_first != '2099-12-31'
                 AND match_date_first != '2099-01-01'
               ORDER BY match_date_first"""
        ).fetchall()

    log.info("Kupony do backfill: %d", len(rows))

    for row in rows:
        d = dict(row)
        coupon_id = d["id"]
        date_str  = d["match_date_first"][:10]
        legs      = json.loads(d["legs_json"])

        # Pomijaj jeśli wszystkie już mają result (nawet None to wartość, sprawdzamy "result" in leg)
        legs_missing = [lg for lg in legs if "result" not in lg or lg.get("result") is None]
        if not legs_missing and all("leg_won" in lg for lg in legs):
            stats["skipped"] += 1
            continue

        log.info("Kupon #%d (%s) | %s | daty: %s", coupon_id, d["status"], date_str, date_str)

        fdb_matches = _fdb_matches(date_str)
        af_matches  = _af_matches(date_str)
        log.info("  Źródła: FDB=%d, AF=%d meczów", len(fdb_matches), len(af_matches))

        updated_legs = [dict(lg) for lg in legs]
        any_found = False
        any_missing = False

        for leg_idx, leg in enumerate(legs):
            # Jeśli już ma result, zachowaj
            if leg.get("result") is not None and "leg_won" in leg:
                continue

            home = leg.get("home", "") or leg.get("gospodarz", "")
            away = leg.get("away", "") or leg.get("goscie", "")
            tip  = leg.get("tip", "")

            if not home or not away:
                mecz = leg.get("mecz", "")
                if " vs " in mecz:
                    home, away = mecz.split(" vs ", 1)
                elif " - " in mecz:
                    home, away = mecz.split(" - ", 1)
                home, away = home.strip(), away.strip()

            res = _find_fdb(home, away, fdb_matches)
            if not res:
                res = _find_af(home, away, af_matches)
            # Źródło 3: FlashScore (~7 dni wstecz)
            if not res:
                try:
                    from footstats.scrapers.flashscore_results import get_match_result
                    res = get_match_result(home, away, date_str, cache_enabled=True)
                except (ImportError, OSError, RuntimeError) as e:
                    log.debug("FlashScore %s vs %s: %s", home, away, e)

            correct = oblicz_tip_correct(tip, res) if res else None
            updated_legs[leg_idx]["result"]  = res
            updated_legs[leg_idx]["leg_won"] = (
                True if correct == 1 else (False if correct == 0 else None)
            )

            icon = "✓" if correct == 1 else ("✗" if correct == 0 else "?")
            log.info("  [%s] %s vs %s | %s → %s", icon, home, away, tip, res or "brak")

            if res:
                any_found = True
            else:
                any_missing = True

        if not any_found:
            log.info("  → żadnego wyniku nie znaleziono, skip")
            stats["partial"] += 1
            continue

        if any_missing:
            stats["partial"] += 1
        else:
            stats["updated"] += 1

        if not dry_run:
            try:
                with _connect() as conn:
                    conn.execute(
                        "UPDATE coupons SET legs_json=? WHERE id=?",
                        (json.dumps(updated_legs, ensure_ascii=False), coupon_id),
                    )
                log.info("  → zapisano legs_json dla kuponu #%d", coupon_id)
            except (OSError, ValueError) as e:
                log.error("  Błąd zapisu kuponu #%d: %s", coupon_id, e)
                stats["errors"] += 1

    log.info(
        "Backfill zakończony: updated=%d partial=%d skipped=%d errors=%d",
        stats["updated"], stats["partial"], stats["skipped"], stats["errors"],
    )
    return stats


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    backfill(dry_run=args.dry_run)
