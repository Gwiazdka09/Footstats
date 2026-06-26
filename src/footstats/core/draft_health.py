"""
core/draft_health.py — sygnał świeżości danych walidacyjnych (cloud-draft).

Cloud-draft może zwrócić `created=0` z dwóch powodów: (a) BENIGN — lokalny draft
PC już pokrył dzisiejsze mecze (idempotencja), albo (b) STARVATION — zbieranie
zamarło (Bzzoiro down / filtry za ciasne / scheduler nie leci). HTTP 200 ich nie
rozróżnia → ślepota. Sygnał: dni od ostatniego kuponu System. created>0 → 0 dni;
created=0 + brak kuponu od ≥`prog_dni` → STALE (alert w logach Cloud Run).
"""
from __future__ import annotations

from datetime import date, datetime

PROG_STALE_DNI = 3  # brak nowego kuponu System przez tyle dni → alert


def _to_date(v) -> date:
    """ISO str / datetime / date → date. TIMESTAMP 'YYYY-MM-DD ...' bierze 10 znaków."""
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


def ocena_swiezosci(last_created, dzis=None, prog_dni: int = PROG_STALE_DNI) -> dict:
    """
    Czy zbieranie danych System nie zamarło. `last_created`: ISO/datetime/date/None
    (None = nigdy nie powstał kupon). `dzis`: domyślnie date.today().
    Zwraca {"stale_days": int|None, "stale": bool}. Brak danych / parse error → stale=True.
    """
    if not last_created:
        return {"stale_days": None, "stale": True}
    try:
        last = _to_date(last_created)
        today = _to_date(dzis) if dzis else date.today()
    except (ValueError, TypeError):
        return {"stale_days": None, "stale": True}
    days = (today - last).days
    return {"stale_days": days, "stale": days >= prog_dni}
