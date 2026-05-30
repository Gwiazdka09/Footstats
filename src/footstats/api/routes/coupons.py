"""Coupon, match, kelly, and stats endpoints."""
import json
import logging
import os
from datetime import datetime, timedelta
from typing import List, Optional

import footstats.config as cfg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from footstats.api.auth import require_auth
from footstats.core.response_cache import cached_response
from footstats.utils.db import connect as _connect

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["coupons"])

_MATCHES_CACHE: list = []


def _to_pct(v, default: float = 33.0) -> float:
    if v is None:
        return default
    f = float(v)
    return round(f * 100 if 0 < f < 1.0 else f, 1)


def _fetch_predictions() -> list:
    try:
        from footstats.scrapers.bzzoiro import BzzoiroClient
        from footstats.config import ENV_BZZOIRO
        key = os.getenv(ENV_BZZOIRO, "").strip()
        _log.info("BZZOIRO_KEY present: %s, length: %d", bool(key), len(key))
        if not key:
            _log.warning("Brak BZZOIRO_KEY — using mock predictions")
            return _mock_predictions()
        client = BzzoiroClient(key)
        preds = client.predykcje_tygodnia()
        _log.info("Bzzoiro returned %d predictions", len(preds) if preds else 0)
        return preds if preds else _mock_predictions()
    except Exception as e:
        _log.error("_fetch_predictions error: %s", e, exc_info=True)
        return _mock_predictions()


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
    match_ids: List[str]


class SelectionItem(BaseModel):
    match_id: str
    home: str
    away: str
    tip: str
    odds: float
    win_prob: float


class KellyRequest(BaseModel):
    selections: List[SelectionItem]


class PlaceCouponRequest(BaseModel):
    selections: List[SelectionItem]
    total_odds: float | None = None
    stake_pln: float | None = None
    match_date: Optional[str] = None


class SettleRequest(BaseModel):
    days_back: Optional[int] = 3
    dry_run: Optional[bool] = False


@router.get("/coupons/active")
@cached_response(ttl_seconds=900, vary_by=["user_id"])
def get_active_coupons(user_id: int = Depends(require_auth)):
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
        d["legs"] = json.loads(d["legs_json"])
        result.append(d)
    return result


@router.get("/coupons")
@cached_response(ttl_seconds=900, vary_by=["limit", "user_id"])
def get_coupons(limit: int = 50, user_id: int = Depends(require_auth)):
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM coupons WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["legs"] = json.loads(d["legs_json"])
        result.append(d)
    return result


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
    except Exception as e:
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
    _MATCHES_CACHE = future[:15] if future else []
    return _MATCHES_CACHE


@router.post("/matches/analyze")
def analyze_matches(req: AnalyzeRequest, user_id: int = Depends(require_auth)):
    global _MATCHES_CACHE
    if not _MATCHES_CACHE:
        _MATCHES_CACHE = _fetch_predictions()
    id_set = {str(i) for i in req.match_ids}
    results = []
    for m in _MATCHES_CACHE:
        if str(m.get("id")) not in id_set:
            continue
        ml = m.get("pred_ml") or {}
        odds = m.get("odds") or {}
        ph = _to_pct(ml.get("prob_home_win"), 40.0)
        pr = _to_pct(ml.get("prob_draw"), 25.0)
        pp = _to_pct(ml.get("prob_away_win"), 35.0)
        po = _to_pct(ml.get("prob_over_25"), 55.0)
        pbt = _to_pct(ml.get("prob_btts_yes"), 45.0)
        s12 = ph + pr + pp or 100.0
        ph = round(ph / s12 * 100, 1)
        pr = round(pr / s12 * 100, 1)
        pp = round(100.0 - ph - pr, 1)

        def _dc_odds(a, b):
            if not a or not b:
                return None
            return round(1 / (1 / a + 1 / b), 2)

        tips = []
        if odds.get("home"): tips.append({"tip": "1", "label": "1 – Gosp.", "odds": odds["home"], "prob": ph, "color": "indigo"})
        if odds.get("draw"): tips.append({"tip": "X", "label": "X – Remis", "odds": odds["draw"], "prob": pr, "color": "slate"})
        if odds.get("away"): tips.append({"tip": "2", "label": "2 – Gość", "odds": odds["away"], "prob": pp, "color": "violet"})
        dc1x = _dc_odds(odds.get("home"), odds.get("draw"))
        if dc1x: tips.append({"tip": "1X", "label": "1X", "odds": dc1x, "prob": round(ph + pr, 1), "color": "blue"})
        dcx2 = _dc_odds(odds.get("draw"), odds.get("away"))
        if dcx2: tips.append({"tip": "X2", "label": "X2", "odds": dcx2, "prob": round(pr + pp, 1), "color": "purple"})
        if odds.get("over_2_5"): tips.append({"tip": "Over 2.5", "label": "Over 2.5", "odds": odds["over_2_5"], "prob": po, "color": "emerald"})
        if odds.get("btts"): tips.append({"tip": "BTTS", "label": "Obie strzelą", "odds": odds["btts"], "prob": pbt, "color": "amber"})
        results.append({
            "id": m["id"], "home": m["gosp"], "away": m["gosc"],
            "liga": m.get("liga", ""), "data": m.get("data", ""), "godzina": m.get("godzina", ""),
            "prob_home": ph, "prob_draw": pr, "prob_away": pp,
            "prob_over": po, "prob_btts": pbt, "tips": tips,
        })
    return results


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


@router.post("/coupons/settle")
def settle_coupons(req: SettleRequest, user_id: int = Depends(require_auth)):
    try:
        from footstats.core.coupon_settlement import settle_active_coupons
        stats = settle_active_coupons(days_back=req.days_back or 3, dry_run=req.dry_run or False, verbose=True)
        return {
            "ok": True,
            "settled": stats.get("settled", 0),
            "partial": stats.get("partial", 0),
            "errors": stats.get("errors", 0),
            "message": f"Rozliczono {stats.get('settled',0)}, częściowych {stats.get('partial',0)}, błędów {stats.get('errors',0)}",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
