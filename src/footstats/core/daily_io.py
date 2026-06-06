"""
daily_io.py – Zapis kuponu do DB wydzielony z daily_agent.py.
"""

import logging

from rich.console import Console

logger = logging.getLogger(__name__)
console = Console()


def _zapisz_kupon_do_db(
    kandydaci: list[dict],
    phase: str,
    groq_resp: str | None,
    stake: float,
    total_odds: float,
) -> int | None:
    """
    Zapisuje kupon do SQLite coupon_tracker. Zwraca coupon_id lub None.

    DRAFT → nowy rekord status=DRAFT.
    FINAL → szuka dzisiejszego DRAFT i promuje do ACTIVE;
            jeśli brak DRAFT — tworzy nowy rekord (fallback).
    """
    try:
        from footstats.core.coupon_tracker import (
            save_coupon, init_coupon_tables,
            get_draft_today, promote_to_active
        )
        from footstats.core.bankroll import process_bet, get_current_bankroll
        from footstats.utils.admin_user import resolve_admin_user_id

        admin_uid = resolve_admin_user_id()
        init_coupon_tables()
        current_bankroll = get_current_bankroll(user_id=admin_uid)

        def _parse_home_away(k: dict) -> tuple[str, str]:
            home = k.get("gospodarz") or k.get("home", "")
            away = k.get("goscie")    or k.get("away", "")
            if not home and not away:
                mecz = k.get("mecz", "")
                if " vs " in mecz:
                    parts = mecz.split(" vs ", 1)
                    home, away = parts[0].strip(), parts[1].strip()
                elif " - " in mecz:
                    parts = mecz.split(" - ", 1)
                    home, away = parts[0].strip(), parts[1].strip()
            return home, away

        legs = []
        for k in kandydaci:
            home, away = _parse_home_away(k)
            legs.append({
                "home":           home,
                "away":           away,
                "tip":            k.get("typ") or k.get("tip", ""),
                "odds":           k.get("kurs", 1.0),
                "decision_score": k.get("decision_score", 0),
                "mecz":           k.get("mecz", f"{home} vs {away}"),
            })

        from datetime import datetime as _dt
        match_date = _dt.now().strftime("%Y-%m-%d")
        avg_score = int(sum(k.get("decision_score", 0) for k in kandydaci) / max(len(kandydaci), 1))

        if phase == "final":
            draft_row = get_draft_today(user_id=admin_uid)
            if draft_row:
                try:
                    promote_to_active(
                        coupon_id=draft_row["id"],
                        legs=legs,
                        groq_reasoning=groq_resp or "",
                        decision_score=avg_score,
                        total_odds=round(total_odds, 2),
                    )
                    console.print(f"[green]Kupon #{draft_row['id']} DRAFT → ACTIVE[/green]")
                    return draft_row["id"]
                except (RuntimeError, ValueError, KeyError) as promo_err:
                    console.print(
                        f"[red]BŁĄD promote_to_active(#{draft_row['id']}): {promo_err}"
                        f" — tworzę nowy kupon ACTIVE jako fallback[/red]"
                    )
            else:
                console.print("[yellow]Brak dzisiejszego DRAFT — tworzę nowy kupon ACTIVE[/yellow]")

        cid = save_coupon(
            phase=phase,
            kupon_type="A",
            legs=legs,
            total_odds=round(total_odds, 2),
            stake_pln=stake,
            groq_reasoning=groq_resp or "",
            decision_score=avg_score,
            match_date_first=match_date,
            user_id=admin_uid,
        )

        if cid and phase == "final":
            from footstats.core.coupon_tracker import update_coupon_status, STATUS_ACTIVE
            update_coupon_status(cid, STATUS_ACTIVE)
            console.print(f"[green]Kupon #{cid} → ACTIVE[/green]")

        if cid and stake > 0:
            process_bet(stake, f"Kupon A ID={cid} ({phase})", user_id=admin_uid)

        return cid
    except (ValueError, KeyError, TypeError, OSError) as e:
        import traceback
        console.print(f"[red]BŁĄD _zapisz_kupon_do_db [{phase}]: {e}[/red]")
        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        return None
