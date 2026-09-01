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

def _pomijaj_btts() -> bool:
    """Czy wyrzucić BTTS z puli selekcji (M5 lever). Domyślnie NIE.

    DLACZEGO TA FLAGA ISTNIEJE: `najlepszy_typ` bierze argmax po surowym
    prawdopodobieństwie z sześciu typów naraz. Rynek DWUSTRONNY ma zawsze jedną
    stronę ≥50% z definicji, trójstronny dzieli prawdopodobieństwo na trzy —
    dlatego 2-way wygrywa argmax w 74% meczów (zmierzone 17.08 na 1755 meczach).
    BTTS trafia do kuponu z powodu STRUKTURY reguły, nie dlatego, że mamy tam
    przewagę. A przewagi nie ma: walk-forward n=15 460 daje model 53,2% przy
    częstości bazowej 54,4% (Brier 0,2496 vs 0,2480) — „zawsze BTTS tak" BIJE model.

    DLACZEGO MIMO TO DOMYŚLNIE WYŁĄCZONA: pomiar na produkcji (23.08, wspólne okno
    2026-05-06..2026-08-16, n=147) daje BTTS n=13, trafność 23,1%, ROI −51,9%,
    a bez BTTS +2,9% wobec −2,0% ogółem. Kierunek się zgadza, ale n=13 to szum —
    jeden zakład więcej przesuwa ROI o 14,5 pp, a test dwumianowy po korekcie na
    wybór najgorszego z czterech rynków daje p=0,111. Flip dopiero po próbce,
    tak samo jak `SELECTION_MIN_CONF` i `LEAGUE_GATING`.

    Czytane przy każdym wywołaniu — flip bez redeploy kodu.
    """
    return os.getenv("SELECTION_SKIP_BTTS", "").strip() in ("1", "true", "True")


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
    `SELECTION_SKIP_BTTS=1` wyrzuca BTTS z puli (M5 lever — patrz `_pomijaj_btts`).
    Zwraca (prob, tip, kurs) lub None.
    """
    odds = w.get("odds") or {}
    best: tuple[float, str, float] | None = None
    pomijaj_btts = _pomijaj_btts()
    for tip, okey in _ODDS_KEY.items():
        if pomijaj_btts and tip == "BTTS":
            continue
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

        # `liga` dokładana 01.09. Bez niej analiza ROI per liga jest niemożliwa:
        # z 243 rozliczonych kuponów lige udało się odtworzyć dla 25 (dopasowanie
        # do `predictions` po nazwach drużyn), bo `predictions` zapisuje wyłącznie
        # typy, które przeszły przez LLM-a. `core/user_stats.py` z tego samego
        # powodu POMIJA grupowanie `per_league` — to jedyne źródło kuponów, które
        # realnie chodzi na produkcji, więc bez tego pola pytanie "które ligi się
        # opłacają" zostaje bez odpowiedzi na zawsze.
        leg = {
            "home": home, "away": away, "tip": tip, "odds": kurs,
            "mecz": mecz, "decision_score": int(prob),
            "liga": w.get("liga", ""),
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
