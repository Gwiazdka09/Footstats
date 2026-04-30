"""Status and config endpoints."""
import sqlite3
from datetime import datetime, timedelta

import footstats.config as cfg
from fastapi import APIRouter, Depends, HTTPException

from footstats.api.auth import require_auth
from footstats.config import DB_PATH

router = APIRouter(prefix="/api", tags=["status"])


def _get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


@router.get("/status")
def get_status(user: str = Depends(require_auth)):
    try:
        conn = _get_conn()
        bankroll = conn.execute(
            "SELECT balance, updated_at FROM bankroll_state WHERE id = 1"
        ).fetchone()
        stats = conn.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status IN ('WON','WIN') THEN 1 ELSE 0 END) as wins,
                SUM(payout_pln) as total_payout,
                SUM(stake_pln) as total_stake
            FROM coupons WHERE status IN ('WON','WIN','LOSE','LOST')
        """).fetchone()
        cutoff_30d = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        wins_30d = conn.execute(
            "SELECT COUNT(*) as n FROM coupons WHERE status IN ('WON','WIN') AND created_at >= ?",
            (cutoff_30d,)
        ).fetchone()
        roi = 0
        if stats and stats["total_stake"]:
            roi = round(
                ((stats["total_payout"] or 0) - stats["total_stake"]) / stats["total_stake"] * 100, 1
            )
        return {
            "bankroll": bankroll["balance"] if bankroll else 0,
            "last_update": bankroll["updated_at"] if bankroll else None,
            "stats": {
                "total_finished": stats["total"] if stats else 0,
                "wins": stats["wins"] if stats else 0,
                "wins_last_30d": wins_30d["n"] if wins_30d else 0,
                "roi_pct": roi,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/config")
def get_bot_config(user: str = Depends(require_auth)):
    return {
        "version": cfg.VERSION,
        "kelly_fraction": cfg.AGENT_KELLY_FRACTION,
        "bankroll_start": cfg.AGENT_BANKROLL,
        "min_confidence": cfg.AGENT_KANDYDAT_PROG,
        "pewniaczek_prog": cfg.PEWNIACZEK_PROG,
        "ostatnie_n": cfg.OSTATNIE_N,
    }
