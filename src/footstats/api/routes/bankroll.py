"""Bankroll endpoints."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from footstats.api.auth import require_auth
from footstats.utils.db import connect as _connect

router = APIRouter(prefix="/api", tags=["bankroll"])


class BankrollUpdate(BaseModel):
    balance: float


@router.post("/bankroll")
def update_bankroll(data: BankrollUpdate, user_id: int = Depends(require_auth)):
    if data.balance < 0:
        raise HTTPException(status_code=400, detail="Saldo nie może być ujemne")
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with _connect() as conn:
            conn.execute(
                "INSERT INTO bankroll_state (user_id, balance, updated_at) VALUES (?, ?, ?)"
                " ON CONFLICT (user_id) DO UPDATE"
                " SET balance=EXCLUDED.balance, updated_at=EXCLUDED.updated_at",
                (user_id, data.balance, now),
            )
        return {"ok": True, "balance": data.balance, "updated_at": now}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bankroll/history")
def get_bankroll_history(limit: int = 50, user_id: int = Depends(require_auth)):
    with _connect() as conn:
        rows = conn.execute(
            "SELECT timestamp, new_balance FROM bankroll_history"
            " WHERE user_id = ? ORDER BY timestamp ASC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    return [{"time": str(r["timestamp"])[:16], "balance": r["new_balance"]} for r in rows]
