"""
FootStats Evening Agent
=======================
Uruchamiany o 23:00 — weryfikuje wyniki kuponów przez API-Football.

Użycie:
    python -m footstats.evening_agent
    python -m footstats.evening_agent --date 2026-04-09
"""

import os
import re
import sys
import argparse
from datetime import datetime
from pathlib import Path

from footstats.utils.normalize import normalize_team_name, team_similarity

import requests
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from footstats.core.coupon_tracker import (
    get_active_coupons,
    get_coupon_legs,
    update_coupon_status,
    init_coupon_tables,
    STATUS_ACTIVE,
)
from footstats.core.backtest import init_db, update_result
from footstats.utils.betting import oblicz_tip_correct
from footstats.core.bankroll import process_win

import logging
log = logging.getLogger(__name__)

console = Console()

API_BASE = "https://v3.football.api-sports.io"


# ── Helpers ───────────────────────────────────────────────────────────────────

_norm = normalize_team_name
_similar = team_similarity


def _wynik_z_fixture(fixture: dict) -> tuple[str, str, str] | None:
    """
    Parsuje fixture z API-Football.
    Zwraca (home_name, away_name, 'HG-AG') lub None jeśli mecz niezakończony.
    """
    status = fixture.get("fixture", {}).get("status", {}).get("short", "")
    if status not in ("FT", "AET", "PEN"):
        return None
    teams = fixture.get("teams", {})
    home = teams.get("home", {}).get("name", "")
    away = teams.get("away", {}).get("name", "")
    goals = fixture.get("goals", {})
    hg, ag = goals.get("home"), goals.get("away")
    if hg is None or ag is None:
        return None
    return home, away, f"{hg}-{ag}"


def _find_result(home: str, away: str, fixtures: list[dict]) -> str | None:
    """
    Fuzzy-match drużyn w liście fixtures API-Football.
    Zwraca wynik '2-1' lub None gdy brak dopasowania (próg similarności >= 0.6).
    """
    best_score = 0.0
    best_result: str | None = None
    for fix in fixtures:
        parsed = _wynik_z_fixture(fix)
        if not parsed:
            continue
        fh, fa, wynik = parsed
        score = (_similar(home, fh) + _similar(away, fa)) / 2
        if score > best_score and score >= 0.6:
            best_score = score
            best_result = wynik
    return best_result


def _save_coupon_legs(coupon_id: int, updated_legs: list[dict]) -> None:
    """Zapisuje zaktualizowane legs_json (z result/leg_won per leg) do DB."""
    import json
    from footstats.core.backtest import _connect as _db_connect
    try:
        with _db_connect() as conn:
            conn.execute(
                "UPDATE coupons SET legs_json=? WHERE id=?",
                (json.dumps(updated_legs, ensure_ascii=False), coupon_id),
            )
    except (OSError, ValueError) as e:
        log.warning("Błąd zapisu legs_json dla kuponu #%s: %s", coupon_id, e)


def _status_kuponu(nogi_statusy: list[str]) -> str:
    """
    Oblicza finalny status kuponu z listy statusów nóg.
    Wejście: lista 'WIN' | 'LOSS' | 'PENDING' | 'VOID'
    """
    if not nogi_statusy:
        return "VOID"
    if "PENDING" in nogi_statusy:
        return STATUS_ACTIVE  # "ACTIVE" — czekamy na resztę meczów
    if all(s == "WIN" for s in nogi_statusy):
        return "WON"
    if any(s == "LOSS" for s in nogi_statusy):
        return "LOST"
    if all(s == "VOID" for s in nogi_statusy):
        return "VOID"
    return "PARTIAL"


# ── API ───────────────────────────────────────────────────────────────────────

def _fetch_results_today(api_key: str, date_str: str, retries: int = 3) -> list[dict]:
    """Pobiera zakończone mecze z API-Football dla daty YYYY-MM-DD (retry x3)."""
    import time
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(
                f"{API_BASE}/fixtures",
                headers={"x-apisports-key": api_key},
                params={"date": date_str, "status": "FT"},
                timeout=15,
            )
            if r.status_code == 200:
                return r.json().get("response", [])
            console.print(f"[yellow]API-Football HTTP {r.status_code} (próba {attempt}/{retries})[/yellow]")
        except (requests.RequestException, ValueError, KeyError) as e:
            console.print(f"[yellow]API-Football błąd sieci (próba {attempt}/{retries}): {e}[/yellow]")
        if attempt < retries:
            time.sleep(10 * attempt)
    return []


# ── CLV ───────────────────────────────────────────────────────────────────────

def _find_fixture_id(home: str, away: str, fixtures: list[dict]) -> int | None:
    """Zwraca API-Football fixture.id dla pary drużyn, lub None."""
    for fix in fixtures:
        parsed = _wynik_z_fixture(fix)
        if not parsed:
            continue
        fh, fa, _ = parsed
        if (_similar(home, fh) + _similar(away, fa)) / 2 >= 0.6:
            return fix.get("fixture", {}).get("id")
    return None


def _fetch_closing_odds(api_key: str, fixture_id: int) -> float | None:
    """
    Pobiera kurs 1X2 'Home Win' z API-Football /odds dla danego fixture.
    Zwraca closing odds bukmachera (Bet365 id=1 lub pierwszy dostępny), lub None.
    """
    try:
        r = requests.get(
            f"{API_BASE}/odds",
            headers={"x-apisports-key": api_key},
            params={"fixture": fixture_id, "bet": 1},  # bet=1 → Match Winner
            timeout=10,
        )
        if r.status_code != 200:
            return None
        resp = r.json().get("response", [])
        if not resp:
            return None
        bookmakers = resp[0].get("bookmakers", [])
        if not bookmakers:
            return None
        bets = bookmakers[0].get("bets", [])
        if not bets:
            return None
        values = bets[0].get("values", [])
        # values: [{"value": "Home", "odd": "1.85"}, {"value": "Draw", ...}, ...]
        for v in values:
            if str(v.get("value", "")).lower() in ("home", "1"):
                return float(v["odd"])
    except (ValueError, KeyError, requests.RequestException):
        pass
    return None


# ── Telegram ──────────────────────────────────────────────────────────────────

def _send_telegram_summary(summary: dict, date_str: str) -> None:
    try:
        from footstats.utils.telegram_notify import send_message
        msg = (
            f"* Evening Report {date_str}*\n"
            f"Sprawdzono: {summary.get('checked', 0)} kuponów\n"
            f"Wygranych: {summary.get('won', 0)}\n"
            f"Przegranych: {summary.get('lost', 0)}\n"
            f"Oczekujących: {summary.get('active', 0)}"
        )
        send_message(msg)
    except (ImportError, OSError, RuntimeError):
        pass  # Telegram opcjonalny


# ── Główna funkcja ────────────────────────────────────────────────────────────

def run_evening_agent(date_str: str | None = None) -> dict:
    """
    Weryfikuje wyniki kuponów dla danej daty.
    Zwraca dict: {checked, won, lost, partial, active}.
    Uruchamiany o 23:00 przez Task Scheduler — automatyczne rozliczanie kuponu.
    """
    load_dotenv()
    api_key = os.getenv("APISPORTS_KEY", "").strip()
    if not api_key:
        console.print("[red]Brak APISPORTS_KEY w .env — evening agent zatrzymany[/red]")
        return {}

    date_str = date_str or datetime.now().strftime("%Y-%m-%d")
    from datetime import datetime as dt
    now = dt.now().strftime("%Y-%m-%d %H:%M:%S")
    console.rule(f"[bold cyan]Evening Agent START — {date_str} ({now})[/bold cyan]")
    console.print(f"[dim]Proces: Automatyczne rozliczanie kuponów (scheduled @ 23:00)[/dim]")

    init_coupon_tables()
    init_db()

    # Rozlicz WSZYSTKIE pending predykcje (nie tylko nogi kuponów) — standalone typy
    # Groq + System paper-trading. Bez tego predictions.tip_correct nie rośnie i
    # calibration_monitor / walidacja są zagłodzone (fix 06-18).
    try:
        from footstats.scrapers.results_updater import update_pending
        rp = update_pending(days_back=3, dry_run=False, verbose=False)
        console.print(f"[dim]Predykcje pending: rozliczono {rp.get('updated', 0)}[/dim]")
    except (OSError, ValueError, RuntimeError, ImportError) as e:
        console.print(f"[yellow]update_pending pominięty: {e}[/yellow]")

    # D2 (06-20): auto-refit kalibracji co +30 settled predykcji (gate i tak pod kontrolą usera).
    try:
        from footstats.core.probability_calibrator import maybe_refit_calibration
        if maybe_refit_calibration():
            console.print("[dim]Kalibracja: auto-refit wykonany (calibration.json zaktualizowany)[/dim]")
    except (OSError, ValueError, RuntimeError, ImportError) as e:
        console.print(f"[yellow]auto-refit kalibracji pominięty: {e}[/yellow]")

    fixtures = _fetch_results_today(api_key, date_str)
    console.print(f"[dim]API-Football: {len(fixtures)} zakończonych meczów[/dim]")

    # WSZYSCY userzy (System 408 + admin 2 + realni). Wcześniej default user_id=1 → 0 kuponów
    # (nikt nie ma user_id=1) → evening rozliczał 0. Stale DRAFT VOIDuje settle_active_coupons (daily_agent).
    active_coupons = get_active_coupons(user_id=None)
    console.print(f"[dim]Aktywne kupony do weryfikacji: {len(active_coupons)}[/dim]")

    summary: dict = {"checked": 0, "won": 0, "lost": 0, "partial": 0, "active": 0}
    nowe_wyniki = 0

    for kupon in active_coupons:
        legs = get_coupon_legs(kupon["id"])
        nogi_statusy: list[str] = []
        updated_legs = [dict(leg) for leg in legs]  # kopia z per-leg results

        for leg_idx, leg in enumerate(legs):
            home   = leg.get("gospodarz") or leg.get("home", "")
            away   = leg.get("goscie")    or leg.get("away", "")
            ai_tip = leg.get("tip") or leg.get("typ") or leg.get("ai_tip", "")

            wynik = _find_result(home, away, fixtures)
            if wynik is None:
                nogi_statusy.append("PENDING")
                updated_legs[leg_idx]["result"] = None
                updated_legs[leg_idx]["leg_won"] = None
                continue

            correct = oblicz_tip_correct(ai_tip, wynik)
            nogi_statusy.append("WIN" if correct == 1 else ("LOSS" if correct == 0 else "VOID"))

            # Zapisz per-leg wynik
            updated_legs[leg_idx]["result"] = wynik
            updated_legs[leg_idx]["leg_won"] = (
                True if correct == 1 else (False if correct == 0 else None)
            )
            nowe_wyniki += 1

            pred_id = leg.get("prediction_id")
            if pred_id:
                try:
                    update_result(pred_id, wynik)
                except (ValueError, KeyError) as e:
                    console.print(f"[yellow]Warning: Could not update prediction {pred_id}: {e}[/yellow]")

                try:
                    from footstats.core.clv_tracker import record_closing_odds
                    fix_id = _find_fixture_id(home, away, fixtures)
                    if fix_id:
                        closing = _fetch_closing_odds(api_key, fix_id)
                        if closing:
                            record_closing_odds(pred_id, closing)
                except (ImportError, ValueError, KeyError):
                    pass

        # Zapisz per-leg wyniki do DB
        _save_coupon_legs(kupon["id"], updated_legs)

        nowy_status = _status_kuponu(nogi_statusy)

        if nowy_status != STATUS_ACTIVE:
            payout = None
            if nowy_status == "WON":
                stake = kupon["stake_pln"] or 10.0
                odds  = kupon["total_odds"] or 1.0
                payout = round(stake * odds * 0.88, 2)  # podatek 12%
            if nowy_status == "WON" and payout:
                process_win(payout, f"Wygrana kuponu ID={kupon['id']}")

            update_coupon_status(kupon["id"], nowy_status, payout_pln=payout)
            key = nowy_status.lower()
            summary[key] = summary.get(key, 0) + 1
        else:
            summary["active"] += 1

        summary["checked"] += 1

    # Wyświetl tabelę
    _print_summary_table(summary)

    # Auto-trainer po 20+ nowych wynikach
    if nowe_wyniki >= 20:
        console.print(f"[green]{nowe_wyniki} nowych wyników → uruchamiam auto-trainer...[/green]")
        import subprocess
        try:
            subprocess.Popen(
                [sys.executable, "-m", "footstats.ai.trainer"],
                cwd=Path(__file__).parents[2],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )  # fire-and-forget auto-trainer
        except OSError as e:
            console.print(f"[red]Auto-trainer start failed: {e.__class__.__name__}: {e}[/red]")

    _send_telegram_summary(summary, date_str)

    # Alert jeśli daily agent nie generował predykcji >26h
    try:
        from footstats.utils.telegram_notify import check_and_alert_agent_down
        check_and_alert_agent_down()
    except (ImportError, OSError, RuntimeError):
        pass

    return summary


def _print_summary_table(summary: dict) -> None:
    t = Table(title="Evening Agent — Podsumowanie")
    t.add_column("Status", style="cyan")
    t.add_column("Liczba", justify="right")
    t.add_row("Sprawdzonych", str(summary.get("checked", 0)))
    t.add_row("Wygranych",  str(summary.get("won", 0)))
    t.add_row("Przegranych", str(summary.get("lost", 0)))
    t.add_row("Oczekujących", str(summary.get("active", 0)))
    console.print(t)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FootStats Evening Agent")
    parser.add_argument("--date", default=None, help="Data YYYY-MM-DD (default: dziś)")
    args = parser.parse_args()
    run_evening_agent(args.date)
