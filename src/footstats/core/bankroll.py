"""
bankroll.py – Zarządzanie kapitałem (Bankroll Management) dla FootStats.
Obsługuje trwałość salda w SQLite oraz logikę reinvestmentu.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from footstats.config import AGENT_BANKROLL, AGENT_KELLY_FRACTION
from footstats.utils.db import connect as _db_connect

_STATE_FILE = Path(__file__).parent.parent.parent.parent / "data" / "agent_state.json"


def _connect():
    return _db_connect()

def init_bankroll_tables(user_id: int = 1) -> None:
    """Inicjalizuje saldo startowe dla użytkownika jeśli nie istnieje."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT balance FROM bankroll_state WHERE user_id = ?", (user_id,)
        ).fetchone()
        if not row:
            conn.execute(
                "INSERT INTO bankroll_state (user_id, balance) VALUES (?, ?)"
                " ON CONFLICT (user_id) DO NOTHING",
                (user_id, AGENT_BANKROLL),
            )

def get_current_bankroll(user_id: int = 1) -> float:
    """Zwraca aktualny balans użytkownika. Inicjalizuje saldo jeśli nie istnieje."""
    init_bankroll_tables(user_id)
    with _connect() as conn:
        row = conn.execute(
            "SELECT balance FROM bankroll_state WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row["balance"] if row else AGENT_BANKROLL


def update_bankroll(change: float, tx_type: str, description: str = "", user_id: int = 1) -> float:
    """Aktualizuje balans o 'change'. tx_type: 'BET', 'WIN', 'REFUND', 'MANUAL'."""
    init_bankroll_tables(user_id)
    with _connect() as conn:
        current = get_current_bankroll(user_id)
        new_balance = current + change
        if new_balance < 0 and tx_type == "BET":
            new_balance = 0
        conn.execute(
            "UPDATE bankroll_state SET balance = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
            (new_balance, user_id),
        )
        conn.execute(
            "INSERT INTO bankroll_history (change_pln, new_balance, type, description, user_id)"
            " VALUES (?, ?, ?, ?, ?)",
            (change, new_balance, tx_type, description, user_id),
        )
        return new_balance


def process_bet(stake: float, description: str = "", user_id: int = 1) -> float:
    """Odejmuje stawkę od bankrolla."""
    return update_bankroll(-stake, "BET", description, user_id)


def process_win(payout: float, description: str = "", user_id: int = 1) -> float:
    """Dodaje 50% wygranej do bankrolla (reinwestycja)."""
    reinvest_amount = round(payout * 0.5, 2)
    return update_bankroll(
        reinvest_amount, "WIN",
        f"Wypłata {payout} PLN (50% reinwestycji): {description}",
        user_id,
    )


# ── P7.8: Stop-Loss & Bankroll Protection ────────────────────────────────────

DAILY_MAX_LOSS_PCT = 0.10   # 10% bankrolla dziennie
# 20% w tygodniu → alert/auto-pause. Konfigurowalne env `WEEKLY_DRAWDOWN_PCT`.
# 06-21: faza PAPER-validation — stop-loss był blokerem (drawdown z zepsutego pipeline'u
# Cel B, już naprawione) wstrzymywał CAŁY pipeline od 06-16. Paper = darmowe → próg
# podniesiony w .env (WEEKLY_DRAWDOWN_PCT) by zbierać dane. PRZYWRÓĆ 0.20 przed real-money/launch.
WEEKLY_DRAWDOWN_ALERT_PCT = float(os.getenv("WEEKLY_DRAWDOWN_PCT", "0.20") or "0.20")
STREAK_THRESHOLD = 3        # po 3 przegranych z rzędu → reduce stakes
STREAK_MULTIPLIER = 0.50    # 50% stawek po streak


def get_daily_loss(user_id: int = 1) -> float:
    """Suma strat z dzisiaj (tylko BET, nie WIN)."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(change_pln), 0) AS total"
            " FROM bankroll_history"
            " WHERE user_id = ? AND type = 'BET'"
            " AND DATE(timestamp) = DATE('now')",
            (user_id,),
        ).fetchone()
        return abs(float(row["total"] or 0))


def check_daily_stop_loss(user_id: int = 1) -> bool:
    """True jeśli dzienna strata przekroczyła DAILY_MAX_LOSS_PCT bankrolla."""
    bankroll = get_current_bankroll(user_id)
    daily_loss = get_daily_loss(user_id)
    limit = bankroll * DAILY_MAX_LOSS_PCT
    return daily_loss >= limit


def get_loss_streak(user_id: int = 1, n: int = 20) -> int:
    """Liczba aktualnych przegranych z rzędu (z ostatnich n kuponów)."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT status FROM coupons"
            " WHERE user_id = ? AND status IN ('WON', 'WIN', 'LOST', 'LOSE')"
            " ORDER BY created_at DESC LIMIT ?",
            (user_id, n),
        ).fetchall()

    streak = 0
    for r in rows:
        if r["status"] in ("LOST", "LOSE"):
            streak += 1
        else:
            break
    return streak


def get_stake_multiplier(user_id: int = 1) -> float:
    """
    Zwraca mnożnik stawki:
    - 0.50 jeśli streak strat >= STREAK_THRESHOLD
    - 1.00 normalnie
    """
    streak = get_loss_streak(user_id)
    if streak >= STREAK_THRESHOLD:
        return STREAK_MULTIPLIER
    return 1.0


def get_weekly_drawdown(user_id: int = 1) -> float:
    """
    Procent straty bankrolla w ostatnich 7 dniach.
    Zwraca wartość dodatnią = % straty, ujemną = % zysku.
    """
    with _connect() as conn:
        row = conn.execute(
            "SELECT new_balance FROM bankroll_history"
            " WHERE user_id = ?"
            " AND timestamp <= NOW() - INTERVAL '7 days'"
            " ORDER BY timestamp DESC LIMIT 1",
            (user_id,),
        ).fetchone()

    if not row:
        return 0.0
    balance_7d_ago = float(row["new_balance"])
    current = get_current_bankroll(user_id)
    if balance_7d_ago <= 0:
        return 0.0
    return (balance_7d_ago - current) / balance_7d_ago


def check_weekly_alert(user_id: int = 1) -> bool:
    """True jeśli tygodniowy drawdown przekracza WEEKLY_DRAWDOWN_ALERT_PCT."""
    return get_weekly_drawdown(user_id) >= WEEKLY_DRAWDOWN_ALERT_PCT


def kelly_fraction(prob: float, kurs: float, bankroll: float, frac: float = 0.25) -> float:
    """
    Fractional Kelly stake w PLN.

    frac=0.25 = 1/4 Kelly (domyślnie, bardziej konserwatywny).
    Zwraca 0.0 gdy edge ujemny (nie stawiaj) lub bankroll=0.
    Minimalny stake: 1 PLN. Maksymalny: 10% bankrolla (stop-loss guard).
    """
    if bankroll <= 0 or kurs <= 1.0 or prob <= 0.0:
        return 0.0
    b = kurs - 1.0
    edge = b * prob - (1.0 - prob)
    if edge <= 0:
        return 0.0
    full_kelly = edge / b
    stake = round(full_kelly * frac * bankroll, 2)
    max_stake = round(bankroll * 0.10, 2)
    return max(1.0, min(stake, max_stake))


# ── 15.1: Agent pause state (stop-loss auto-pause) ──────────────────────────

def is_agent_paused() -> bool:
    """Zwraca True jeśli agent jest zapauzowany przez stop-loss."""
    try:
        return bool(json.loads(_STATE_FILE.read_text(encoding="utf-8")).get("paused", False))
    except (FileNotFoundError, ValueError, OSError):
        return False


def set_agent_paused(paused: bool, reason: str = "") -> None:
    """Ustawia status pauzy agenta. paused=False → wznowienie."""
    data = {
        "paused": paused,
        "paused_at": datetime.now(timezone.utc).isoformat() if paused else None,
        "reason": reason,
    }
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _STATE_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def get_pause_state() -> dict:
    """Zwraca pełny stan pauzy: {paused, paused_at, reason}."""
    try:
        return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, OSError):
        return {"paused": False, "paused_at": None, "reason": ""}


def check_and_auto_pause(user_id: int = 1) -> bool:
    """
    Sprawdza tygodniowy drawdown i pauzuje agenta jeśli >= WEEKLY_DRAWDOWN_ALERT_PCT.
    Zwraca True jeśli właśnie zapauzowano (nowe zdarzenie), False jeśli OK.
    """
    if is_agent_paused():
        return False  # już zapauzowany — nie duplikuj alertu
    dd = get_weekly_drawdown(user_id)
    if dd >= WEEKLY_DRAWDOWN_ALERT_PCT:
        set_agent_paused(True, reason=f"Tygodniowy drawdown {dd:.1%} >= {WEEKLY_DRAWDOWN_ALERT_PCT:.0%}")
        return True
    return False


if __name__ == "__main__":
    init_bankroll_tables()
    print(f"Aktualny bankroll: {get_current_bankroll()} PLN")
    streak = get_loss_streak()
    mult = get_stake_multiplier()
    print(f"Streak strat: {streak}, mnoznik stawki: {mult}")
    dd = get_weekly_drawdown()
    print(f"Tygodniowy drawdown: {dd:+.1%}")
