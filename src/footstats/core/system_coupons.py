"""Automatyczne generowanie codziennych propozycji konta 'System'.

Raz dziennie (faza draft) dzieli predykcje na koszyki ryzyka (low/medium/high)
przez core.risk_proposals.build_daily_proposals i zapisuje je jako kupony
konta 'System' z shared=TRUE — trafiają na listę "Najlepsi typerzy".
"""
from __future__ import annotations

import logging
from datetime import datetime

from footstats.core.coupon_tracker import init_coupon_tables, save_coupon
from footstats.core.risk_proposals import RISK_TIERS, build_daily_proposals
from footstats.utils.admin_user import resolve_system_user_id
from footstats.utils.db import connect as _connect

_log = logging.getLogger(__name__)


def na_ksztalt_pred_ml(wyniki: list[dict]) -> list[dict]:
    """Mecze z `quick_picks` w kształcie, którego oczekuje `build_tips`.

    `build_tips` czyta `m["pred_ml"]` z nazwami z API Bzzoiro (`prob_home_win`,
    `prob_draw`, `prob_away_win`, `prob_over_25`, `prob_btts_yes`), a nasze
    `wyniki` niosą `pw/pr/pp/bt/o25`. Bez tłumaczenia `build_tips` NIE PADA —
    podstawia domyślne wartości:

        ph = to_pct(ml.get("prob_home_win"), 40.0)

    czyli wyprodukowałby kupony ze zmyślonych 40/25/35/55/45, nie do odróżnienia
    od prawdziwych, i wystawił je na publiczny leaderboard (`shared=TRUE`).

    Dlatego mecz BEZ kompletu prawdopodobieństw 1X2 wypada tutaj, zamiast iść
    dalej z podkładką. Zero też liczy się jako brak: `quick_picks` oddaje 0.0
    dla meczu spoza pokrycia modelu, a to nie jest "szansa 0%".

    Rynki totali (BTTS, Over 2.5) są opcjonalne — `build_tips` sam je pominie,
    gdy klucza nie ma, i wtedy nie wystawi na nie typu.
    """
    gotowe: list[dict] = []
    for w in wyniki:
        pw, pr, pp = w.get("pw"), w.get("pr"), w.get("pp")
        if not all(isinstance(v, (int, float)) and v > 0 for v in (pw, pr, pp)):
            continue
        ml = {"prob_home_win": pw, "prob_draw": pr, "prob_away_win": pp}
        if isinstance(w.get("o25"), (int, float)) and w["o25"] > 0:
            ml["prob_over_25"] = w["o25"]
        if isinstance(w.get("bt"), (int, float)) and w["bt"] > 0:
            ml["prob_btts_yes"] = w["bt"]
        # `build_tips` czyta TAKZE `m["id"]`, `m["gosp"]`, `m["gosc"]` — nazwy
        # z API Bzzoiro, ktorych `quick_picks` nie ma. Pierwsze podejscie tlumaczylo
        # samo `pred_ml` i produkcja odpowiedziala `KeyError: 'id'` (02.09, draft
        # 05:31 UTC: candidates=48, created=31, risk_created=0).
        # `id` skladamy z pary druzyn i daty: musi byc stabilne (idempotencja
        # zapisu przy powtorzonym drafcie) i rozne dla roznych meczow.
        gosp = w.get("gospodarz", "")
        gosc = w.get("goscie", "")
        gotowe.append({
            **w,
            "pred_ml": ml,
            "id": f"{gosp}|{gosc}|{w.get('data', '')}",
            "gosp": gosp,
            "gosc": gosc,
        })
    return gotowe


def _existing_system_tiers(system_uid: int, date_str: str) -> set[str]:
    init_coupon_tables()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT kupon_type FROM coupons "
            "WHERE user_id = ? AND match_date_first = ? AND kupon_type LIKE 'risk_%%'",
            (system_uid, date_str),
        ).fetchall()
    return {r["kupon_type"] for r in rows}


def generate_system_coupons(predictions: list[dict], date_str: str | None = None) -> list[int]:
    """Generuje i zapisuje propozycje dnia jako udostępnione kupony konta 'System'.

    Zwraca listę id nowo utworzonych kuponów. Pomija koszyki puste oraz koszyki,
    dla których kupon na dany dzień już istnieje (idempotentne przy ponownym uruchomieniu).
    """
    system_uid = resolve_system_user_id()
    if not system_uid:
        _log.warning("Konto 'System' niedostępne — pomijam generowanie propozycji dnia")
        return []

    date_str = date_str or datetime.now().strftime("%Y-%m-%d")
    existing = _existing_system_tiers(system_uid, date_str)

    proposals = build_daily_proposals(predictions)
    created: list[int] = []
    for tier in RISK_TIERS:
        kupon_type = f"risk_{tier}"
        if kupon_type in existing:
            continue
        legs = proposals[tier]["legs"]
        if not legs:
            continue
        cid = save_coupon(
            phase="system",
            kupon_type=kupon_type,
            legs=legs,
            total_odds=proposals[tier]["total_odds"],
            match_date_first=date_str,
            user_id=system_uid,
            shared=True,
        )
        created.append(cid)
    return created
