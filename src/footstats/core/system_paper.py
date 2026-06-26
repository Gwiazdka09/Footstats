"""
system_paper.py — FAZA 19: paper-trading bota na koncie System.

Dla każdego analizowanego meczu tworzy 1 single-leg kupon (najlepszy legalny typ
po filtrach Fazy 17), flat stake. Cel: czysty per-tip win rate / ROI na realnych
danych — bez bundlowania AKO, gdzie jedna zła noga topi cały kupon.

Kupony NIE są `shared` → nie wchodzą do leaderboardu. Rozliczają się normalnie
przez coupon_settlement (status ACTIVE → WON/LOST).
"""
from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

MIN_PROB = 40.0       # p_modelu < 40% → odrzuć (Faza 17.2)
MAX_KURS = 4.0        # kurs > 4.0 → longshot, odrzuć (Faza 17.2)
MIN_KURS = 1.2        # kurs < 1.2 → brak wartości
DEFAULT_STAKE = 2.0   # flat stake (decyzja: czysty sygnał ROI)


def _min_prob() -> float:
    """
    Próg p_modelu selekcji typu (M1 lever #1 — selekcja high-conf).

    Domyślnie `MIN_PROB` (40) = zero zmiany prod. Env `SELECTION_MIN_CONF`
    podnosi go do pasma high-conf (offline 65%+ = 68% accuracy). Wartość poza
    [0,100] lub nieparsowalna → fallback do `MIN_PROB`. Czytane przy każdym
    wywołaniu (jak `ensemble._env_market_weight`) — flip bez redeploy kodu.
    """
    raw = os.getenv("SELECTION_MIN_CONF", "").strip()
    if not raw:
        return MIN_PROB
    try:
        v = float(raw)
    except ValueError:
        return MIN_PROB
    return v if 0.0 <= v <= 100.0 else MIN_PROB

# tip → klucz kursu w odds dict kandydata
_ODDS_KEY: dict[str, str] = {
    "1": "home", "X": "draw", "2": "away",
    "Over 2.5": "over_2_5", "Under 2.5": "under_2_5", "BTTS": "btts",
}


def _prob_dla_typu(w: dict, tip: str) -> float | None:
    """Prawdopodobieństwo modelu (%) dla typu z pól kandydata (pw/pr/pp/o25/bt)."""
    o25 = w.get("o25") or 0
    return {
        "1": w.get("pw") or 0,
        "X": w.get("pr") or 0,
        "2": w.get("pp") or 0,
        "Over 2.5": o25,
        "Under 2.5": 100.0 - o25,
        "BTTS": w.get("bt") or 0,
    }.get(tip)


def najlepszy_typ(w: dict) -> tuple[float, str, float] | None:
    """
    Najlepszy legalny typ dla meczu: max p_modelu wśród typów spełniających
    filtry Fazy 17 (`_min_prob()` ≤ p, MIN_KURS ≤ kurs ≤ MAX_KURS).
    Próg p domyślnie MIN_PROB (40), podnoszony env `SELECTION_MIN_CONF` (M1 lever #1).
    Zwraca (prob, tip, kurs) lub None.
    """
    odds = w.get("odds") or {}
    best: tuple[float, str, float] | None = None
    for tip, okey in _ODDS_KEY.items():
        kurs_raw = odds.get(okey)
        if kurs_raw is None:
            continue
        try:
            kurs = float(kurs_raw)
        except (TypeError, ValueError):
            continue
        if kurs < MIN_KURS or kurs > MAX_KURS:
            continue
        p = _prob_dla_typu(w, tip)
        if p is None or p < _min_prob():
            continue
        if best is None or p > best[0]:
            best = (p, tip, kurs)
    return best


def _resolve_system_user_id() -> int | None:
    from footstats.utils.db import connect
    with connect() as c:
        row = c.execute("SELECT id FROM users WHERE username = 'System' LIMIT 1").fetchone()
        return row["id"] if row else None


def build_single_leg_coupons(wyniki: list[dict], stake: float = DEFAULT_STAKE,
                             user_id: int | None = None) -> int:
    """
    Tworzy single-leg kupony System dla analizowanych meczów. Zwraca liczbę utworzonych.
    Stosuje whitelist lig (Faza 17.4) + filtr longshot (Faza 17.2). Idempotentne:
    pomija mecz, jeśli System ma już kupon na tę parę w tej dacie.
    """
    from footstats.core.coupon_tracker import (
        save_coupon, update_coupon_status, STATUS_ACTIVE, init_coupon_tables,
    )
    from footstats.core.daily_filters import _pre_filtruj_ligi
    from footstats.utils.db import connect

    if user_id is None:
        user_id = _resolve_system_user_id()
    if not user_id:
        log.warning("Brak użytkownika System — pomijam paper-trading")
        return 0

    init_coupon_tables()
    kandydaci = _pre_filtruj_ligi(wyniki)   # whitelist lig (Faza 17.4)
    created = 0

    for w in kandydaci:
        home = w.get("gospodarz")
        away = w.get("goscie")
        if not home or not away:
            continue
        best = najlepszy_typ(w)
        if not best:
            continue
        prob, tip, kurs = best
        mdate = w.get("data")
        mecz = f"{home} vs {away}"

        # Idempotencja: System nie ma już kuponu na ten mecz w tej dacie
        with connect() as c:
            exists = c.execute(
                "SELECT 1 FROM coupons WHERE user_id = ? AND match_date_first = ?"
                " AND legs_json LIKE ? LIMIT 1",
                (user_id, mdate, f"%{mecz}%"),
            ).fetchone()
        if exists:
            continue

        leg = {
            "home": home, "away": away, "tip": tip, "odds": kurs,
            "mecz": mecz, "decision_score": int(prob),
        }
        cid = save_coupon(
            phase="system", kupon_type="SINGLE", legs=[leg],
            total_odds=kurs, stake_pln=stake, decision_score=int(prob),
            match_date_first=mdate, user_id=user_id, shared=False,
        )
        if cid:
            update_coupon_status(cid, STATUS_ACTIVE)
            created += 1

    log.info("System paper-trading: utworzono %d single-leg kuponów", created)
    return created
