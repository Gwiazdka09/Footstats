"""Coupon, match, kelly, and stats endpoints."""
import hmac
import json
import logging
import math
import os
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Union

import footstats.config as cfg
import psycopg2
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from footstats.api.auth import require_admin, require_auth
from footstats.core import match_linker
from footstats.core.coupon_tracker import STATUS_ACTIVE, save_coupon, update_coupon_status
from footstats.core.probability_calibrator import calibrate_confidence
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
        return preds or _fallback_predictions()
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


# Prawdopodobienstwa jako UŁAMKI 0-1, nie procenty — tak wysyla GUI
# (MarketsPanel.jsx / BetBuilderPanel.jsx dziela przez 100).
#
# Granice sa tu po to, zeby procenty konczyly sie bledem 422, a nie cichym
# smieciem: `estimate_lambdas_from_probs` startuje z best_loss=999, wiec przy
# wejsciu 70.0 ZADNA kombinacja lambd nie poprawia straty i funkcja zwraca
# nietkniete (1.0, 1.0) — katalog rynkow wychodzi bez sensu, a HTTP to 200.
_PROB = Field(ge=0.0, le=1.0, description="Prawdopodobienstwo jako ulamek 0-1")


class BetBuilderRequest(BaseModel):
    prob_home_win: float = _PROB
    prob_away_win: float = _PROB
    prob_over_25: float = _PROB
    selected: List[str] = []


class MarketsRequest(BaseModel):
    prob_home_win: float = _PROB
    prob_away_win: float = _PROB
    prob_over_25: float = _PROB
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


class PreviewLeg(BaseModel):
    home: str
    away: str
    tip: str


class PreviewSignalRequest(BaseModel):
    legs: List[PreviewLeg]
    match_date: Optional[str] = None


_MAX_TEXT_LEN = 120
_MAX_BOOKMAKER_LEN = 60
_MAX_PREVIEW_LEGS = 30


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


# Statusy, przy ktorych zrodlo mowi WPROST, ze meczu juz nie ma po co typowac.
# Lista jest blokujaca, nie dopuszczajaca: status nieznany NIE wyklucza meczu,
# tylko oddaje decyzje zegarowi. Odwrotnie — allowlista — oprozniłaby kreator
# w dniu, w ktorym dostawca zmieni slownik, i nikt by nie zauwazyl dlaczego.
_STATUSY_ROZPOCZETE = frozenset({
    "inprogress", "in_progress", "live", "playing", "halftime", "ht",
    "finished", "ft", "ended", "aet", "pen", "afterpen",
    "cancelled", "canceled", "postponed", "abandoned", "suspended", "awarded",
})


def _moment_meczu(m: dict) -> datetime | None:
    """Poczatek meczu jako moment ZE STREFA (UTC). None gdy nie da sie odczytac.

    Pole `godzina` NIE MA jednej konwencji w tym projekcie: `api_football`
    i `football_data` dopisuja do niej " UTC", `bzzoiro` i `terminarz` oddaja
    goly wycinek ISO. Poprzednia wersja parsowala to jednym `strptime`
    z `"%H:%M"`, wiec wiersze z sufiksem rzucaly `ValueError` i wypadaly CICHO —
    kreator gubil cale zrodla, a lista dalej wygladala poprawnie.

    `data_full` (pelne ISO, czesto z przesunieciem strefy) jest wiarygodniejsze
    i dlatego idzie pierwsze. Gdy zostaje sama `data`+`godzina` bez strefy,
    przyjmujemy UTC — i to jest ZALOZENIE, nie fakt: `bzzoiro.py` tnie
    `event_date` bez normalizacji, a jego przesuniecie nie jest w kodzie nigdzie
    potwierdzone. Dlatego zegar NIE jest tu jedynym zabezpieczeniem i pracuje
    razem z `_STATUSY_ROZPOCZETE`.
    """
    pelna = str(m.get("data_full") or "").strip()
    data = str(m.get("data") or "").strip()
    godzina = str(m.get("godzina") or "").strip()
    if godzina.upper().endswith("UTC"):
        godzina = godzina[:-3].strip()
    godzina = godzina[-5:] if len(godzina) > 5 else godzina

    try:
        if pelna:
            dt = datetime.fromisoformat(pelna.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        if data and godzina:
            return datetime.strptime(f"{data} {godzina}", "%Y-%m-%d %H:%M").replace(
                tzinfo=timezone.utc)
    except (ValueError, TypeError):
        # NIE cisza. Mecz bez czytelnej daty wypada z kreatora, a wlasnie tak
        # znikaly cale zrodla: `strptime` dlawilo sie sufiksem " UTC", `except`
        # polykalo blad i lista dalej wygladala poprawnie.
        _log.warning("Nieczytelna data meczu id=%s: data_full=%r data=%r godzina=%r",
                     m.get("id"), pelna, data, m.get("godzina"))
    return None


def _juz_sie_zaczal(m: dict, teraz: datetime) -> bool:
    """Czy mecz odpadl z typowania. Status jest wazniejszy niz zegar.

    Status pochodzi od dostawcy i jest stwierdzeniem faktu; godzina wymaga
    zalozenia o strefie. Gdy oba sa dostepne, wystarczy jedno, zeby wykluczyc.
    """
    if str(m.get("status") or "").strip().lower().replace(" ", "") in _STATUSY_ROZPOCZETE:
        return True
    moment = _moment_meczu(m)
    return moment is not None and moment <= teraz


@router.get("/matches/today")
@cached_response(ttl_seconds=600, vary_by=["user_id"])
def get_matches_today(user_id: int = Depends(require_auth)):
    global _MATCHES_CACHE
    preds = _fetch_predictions()
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=48)
    future = []
    for m in preds:
        moment = _moment_meczu(m)
        if moment is None or moment > cutoff or _juz_sie_zaczal(m, now):
            continue
        future.append(m)
    future.sort(key=lambda m: _moment_meczu(m) or cutoff)
    _MATCHES_CACHE = future[:30] if future else []
    return _MATCHES_CACHE


@router.post("/matches/analyze")
def analyze_matches(req: AnalyzeRequest, user_id: int = Depends(require_auth)):
    global _MATCHES_CACHE
    if not _MATCHES_CACHE:
        _MATCHES_CACHE = _fetch_predictions()
    from footstats.core.match_tips import build_tips
    id_set = {str(i) for i in req.match_ids}
    # Filtr czasowy MUSI byc takze tutaj. `_MATCHES_CACHE` to globalna zmienna
    # dzielona miedzy endpointami i uzytkownikami, a `/coupons/daily-proposals`
    # wypelnia ja lista NIEFILTROWANA — wiec mecz zakonczony dalo sie
    # zanalizowac, podajac jego id, nawet gdy `/matches/today` go nie pokazal.
    # Zgloszone z GUI 04.09.2026.
    teraz = datetime.now(timezone.utc)
    return [build_tips(m) for m in _MATCHES_CACHE
            if str(m.get("id")) in id_set and not _juz_sie_zaczal(m, teraz)]


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


def _empty_signal() -> dict:
    """Sygnał dla nogi bez dopasowania — same nulle (front nic nie renderuje)."""
    return {
        "matched": False, "our_tip": None, "our_confidence_pct": None,
        "prob_home": None, "prob_draw": None, "prob_away": None, "agrees": None,
    }


@router.post("/coupon/preview-signal")
def preview_signal(req: PreviewSignalRequest, user_id: int = Depends(require_auth)) -> list:
    """
    Dziennik kuponów (J6, Etap B): podgląd NASZEGO sygnału (typ, pewność,
    prawdopodobieństwa 1X2) obok wyboru użytkownika — dla każdej nogi
    formularza ręcznego kuponu, przed zapisem.

    READ-ONLY: cała logika dopasowania delegowana do `match_linker.link_leg`
    (wyłącznie SELECT z predictions) — endpoint sam nie dotyka DB, zero
    zewnętrznych API. Auth wymagane, żeby nie wyciekać predykcji anonimom.
    """
    if len(req.legs) > _MAX_PREVIEW_LEGS:
        raise HTTPException(
            status_code=400,
            detail=f"Maksymalnie {_MAX_PREVIEW_LEGS} nóg na podgląd sygnału",
        )
    result = []
    for leg in req.legs:
        link = match_linker.link_leg(leg.home, leg.away, req.match_date)
        if not link.matched or link.prediction is None:
            result.append(_empty_signal())
            continue
        pred = link.prediction
        our_tip = pred["ai_tip"]
        if not our_tip:  # LOW-1: predykcja bez tipu = brak użytecznego sygnału
            result.append(_empty_signal())
            continue
        user_tip = leg.tip.strip()
        result.append({
            "matched": True,
            "our_tip": our_tip,
            "our_confidence_pct": round(calibrate_confidence(pred["ai_confidence"]) * 100),
            "prob_home": pred["prob_home"],
            "prob_draw": pred["prob_draw"],
            "prob_away": pred["prob_away"],
            # LOW-2: agrees=None dopóki user nie wpisał typu (nie pokazuj "rozjazdu" przedwcześnie)
            "agrees": user_tip.upper() == our_tip.strip().upper() if user_tip else None,
        })
    return result


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


_LEADERBOARD_SORT_FIELDS = {"win_rate": "win_rate", "roi": "roi", "profit": "profit_pln"}
_STATUSY_ROZLICZONE = ("WON", "WIN", "LOST", "LOSE")
# Automat, nie typer. 30 kuponow dziennie zalalyby kazdego czlowieka, a konto
# System nie jest niczyim wynikiem — decyzja produktowa z 04.09.2026.
_KONTA_NIE_TYPERZY = ("System",)
# Ponizej tylu rozliczonych kuponow wiersz dostaje znacznik `malo_danych`.
# Bez niego 100% skutecznosci z dwoch kuponow wyglada jak mistrzostwo.
MALO_DANYCH_PONIZEJ = 5


def _rozliczone_sql() -> str:
    """Lista statusow rozliczonych jako fragment SQL, z JEDNEGO zrodla.

    Wpisana recznie w kilku zapytaniach rozjechalaby sie po cichu — to
    charakterystyczny ksztalt bledu w tym repo (ta sama regula w kilku kopiach).
    Wartosci sa nasze, nie uzytkownika, wiec nie ida parametrami: inaczej ta
    sama lista musialaby byc doklejana do `params` w kazdym wywolaniu i wracamy
    do tego samego problemu.
    """
    return ",".join(f"'{s}'" for s in _STATUSY_ROZLICZONE)


def _zaslepki(wartosci: tuple[str, ...]) -> str:
    """Same znaki zapytania, tyle ile wartosci. Wartosci ida parametrami."""
    return ",".join("?" for _ in wartosci)


# Zapytania trzymane jako SZABLONY, a skladane jednym `.format()`, zeby dalo sie
# przy nim postawic `# nosec`. Bandit kotwiczy B608 na linii OTWIERAJACEJ
# f-stringa, a tam — w srodku potrojnego cudzyslowu — komentarz Pythona nie ma
# gdzie stanac i ladowal wprost w SQL (`unrecognized token: "#"`).
#
# Do SQL trafiaja wylacznie znaki zapytania i nasze wlasne stale statusow;
# zadna wartosc od uzytkownika nie jest tu interpolowana.
_SZABLON_RANKINGU = """
    SELECT u.id as user_id, u.username,
           COUNT(*) as total,
           SUM(CASE WHEN c.status IN ('WON','WIN') THEN 1 ELSE 0 END) as wins,
           SUM(COALESCE(c.stake_pln, 0)) as staked,
           SUM(COALESCE(c.payout_pln, 0)) as payout,
           SUM(CASE WHEN c.shared THEN 1 ELSE 0 END) as do_wgladu
    FROM coupons c
    JOIN users u ON u.id = c.user_id
    WHERE u.leaderboard_opt_in = TRUE
      AND u.username NOT IN ({konta})
      AND c.status IN ({statusy})
"""

_SZABLON_OCZEKUJACYCH = """
    SELECT c.id, c.created_at, c.total_odds, c.stake_pln,
           c.legs_json, c.match_date_first, u.username
      FROM coupons c
      JOIN users u ON u.id = c.user_id
     WHERE c.shared = TRUE
       AND c.status NOT IN ({statusy}, 'VOID')
       AND u.username NOT IN ({konta})
     ORDER BY c.created_at DESC
     LIMIT 20
"""


@router.get("/leaderboard")
@cached_response(ttl_seconds=1800, vary_by=["sort", "days"])
def get_leaderboard(min_coupons: int = 2, limit: int = 20, sort: str = "win_rate", days: int = 0):
    """Ranking typerów wg wybranej metryki na udostępnionych (shared=TRUE), rozliczonych
    (WON/WIN/LOST/LOSE) kuponach.

    Metryki per user: win_rate (wins/total*100), staked/payout (suma stawek/wypłat),
    profit_pln (payout-staked), roi (profit/staked*100, 0.0 gdy staked=0 — bez ZeroDivision).
    `sort` wybiera metrykę rankingu (win_rate/roi/profit) — nieznana wartość to 400.
    Tiebreak zawsze total DESC. `days` filtruje okno czasowe po created_at (0/brak = całość).

    Bez agregacji per-ligę: schemat legów niespójny między źródłami kuponów (manual
    free-form bez ligi, część automatów bez klucza "liga") — grupowanie byłoby
    zawodne, analogicznie do per_league w core/user_stats.py.
    """
    if sort not in _LEADERBOARD_SORT_FIELDS:
        raise HTTPException(
            status_code=400,
            detail=f"Nieznany sort '{sort}'. Dozwolone: {', '.join(sorted(_LEADERBOARD_SORT_FIELDS))}",
        )
    try:
        # Metryki liczone ze WSZYSTKICH rozliczonych kuponow uzytkownika, nie
        # z podzbioru `shared`. Do 04.09.2026 bylo odwrotnie i oznaczalo to,
        # ze oceniany sam wybiera, co wchodzi do jego statystyki: udostepniasz
        # trafione, chowasz pudla, masz 100% skutecznosci. Metryka sterowana
        # selekcja nie mierzy niczego — ten sam mechanizm, przez ktory 14.08
        # padlo 52 podzbiory.
        #
        # Zgoda przeniesiona na `users.leaderboard_opt_in`, a `c.shared`
        # decyduje juz TYLKO o tym, ktore pojedyncze kupony inni ogladaja
        # (patrz `get_user_shared_coupons` nizej).
        query = _SZABLON_RANKINGU.format(  # nosec B608 — patrz komentarz przy szablonie
            konta=_zaslepki(_KONTA_NIE_TYPERZY), statusy=_rozliczone_sql())
        params: list = list(_KONTA_NIE_TYPERZY)
        if days > 0:
            cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            query += " AND c.created_at >= ?"
            params.append(cutoff)
        query += " GROUP BY u.id, u.username HAVING COUNT(*) >= ?"
        params.append(min_coupons)

        with _connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()

        result = []
        for r in rows:
            total = r["total"]
            wins = r["wins"] or 0
            staked = r["staked"] or 0.0
            payout = r["payout"] or 0.0
            profit_pln = payout - staked
            result.append({
                "user_id": r["user_id"],
                "username": r["username"],
                "total": total,
                "wins": wins,
                "win_rate": round(wins / total * 100, 1) if total else 0.0,
                "staked": round(staked, 2),
                "payout": round(payout, 2),
                "profit_pln": round(profit_pln, 2),
                "roi": round(profit_pln / staked * 100, 1) if staked else 0.0,
                # Ile z tych kuponow mozna KLIKNAC i obejrzec. Metryki licza sie
                # ze wszystkich, ale podglad tylko z udostepnionych — wiec ta
                # liczba mowi, ile z wyniku da sie zweryfikowac samemu.
                "do_wgladu": int(r["do_wgladu"] or 0),
                "malo_danych": total < MALO_DANYCH_PONIZEJ,
            })

        sort_field = _LEADERBOARD_SORT_FIELDS[sort]
        result.sort(key=lambda row: (row[sort_field], row["total"]), reverse=True)
        return result[:limit]
    except psycopg2.Error as e:
        _log.error("get_leaderboard error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/leaderboard/pending")
@cached_response(ttl_seconds=120)
def get_pending_shared():
    """Świeżo udostępnione kupony, jeszcze nierozliczone.

    Bez tego udostępnienie nie robi z perspektywy użytkownika NIC: ranking
    liczy tylko rozliczone, więc kupon czeka tygodniami niewidoczny. Zmierzone
    na produkcji 04.09.2026 — trzy z czterech udostępnionych kuponów ludzi
    miały status ACTIVE i nie pojawiały się nigdzie.

    Ranking celowo ich NIE liczy: wynik nierozstrzygnięty nie jest wynikiem.
    Ta lista pokazuje je obok rankingu, nie w nim.
    """
    zapytanie = _SZABLON_OCZEKUJACYCH.format(  # nosec B608 — patrz komentarz przy szablonie
        konta=_zaslepki(_KONTA_NIE_TYPERZY), statusy=_rozliczone_sql())
    try:
        with _connect() as conn:
            rows = conn.execute(zapytanie, tuple(_KONTA_NIE_TYPERZY)).fetchall()
        return [dict(r) for r in rows]
    except psycopg2.Error as e:
        _log.error("get_pending_shared error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/me/leaderboard")
def set_leaderboard_opt_in(req: ShareRequest, user_id: int = Depends(require_auth)):
    """Zgoda na obecność w rankingu typerów.

    ODDZIELNA od udostępniania pojedynczych kuponów i taka musi zostać:
    wejście do rankingu oznacza, że liczą się WSZYSTKIE rozliczone kupony,
    także te, których użytkownik świadomie nie pokazał. Kliknięcie „udostępnij"
    na jednym kuponie nie jest na to zgodą.
    """
    try:
        with _connect() as conn:
            conn.execute("UPDATE users SET leaderboard_opt_in = ? WHERE id = ?",
                         (req.shared, user_id))
        from footstats.core.response_cache import clear_response_cache
        clear_response_cache()
        return {"ok": True, "leaderboard_opt_in": req.shared}
    except psycopg2.Error as e:
        _log.error("set_leaderboard_opt_in error: %s", e, exc_info=True)
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

        # D8: osiem dni `settled: 0` przy 20+ kuponach czekajacych przeszlo bez
        # sygnalu (16-23.08, zawieszone konto API-Football). Alarmujemy tylko gdy
        # cos, co JESZCZE da sie zdobyc, nie zostalo rozliczone — kolejka pelna
        # kuponow poza horyzontem zrodel to normalny stan, nie awaria.
        from footstats.core.coupon_settlement import rozliczanie_stoi
        anomalia = rozliczanie_stoi(stats.get("settled", 0),
                                    stats.get("czekajace_w_zasiegu", 0))
        if anomalia:
            _log.error("ALERT rozliczanie stoi: %s | %s", anomalia, stats)
            try:
                from footstats.utils.telegram_notify import send_alert
                send_alert("FootStats — rozliczanie stoi", anomalia)
            except (ImportError, OSError, RuntimeError) as e:
                _log.warning("Alert o stojacym rozliczaniu nie poszedl: %s", e)

        # Drugi, NIEZALEZNY sygnal. Kupon poza horyzontem zrodel nie liczy sie do
        # `czekajace_w_zasiegu`, wiec alarm wyzej milczy o nim poprawnie — a kupon
        # i tak znika z accuracy oraz ROI. 24.08 tak wlasnie czekalo 20 sztuk.
        from footstats.core.coupon_settlement import kupony_przepadly
        przepadle = kupony_przepadly(stats.get("voided_brak_wyniku", 0))
        if przepadle:
            _log.error("ALERT kupony przepadly: %s | %s", przepadle, stats)
            try:
                from footstats.utils.telegram_notify import send_alert
                send_alert("FootStats — kupony przepadly", przepadle)
            except (ImportError, OSError, RuntimeError) as e:
                _log.warning("Alert o przepadlych kuponach nie poszedl: %s", e)

        return {
            "ok": True,
            "settled": stats.get("settled", 0),
            "partial": stats.get("partial", 0),
            "errors": stats.get("errors", 0),
            "voided": stats.get("voided", 0),
            "voided_brak_wyniku": stats.get("voided_brak_wyniku", 0),
            "czekajace_w_zasiegu": stats.get("czekajace_w_zasiegu", 0),
        }
    except (ValueError, KeyError, RuntimeError) as e:
        _log.error("cron_settle error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cron/settle-manual")
def cron_settle_manual(x_cron_secret: str = Header(default=""), dry_run: bool = False):
    """Endpoint dla Google Cloud Scheduler — auto-rozlicza kupony manual (dziennik, J4c).

    Rozlicza TYLKO nogi, dla których wynik mamy już w NASZEJ bazie: `predictions`
    (link_leg matched="exact" + niepusty actual_result), a gdy tam go nie ma —
    `model_log`, czyli szerszy dziennik kalibracyjny. Zero zewnętrznych API
    (chyba że `MANUAL_SETTLE_EXTERNAL=1`), zero bankrollu. Osobny trigger,
    NIE wpięty domyślnie w scheduler (enablement to świadoma decyzja usera,
    patrz `settle_manual_coupons`).
    """
    expected = os.getenv("CRON_SECRET", "")
    if not expected or not hmac.compare_digest(x_cron_secret, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        from footstats.core.coupon_settlement import settle_manual_coupons
        from footstats.core.response_cache import clear_response_cache
        stats = settle_manual_coupons(dry_run=dry_run, verbose=True)
        clear_response_cache()
        _log.info("cron_settle_manual: %s", stats)

        # Lustro alarmu z `/cron/settle`. Tam kupon po VOID_AFTER_DAYS cicho
        # ZNIKAŁ; tu cicho ZOSTAJE — i zostanie na zawsze, bo nasze źródła tej
        # ligi nie pokrywają. Statusu nie ruszamy (patrz `dziennik_utknal`),
        # więc jedynym wyjściem jest powiedzieć o tym człowiekowi.
        from footstats.core.coupon_settlement import dziennik_utknal
        utkniete = dziennik_utknal(stats.get("przeterminowane", 0))
        if utkniete:
            _log.warning("ALERT dziennik utknal: %s | %s", utkniete, stats)
            try:
                from footstats.utils.telegram_notify import send_alert
                send_alert("FootStats — dziennik czeka na Ciebie", utkniete)
            except (ImportError, OSError, RuntimeError) as e:
                _log.warning("Alert o utknietym dzienniku nie poszedl: %s", e)

        return {
            "ok": True,
            "settled": stats.get("settled", 0),
            "skipped": stats.get("skipped", 0),
            "errors": stats.get("errors", 0),
            # D5: ile nóg rozliczyły źródła zewnętrzne. Zero przy włączonej fladze
            # znaczy, że wydatek na API nic nie dał — to trzeba widzieć w odpowiedzi,
            # nie tylko w logach.
            "z_zewnatrz": stats.get("z_zewnatrz", 0),
            # Nogi ROZLICZONYCH kuponów, które rozwiązał `model_log` — tabela
            # szersza niż `predictions` (161 vs 424 wiersze na prod 28.08). Nogi
            # kuponów, które i tak zostały ACTIVE, celowo się tu nie liczą:
            # inaczej ta liczba rosłaby codziennie dla tego samego zawieszonego
            # kuponu i pokazywałaby sukces tam, gdzie nic nie zeszło z kolejki.
            "z_model_log": stats.get("z_model_log", 0),
            # Podzbiór `skipped`, którego nikt już nie rozliczy automatycznie.
            "przeterminowane": stats.get("przeterminowane", 0),
        }
    except (ValueError, KeyError, RuntimeError) as e:
        _log.error("cron_settle_manual error: %s", e, exc_info=True)
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
    podsumowanie = {k: v for k, v in result.items() if k != "legs"}

    # Poziom logu zależny od wyniku. Wcześniej wszystko szło na INFO, więc draft
    # zwracający {'ok': False, 'error': 'brak BZZOIRO_KEY'} przy HTTP 200 nie rzucał
    # się w oczy — System paper-trading stał 9 dni (20-29.07) i nikt tego nie widział.
    if not result.get("ok"):
        _log.error("cron_draft NIEUDANY (dry_run=%s): %s", dry_run, podsumowanie)
    elif not dry_run and result.get("created", 0) == 0:
        # Zero kuponów w trybie live to nie zawsze błąd (off-season, brak kandydatów),
        # ale utrzymujące się zero oznacza, że pętla zbierania danych nie żyje.
        _log.warning("cron_draft: 0 kuponow utworzonych (dry_run=False): %s", podsumowanie)
    else:
        _log.info("cron_draft (dry_run=%s): %s", dry_run, podsumowanie)
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
