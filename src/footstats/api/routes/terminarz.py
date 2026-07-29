"""Terminarz lig — endpointy dla zakładki „Terminarz" w GUI.

Dane z darmowych źródeł bez klucza (openfootball + OpenLigaDB), więc nie zużywają
budżetu API-Football. Cache jest długi (6h): terminarz sezonu zmienia się rzadko,
a każde odpytanie to kilkanaście requestów do GitHuba.
"""
from fastapi import APIRouter, Depends, HTTPException, Query

from footstats.api.auth import require_auth
from footstats.core.response_cache import cached_response
from footstats.scrapers.terminarz import (
    LIGI,
    biezacy_sezon,
    dni_do,
    nadchodzace,
    pobierz_terminarz,
    przeglad_lig,
    start_sezonu,
)

router = APIRouter(prefix="/api", tags=["terminarz"])

_CACHE_TTL = 6 * 3600


@router.get("/terminarz/ligi")
def lista_lig(user_id: int = Depends(require_auth)):
    """Lista obsługiwanych lig — do selektora w GUI."""
    return {
        "sezon": biezacy_sezon(),
        "ligi": [
            {"kod": kod, "nazwa": meta["nazwa"], "kraj": meta["kraj"]}
            for kod, meta in LIGI.items()
        ],
    }


@router.get("/terminarz")
@cached_response(ttl_seconds=_CACHE_TTL, vary_by=["limit_na_lige"])
def przeglad(
    limit_na_lige: int = Query(3, ge=1, le=10),
    user_id: int = Depends(require_auth),
):
    """
    Przegląd wszystkich lig: start sezonu, odliczanie, najbliższe mecze.

    Zasila główny widok zakładki. Liga, której nie udało się pobrać, jest pomijana
    — jedno padnięte źródło nie może wyczyścić całej zakładki.
    """
    ligi = przeglad_lig(limit_na_lige=limit_na_lige)
    return {"ligi": ligi, "liczba_lig": len(ligi)}


@router.get("/terminarz/{kod_ligi}")
@cached_response(ttl_seconds=_CACHE_TTL, vary_by=["kod_ligi", "tylko_nadchodzace", "limit"])
def terminarz_ligi(
    kod_ligi: str,
    tylko_nadchodzace: bool = Query(True),
    limit: int = Query(50, ge=1, le=500),
    user_id: int = Depends(require_auth),
):
    """Terminarz pojedynczej ligi. 404 gdy kod ligi nieobsługiwany."""
    if kod_ligi not in LIGI:
        raise HTTPException(status_code=404, detail="Nieobsługiwana liga")

    mecze = pobierz_terminarz(kod_ligi)
    if not mecze:
        # Brak danych to nie błąd serwera — źródło bywa niedostępne albo sezon
        # jeszcze nieopublikowany. GUI pokazuje pusty stan, nie komunikat błędu.
        return {
            "liga": LIGI[kod_ligi]["nazwa"],
            "kod": kod_ligi,
            "sezon": None,
            "start_sezonu": None,
            "dni_do_startu": None,
            "mecze": [],
        }

    start = start_sezonu(mecze)
    wybrane = nadchodzace(mecze, limit=limit) if tylko_nadchodzace else mecze[:limit]
    return {
        "liga": LIGI[kod_ligi]["nazwa"],
        "kod": kod_ligi,
        "kraj": LIGI[kod_ligi]["kraj"],
        "sezon": mecze[0].get("sezon"),
        "start_sezonu": start,
        "dni_do_startu": dni_do(start) if start else None,
        "meczow_total": len(mecze),
        "meczow_rozegranych": sum(1 for m in mecze if m.get("rozegrany")),
        "mecze": wybrane,
    }
