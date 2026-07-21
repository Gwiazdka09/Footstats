"""core/user_stats.py – READ-ONLY agregat statystyk usera z rozliczonych kuponów (J1).

Liczy win-rate/P&L/ROI/streak wyłącznie z tabeli `coupons` (patrz coupon_tracker.py
za schemat i coupon_settlement.py za statusy). Rozliczone = status WON/LOST — DRAFT
i ACTIVE to kupony jeszcze pending, a PARTIAL/VOID nigdy nie zostały "żywym" zakładem
rozliczonym wynikiem, więc żadne z nich nie wchodzą do win-rate/streak (spec J1).

Żadnych INSERT/UPDATE/DELETE — tylko SELECT.

Uwaga o per_league: schemat legów kuponu jest NIESPÓJNY między źródłami kuponów
— risk_proposals.py/system_coupons.py dopisują klucz "liga" do legów, ale
daily_io.py/system_paper.py go nie mają (home/away/tip/odds/decision_score/mecz).
Grupowanie per_league byłoby więc zawodne (część kuponów bez ligi) bez ujednolicenia
schematu legów u źródła — dlatego POMINIĘTE w tej wersji.
"""

from dataclasses import dataclass
from datetime import datetime

from footstats.core.coupon_tracker import STATUS_LOST, STATUS_WON

SETTLED_STATUSES = (STATUS_WON, STATUS_LOST)


@dataclass(frozen=True)
class CouponResult:
    """Zysk-jednostki pojedynczego rozliczonego kuponu (do best/worst)."""

    coupon_id: int
    profit_units: float


@dataclass(frozen=True)
class ProgressPoint:
    """Jeden punkt krzywej postępu (J3) — stan kumulatywny po N-tym rozliczonym kuponie."""

    date: str
    cumulative_profit: float
    running_win_rate: float
    settled_count: int


@dataclass(frozen=True)
class UserStats:
    """Zagregowane statystyki usera policzone z rozliczonych kuponów."""

    user_id: int
    total_coupons: int
    settled_count: int
    wins: int
    losses: int
    win_rate: float
    profit_units: float
    roi: float
    current_streak: int
    best_coupon: CouponResult | None
    worst_coupon: CouponResult | None


def _profit_units(status: str, stake: float | None, odds: float | None) -> float:
    """Zysk-jednostki jednego kuponu: wygrana +stake*(kurs-1), przegrana -stake.

    WON bez kursu (odds brak/None/0) → 0.0, nie -stake — brak danych o kursie
    nie może zamienić wygranej w (fałszywą) stratę.
    """
    stake_val = stake or 0.0
    if status == STATUS_WON:
        if not odds:
            return 0.0
        return stake_val * (odds - 1.0)
    return -stake_val


def _row_date(value: object) -> str:
    """created_at (str TIMESTAMP z SQLite / datetime z Postgresa) -> 'YYYY-MM-DD'."""
    if isinstance(value, datetime):
        return value.date().isoformat()
    return str(value)[:10]


def _calc_streak(rows: list) -> int:
    """Aktualna seria licząc od najnowszego rozliczonego kuponu (rows: DESC).

    Dodatnia = seria W, ujemna = seria L, 0 gdy brak rozliczonych kuponów.
    """
    if not rows:
        return 0
    first_status = rows[0]["status"]
    count = 0
    for row in rows:
        if row["status"] != first_status:
            break
        count += 1
    return count if first_status == STATUS_WON else -count


def get_user_stats(user_id: int) -> UserStats:
    """Liczy statystyki usera z tabeli coupons (SELECT-only, brak zapisu).

    settled = status WON/LOST (DRAFT/ACTIVE/PARTIAL/VOID nie liczą się do
    win-rate/streak/ROI — patrz spec J1). Streak liczony od najnowszego
    rozliczonego kuponu wstecz (nie od proporcji wygranych/przegranych).
    """
    # Lokalny import (jak w coupon_settlement.py) – pozwala testom monkeypatchować
    # coupon_tracker._connect i mieć spójny widok tej samej (izolowanej) bazy.
    from footstats.core.coupon_tracker import _connect

    with _connect() as conn:
        total_coupons = conn.execute(
            "SELECT COUNT(*) AS n FROM coupons WHERE user_id = ?", (user_id,)
        ).fetchone()["n"]
        rows = conn.execute(
            """
            SELECT id, status, stake_pln, total_odds
            FROM coupons
            WHERE user_id = ? AND status IN (?, ?)
            ORDER BY created_at DESC, id DESC
            """,
            (user_id, *SETTLED_STATUSES),
        ).fetchall()

    settled_count = len(rows)
    wins = sum(1 for row in rows if row["status"] == STATUS_WON)
    losses = settled_count - wins
    win_rate = wins / settled_count if settled_count else 0.0

    results = [
        CouponResult(row["id"], _profit_units(row["status"], row["stake_pln"], row["total_odds"]))
        for row in rows
    ]
    profit_units = sum(result.profit_units for result in results)
    total_staked = sum((row["stake_pln"] or 0.0) for row in rows)
    roi = profit_units / total_staked if total_staked else 0.0

    return UserStats(
        user_id=user_id,
        total_coupons=total_coupons,
        settled_count=settled_count,
        wins=wins,
        losses=losses,
        win_rate=win_rate,
        profit_units=profit_units,
        roi=roi,
        current_streak=_calc_streak(rows),
        best_coupon=max(results, key=lambda r: r.profit_units) if results else None,
        worst_coupon=min(results, key=lambda r: r.profit_units) if results else None,
    )


def get_progress_series(user_id: int) -> list[ProgressPoint]:
    """Krzywa postępu w czasie (J3) — kumulatywny profit i win-rate po kolejnych
    rozliczonych kuponach usera (SELECT-only, brak zapisu).

    Uwaga o dacie: schemat `coupons` (init_coupon_tables w coupon_tracker.py) NIE
    ma osobnej kolumny daty rozliczenia (brak settled_at/updated_at) — użyto więc
    `created_at`, tak samo jak streak w J1 (`get_user_stats`/`_calc_streak`).

    Sortowanie chronologiczne (created_at ASC, id ASC jako tiebreaker przy
    identycznym znaczniku czasu — kupony rozliczane w tej samej sekundzie zachowują
    kolejność wstawienia). Pusty user -> [] bez wyjątku.
    """
    from footstats.core.coupon_tracker import _connect

    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, status, stake_pln, total_odds, created_at
            FROM coupons
            WHERE user_id = ? AND status IN (?, ?)
            ORDER BY created_at ASC, id ASC
            """,
            (user_id, *SETTLED_STATUSES),
        ).fetchall()

    points: list[ProgressPoint] = []
    cumulative_profit = 0.0
    wins = 0
    for settled_count, row in enumerate(rows, start=1):
        cumulative_profit += _profit_units(row["status"], row["stake_pln"], row["total_odds"])
        if row["status"] == STATUS_WON:
            wins += 1
        points.append(
            ProgressPoint(
                date=_row_date(row["created_at"]),
                cumulative_profit=cumulative_profit,
                running_win_rate=wins / settled_count,
                settled_count=settled_count,
            )
        )
    return points
