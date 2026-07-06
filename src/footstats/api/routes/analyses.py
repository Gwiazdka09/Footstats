"""Analizy meczowe — endpoint zakładki (Sofascore-style).

GET  /api/analyses/matches   → karty ważnych meczów (top-5+WC+Euro+EKS) z modelem +
                               gole/mecz (team_stats) + goal_share. Bez LLM (szybkie).
POST /api/analyses/llm       → analiza LLM on-demand, cache po data-hash (raz generuje,
                               regen tylko gdy dane się zmienią — zero spam-requestów).
"""
from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Body

from footstats.core.match_analysis import (
    build_match_card, analysis_prompt, card_data_hash,
    get_cached_analysis, set_cached_analysis,
)
from footstats.core.player_db import team_goal_shares_recent, get_team_stats

router = APIRouter(prefix="/api", tags=["analyses"])
log = logging.getLogger(__name__)

# Ważne ligi (substring nazwy): top-5 + Mistrzostwa Świata + Euro + Ekstraklasa
_WAZNE = (
    "premier league", "la liga", "primera division", "serie a", "bundesliga",
    "ligue 1", "world cup", "mistrzostwa", "euro 20", "euro 2028", "european championship",
    "ekstraklasa", "pko bp",
)
_SEASON = 2026


def _norm(p):
    if p is None:
        return None
    p = float(p)
    return round(p if p > 1 else p * 100, 1)   # 0-1 → 0-100


def _wazna(liga: str | None) -> bool:
    return any(w in (liga or "").lower() for w in _WAZNE)


def _build_cards(events: list[dict]) -> list[dict]:
    """Pure: z eventów Bzzoiro buduje karty ważnych meczów + team_stats/goal_share."""
    cards = []
    for m in events:
        if not _wazna(m.get("liga")):
            continue
        ml = m.get("pred_ml") or {}
        home, away = m.get("gosp"), m.get("gosc")
        match = {
            "gospodarz": home, "goscie": away, "liga": m.get("liga"), "data": m.get("data"),
            "pw": _norm(ml.get("prob_home_win")), "pr": _norm(ml.get("prob_draw")),
            "pp": _norm(ml.get("prob_away_win")), "o25": _norm(ml.get("prob_over_25")),
            "bt": _norm(ml.get("prob_btts_yes")),
        }
        card = build_match_card(
            match,
            ts_home=get_team_stats(home, _SEASON), ts_away=get_team_stats(away, _SEASON),
            gs_home=team_goal_shares_recent(home, _SEASON), gs_away=team_goal_shares_recent(away, _SEASON),
            inj_home=m.get("injuries_home"), inj_away=m.get("injuries_away"),
        )
        card["odds"] = m.get("odds")
        cards.append(card)
    return cards


@router.get("/analyses/matches")
def analyses_matches():
    """Karty ważnych meczów (dane, bez LLM). Źródło: Bzzoiro predykcje_tygodnia."""
    try:
        from footstats.scrapers.bzzoiro import BzzoiroClient
        klucz = os.getenv("BZZOIRO_KEY", "").strip()
        if not klucz:
            return {"matches": [], "error": "brak BZZOIRO_KEY"}
        events = BzzoiroClient(klucz).predykcje_tygodnia() or []
    except (OSError, ValueError, KeyError) as e:
        log.warning("analyses_matches: %s", e)
        return {"matches": [], "error": str(e)}
    return {"matches": _build_cards(events)}


@router.post("/analyses/llm")
def analyses_llm(card: dict = Body(...)):
    """Analiza LLM on-demand dla jednej karty. Cache po data-hash (raz generuje)."""
    h = card_data_hash(card)
    cached = get_cached_analysis(h)
    if cached is not None:
        return {"analysis": cached, "cached": True}
    try:
        from footstats.ai.client import zapytaj_ai
        text = zapytaj_ai(analysis_prompt(card), max_tokens=500)
    except (ImportError, RuntimeError, OSError, ValueError, KeyError) as e:
        log.warning("analyses_llm: %s", e)   # LLM/sieć nie może wywalić endpointu
        return {"analysis": None, "error": "LLM niedostępny"}
    if text:
        set_cached_analysis(h, text)
    return {"analysis": text, "cached": False}
