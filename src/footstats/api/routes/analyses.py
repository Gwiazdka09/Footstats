"""Analizy meczowe — statystyki drużyn dla wszystkich użytkowników.

GET /api/analyses/matches → karty ważnych meczów (top-5+WC+Euro+EKS): gole/mecz
                            (team_stats), strzelcy (goal_share), kontuzje.

Od 10.09.2026 BEZ predykcji: karta nie niesie prawdopodobieństw 1X2/Over/BTTS
ani kursów, a analiza LLM (`POST /analyses/llm`) jest usunięta. Decyzja usera:
nasze typy nie pokazują się w GUI poza kreatorem „Stwórz Kupon” — ta zakładka
to dane o drużynach, nie prognoza.
"""
from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends

from footstats.api.auth import require_auth
from footstats.core.match_analysis import build_match_card
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


def _wazna(liga: str | None) -> bool:
    return any(w in (liga or "").lower() for w in _WAZNE)


def _build_cards(events: list[dict]) -> list[dict]:
    """Pure: z eventów Bzzoiro buduje karty ważnych meczów + team_stats/goal_share.

    `pred_ml` i `odds` z eventu są celowo POMIJANE — karta to statystyki drużyn.
    """
    cards = []
    for m in events:
        if not _wazna(m.get("liga")):
            continue
        home, away = m.get("gosp"), m.get("gosc")
        if not home or not away:
            # Zdarzenie bez nazw druzyn szlo do `get_team_stats(None, ...)`.
            # Karta meczu bez nazw i tak jest bezuzyteczna — pomijamy, ale
            # GLOSNO: cisza tutaj chowalaby uszkodzone zrodlo zdarzen.
            log.warning("Zdarzenie bez nazw druzyn (gosp=%r, gosc=%r, liga=%r)"
                        " — pomijam karte meczu", home, away, m.get("liga"))
            continue
        match = {"gospodarz": home, "goscie": away, "liga": m.get("liga"), "data": m.get("data")}
        card = build_match_card(
            match,
            ts_home=get_team_stats(home, _SEASON), ts_away=get_team_stats(away, _SEASON),
            gs_home=team_goal_shares_recent(home, _SEASON), gs_away=team_goal_shares_recent(away, _SEASON),
            inj_home=m.get("injuries_home"), inj_away=m.get("injuries_away"),
        )
        # `build_match_card` zawsze dokłada blok `model` (używał go prompt LLM) —
        # tu go wycinamy, żeby w odpowiedzi nie jechały nawet puste pola predykcji.
        cards.append({k: v for k, v in card.items() if k != "model"})
    return cards


@router.get("/analyses/matches")
def analyses_matches(user_id: int = Depends(require_auth)):
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
