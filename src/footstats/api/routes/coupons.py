"""Coupon, match, kelly, and stats endpoints."""
import hmac
import json
import logging
import math
import os
from datetime import datetime, timedelta
from typing import List, Optional, Union

import footstats.config as cfg
import psycopg2
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from footstats.api.auth import require_admin, require_auth
from footstats.core.coupon_tracker import STATUS_ACTIVE, save_coupon, update_coupon_status
from footstats.core.response_cache import cached_response
from footstats.utils.db import connect as _connect

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["coupons"])

_MATCHES_CACHE: list = []


def _fallback_predictions() -> list:
    """
    Gdy brak realnych danych: mock TYLKO w trybie demo (DEMO_MODE=1), inaczej pusta
    lista. Bez tego realny user widziałby fałszywe mecze (Legia/Lech) jako prawdziwe.
    """
    if os.getenv("DEMO_MODE", "").strip() == "1":
        return _mock_predictions()
    return []


def _fetch_predictions() -> list:
    try:
        from footstats.scrapers.bzzoiro import BzzoiroClient
        from footstats.config import ENV_BZZOIRO
        key = os.getenv(ENV_BZZOIRO, "").strip()
        _log.info("BZZOIRO_KEY present: %s, length: %d", bool(key), len(key))
        if not key:
            _log.warning("Brak BZZOIRO_KEY — brak realnych predykcji (mock tylko w DEMO_MODE)")
            return _fallback_predictions()
        client = BzzoiroClient(key)
        preds = client.predykcje_tygodnia()
        _log.info("Bzzoiro returned %d predictions", len(preds) if preds else 0)
        return preds if preds else _fallback_predictions()
    except (OSError, ValueError, RuntimeError) as e:
        _log.error("_fetch_predictions error: %s", e, exc_info=True)
        return _fallback_predictions()


def _mock_predictions() -> list:
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    day2 = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
    return [
        {"id": "m001", "gosp": "Legia Warszawa", "gosc": "Lech Poznań", "liga": "PKO BP Ekstraklasa",
         "data": tomorrow, "godzina": "18:00",
         "pred_ml": {"prob_home_win": 0.52, "prob_draw": 0.28, "prob_away_win": 0.20, "prob_over_25": 0.61, "prob_btts_yes": 0.48},
         "odds": {"home": 1.85, "draw": 3.40, "away": 4.10, "over_2_5": 1.72, "under_2_5": 2.05, "btts": 1.90}},
        {"id": "m002", "gosp": "Ajax Amsterdam", "gosc": "PSV Eindhoven", "liga": "Eredivisie",
         "data": tomorrow, "godzina": "20:45",
         "pred_ml": {"prob_home_win": 0.45, "prob_draw": 0.25, "prob_away_win": 0.30, "prob_over_25": 0.72, "prob_btts_yes": 0.58},
         "odds": {"home": 2.10, "draw": 3.30, "away": 3.50, "over_2_5": 1.58, "under_2_5": 2.40, "btts": 1.75}},
        {"id": "m003", "gosp": "Roma", "gosc": "Lazio", "liga": "Serie A",
         "data": day2, "godzina": "20:45",
         "pred_ml": {"prob_home_win": 0.40, "prob_draw": 0.30, "prob_away_win": 0.30, "prob_over_25": 0.58, "prob_btts_yes": 0.52},
         "odds": {"home": 2.30, "draw": 3.20, "away": 3.10, "over_2_5": 1.80, "under_2_5": 1.98, "btts": 1.85}},
    ]


class AnalyzeRequest(BaseModel):
    match_ids: List[Union[int, str]]


class SelectionItem(BaseModel):
    match_id: Union[int, str]
    home: str
    away: str
    tip: str
    odds: float
    win_prob: float


class KellyRequest(BaseModel):
    selections: List[SelectionItem]


class BetBuilderRequest(BaseModel):
    prob_home_win: float
    prob_away_win: float
    prob_over_25: float
    selected: List[str] = []


class MarketsRequest(BaseModel):
    prob_home_win: float
    prob_away_win: float
    prob_over_25: float
    odds: dict = {}


class PlaceCouponRequest(BaseModel):
    selections: List[SelectionItem]
    total_odds: float | None = None
    stake_pln: float | None = None
    match_date: Optional[str] = None
    validate_only: bool = False  # waliduj bez zapisu (smoke/dry-run) — ZERO writes


class SettleRequest(BaseModel):
    days_back: Optional[int] = 3
    dry_run: Optional[bool] = False


class ShareRequest(BaseModel):
    shared: bool


class ManualLeg(BaseModel):
    home: str
    away: str
    tip: str
    odds: float


class ManualCouponRequest(BaseModel):
    legs: List[ManualLeg]
    stake_pln: float
    bookmaker: Optional[str] = None
    match_date: Optional[str] = None


class CouponResultRequest(BaseModel):
    result: str  # "WON" | "LOST" | "VOID"


_MAX_TEXT_LEN = 120
_MAX_BOOKMAKER_LEN = 60


def _validate_manual_coupon(req: ManualCouponRequest) -> None:
    """Waliduje ręczny wpis kuponu (fail-fast, granica systemu — HTTP 400 + PL detail)."""
    if not req.legs:
        raise HTTPException(status_code=400, detail="Kupon musi mieć co najmniej jedną nogę")
    if req.stake_pln <= 0:
        raise HTTPException(status_code=400, detail="Stawka musi być dodatnia")
    if req.bookmaker and len(req.bookmaker) > _MAX_BOOKMAKER_LEN:
        raise HTTPException(
            status_code=400,
            detail=f"Nazwa bukmachera zbyt długa (max {_MAX_BOOKMAKER_LEN} znaków)",
        )
    if req.match_date:
        try:
            datetime.strptime(req.match_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Data meczu musi być w formacie RRRR-MM-DD")
    for leg in req.legs:
        if leg.odds <= 1.0:
            raise HTTPException(status_code=400, detail="Kurs każdej nogi musi być większy niż 1.0")
        for pole, wartosc in (("gospodarz", leg.home), ("gość", leg.away), ("typ", leg.tip)):
            if not wartosc or not wartosc.strip():
                raise HTTPException(status_code=400, detail=f"Pole '{pole}' nie może być puste")
            if len(wartosc) > _MAX_TEXT_LEN:
                raise HTTPException(
                    status_code=400,
                    detail=f"Pole '{pole}' zbyt długie (max {_MAX_TEXT_LEN} znaków)",
                )


@router.get("/coupons/active")
@cached_response(ttl_seconds=30, vary_by=["user_id"])
def get_active_coupons(user_id: int = Depends(require_auth)):
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT * FROM coupons"
                " WHERE status IN ('ACTIVE','PENDING') AND user_id = ?"
                " ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["legs"] = json.loads(d.get("legs_json") or "[]")
            result.append(d)
        return result
    except psycopg2.Error as e:
        _log.error("get_active_coupons error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/coupons")
@cached_response(ttl_seconds=30, vary_by=["limit", "user_id"])
def get_coupons(limit: int = 50, user_id: int = Depends(require_auth)):
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT * FROM coupons WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["legs"] = json.loads(d.get("legs_json") or "[]")
            result.append(d)
        return result
    except psycopg2.Error as e:
        _log.error("get_coupons error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats/coupon-summary")
@cached_response(ttl_seconds=1800, vary_by=["days", "user_id"])
def get_coupon_summary(days: int = 30, user_id: int = Depends(require_auth)):
    try:
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT COUNT(*) as cnt, SUM(stake_pln) as total_stake,
                       SUM(payout_pln) as total_return, kupon_type, status
                FROM coupons
                WHERE created_at >= ? AND user_id = ?
                GROUP BY kupon_type, status
                """,
                (cutoff, user_id),
            ).fetchall()
            streak_rows = conn.execute(
                "SELECT status FROM coupons"
                " WHERE created_at >= ? AND user_id = ?"
                " ORDER BY created_at DESC LIMIT 20",
                (cutoff, user_id),
            ).fetchall()
        stats: dict = {
            "total_coupons": 0, "total_stake": 0.0, "total_return": 0.0,
            "roi_percent": 0.0, "win_count": 0, "loss_count": 0,
            "void_count": 0, "by_type": {},
        }
        for row in rows:
            cnt = row["cnt"]
            stake = row["total_stake"] or 0.0
            ret = row["total_return"] or 0.0
            typ = row["kupon_type"] or "unknown"
            st = row["status"] or "unknown"
            stats["total_coupons"] += cnt
            stats["total_stake"] += stake
            if st == "WIN":
                stats["win_count"] += cnt
                stats["total_return"] += ret
            elif st == "LOSS":
                stats["loss_count"] += cnt
            elif st == "VOID":
                stats["void_count"] += cnt
            if typ not in stats["by_type"]:
                stats["by_type"][typ] = {"wins": 0, "stake": 0.0, "return": 0.0}
            if st == "WIN":
                stats["by_type"][typ]["wins"] += cnt
                stats["by_type"][typ]["return"] += ret
            stats["by_type"][typ]["stake"] += stake
        if stats["total_stake"] > 0:
            stats["roi_percent"] = round(
                (stats["total_return"] - stats["total_stake"]) / stats["total_stake"] * 100, 1
            )
        current = max_s = 0
        for sr in streak_rows:
            if sr["status"] == "WIN":
                current += 1
                max_s = max(max_s, current)
            else:
                current = 0
        stats["streak"] = {"current": current, "max": max_s}
        stats["confidence_avg"] = 0.0
        return stats
    except psycopg2.Error as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/matches/today")
@cached_response(ttl_seconds=600, vary_by=["user_id"])
def get_matches_today(user_id: int = Depends(require_auth)):
    global _MATCHES_CACHE
    preds = _fetch_predictions()
    now = datetime.now()
    cutoff = now + timedelta(hours=48)
    future = []
    for m in preds:
        try:
            dt = datetime.strptime(f"{m.get('data','')} {m.get('godzina','')}", "%Y-%m-%d %H:%M")
            if now < dt <= cutoff:
                future.append(m)
        except (ValueError, TypeError):
            continue
    future.sort(key=lambda m: (m.get("data", ""), m.get("godzina", "")))
    _MATCHES_CACHE = future[:30] if future else []
    return _MATCHES_CACHE


@router.post("/matches/analyze")
def analyze_matches(req: AnalyzeRequest, user_id: int = Depends(require_auth)):
    global _MATCHES_CACHE
    if not _MATCHES_CACHE:
        _MATCHES_CACHE = _fetch_predictions()
    from footstats.core.match_tips import build_tips
    id_set = {str(i) for i in req.match_ids}
    return [build_tips(m) for m in _MATCHES_CACHE if str(m.get("id")) in id_set]


@router.get("/coupons/daily-proposals")
@cached_response(ttl_seconds=600, vary_by=["user_id"])
def get_daily_proposals(user_id: int = Depends(require_auth)):
    """Codzienne propozycje kuponów wg ryzyka: low/medium/high."""
    global _MATCHES_CACHE
    if not _MATCHES_CACHE:
        _MATCHES_CACHE = _fetch_predictions()
    from footstats.core.risk_proposals import build_daily_proposals
    return build_daily_proposals(_MATCHES_CACHE)


@router.post("/betbuilder/markets")
def betbuilder_markets(req: BetBuilderRequest, user_id: int = Depends(require_auth)):
    """
    FAZA 18.2: stan kreatora BetBuilder dla 1 meczu.
    Z prawdopodobieństw 1X2/Over estymuje lambdy Poissona, buduje macierz wyników
    i zwraca rynki z szansą + regułami korelacji (allowed/powod) dla `selected`.
    """
    from footstats.core.bet_builder import estimate_lambdas_from_probs, probability_matrix
    from footstats.core.betbuilder_rules import oblicz_rynki

    lh, la = estimate_lambdas_from_probs(
        req.prob_home_win, req.prob_away_win, req.prob_over_25
    )
    mat = probability_matrix(lh, la)
    wynik = oblicz_rynki(mat, req.selected)
    wynik["lambdas"] = {"home": lh, "away": la}
    return wynik


@router.post("/markets/catalog")
def markets_catalog(req: MarketsRequest, user_id: int = Depends(require_auth)):
    """
    FAZA 20: pełny katalog rynków bramkowych dla meczu (pogrupowany jak STS).
    Z prob 1X2/Over estymuje lambdy Poissona → liczy ~34 rynki rozliczalne.
    Kurs: Bzzoiro gdy w `odds`, inaczej fair (1/prob).
    """
    from footstats.core.bet_builder import estimate_lambdas_from_probs
    from footstats.core.markets import build_market_catalog

    lh, la = estimate_lambdas_from_probs(
        req.prob_home_win, req.prob_away_win, req.prob_over_25
    )
    return {
        "lambdas": {"home": lh, "away": la},
        "grupy": build_market_catalog(lh, la, bzz_odds=req.odds),
    }


@router.post("/coupon/kelly")
def calculate_kelly(req: KellyRequest, user_id: int = Depends(require_auth)):
    if not req.selections:
        raise HTTPException(status_code=400, detail="Brak typów")
    with _connect() as conn:
        row = conn.execute(
            "SELECT balance FROM bankroll_state WHERE user_id = ?", (user_id,)
        ).fetchone()
        bankroll = float(row["balance"]) if row else float(cfg.AGENT_BANKROLL)
        frac_row = conn.execute(
            "SELECT value FROM bot_settings WHERE user_id = ? AND key = 'kelly_fraction'",
            (user_id,),
        ).fetchone()
        fraction = int(frac_row["value"]) if frac_row else cfg.AGENT_KELLY_FRACTION
    total_odds = 1.0
    win_prob = 1.0
    for s in req.selections:
        total_odds *= s.odds
        p = s.win_prob / 100.0 if s.win_prob > 1.0 else s.win_prob
        win_prob *= p
    b = total_odds - 1.0
    f_star = max((b * win_prob - (1.0 - win_prob)) / b, 0.0) if b > 0 else 0.0
    stake = round(f_star / fraction * bankroll, 2)
    stake = max(stake, 2.0)
    stake = min(stake, round(bankroll * 0.20, 2))
    return {
        "total_odds": round(total_odds, 2), "win_prob_pct": round(win_prob * 100, 1),
        "f_star_pct": round(f_star * 100, 2), "stake_pln": stake,
        "bankroll": bankroll, "kelly_fraction": fraction,
    }


@router.post("/coupon/place")
def place_coupon(req: PlaceCouponRequest, user_id: int = Depends(require_auth)):
    if not req.stake_pln or req.stake_pln < 2.0:
        raise HTTPException(status_code=400, detail="Minimalna stawka to 2.00 PLN")
    with _connect() as conn:
        row = conn.execute(
            "SELECT balance FROM bankroll_state WHERE user_id = ?", (user_id,)
        ).fetchone()
        balance = float(row["balance"]) if row else 0.0
        if req.stake_pln > balance:
            raise HTTPException(status_code=400, detail=f"Niewystarczający bankroll ({balance:.2f} PLN)")
        if req.validate_only:
            # Walidacja przeszła (stawka>=2, bankroll OK) — BEZ zapisu do DB.
            # Używane przez operator smoke: wcześniej smoke realnie INSERT-ował
            # kupon do prod Neon + zjadał bankroll (martwe ACTIVE z datą 2099).
            return {"ok": True, "validated": True, "stake_pln": req.stake_pln}
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        legs_json = json.dumps(
            [{"home": s.home, "away": s.away, "tip": s.tip, "odds": s.odds, "decision_score": int(s.win_prob)}
             for s in req.selections],
            ensure_ascii=False,
        )
        coupon_row = conn.execute(
            """
            INSERT INTO coupons
                (created_at, phase, status, kupon_type, legs_json,
                 total_odds, stake_pln, payout_pln, match_date_first, user_id)
            VALUES (?,?,?,?,?,?,?,?,?,?) RETURNING id
            """,
            (now, "final", "ACTIVE", "accumulator", legs_json,
             req.total_odds, req.stake_pln, None,
             req.match_date or datetime.now().strftime("%Y-%m-%d"), user_id),
        ).fetchone()
        coupon_id = coupon_row["id"]
        new_balance = round(balance - req.stake_pln, 2)
        conn.execute(
            "UPDATE bankroll_state SET balance=?, updated_at=? WHERE user_id=?",
            (new_balance, now, user_id),
        )
        conn.execute(
            "INSERT INTO bankroll_history (timestamp, change_pln, new_balance, type, description, user_id)"
            " VALUES (?,?,?,?,?,?)",
            (now, -req.stake_pln, new_balance, "BET",
             f"Kupon AI ({', '.join(s.tip for s in req.selections)})", user_id),
        )
    from footstats.core.response_cache import clear_response_cache
    clear_response_cache()
    return {"ok": True, "coupon_id": coupon_id, "new_balance": new_balance, "stake_pln": req.stake_pln}


@router.post("/coupon/manual")
def manual_coupon(req: ManualCouponRequest, user_id: int = Depends(require_auth)):
    """
    Dziennik kuponów (J4a): ręczny wpis kuponu obstawionego gdzie indziej.
    Free-form (bez match_id z naszej listy), NEUTRALNY dla bankrollu —
    dziennik nie rusza papierowego salda (bankroll_state).
    """
    _validate_manual_coupon(req)
    legs = [{"home": leg.home, "away": leg.away, "tip": leg.tip, "odds": leg.odds} for leg in req.legs]
    total_odds = round(math.prod(leg.odds for leg in req.legs), 2)
    coupon_id = save_coupon(
        phase="manual",
        kupon_type="manual",
        legs=legs,
        total_odds=total_odds,
        stake_pln=req.stake_pln,
        bookmaker=req.bookmaker,
        match_date_first=req.match_date,
        user_id=user_id,
    )
    update_coupon_status(coupon_id, STATUS_ACTIVE)
    from footstats.core.response_cache import clear_response_cache
    clear_response_cache()
    return {"ok": True, "coupon_id": coupon_id, "total_odds": total_odds, "status": STATUS_ACTIVE}


@router.patch("/coupon/{coupon_id}/result")
def set_coupon_result(coupon_id: int, req: CouponResultRequest, user_id: int = Depends(require_auth)):
    """Ręczne oznaczenie wyniku kuponu z dziennika (J4a).

    CAS-guard (expected_status=ACTIVE) chroni przed podwójnym rozliczeniem —
    drugie wywołanie na już rozliczonym kuponie zwraca 409. Zero operacji na
    bankroll_state (dziennik jest neutralny dla papierowego salda).
    Tylko kupony kupon_type='manual' — inaczej user mógłby ręcznie wymusić
    fałszywy WON na własnym kuponie AI (accumulator/system), który normalnie
    rozlicza automat (coupon_settlement).
    """
    if req.result not in ("WON", "LOST", "VOID"):
        raise HTTPException(status_code=400, detail="Wynik musi być WON, LOST lub VOID")
    try:
        with _connect() as conn:
            row = conn.execute(
                "SELECT user_id, stake_pln, total_odds, kupon_type FROM coupons WHERE id = ?",
                (coupon_id,),
            ).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Kupon nie istnieje")
            if int(row["user_id"]) != user_id:
                raise HTTPException(status_code=403, detail="Brak uprawnień do tego kuponu")
            if row["kupon_type"] != "manual":
                raise HTTPException(
                    status_code=400,
                    detail="Tylko ręcznie dodane kupony można rozliczać ręcznie",
                )
            stake = float(row["stake_pln"] or 0.0)
            total_odds = float(row["total_odds"] or 0.0)
    except psycopg2.Error as e:
        _log.error("set_coupon_result lookup error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    if req.result == "WON":
        payout = round(stake * total_odds, 2)
    elif req.result == "LOST":
        payout = 0.0
    else:  # VOID — neutralne, stawka zwrócona
        payout = stake

    zmieniono = update_coupon_status(
        coupon_id, req.result, payout_pln=payout, expected_status="ACTIVE"
    )
    if not zmieniono:
        raise HTTPException(status_code=409, detail="Kupon już rozliczony lub nieaktywny")
    from footstats.core.response_cache import clear_response_cache
    clear_response_cache()
    return {"ok": True, "coupon_id": coupon_id, "status": req.result, "payout_pln": payout}


@router.patch("/coupon/{coupon_id}/share")
def share_coupon(coupon_id: int, req: ShareRequest, user_id: int = Depends(require_auth)):
    """Udostępnij/ukryj własny kupon na liście 'Najlepsi typerzy'."""
    try:
        with _connect() as conn:
            row = conn.execute(
                "SELECT user_id FROM coupons WHERE id = ?", (coupon_id,)
            ).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Kupon nie istnieje")
            if int(row["user_id"]) != user_id:
                raise HTTPException(status_code=403, detail="Brak uprawnień do tego kuponu")
            conn.execute(
                "UPDATE coupons SET shared = ? WHERE id = ?", (req.shared, coupon_id)
            )
        from footstats.core.response_cache import clear_response_cache
        clear_response_cache()
        return {"ok": True, "coupon_id": coupon_id, "shared": req.shared}
    except psycopg2.Error as e:
        _log.error("share_coupon error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/leaderboard")
@cached_response(ttl_seconds=1800)
def get_leaderboard(min_coupons: int = 3, limit: int = 20):
    """Ranking najlepszych typerów wg win rate na udostępnionych kuponach."""
    try:
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT u.id as user_id, u.username,
                       COUNT(*) as total,
                       SUM(CASE WHEN c.status IN ('WON','WIN') THEN 1 ELSE 0 END) as wins
                FROM coupons c
                JOIN users u ON u.id = c.user_id
                WHERE c.shared = TRUE AND c.status IN ('WON','WIN','LOST','LOSE')
                GROUP BY u.id, u.username
                HAVING COUNT(*) >= ?
                ORDER BY (CAST(SUM(CASE WHEN c.status IN ('WON','WIN') THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*)) DESC,
                         total DESC
                LIMIT ?
                """,
                (min_coupons, limit),
            ).fetchall()
        result = []
        for r in rows:
            total = r["total"]
            wins = r["wins"] or 0
            result.append({
                "user_id": r["user_id"],
                "username": r["username"],
                "total": total,
                "wins": wins,
                "win_rate": round(wins / total * 100, 1) if total else 0.0,
            })
        return result
    except psycopg2.Error as e:
        _log.error("get_leaderboard error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/leaderboard/{username}/coupons")
@cached_response(ttl_seconds=600, vary_by=["username"])
def get_user_shared_coupons(username: str, limit: int = 20):
    """Udostępnione kupony danego typera (publiczny podgląd)."""
    try:
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT c.* FROM coupons c
                JOIN users u ON u.id = c.user_id
                WHERE u.username = ? AND c.shared = TRUE
                ORDER BY c.created_at DESC LIMIT ?
                """,
                (username, limit),
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["legs"] = json.loads(d.get("legs_json") or "[]")
            # OWASP API3: publiczny podgląd — nie wystawiaj wewn. identyfikatora usera.
            d.pop("user_id", None)
            result.append(d)
        return result
    except psycopg2.Error as e:
        _log.error("get_user_shared_coupons error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/coupons/settle")
def settle_coupons(req: SettleRequest, user_id: int = Depends(require_admin)):
    # AUTHZ: settle_active_coupons rozlicza kupony WSZYSTKICH userów (brak filtra
    # user_id) → tylko admin. Wcześniej require_auth = każdy zalogowany mógł
    # wymusić rozliczenie/VOID cudzych kuponów (+ wektor DoS na FlashScore/AF).
    try:
        from footstats.core.coupon_settlement import settle_active_coupons
        stats = settle_active_coupons(days_back=req.days_back or 3, dry_run=req.dry_run or False, verbose=True)
        return {
            "ok": True,
            "settled": stats.get("settled", 0),
            "partial": stats.get("partial", 0),
            "errors": stats.get("errors", 0),
            "voided": stats.get("voided", 0),
            "message": (
                f"Rozliczono {stats.get('settled',0)}, częściowych {stats.get('partial',0)}, "
                f"VOID {stats.get('voided',0)}, błędów {stats.get('errors',0)}"
            ),
        }
    except (ValueError, KeyError, AttributeError, TypeError) as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cron/settle")
def cron_settle(x_cron_secret: str = Header(default=""), days_back: int = 3):
    """Endpoint dla Google Cloud Scheduler — rozlicza ACTIVE kupony."""
    expected = os.getenv("CRON_SECRET", "")
    if not expected or not hmac.compare_digest(x_cron_secret, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        from footstats.core.coupon_settlement import settle_active_coupons
        from footstats.core.response_cache import clear_response_cache
        stats = settle_active_coupons(days_back=days_back, dry_run=False, verbose=True)
        clear_response_cache()
        _log.info("cron_settle: %s", stats)
        return {
            "ok": True,
            "settled": stats.get("settled", 0),
            "partial": stats.get("partial", 0),
            "errors": stats.get("errors", 0),
        }
    except (ValueError, KeyError, RuntimeError) as e:
        _log.error("cron_settle error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cron/draft")
def cron_draft(x_cron_secret: str = Header(default=""), days: int = 2, dry_run: bool = True):
    """Endpoint dla Google Cloud Scheduler — lite draft System paper-trading (PC-niezależny).

    Generuje predykcje System (model-only, requests: Bzzoiro → quick_picks), bez
    Playwright/Groq/Telegram. dry_run=True (DEFAULT) = podgląd, ZERO zapisów Neon.
    Live zbieranie danych: wywołać z dry_run=false (świadomie, po weryfikacji dry-run).
    """
    expected = os.getenv("CRON_SECRET", "")
    if not expected or not hmac.compare_digest(x_cron_secret, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")
    from footstats.core.cloud_draft import generuj_system_draft
    result = generuj_system_draft(dni=days, dry_run=dry_run)
    _log.info("cron_draft (dry_run=%s): %s", dry_run,
              {k: v for k, v in result.items() if k != "legs"})
    return result


@router.post("/cron/evict-cache")
def cron_evict_cache(x_cron_secret: str = Header(default=""), max_days: int = 30):
    """Endpoint dla Google Cloud Scheduler — usuwa stare pliki cache."""
    expected = os.getenv("CRON_SECRET", "")
    if not expected or not hmac.compare_digest(x_cron_secret, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        from footstats.utils.cache_evict import evict_old_cache
        deleted = evict_old_cache(max_days=max_days)
        _log.info("cron_evict_cache: usunięto %d pliki (>%dd)", deleted, max_days)
        return {"ok": True, "deleted": deleted, "max_days": max_days}
    except (OSError, ImportError, ValueError) as e:
        _log.error("cron_evict_cache error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
