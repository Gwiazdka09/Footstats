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
