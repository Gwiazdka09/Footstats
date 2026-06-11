"""
coupon_settlement.py – Rozliczanie ACTIVE kuponów z fallback na FlashScore/football-data.org.

Hierarchia źródeł wyników (każdy kolejny to fallback):
  1. API-Football (v3.football.api-sports.io) – tylko ~3 dni wstecz (Free plan)
  2. football-data.org – pełna historia
  3. FlashScore mobi – ~7 dni wstecz
  4. Tabela predictions w DB

Po rozliczeniu:
  - WIN: zaktualizuj bankroll
  - LOSE: wyślij do post_match_analyzer (RAG feedback)
  - legs_json: każdy leg dostaje pola `result` i `leg_won` dla UI

Użycie:
    from footstats.core.coupon_settlement import settle_active_coupons
    settle_active_coupons(days_back=60, dry_run=False, verbose=True)
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger(__name__)

from footstats.utils.betting import oblicz_tip_correct
from footstats.utils.normalize import normalize_team_name


def _get_fixtures_api(api_key: str, date_str: str) -> list[dict]:
    """Pobiera fixtures z API-Football dla całej daty (bez filtrowania po lidze)."""
    import requests
    from requests import RequestException
    try:
        r = requests.get(
            "https://v3.football.api-sports.io/fixtures",
            headers={"x-apisports-key": api_key},
            params={"date": date_str},
            timeout=15,
        )
        r.raise_for_status()
        return r.json().get("response", [])
    except (RequestException, ValueError, KeyError) as e:
        log.debug("API-Football error for date %s: %s", date_str, e)
        return []


def _get_matches_fdb(fdb_key: str, date_str: str) -> list[dict]:
    """Pobiera zakończone mecze z football-data.org (pełna historia)."""
    import requests
    from requests import RequestException
    if not fdb_key:
        return []
    try:
        r = requests.get(
            "https://api.football-data.org/v4/matches",
            headers={"X-Auth-Token": fdb_key},
            params={"dateFrom": date_str, "dateTo": date_str, "status": "FINISHED"},
            timeout=15,
        )
        r.raise_for_status()
        return r.json().get("matches", [])
    except (RequestException, ValueError, KeyError) as e:
        log.debug("football-data.org error for date %s: %s", date_str, e)
        return []


def _znajdz_wynik_fdb(home: str, away: str, matches: list[dict]) -> str | None:
    """Fuzzy-match meczu w danych z football-data.org. Zwraca 'HG-AG' lub None."""
    from difflib import SequenceMatcher
    best_score = 0.0
    best_result: str | None = None
    for m in matches:
        fh = m.get("homeTeam", {}).get("name", "")
        fa = m.get("awayTeam", {}).get("name", "")
        nh = normalize_team_name(home)
        nfh = normalize_team_name(fh)
        na = normalize_team_name(away)
        nfa = normalize_team_name(fa)
        score = (
            SequenceMatcher(None, nh, nfh).ratio()
            + SequenceMatcher(None, na, nfa).ratio()
        ) / 2
        if score >= 0.6 and score > best_score:
            ft = m.get("score", {}).get("fullTime", {})
            hg, ag = ft.get("home"), ft.get("away")
            if hg is not None and ag is not None:
                best_score = score
                best_result = f"{hg}-{ag}"
    return best_result


def settle_active_coupons(
    days_back: int = 3,
    dry_run: bool = False,
    verbose: bool = True,
) -> dict:
    """
    Rozlicza ACTIVE kupony z fallback na FlashScore.

    Args:
        days_back: Ile dni wstecz sprawdzać
        dry_run: Tylko pokaż co by zmienił
        verbose: Drukuj log

    Returns:
        {"settled": N, "partial": M, "errors": K}
    """
    from footstats.core.backtest import _connect, init_db
    from footstats.scrapers.results_updater import _get_api_key, _znajdz_wynik
    from footstats.scrapers.flashscore_results import get_match_result

    init_db()

    today = datetime.now().date()
    cutoff = today - timedelta(days=days_back)

    with _connect() as conn:
        rows = conn.execute(
            """SELECT id, legs_json, total_odds, stake_pln, match_date_first
               FROM coupons
               WHERE status = 'ACTIVE'""",
        ).fetchall()

    if not rows:
        if verbose:
            print("[CouponSettlement] Brak ACTIVE kuponów do rozliczenia.")
        return {"settled": 0, "partial": 0, "errors": 0}

    if verbose:
        print(f"[CouponSettlement] ACTIVE kuponów do sprawdzenia: {len(rows)}")

    import os
    api_key = _get_api_key()
    fdb_key = os.getenv("FOOTBALL_API_KEY", "").strip()
    stats = {"settled": 0, "partial": 0, "errors": 0}
    fixtures_cache: dict[str, list] = {}
    fdb_cache: dict[str, list] = {}

    for row in rows:
        coupon_id = row["id"]
        legs = json.loads(row["legs_json"])
        total_odds = row["total_odds"]
        stake = row["stake_pln"]
        match_date = row["match_date_first"]
        mdate = match_date[:10]

        # Sprawdź czy data nie za stara
        try:
            leg_date = datetime.fromisoformat(match_date).date()
            if leg_date < cutoff:
                if verbose:
                    print(f"  [SKIP] Kupon #{coupon_id} — data {match_date} za stara (>{days_back}d)")
                continue
        except (ValueError, TypeError):
            pass

        leg_results: list[int | None] = []
        any_leg_lost = False
        updated_legs = [dict(leg) for leg in legs]  # kopia do zapisu per-leg results

        for leg_idx, leg in enumerate(legs):
            home = leg.get("home", "")
            away = leg.get("away", "")

            if not home or not away:
                mecz = leg.get("mecz", "")
                if " vs " in mecz:
                    home, away = mecz.split(" vs ", 1)
                elif " - " in mecz:
                    home, away = mecz.split(" - ", 1)
                home, away = home.strip(), away.strip()

            # Źródło 1: API-Football (cache per data)
            if mdate not in fixtures_cache:
                fixtures_cache[mdate] = _get_fixtures_api(api_key, mdate) if api_key else []

            pending_mock = {"team_home": home, "team_away": away}
            res = _znajdz_wynik(pending_mock, fixtures_cache[mdate])

            if not res:
                norm_home = normalize_team_name(home)
                norm_away = normalize_team_name(away)
                if norm_home != home.lower() or norm_away != away.lower():
                    norm_mock = {"team_home": norm_home, "team_away": norm_away}
                    res = _znajdz_wynik(norm_mock, fixtures_cache[mdate])

            # Źródło 2: football-data.org (pełna historia)
            if not res:
                if mdate not in fdb_cache:
                    fdb_cache[mdate] = _get_matches_fdb(fdb_key, mdate)
                res = _znajdz_wynik_fdb(home, away, fdb_cache[mdate])

            # Źródło 3: FlashScore mobi (~7 dni)
            if not res:
                res = get_match_result(home, away, mdate, cache_enabled=True)

            # Źródło 4: tabela predictions w DB
            if not res:
                try:
                    with _connect() as pred_conn:
                        pred_row = pred_conn.execute(
                            "SELECT actual_result FROM predictions WHERE match_date=? AND (team_home LIKE ? OR team_away LIKE ?) LIMIT 1",
                            (mdate, f"%{home}%", f"%{away}%")
                        ).fetchone()
                    if pred_row and pred_row["actual_result"]:
                        res = pred_row["actual_result"]
                except (OSError, ValueError, RuntimeError):
                    pass

            correct = oblicz_tip_correct(leg["tip"], res)
            leg_results.append(correct)

            # Zapisz per-leg wynik do updated_legs (dla UI)
            updated_legs[leg_idx]["result"] = res
            updated_legs[leg_idx]["leg_won"] = (
                True if correct == 1 else (False if correct == 0 else None)
            )

            if verbose:
                status_text = "OK" if correct == 1 else "MISS" if correct == 0 else "WAITING"
                print(f"    - {leg.get('home','?')} vs {leg.get('away','?')} (Tip: {leg['tip']}, Res: {res or '?'}) -> {status_text}")

            if correct == 0:
                any_leg_lost = True

        # PARTIAL: nie wszystkie wyniki znane
        if None in leg_results and not any_leg_lost:
            # Zapisz tymczasowo znane per-leg wyniki (partial update)
            if not dry_run:
                try:
                    with _connect() as conn:
                        conn.execute(
                            "UPDATE coupons SET legs_json=? WHERE id=?",
                            (json.dumps(updated_legs, ensure_ascii=False), coupon_id),
                        )
                except (OSError, ValueError) as e:
                    log.debug("Błąd zapisu partial legs_json dla #%s: %s", coupon_id, e)
            stats["partial"] += 1
            if verbose:
                print(f"  [PARTIAL] Kupon #{coupon_id} — czekam na brakujące wyniki\n")
            continue

        # Finalne rozliczenie
        all_correct = all(r == 1 for r in leg_results) and not any_leg_lost
        new_status = "WON" if all_correct else "LOST"
        payout = round(stake * total_odds, 2) if all_correct else 0.0
        roi = round((payout - stake) / stake * 100, 1) if stake else 0.0

        if verbose:
            tag = "DRY" if dry_run else "SETTLE"
            print(f"  [{tag}] Kupon #{coupon_id} → {new_status} | wypłata: {payout} PLN | ROI: {roi}%\n")

        if not dry_run:
            try:
                with _connect() as conn:
                    conn.execute(
                        "UPDATE coupons SET status=?, payout_pln=?, roi_pct=?, legs_json=? WHERE id=?",
                        (new_status, payout, roi,
                         json.dumps(updated_legs, ensure_ascii=False), coupon_id),
                    )
                    log.info("Kupon #%s → %s | payout=%.2f | roi=%.1f%%", coupon_id, new_status, payout, roi)

                    if all_correct and payout > 0:
                        cur_balance = conn.execute(
                            "SELECT balance FROM bankroll_state ORDER BY id DESC LIMIT 1"
                        ).fetchone()
                        if cur_balance:
                            new_balance = round(cur_balance["balance"] + payout, 2)
                            conn.execute(
                                "UPDATE bankroll_state SET balance=?, updated_at=? "
                                "WHERE id=(SELECT MAX(id) FROM bankroll_state)",
                                (new_balance, datetime.now().isoformat()),
                            )
                            conn.execute(
                                "INSERT INTO bankroll_history "
                                "(timestamp, change_pln, new_balance, type, description) "
                                "VALUES (?,?,?,?,?)",
                                (
                                    datetime.now().isoformat(),
                                    payout,
                                    new_balance,
                                    "WIN",
                                    f"Kupon #{coupon_id} WON",
                                ),
                            )

                if not all_correct:
                    failed_legs = [lg for lg in updated_legs if lg.get("leg_won") is False]
                    parts = [
                        f"Leg #{i+1}: {lg.get('home','?')} vs {lg.get('away','?')} "
                        f"Tip:{lg.get('tip','?')} Wynik:{lg.get('result','?')}"
                        for i, lg in enumerate(updated_legs) if lg.get("leg_won") is False
                    ]
                    lose_reason = (
                        f"PRZEGRANY kupon ({len(legs)} legów, {len(failed_legs)} chybionych). "
                        + "; ".join(parts)
                    )
                    _send_to_rag_feedback(coupon_id, updated_legs, mdate, lose_reason, verbose=verbose)

                stats["settled"] += 1
            except (KeyError, TypeError, ValueError, OSError) as e:
                log.error("Błąd rozliczania kuponu ID=%s: %s", coupon_id, e)
                stats["errors"] += 1
        else:
            stats["settled"] += 1  # dry_run: count without DB write

    if verbose:
        print(
            f"\n[CouponSettlement] Rozliczonych: {stats['settled']} | "
            f"Częściowych: {stats['partial']} | Błędów: {stats['errors']}"
        )
    return stats


def _send_to_rag_feedback(coupon_id: int, legs: list, mdate: str, reason: str, verbose: bool = True) -> None:
    """
    Wysyła info o przegranych legach kuponu do ai_feedback (RAG learning).

    ai_feedback.match_id ma FK do predictions.id (nie coupons.id), więc dla
    każdego przegranego lega szukamy odpowiadającej predykcji po dacie i drużynach.

    Args:
        coupon_id: ID kuponu (do logu/kontekstu)
        legs: Lista leg'ów kuponu (z polami home/away/tip/result/leg_won)
        mdate: Data meczów kuponu (YYYY-MM-DD)
        reason: Powód porażki (do logu)
        verbose: Drukuj log
    """
    from footstats.ai.post_match_analyzer import _zapisz_feedback
    from footstats.core.backtest import _connect

    if verbose:
        log.info("Kupon #%s: %s", coupon_id, reason)

    for i, leg in enumerate(legs):
        if leg.get("leg_won") is not False:
            continue

        home = leg.get("home", "")
        away = leg.get("away", "")

        try:
            with _connect() as conn:
                pred_row = conn.execute(
                    "SELECT id FROM predictions "
                    "WHERE match_date=? AND team_home LIKE ? AND team_away LIKE ? LIMIT 1",
                    (mdate, f"%{home}%", f"%{away}%"),
                ).fetchone()

            if not pred_row:
                log.debug("Brak predictions dla %s vs %s (%s) — pomijam RAG feedback", home, away, mdate)
                continue

            prediction_details = {
                "coupon_id": coupon_id,
                "tip": leg.get("tip", "?"),
                "result": leg.get("result", "?"),
            }
            leg_reason = (
                f"Kupon #{coupon_id}, leg #{i + 1}: {home} vs {away} "
                f"Tip:{leg.get('tip', '?')} Wynik:{leg.get('result', '?')}"
            )

            _zapisz_feedback(
                match_id=pred_row["id"],
                prediction_details=prediction_details,
                reason=leg_reason,
            )

            if verbose:
                log.info("Wysłano feedback do RAG dla kuponu #%s, leg #%s", coupon_id, i + 1)
        except (ImportError, AttributeError, TypeError, ValueError, OSError) as e:
            log.warning("Błąd wysyłania feedback do RAG dla kuponu #%s, leg #%s: %s", coupon_id, i + 1, e)


def _generate_lesson(legs: list, results: str | None) -> str:
    """
    Generuje krótki wniosek z porażki dla RAG.
    """
    lessons = []
    for leg in legs:
        mecz = leg.get("mecz", "?")
        tip = leg.get("tip", "?")
        lessons.append(f"• {mecz}: {tip} (wynik: {results})")

    return "Kupon nietrafiany:\n" + "\n".join(lessons)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    settle_active_coupons(days_back=3, dry_run=False, verbose=True)
