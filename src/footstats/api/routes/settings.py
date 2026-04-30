"""Bot settings endpoints."""
import sqlite3
from typing import Optional

import footstats.config as cfg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from footstats.api.auth import require_auth
from footstats.config import DB_PATH

router = APIRouter(prefix="/api", tags=["settings"])


def _get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


class SettingsUpdate(BaseModel):
    version: Optional[str] = None
    pewniaczek_prog: Optional[float] = None
    kandydat_prog: Optional[float] = None
    kelly_fraction: Optional[int] = None
    kelly_w1_multipliers: Optional[str] = None


@router.get("/settings")
def get_settings(user: str = Depends(require_auth)):
    conn = _get_conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_settings (
                key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT
            )
        """)
        defaults = {
            "version": cfg.VERSION,
            "pewniaczek_prog": str(cfg.PEWNIACZEK_PROG),
            "kandydat_prog": str(round(cfg.AGENT_KANDYDAT_PROG * 100, 1)),
            "kelly_fraction": str(cfg.AGENT_KELLY_FRACTION),
            "kelly_w1_multipliers": "0.7 / 1.0 / 1.1",
        }
        for key, val in defaults.items():
            conn.execute(
                "INSERT OR IGNORE INTO bot_settings (key, value, updated_at) VALUES (?,?,datetime('now'))",
                (key, val),
            )
        conn.commit()
        rows = conn.execute("SELECT key, value FROM bot_settings").fetchall()
        data = {r["key"]: r["value"] for r in rows}
    finally:
        conn.close()
    return {
        "version": data.get("version", cfg.VERSION),
        "pewniaczek_prog": float(data.get("pewniaczek_prog", cfg.PEWNIACZEK_PROG)),
        "kandydat_prog": float(data.get("kandydat_prog", round(cfg.AGENT_KANDYDAT_PROG * 100, 1))),
        "kelly_fraction": int(data.get("kelly_fraction", cfg.AGENT_KELLY_FRACTION)),
        "kelly_w1_multipliers": data.get("kelly_w1_multipliers", "0.7 / 1.0 / 1.1"),
        "kelly_w2_desc": "forma bota (3× streak WIN/LOSE)",
    }


@router.post("/settings")
def update_settings(data: SettingsUpdate, user: str = Depends(require_auth)):
    updates: dict[str, str] = {}
    if data.version is not None: updates["version"] = data.version
    if data.pewniaczek_prog is not None: updates["pewniaczek_prog"] = str(data.pewniaczek_prog)
    if data.kandydat_prog is not None: updates["kandydat_prog"] = str(data.kandydat_prog)
    if data.kelly_fraction is not None: updates["kelly_fraction"] = str(data.kelly_fraction)
    if data.kelly_w1_multipliers is not None: updates["kelly_w1_multipliers"] = data.kelly_w1_multipliers
    if not updates:
        raise HTTPException(status_code=400, detail="Brak pól do aktualizacji")
    conn = _get_conn()
    try:
        for key, val in updates.items():
            conn.execute(
                "INSERT OR REPLACE INTO bot_settings (key, value, updated_at) VALUES (?,?,datetime('now'))",
                (key, val),
            )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "updated": list(updates.keys())}
