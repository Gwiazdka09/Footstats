"""clv_tracker.py — Closing Line Value (CLV) tracking.

CLV mierzy wartość zakładu: czy kurs który dostałeś był lepszy
od rynkowego kursu zamknięcia (tuż przed meczem).

Formuła:
    CLV% = (bet_odds / closing_odds - 1) * 100
    CLV > 0 → wygrałeś z rynkiem (zakład z wartością)
    CLV < 0 → rynek był mądrzejszy od Ciebie

Użycie:
    from footstats.core.clv_tracker import record_closing_odds, get_clv_report
    record_closing_odds(prediction_id=42, closing_odds=1.85)
    report = get_clv_report()
"""
from __future__ import annotations

import logging

from footstats.utils.db import connect as _connect

_log = logging.getLogger(__name__)


def _ensure_clv_column() -> None:
    """Dodaje kolumnę clv_closing_odds jeśli nie istnieje."""
    with _connect() as conn:
        try:
            conn.execute(
                "ALTER TABLE predictions ADD COLUMN clv_closing_odds REAL"
            )
        except Exception:  # noqa: broad-except — DB-specific "column exists" errors vary by driver
            pass


def calculate_clv(bet_odds: float, closing_odds: float) -> float | None:
    """
    CLV% = (bet_odds / closing_odds - 1) * 100.
    Zwraca None przy nieprawidłowych kursach.
    """
    if not bet_odds or not closing_odds or closing_odds <= 1.0 or bet_odds <= 1.0:
        return None
    return round((bet_odds / closing_odds - 1) * 100, 2)


def record_closing_odds(
    prediction_id: int,
    closing_odds: float,
) -> float | None:
    """
    Zapisuje kurs zamknięcia dla predykcji i zwraca obliczone CLV%.

    Args:
        prediction_id: ID rekordu w tabeli predictions.
        closing_odds: kurs rynkowy tuż przed meczem (np. z Betexplorer).

    Returns:
        CLV% lub None jeśli brak danych.
    """
    _ensure_clv_column()

    with _connect() as conn:
        row = conn.execute(
            "SELECT odds FROM predictions WHERE id = ?",
            (prediction_id,),
        ).fetchone()

    if not row or not row["odds"]:
        _log.warning("[CLV] Brak odds dla prediction_id=%d", prediction_id)
        return None

    bet_odds = float(row["odds"])
    clv_pct = calculate_clv(bet_odds, closing_odds)

    with _connect() as conn:
        conn.execute(
            "UPDATE predictions SET clv_closing_odds = ? WHERE id = ?",
            (closing_odds, prediction_id),
        )

    _log.info(
        "[CLV] id=%d bet=%.2f closing=%.2f CLV=%.1f%%",
        prediction_id, bet_odds, closing_odds, clv_pct or 0,
    )
    return clv_pct


def get_clv_report(
    min_samples: int = 5,
    days: int = 90,
) -> dict:
    """
    Raport CLV: ogólny + per liga.

    Zwraca:
        {
            "overall": {"n": int, "clv_avg": float, "positive_pct": float},
            "per_liga": [{"liga": str, "n": int, "clv_avg": float}, ...]
        }
    """
    _ensure_clv_column()

    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT league, odds, clv_closing_odds, tip_correct
            FROM predictions
            WHERE clv_closing_odds IS NOT NULL
              AND odds IS NOT NULL
              AND odds > 1.0
              AND clv_closing_odds > 1.0
              AND match_date >= date('now', ? || ' days')
            """,
            (f"-{days}",),
        ).fetchall()

    if not rows:
        return {"overall": None, "per_liga": []}

    clvs: list[float] = []
    per_liga: dict[str, list[float]] = {}

    for r in rows:
        clv = calculate_clv(float(r["odds"]), float(r["clv_closing_odds"]))
        if clv is None:
            continue
        clvs.append(clv)
        lg = r["league"] or "Nieznana"
        per_liga.setdefault(lg, []).append(clv)

    if not clvs:
        return {"overall": None, "per_liga": []}

    overall = {
        "n":            len(clvs),
        "clv_avg":      round(sum(clvs) / len(clvs), 2),
        "positive_pct": round(sum(1 for c in clvs if c > 0) / len(clvs) * 100, 1),
    }

    liga_stats = []
    for liga, vals in per_liga.items():
        if len(vals) < min_samples:
            continue
        liga_stats.append({
            "liga":     liga,
            "n":        len(vals),
            "clv_avg":  round(sum(vals) / len(vals), 2),
            "positive_pct": round(sum(1 for v in vals if v > 0) / len(vals) * 100, 1),
        })
    liga_stats.sort(key=lambda x: x["clv_avg"], reverse=True)

    return {"overall": overall, "per_liga": liga_stats}


def batch_record_closing_odds(records: list[dict]) -> int:
    """
    Zapisuje kursy zamknięcia dla wielu predykcji naraz.

    Args:
        records: lista {"prediction_id": int, "closing_odds": float}

    Returns:
        Liczba zaktualizowanych rekordów.
    """
    _ensure_clv_column()
    updated = 0
    for r in records:
        pid = r.get("prediction_id")
        odds = r.get("closing_odds")
        if pid and odds:
            result = record_closing_odds(pid, odds)
            if result is not None:
                updated += 1
    return updated
