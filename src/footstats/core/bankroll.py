"""
bankroll.py – Zarządzanie kapitałem (Bankroll Management) dla FootStats.
Obsługuje trwałość salda w SQLite oraz logikę reinvestmentu.
"""

from datetime import datetime, timezone
from footstats.config import AGENT_BANKROLL, AGENT_KELLY_FRACTION
from footstats.utils.db import connect as _db_connect


def _connect():
    return _db_connect()

def init_bankroll_tables(user_id: int = 1) -> None:
    """Inicjalizuje saldo startowe dla użytkownika jeśli nie istnieje."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT balance FROM bankroll_state WHERE user_id = ?", (user_id,)
        ).fetchone()
        if not row:
            conn.execute(
                "INSERT INTO bankroll_state (user_id, balance) VALUES (?, ?)"
                " ON CONFLICT (user_id) DO NOTHING",
                (user_id, AGENT_BANKROLL),
            )
        conn.commit()
    finally:
        conn.close()

def get_current_bankroll(user_id: int = 1) -> float:
    """Zwraca aktualny balans użytkownika. Inicjalizuje saldo jeśli nie istnieje."""
    init_bankroll_tables(user_id)
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT balance FROM bankroll_state WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row["balance"] if row else AGENT_BANKROLL
    finally:
        conn.close()


def update_bankroll(change: float, tx_type: str, description: str = "", user_id: int = 1) -> float:
    """Aktualizuje balans o 'change'. tx_type: 'BET', 'WIN', 'REFUND', 'MANUAL'."""
    init_bankroll_tables(user_id)
    conn = _connect()
    try:
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
        conn.commit()
        return new_balance
    finally:
        conn.close()


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


if __name__ == "__main__":
    init_bankroll_tables()
    print(f"Aktualny bankroll: {get_current_bankroll()} PLN")
