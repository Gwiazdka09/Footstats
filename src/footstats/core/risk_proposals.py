"""Codzienne propozycje kuponów wg poziomu ryzyka (low/medium/high).

Czysta funkcja: bierze listę meczów-predykcji (jak z _fetch_predictions)
i dzieli najlepsze typy na 3 koszyki ryzyka.
"""
from __future__ import annotations

import math

from footstats.core.match_tips import build_tips

RISK_TIERS: tuple[str, ...] = ("low", "medium", "high")
MAX_LEGS_PER_TIER = 6

# Docelowy łączny kurs kuponu dla każdego poziomu ryzyka.
TIER_TARGET_ODDS: dict[str, float] = {"low": 5.0, "medium": 20.0, "high": 50.0}


def _classify_tip(tip: dict) -> str | None:
    """Przypisz typ do koszyka ryzyka na podstawie kursu i prawdopodobieństwa."""
    odds = tip["odds"]
    prob = tip["prob"]
    if not odds:
        return None
    if prob >= 60 and odds <= 1.6:
        return "low"
    if 40 <= prob < 60 and 1.6 < odds <= 2.5:
        return "medium"
    if prob < 40 or odds > 2.5:
        return "high"
    return None


def build_daily_proposals(predictions: list[dict], max_legs: int = MAX_LEGS_PER_TIER) -> dict:
    """Zwraca {risk: {risk, legs, total_odds}} dla low/medium/high.

    Dla każdego poziomu ryzyka dobiera nogi (od najpewniejszej) tak, by łączny
    kurs zbliżył się do TIER_TARGET_ODDS, nie przekraczając max_legs.
    """
    candidates: dict[str, list[dict]] = {t: [] for t in RISK_TIERS}

    for m in predictions:
        analyzed = build_tips(m)
        best_per_tier: dict[str, dict] = {}
        for tip in analyzed["tips"]:
            tier = _classify_tip(tip)
            if tier is None:
                continue
            current = best_per_tier.get(tier)
            if current is None or tip["prob"] > current["prob"]:
                best_per_tier[tier] = tip

        for tier, tip in best_per_tier.items():
            candidates[tier].append({
                "match_id": analyzed["id"],
                "home": analyzed["home"],
                "away": analyzed["away"],
                "liga": analyzed.get("liga", ""),
                "data": analyzed.get("data", ""),
                "godzina": analyzed.get("godzina", ""),
                "tip": tip["tip"],
                "label": tip["label"],
                "odds": tip["odds"],
                "prob": tip["prob"],
            })

    result = {}
    for tier in RISK_TIERS:
        target = TIER_TARGET_ODDS[tier]
        legs: list[dict] = []
        total_odds = 1.0
        for leg in sorted(candidates[tier], key=lambda c: c["prob"], reverse=True):
            if len(legs) >= max_legs or total_odds >= target:
                break
            legs.append(leg)
            total_odds *= leg["odds"]
        result[tier] = {
            "risk": tier,
            "legs": legs,
            "total_odds": round(total_odds, 2) if legs else 0.0,
        }
    return result
