"""GET /api/stats/me — statystyki zalogowanego usera z rozliczonych kuponów (J2).
GET /api/stats/progress — krzywa postępu w czasie (J3).

Cienka warstwa nad footstats.core.user_stats (SELECT-only, J1) — zob. ten moduł
za definicję pól i reguły rozliczenia (co wchodzi do win-rate/streak/postępu).
"""
import dataclasses
import logging

from fastapi import APIRouter, Depends, HTTPException

from footstats.api.auth import require_auth
from footstats.core.user_stats import get_progress_series, get_user_stats

router = APIRouter(prefix="/api", tags=["user-stats"])
log = logging.getLogger(__name__)


@router.get("/stats/me")
def stats_me(user_id: int = Depends(require_auth)) -> dict:
    """Zwraca zagregowane statystyki (win-rate/ROI/profit/streak/best/worst) usera."""
    try:
        stats = get_user_stats(user_id)
    except Exception as e:  # noqa: BLE001 — DB/psycopg2: zwróć 503, nie 500
        log.warning("stats/me: odczyt statystyk nieudany (user_id=%s): %s", user_id, e)
        raise HTTPException(status_code=503, detail="Dane niedostępne")
    return dataclasses.asdict(stats)


@router.get("/stats/progress")
def stats_progress(user_id: int = Depends(require_auth)) -> list[dict]:
    """Zwraca krzywą postępu (kumulatywny profit + running win-rate) usera."""
    try:
        series = get_progress_series(user_id)
    except Exception as e:  # noqa: BLE001 — DB/psycopg2: zwróć 503, nie 500
        log.warning("stats/progress: odczyt serii nieudany (user_id=%s): %s", user_id, e)
        raise HTTPException(status_code=503, detail="Dane niedostępne")
    return [dataclasses.asdict(point) for point in series]
