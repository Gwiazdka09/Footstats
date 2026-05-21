"""Coupon review: web context + Groq."""

from __future__ import annotations

import json
import logging
from typing import Any

log = logging.getLogger(__name__)


def _legs_from_coupon(row: dict) -> list[dict]:
    legs_raw = row.get("legs_json") or row.get("legs") or "[]"
    if isinstance(legs_raw, str):
        try:
            return json.loads(legs_raw)
        except json.JSONDecodeError:
            return []
    return legs_raw if isinstance(legs_raw, list) else []


def _picks_text(legs: list[dict], stake: float) -> str:
    lines = []
    for leg in legs:
        home = leg.get("home") or leg.get("gospodarz", "")
        away = leg.get("away") or leg.get("goscie", "")
        tip = leg.get("tip") or leg.get("typ", "")
        odds = leg.get("odds") or leg.get("kurs", 1.0)
        lines.append(f"{home} vs {away} - {tip} @ {odds}")
    return "\n".join(lines) + f"\n\nStake: {stake} PLN"


def review_coupons(
    coupons: list[dict],
    max_legs: int = 8,
) -> list[dict[str, Any]]:
    from footstats.ai.analyzer import ai_sprawdz_kupon
    from footstats.data.context_scraper import get_match_context

    results: list[dict[str, Any]] = []
    for coupon in coupons:
        cid = coupon.get("id")
        legs = _legs_from_coupon(coupon)[:max_legs]
        stake = float(coupon.get("stake_pln") or 10)
        contexts = []
        for leg in legs:
            home = leg.get("home") or ""
            away = leg.get("away") or ""
            liga = leg.get("liga", "")
            try:
                ctx = get_match_context(home, away, liga)
                contexts.append({"home": home, "away": away, "context": ctx})
            except Exception as exc:
                log.warning("context %s vs %s: %s", home, away, exc)
                contexts.append({"home": home, "away": away, "error": str(exc)})

        picks = _picks_text(legs, stake)
        try:
            ai_text = ai_sprawdz_kupon(picks, stawka=stake)
        except Exception as exc:
            ai_text = f"Groq error: {exc}"

        results.append({
            "coupon_id": cid,
            "legs_count": len(legs),
            "contexts": contexts,
            "ai_review": ai_text,
            "revised_note": "See ai_review for suggested changes.",
        })
    return results


def append_review_to_coupon(coupon_id: int, review_text: str, user_id: int) -> None:
    from footstats.utils.db import connect

    snippet = f"\n\n--- operator_review ---\n{review_text[:4000]}"
    with connect() as conn:
        row = conn.execute(
            "SELECT groq_reasoning FROM coupons WHERE id = ? AND user_id = ?",
            (coupon_id, user_id),
        ).fetchone()
        if not row:
            return
        new_reason = (row["groq_reasoning"] or "") + snippet
        conn.execute(
            "UPDATE coupons SET groq_reasoning = ? WHERE id = ?",
            (new_reason, coupon_id),
        )
        conn.commit()
