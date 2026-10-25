"""Admin-only: opis meczu na żądanie (karta liczb + opis LLM).

POST /api/admin/opis-meczu → {karta, opis, z_cache}. Spec:
docs/superpowers/specs/2026-10-23-opisy-meczow-admin-design.md.

Decyzja właściciela (23.10): opisy są DLA NIEGO, nie dla ludzi — endpoint tylko dla
admina i nie zmienia zasady z `CLAUDE.md`, że nasze typy nie pokazują się zwykłym
użytkownikom. Cała logika (karta, prompt, cache) siedzi w `core/opis_meczu.py`;
tutaj tylko źródła zewnętrzne (zbiór historyczny, Bzzoiro, player_db) i HTTP.

UWAGA: bez `from __future__ import annotations` — slowapi owija funkcję
dekoratorem, a FastAPI musi rozwiązać adnotacje `Request`/modelu w jej globalach.
"""
import logging
import os
import threading
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from footstats.ai.client import zapytaj_ai
from footstats.api.auth import require_admin
from footstats.api.limiter import limiter
from footstats.api.routes.analyses import _SEASON as _SEZON
from footstats.core import opis_meczu

if TYPE_CHECKING:
    import pandas as pd

router = APIRouter(prefix="/api", tags=["admin", "opisy"])
log = logging.getLogger(__name__)


class OpisMeczuRequest(BaseModel):
    """To, co GUI ma na karcie meczu z `/analyses/matches`."""
    home: str = Field(min_length=1, max_length=100)
    away: str = Field(min_length=1, max_length=100)
    liga: str | None = Field(default=None, max_length=100)
    data: str | None = Field(default=None, max_length=32)


# ── Zbiór historyczny: leniwie, raz na proces ───────────────────────────────
#
# Parquet (~140 tys. meczów) czyta się ~sekundę i zajmuje sporo pamięci, więc nie
# ładujemy go przy starcie API — dopiero przy pierwszym żądaniu o opis (pierwsze
# jest wolniejsze). Porażka (brak pliku/pyarrow) NIE jest zapamiętywana: cache'owane
# None zamroziłoby Poissona do restartu procesu mimo naprawy.
_zbior_df: "pd.DataFrame | None" = None
_blokada_zbioru = threading.Lock()


def _wczytaj_zbior() -> "pd.DataFrame | None":
    """Zbiór w schemacie produkcyjnym (jak `quick_picks`) albo None."""
    try:
        from footstats.core.wf_harness import adapt_to_prod_schema
        from footstats.data.historical_loader import load_cached
        from footstats.utils.logging import waliduj_df_wyniki

        surowy = load_cached()
        if surowy is None:
            return None
        df = adapt_to_prod_schema(surowy)
    except (FileNotFoundError, ImportError, OSError, ValueError) as e:
        log.warning("opis-meczu: dane historyczne niedostępne (%s: %s) — karta bez Poissona",
                    type(e).__name__, e)
        return None
    if not waliduj_df_wyniki(df, "df_mecze (opis-meczu)"):
        return None
    return df


def _zbior() -> "pd.DataFrame | None":
    global _zbior_df
    with _blokada_zbioru:
        if _zbior_df is None:
            _zbior_df = _wczytaj_zbior()
        return _zbior_df


# ── Pozostałe źródła ────────────────────────────────────────────────────────

def _pobierz_eventy() -> list[dict[str, Any]]:
    """Eventy Bzzoiro (cache HTTP siedzi w kliencie). Awaria → [] i ostrzeżenie."""
    klucz = os.getenv("BZZOIRO_KEY", "").strip()
    if not klucz:
        log.warning("opis-meczu: brak BZZOIRO_KEY — karta bez Bzzoiro i kursów")
        return []
    try:
        from footstats.scrapers.bzzoiro import BzzoiroClient

        return BzzoiroClient(klucz).predykcje_tygodnia() or []
    except (RuntimeError, OSError, ValueError, KeyError) as e:
        log.warning("opis-meczu: Bzzoiro niedostępne (%s: %s)", type(e).__name__, e)
        return []


def _statystyki_druzyn(
    home: str, away: str, liga: str | None, data: str | None,
) -> dict[str, Any] | None:
    """Karta statystyk drużyn z player_db (gf_pg, rating, strzelcy). Opcjonalna."""
    try:
        from footstats.core.match_analysis import build_match_card
        from footstats.core.player_db import get_team_stats, team_goal_shares_recent
        from footstats.scrapers.teamnews.sklad import strzelcy_w_skladzie

        return build_match_card(
            {"gospodarz": home, "goscie": away, "liga": liga, "data": data},
            ts_home=get_team_stats(home, _SEZON), ts_away=get_team_stats(away, _SEZON),
            gs_home=strzelcy_w_skladzie(team_goal_shares_recent(home, _SEZON), home),
            gs_away=strzelcy_w_skladzie(team_goal_shares_recent(away, _SEZON), away),
        )
    except Exception as e:  # noqa: BLE001 — DB/sqlite3/psycopg2: statystyki są dodatkiem
        log.warning("opis-meczu: statystyki drużyn niedostępne (%s: %s)", type(e).__name__, e)
        return None


# ── Endpoint ────────────────────────────────────────────────────────────────

@router.post("/admin/opis-meczu")
@limiter.limit("10/minute")
def opisz_mecz(
    request: Request,
    req: OpisMeczuRequest,
    _admin: int = Depends(require_admin),
) -> dict[str, Any]:
    """Karta liczb meczu + opis LLM (cache 6 h). 404 gdy brak meczu w Bzzoiro i Poissona."""
    bzz = opis_meczu.dopasuj_event(_pobierz_eventy(), req.home, req.away, req.data)
    karta = opis_meczu.zbuduj_karte(
        req.home, req.away, req.liga, req.data, _zbior(), bzz,
        karta_druzyn=_statystyki_druzyn(req.home, req.away, req.liga, req.data),
    )
    if bzz is None and karta["poisson"] is None:
        # Bez żadnej liczby o meczu nie ma czego opisywać (żadnego „ogólnego” tekstu
        # z wiedzy modelu — spec). Szczegółów NIE zwracamy (audyt 24.09).
        raise HTTPException(status_code=404, detail="Brak danych o tym meczu")

    opis, z_cache = opis_meczu.opisz_z_info(karta, zapytaj=zapytaj_ai)
    return {"karta": karta, "opis": opis, "z_cache": z_cache}
