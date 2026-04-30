"""Bankroll endpoints."""
import sqlite3
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from footstats.api.auth import require_auth
from footstats.config import DB_PATH

router = APIRouter(prefix="/api", tags=["bankroll"])


def _get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


class BankrollUpdate(BaseModel):
    balance: float


@router.post("/bankroll")
def update_bankroll(data: BankrollUpdate, user: str = Depends(require_auth)):
    if data.balance < 0:
        raise HTTPException(status_code=400, detail="Saldo nie może być ujemne")
    conn = _get_conn()
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "INSERT OR REPLACE INTO bankroll_state (id, balance, updated_at) VALUES (1, ?, ?)",
            (data.balance, now),
        )
        conn.commit()
        return {"ok": True, "balance": data.balance, "updated_at": now}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/bankroll/history")
def get_bankroll_history(limit: int = 50, user: str = Depends(require_auth)):
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT timestamp, new_balance FROM bankroll_history ORDER BY timestamp ASC LIMIT ?",
            (limit,),
        ).fetchall()
        return [{"time": r["timestamp"][:16], "balance": r["new_balance"]} for r in rows]
    finally:
        conn.close()
