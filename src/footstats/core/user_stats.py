"""core/user_stats.py – READ-ONLY agregat statystyk usera z rozliczonych kuponów (J1).

Liczy win-rate/P&L/ROI/streak wyłącznie z tabeli `coupons` (patrz coupon_tracker.py
za schemat i coupon_settlement.py za statusy). Rozliczone = status WON/LOST — DRAFT
i ACTIVE to kupony jeszcze pending, a PARTIAL/VOID nigdy nie zostały "żywym" zakładem
rozliczonym wynikiem, więc żadne z nich nie wchodzą do win-rate/streak (spec J1).

Żadnych INSERT/UPDATE/DELETE — tylko SELECT.

Uwaga o per_league: schemat legów był NIESPÓJNY między źródłami — risk_proposals.py
i system_coupons.py dopisywały klucz "liga", a daily_io.py i system_paper.py nie.
**Ujednolicone 01.09**: oba brakujące źródła dokładają teraz "liga".

Grupowanie per_league dalej NIE jest włączone, ale z innego powodu: 326 kuponów
zapisanych PRZED tą zmianą nie ma tego pola i już go nie dostanie. Zmierzone
01.09 — próba policzenia ROI per liga przez dopasowanie do `predictions` po
nazwach drużyn objęła 25 z 243 rozliczonych kuponów, bo `predictions` zapisuje
wyłącznie typy, które przeszły przez LLM-a. Statystyka per_league będzie więc
wiarygodna dopiero na kuponach od 01.09 w górę — włączać ją, gdy uzbiera się
próba, nie wcześniej.
"""

import json
import logging
import math
import re
from dataclasses import dataclass
from datetime import datetime

from footstats.core.coupon_tracker import STATUS_LOST, STATUS_WON, wyplata_po_podatku
from footstats.utils.betting import (
    _LICZBA,
    _RE_GOL,
    _RE_ROGI,
    _RE_SOT,
    _rozbij_typ,
)

log = logging.getLogger(__name__)

MALA_PROBA_N = 20

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


def _profit_units(
    status: str, stake: float | None, odds: float | None, payout: float | None = None
) -> float:
    """Zysk-jednostki jednego kuponu, z FAKTYCZNEJ wypłaty (spójnie z rankingiem).

    WON z `payout_pln` → payout - stake (wypłata z buka, np. z boosterem).
    WON bez wypłaty → netto po podatku (`wyplata_po_podatku`) - stake.
    LOST → -stake. WON bez kursu i bez wypłaty → 0.0, nie -stake: brak danych
    nie może zamienić wygranej w (fałszywą) stratę.
    """
    stake_val = stake or 0.0
    if status == STATUS_WON:
        if payout is not None:
            return payout - stake_val
        if not odds:
            return 0.0
        return wyplata_po_podatku(stake_val, odds) - stake_val
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
            SELECT id, status, stake_pln, total_odds, payout_pln
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
        CouponResult(row["id"], _profit_units(
            row["status"], row["stake_pln"], row["total_odds"], row["payout_pln"]
        ))
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
            SELECT id, status, stake_pln, total_odds, payout_pln, created_at
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
        cumulative_profit += _profit_units(
            row["status"], row["stake_pln"], row["total_odds"], row["payout_pln"]
        )
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


# ── Statystyki wg rodzaju typu ────────────────────────────────────────────────
_RE_WYNIK = re.compile(r"^[1X2]$")
_RE_PODWOJNA = re.compile(r"^(1X|X2|12)$")
_RE_GOLE_MECZU = re.compile(rf"^(OVER|UNDER)\s+{_LICZBA}$")
_RE_BTTS = re.compile(r"^BTTS(\s+(NO|NIE|TAK|YES))?$")
_RE_GOLE_DRUZYNY = re.compile(
    rf"^(?:[12]\s+(OVER|UNDER)\s+{_LICZBA}|(GOSPODARZ|GO[SŚ][CĆ])\s+STRZELI.*)$"
)
_BLEDY_LEGS = (ValueError, TypeError)


@dataclass(frozen=True)
class MarketStat:
    """Skuteczność nóg jednego rodzaju typu (pomiar, nie rekomendacja)."""

    market: str
    n: int
    wins: int
    hit_rate: float
    implied_prob: float
    edge_pp: float
    se_pp: float
    n_za_male: bool
    skladniki: list[str]


def _rodzaj_czlonu(czlon: str) -> str:
    """Rodzaj pojedynczego członu typu (już po upper/strip)."""
    if _RE_WYNIK.match(czlon):
        return "Wynik 1X2"
    if _RE_PODWOJNA.match(czlon):
        return "Podwójna szansa"
    if _RE_GOLE_MECZU.match(czlon):
        return "Gole w meczu"
    if _RE_BTTS.match(czlon):
        return "Obie strzelą"
    if _RE_GOLE_DRUZYNY.match(czlon):
        return "Gole drużyny"
    if _RE_ROGI.match(czlon):
        return "Rzuty rożne"
    if _RE_GOL.match(czlon):
        return "Zawodnik: gol"
    if _RE_SOT.match(czlon):
        return "Zawodnik: celne strzały"
    return "Inne"


def _rozbij_bb(tip: str) -> list[str] | None:
    """Człony typu Bet Builder (po upper) albo None, gdy tip nie jest BB."""
    tekst = (tip or "").strip().upper()
    if tekst.startswith("BB:") or tekst.startswith("BB "):
        return _rozbij_typ(tekst[3:].strip())
    return None


def skladniki_bb(tip: str) -> list[str]:
    """Unikalne rodzaje członów BB (kolejność pierwszego wystąpienia); [] gdy nie BB."""
    czlony = _rozbij_bb(tip)
    if czlony is None:
        return []
    return list(dict.fromkeys(_rodzaj_czlonu(c) for c in czlony))


def klasyfikuj_rynek(tip: str | None) -> str:
    """Rodzaj typu po polsku; BB liczony jako całość („Bet Builder")."""
    if _rozbij_bb(tip or "") is not None:
        return "Bet Builder"
    czlony = _rozbij_typ((tip or "").strip().upper())
    if len(czlony) != 1:
        return "Inne"
    return _rodzaj_czlonu(czlony[0])


def _nogi_rozliczone(legs_json: object) -> list[tuple[str, float | None, bool]]:
    """(tip, kurs, trafiona) tylko dla nóg z leg_won True/False; reszta pomijana."""
    try:
        legs = json.loads(legs_json) if isinstance(legs_json, str) else legs_json
    except ValueError as e:
        log.warning("market_stats: nieczytelny legs_json: %s", e)
        return []
    wynik: list[tuple[str, float | None, bool]] = []
    for leg in legs or []:
        if not isinstance(leg, dict) or leg.get("leg_won") not in (True, False):
            continue
        try:
            kurs = float(leg["odds"]) if leg.get("odds") else None
        except _BLEDY_LEGS as e:
            log.warning("market_stats: zły kurs nogi %r: %s", leg.get("odds"), e)
            kurs = None
        wynik.append((str(leg.get("tip", "")), kurs, leg["leg_won"] is True))
    return wynik


def _zbuduj_stat(
    market: str, nogi: list[tuple[float | None, bool]], skladniki: list[str]
) -> MarketStat:
    """Agreguje nogi jednego rodzaju do MarketStat."""
    n = len(nogi)
    wins = sum(1 for _, won in nogi if won)
    hit = wins / n
    implied_list = [1.0 / k for k, _ in nogi if k and k > 1.0]
    implied = sum(implied_list) / len(implied_list) if implied_list else 0.0
    return MarketStat(
        market=market,
        n=n,
        wins=wins,
        hit_rate=hit,
        implied_prob=implied,
        edge_pp=(hit - implied) * 100 if implied_list else 0.0,
        se_pp=math.sqrt(hit * (1 - hit) / n) * 100,
        n_za_male=n < MALA_PROBA_N,
        skladniki=skladniki,
    )


def get_market_stats(user_id: int) -> list[MarketStat]:
    """Statystyki nóg kuponów manual (WON/LOST) wg rodzaju typu, malejąco po n.

    Liczą się tylko nogi z leg_won True/False: kupon LOST rozliczany jest na
    pierwszej przegranej nodze, reszta nie ma leg_won i jest pomijana (nie zgadujemy).
    SELECT-only.
    """
    from footstats.core.coupon_tracker import _connect

    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT legs_json FROM coupons
            WHERE user_id = ? AND kupon_type = 'manual' AND status IN (?, ?)
            """,
            (user_id, *SETTLED_STATUSES),
        ).fetchall()

    grupy: dict[str, list[tuple[float | None, bool]]] = {}
    skladniki: dict[str, list[str]] = {}
    for row in rows:
        for tip, kurs, won in _nogi_rozliczone(row["legs_json"]):
            rodzaj = klasyfikuj_rynek(tip)
            grupy.setdefault(rodzaj, []).append((kurs, won))
            if rodzaj == "Bet Builder":
                znane = skladniki.setdefault(rodzaj, [])
                znane.extend(s for s in skladniki_bb(tip) if s not in znane)
    stats = [_zbuduj_stat(m, nogi, skladniki.get(m, [])) for m, nogi in grupy.items()]
    return sorted(stats, key=lambda s: s.n, reverse=True)
