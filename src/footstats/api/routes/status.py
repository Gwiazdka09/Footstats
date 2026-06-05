"""Status and config endpoints."""
import json
from datetime import datetime, timedelta
from pathlib import Path

import footstats.config as cfg
from fastapi import APIRouter, Depends, HTTPException

from footstats.api.auth import require_auth
from footstats.utils.db import connect as _connect

router = APIRouter(prefix="/api", tags=["status"])


@router.get("/status")
def get_status(user_id: int = Depends(require_auth)):
    try:
        with _connect() as conn:
            bankroll = conn.execute(
                "SELECT balance, updated_at FROM bankroll_state WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            stats = conn.execute(
                """
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status IN ('WON','WIN') THEN 1 ELSE 0 END) as wins,
                    SUM(payout_pln) as total_payout,
                    SUM(stake_pln) as total_stake
                FROM coupons
                WHERE status IN ('WON','WIN','LOSE','LOST') AND user_id = ?
                """,
                (user_id,),
            ).fetchone()
            cutoff_30d = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            wins_30d = conn.execute(
                "SELECT COUNT(*) as n FROM coupons"
                " WHERE status IN ('WON','WIN') AND created_at >= ? AND user_id = ?",
                (cutoff_30d, user_id),
            ).fetchone()
        roi = 0
        if stats and stats["total_stake"]:
            roi = round(
                ((stats["total_payout"] or 0) - stats["total_stake"]) / stats["total_stake"] * 100, 1
            )
        return {
            "bankroll": bankroll["balance"] if bankroll else 0,
            "last_update": str(bankroll["updated_at"]) if bankroll else None,
            "stats": {
                "total_finished": stats["total"] if stats else 0,
                "wins": stats["wins"] if stats else 0,
                "wins_last_30d": wins_30d["n"] if wins_30d else 0,
                "roi_pct": roi,
            },
        }
    except (ValueError, KeyError, AttributeError, TypeError) as e:
        raise HTTPException(status_code=500, detail=str(e))


_CALIBRATION_PATH = Path(__file__).parent.parent.parent.parent.parent / "data" / "model_calibration.json"


@router.get("/calibration")
def get_calibration(user_id: int = Depends(require_auth)):
    try:
        data = json.loads(_CALIBRATION_PATH.read_text(encoding="utf-8"))
        return data
    except FileNotFoundError:
        return {"updated_at": None, "factor_home": None, "factor_away": None, "n_matches": 0}
    except (ValueError, KeyError, AttributeError, TypeError) as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config")
def get_bot_config(user_id: int = Depends(require_auth)):
    return {
        "version": cfg.VERSION,
        "kelly_fraction": cfg.AGENT_KELLY_FRACTION,
        "bankroll_start": cfg.AGENT_BANKROLL,
        "min_confidence": cfg.AGENT_KANDYDAT_PROG,
        "pewniaczek_prog": cfg.PEWNIACZEK_PROG,
        "ostatnie_n": cfg.OSTATNIE_N,
    }
