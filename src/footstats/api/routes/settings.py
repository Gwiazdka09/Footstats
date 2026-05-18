"""Bot settings endpoints."""
from typing import Optional

import footstats.config as cfg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from footstats.api.auth import require_auth
from footstats.core.response_cache import cached_response
from footstats.utils.db import connect as _connect

router = APIRouter(prefix="/api", tags=["settings"])


class SettingsUpdate(BaseModel):
    version: Optional[str] = None
    pewniaczek_prog: Optional[float] = None
    kandydat_prog: Optional[float] = None
    kelly_fraction: Optional[int] = None
    kelly_w1_multipliers: Optional[str] = None


@router.get("/settings")
@cached_response(ttl_seconds=1800, vary_by=["user_id"])
def get_settings(user_id: int = Depends(require_auth)):
    defaults = {
        "version": cfg.VERSION,
        "pewniaczek_prog": str(cfg.PEWNIACZEK_PROG),
        "kandydat_prog": str(round(cfg.AGENT_KANDYDAT_PROG * 100, 1)),
        "kelly_fraction": str(cfg.AGENT_KELLY_FRACTION),
        "kelly_w1_multipliers": "0.7 / 1.0 / 1.1",
    }
    with _connect() as conn:
        for key, val in defaults.items():
            conn.execute(
                "INSERT INTO bot_settings (user_id, key, value, updated_at)"
                " VALUES (?,?,?,CURRENT_TIMESTAMP)"
                " ON CONFLICT (user_id, key) DO NOTHING",
                (user_id, key, val),
            )
        rows = conn.execute(
            "SELECT key, value FROM bot_settings WHERE user_id = ?", (user_id,)
        ).fetchall()
    data = {r["key"]: r["value"] for r in rows}
    return {
        "version": data.get("version", cfg.VERSION),
        "pewniaczek_prog": float(data.get("pewniaczek_prog", cfg.PEWNIACZEK_PROG)),
        "kandydat_prog": float(data.get("kandydat_prog", round(cfg.AGENT_KANDYDAT_PROG * 100, 1))),
        "kelly_fraction": int(data.get("kelly_fraction", cfg.AGENT_KELLY_FRACTION)),
        "kelly_w1_multipliers": data.get("kelly_w1_multipliers", "0.7 / 1.0 / 1.1"),
        "kelly_w2_desc": "forma bota (3× streak WIN/LOSE)",
    }


@router.post("/settings")
def update_settings(data: SettingsUpdate, user_id: int = Depends(require_auth)):
    updates: dict[str, str] = {}
    if data.version is not None: updates["version"] = data.version
    if data.pewniaczek_prog is not None: updates["pewniaczek_prog"] = str(data.pewniaczek_prog)
    if data.kandydat_prog is not None: updates["kandydat_prog"] = str(data.kandydat_prog)
    if data.kelly_fraction is not None: updates["kelly_fraction"] = str(data.kelly_fraction)
    if data.kelly_w1_multipliers is not None: updates["kelly_w1_multipliers"] = data.kelly_w1_multipliers
    if not updates:
        raise HTTPException(status_code=400, detail="Brak pól do aktualizacji")
    with _connect() as conn:
        for key, val in updates.items():
            conn.execute(
                "INSERT INTO bot_settings (user_id, key, value, updated_at)"
                " VALUES (?,?,?,CURRENT_TIMESTAMP)"
                " ON CONFLICT (user_id, key)"
                " DO UPDATE SET value=EXCLUDED.value, updated_at=EXCLUDED.updated_at",
                (user_id, key, val),
            )
    return {"ok": True, "updated": list(updates.keys())}
