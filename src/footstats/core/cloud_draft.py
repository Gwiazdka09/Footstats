"""
core/cloud_draft.py — lite draft System paper-trading do uruchomienia w chmurze.

Generuje predykcje System (model-only, single-leg) sama ścieżką requests
(Bzzoiro API → quick_picks → predict_match) — BEZ Playwright, BEZ Groq, BEZ
Telegrama. Przeznaczone do endpointu `/cron/draft` (Cloud Scheduler), żeby
zbieranie danych walidacyjnych było PC-niezależne (lokalny draft wymaga
włączonego PC o 08:00; settlement już jest cloudowy).

- `dry_run=True` (DEFAULT): generuje i ZWRACA podgląd, ZERO zapisów do Neon.
- `dry_run=False`: tworzy single-leg kupony System w Neon (`build_single_leg_coupons`).

UWAGA: pełny model Poissona wymaga `full_dataset.parquet` (load_cached). Gdy brak
(np. pliku nie ma w obrazie Cloud Run), `quick_picks` degraduje gracefully do
predykcji Bzzoiro-ML — wtedy `model_source="bzzoiro-ml"` (NIE nasz model). Pole
`model_source` w odpowiedzi pozwala to zweryfikować PRZED włączeniem live.
"""
from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)


def _wykryj_model_source() -> str:
    """Czy dostępna jest historia (nasz Poisson-DC) czy fallback Bzzoiro-ML."""
    try:
        from footstats.data.historical_loader import load_cached
        df = load_cached()
        return "poisson-dc" if df is not None and len(df) else "bzzoiro-ml"
    except (OSError, ValueError, ImportError, KeyError):
        return "bzzoiro-ml"


def generuj_system_draft(dni: int = 2, dry_run: bool = True) -> dict:
    """Lite draft System (requests-only). Zwraca słownik podsumowania.

    Nigdy nie rzuca (endpoint musi być graceful): błąd → {"ok": False, "error": ...}.
    dry_run=True → zero zapisów Neon (podgląd `would_create`/`legs`).
    dry_run=False → zapis kuponów System do Neon, zwraca `created`.
    """
    try:
        from footstats.scrapers.bzzoiro import BzzoiroClient, ENV_BZZOIRO
        from footstats.core.quick_picks import szybkie_pewniaczki_2dni
        from footstats.config import AGENT_KANDYDAT_PROG

        klucz = os.getenv(ENV_BZZOIRO, "")
        if not klucz:
            return {"ok": False, "error": "brak BZZOIRO_API_KEY"}

        klient = BzzoiroClient(klucz)
        ok, msg = klient.waliduj()
        if not ok:
            return {"ok": False, "error": f"Bzzoiro niedostępne: {msg}"}

        model_source = _wykryj_model_source()
        wyniki = szybkie_pewniaczki_2dni(klient, prog=AGENT_KANDYDAT_PROG, godziny=dni * 24)

        # Podgląd selekcji single-leg — identyczny dobór jak build_single_leg_coupons,
        # ale bez zapisu i bez sprawdzania idempotencji (to wymaga Neon).
        from footstats.core.system_paper import najlepszy_typ
        from footstats.core.daily_filters import _pre_filtruj_ligi

        kandydaci = _pre_filtruj_ligi(wyniki)
        viable = []
        for w in kandydaci:
            if not w.get("gospodarz") or not w.get("goscie"):
                continue
            best = najlepszy_typ(w)
            if best:
                prob, tip, kurs = best
                viable.append({
                    "mecz": f"{w['gospodarz']} vs {w['goscie']}",
                    "tip": tip, "kurs": kurs, "prob": round(prob, 1),
                    "liga": w.get("liga", ""), "data": w.get("data"),
                })

        if dry_run:
            return {
                "ok": True, "dry_run": True, "model_source": model_source,
                "candidates": len(wyniki), "after_league_filter": len(kandydaci),
                "would_create": len(viable), "legs": viable[:50],
            }

        from footstats.core.system_paper import build_single_leg_coupons
        created = build_single_leg_coupons(wyniki)
        return {
            "ok": True, "dry_run": False, "model_source": model_source,
            "candidates": len(wyniki), "created": created,
        }
    except Exception as e:  # noqa: BLE001 — endpoint musi być graceful (nigdy 500)
        log.error("generuj_system_draft błąd: %s", e, exc_info=True)
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
