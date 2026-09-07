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

import json
import logging
from datetime import datetime, timedelta

from footstats.utils.db import connect as _connect

_log = logging.getLogger(__name__)


def _ensure_clv_column() -> None:
    """Dodaje kolumnę clv_closing_odds jeśli nie istnieje."""
    with _connect() as conn:
        try:
            conn.execute(
                "ALTER TABLE predictions ADD COLUMN clv_closing_odds REAL"
            )
        except Exception:  # noqa: BLE001 — DB-specific "column exists" errors vary by driver
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

    # date('now', ...) jest SQLite-only → na Neon/Postgres (prod) rzucało błąd
    # i CLV report był martwy. Liczymy próg w Pythonie i porównujemy stringowo
    # (match_date to ISO 'YYYY-MM-DD...' → leksykograficzne >= działa na obu DB).
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    with _connect() as conn:
        # `odds_verified = 1` — kurs w `predictions` zapisuje sie PRZED weryfikacja
        # (KROK 3 vs KROK 4 `daily_agent`), wiec niezweryfikowany bywa kursem
        # zaproponowanym przez model jezykowy. CLV liczone na takim kursie mierzy
        # halucynacje, nie przewage nad rynkiem.
        rows = conn.execute(
            """
            SELECT league, odds, clv_closing_odds, tip_correct
            FROM predictions
            WHERE clv_closing_odds IS NOT NULL
              AND odds IS NOT NULL
              AND odds > 1.0
              AND clv_closing_odds > 1.0
              AND COALESCE(odds_verified, 0) = 1
              AND match_date >= ?
            """,
            (cutoff,),
        ).fetchall()
        pominiete = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM predictions
            WHERE clv_closing_odds IS NOT NULL
              AND odds IS NOT NULL
              AND odds > 1.0
              AND clv_closing_odds > 1.0
              AND COALESCE(odds_verified, 0) = 0
              AND match_date >= ?
            """,
            (cutoff,),
        ).fetchone()

    # Pusty raport z powodu braku weryfikacji to CO INNEGO niz brak danych —
    # bez tego ostrzezenia wyglada jak cisza, a jest odrzuceniem calej proby.
    n_pominietych = (dict(pominiete).get("n") if pominiete else 0) or 0
    if n_pominietych:
        _log.warning("[CLV] pominieto %d predykcji z niezweryfikowanym kursem"
                     " (zapis przed KROK 4) — nie nadaja sie do CLV", n_pominietych)

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


def raport_clv_z_kuponow(kupony, min_probek: int = 5) -> dict:
    """CLV liczone z NÓG kuponów — jedyna ścieżka, która obejmuje paper-trading.

    `get_clv_report` wyżej czyta `predictions`, a ta tabela ma 291 wierszy wobec
    439 rozliczonych kuponów i pokrywa wyłącznie typy przepuszczone przez LLM-a.
    Główne źródło danych, `system_paper.build_single_leg_coupons` (429 z tych
    kuponów), nie dotyka `predictions` w ogóle — bierze typ prosto z modelu.
    Raport oparty tylko na tamtej tabeli mierzyłby ułamek ruchu i wyglądałby
    przy tym kompletnie.

    `kupony`: wiersze z `coupons` (dict albo sqlite3.Row) z `legs_json`. Nogi
    dostają `clv_closing` w `evening_agent` przy rozliczaniu.

    Grupujemy po TYPIE, nie po lidze: 1X2 i Over/Under to różne rynki o różnej
    marży, więc jedna średnia je miesza. `overall` liczy się z wszystkich nóg
    naraz (średnia ważona), nie ze średnich kubełków — kubełek z jedną nogą nie
    może ważyć tyle co kubełek ze setką.
    """
    clvs: list[float] = []
    per_typ: dict[str, list[float]] = {}
    # Zbiorczo, nie per wiersz: przy zepsutym zapisie byłyby to setki linii,
    # a szum niszczy alarmy tak samo skutecznie jak cisza.
    zepsute_nogi = 0

    for kupon in kupony:
        surowe = kupon["legs_json"] if "legs_json" in _klucze(kupon) else None
        try:
            nogi = json.loads(surowe or "[]")
        except (ValueError, TypeError):
            # Pojedynczy zepsuty wiersz nie może wyciszyć całego raportu.
            _log.warning("[CLV] pomijam kupon z nieczytelnym legs_json")
            continue
        for noga in nogi:
            try:
                bet = float(noga.get("odds") or 0.0)
                zamkniecie = float(noga.get("clv_closing") or 0.0)
            except (TypeError, ValueError) as e:
                zepsute_nogi += 1
                if zepsute_nogi == 1:
                    _log.debug("[CLV] noga z nieliczbowym kursem (%s: %s)",
                               type(e).__name__, e)
                continue
            clv = calculate_clv(bet, zamkniecie)
            if clv is None:
                continue
            clvs.append(clv)
            per_typ.setdefault(str(noga.get("tip") or "?"), []).append(clv)

    if zepsute_nogi:
        # Cicha strata próby przekłada się wprost na przesunięty CLV, a raport
        # bez tej liczby wygląda identycznie jak raport z kompletu danych.
        _log.warning("[CLV] %d nog pominietych — kurs wziecia albo zamkniecia"
                     " nie jest liczba", zepsute_nogi)

    if not clvs:
        return {"overall": None, "per_typ": []}

    def _staty(vals: list[float]) -> dict:
        return {"n": len(vals),
                "clv_avg": round(sum(vals) / len(vals), 2),
                "positive_pct": round(sum(1 for v in vals if v > 0) / len(vals) * 100, 1)}

    typy = [{"typ": t, **_staty(v)} for t, v in per_typ.items() if len(v) >= min_probek]
    typy.sort(key=lambda x: x["clv_avg"], reverse=True)
    return {"overall": _staty(clvs), "per_typ": typy}


def _klucze(wiersz) -> set:
    """Nazwy kolumn wiersza. `dict` i `sqlite3.Row` maja oba `.keys()`.

    Potrzebne, bo `"legs_json" in row` na `sqlite3.Row` iteruje WARTOSCI, nie
    nazwy kolumn — czyli odpowiada na inne pytanie i po cichu daje False.
    """
    return set(wiersz.keys()) if hasattr(wiersz, "keys") else set()


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
