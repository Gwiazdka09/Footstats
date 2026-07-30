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
    """Czy quick_picks REALNIE użyje Poisson-DC, czy fallback Bzzoiro-ML.

    quick_picks adaptuje schemat `load_cached` → Poisson, chyba że escape-hatch
    `QUICK_PICKS_USE_POISSON_CACHE=0`. Gdy brak danych (parquet) → Bzzoiro-ML.
    """
    use_poisson = os.getenv("QUICK_PICKS_USE_POISSON_CACHE", "1").strip()
    if use_poisson in ("0", "false", "False"):
        return "bzzoiro-ml"  # escape-hatch OFF → quick_picks pomija Poisson (schema mismatch)
    try:
        from footstats.data.historical_loader import load_cached
        df = load_cached()
        return "poisson-dc" if df is not None and len(df) else "bzzoiro-ml"
    except (OSError, ValueError, ImportError, KeyError):
        return "bzzoiro-ml"


def _swiezosc_danych_system() -> dict:
    """Dni od ostatniego kuponu System (created_at) → sygnał czy zbieranie żyje.

    Graceful: błąd DB nie może wywalić draftu → {"stale_days": None, "stale": None}.
    """
    try:
        from footstats.utils.db import connect
        from footstats.core.draft_health import ocena_swiezosci
        with connect() as c:
            row = c.execute(
                "SELECT MAX(cu.created_at) AS last FROM coupons cu "
                "JOIN users u ON u.id = cu.user_id WHERE u.username = 'System'"
            ).fetchone()
        last = row["last"] if row else None
        return ocena_swiezosci(last)
    except Exception as e:  # noqa: BLE001 — observability nie może wywalić draftu
        log.warning("swiezosc danych System nieobliczalna: %s", e)
        return {"stale_days": None, "stale": None}


def _dolacz_sygnal_elo(nogi: list[dict]) -> int:
    """
    Dopisuje do każdej nogi prognozę ClubElo (`elo`) i flagę zgodności (`elo_zgoda`).

    Zwraca liczbę nóg, dla których ClubElo znało mecz. Zero nie jest błędem —
    ClubElo pokrywa głównie kluby europejskie, więc przy meczach Brasileirão/USL
    pokrycie bywa zerowe i to jest normalne.

    Graceful: cokolwiek pójdzie nie tak, draft leci dalej bez tego pola.
    """
    if not nogi:
        return 0
    try:
        from footstats.scrapers.clubelo import klucz_meczu, pobierz_fixtures
    except ImportError as e:
        # Logujemy, bo cichy `return 0` już raz ukrył literówkę w nazwie importu —
        # sygnał po prostu nie działał i nic tego nie zgłaszało.
        log.warning("sygnal ClubElo niedostepny (import): %s", e)
        return 0

    try:
        indeks = {
            klucz_meczu(m["gospodarz"], m["goscie"]): m["prob"]
            for m in pobierz_fixtures()
        }
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as e:
        # Sygnał porównawczy jest dodatkiem — jego awaria NIE MOŻE zmienić wyniku
        # draftu na ok:False. Tak właśnie zepsuł 4 testy przy pierwszym podejściu.
        log.debug("sygnal ClubElo pominiety: %s", e)
        return 0
    if not indeks:
        return 0

    _TIP_NA_KLUCZ = {"1": "pw", "X": "pr", "2": "pp", "BTTS": "bt", "Over 2.5": "o25"}
    trafien = 0
    for noga in nogi:
        mecz = str(noga.get("mecz") or "")
        if " vs " not in mecz:
            continue
        gosp, gosc = mecz.split(" vs ", 1)
        prob_elo = indeks.get(klucz_meczu(gosp, gosc))
        if not prob_elo:
            continue
        trafien += 1
        noga["elo"] = prob_elo
        klucz = _TIP_NA_KLUCZ.get(str(noga.get("tip")))
        if klucz and klucz in prob_elo:
            # „Zgoda" = ClubElo też daje temu typowi przewagę (>50% dla rynków
            # dwustronnych, >33% dla 1X2). Celowo luźne — to sygnał, nie filtr.
            prog = 33.0 if klucz in ("pw", "pr", "pp") else 50.0
            noga["elo_zgoda"] = prob_elo[klucz] >= prog
    return trafien


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

        # Bzzoiro to źródło główne (mecze + ML). Gdy padnie — fallback na fixtures
        # z API-Football, żeby dzień nie przepadł. Fallback nie ma ML, więc prob
        # liczy sam Poisson (wymaga parquetu — patrz P0/A w TODO.md).
        klucz = os.getenv(ENV_BZZOIRO, "")
        klient = None
        fixtures_source = "bzzoiro"
        powod_fallbacku = ""

        if not klucz:
            # Nazwa zmiennej z ENV_BZZOIRO, nie zaszyta na sztywno — wcześniej komunikat
            # mówił "BZZOIRO_API_KEY", a realna zmienna to BZZOIRO_KEY, co przy diagnozie
            # incydentu (draft cicho zwracał ok:False od 20.07) wysyłało na złą ścieżkę.
            powod_fallbacku = f"brak {ENV_BZZOIRO} w env"
        else:
            kandydat = BzzoiroClient(klucz)
            ok, msg = kandydat.waliduj()
            if ok:
                klient = kandydat
            else:
                powod_fallbacku = f"Bzzoiro niedostępne: {msg}"

        if klient is None:
            from footstats.scrapers.fixtures_fallback import FixturesFallbackClient
            log.warning("cloud_draft fallback fixtures — %s", powod_fallbacku)
            zapas = FixturesFallbackClient(dni=dni)
            ok_fb, msg_fb = zapas.waliduj()
            if not ok_fb:
                return {
                    "ok": False,
                    "error": f"{powod_fallbacku}; fallback też nieaktywny: {msg_fb}",
                }
            klient = zapas
            fixtures_source = "api-football-fallback"

        model_source = _wykryj_model_source()
        wyniki = szybkie_pewniaczki_2dni(klient, prog=AGENT_KANDYDAT_PROG, godziny=dni * 24)

        if fixtures_source != "bzzoiro" and not wyniki:
            log.warning(
                "cloud_draft: fallback fixtures dał 0 kandydatów — bez ML prob "
                "musi policzyc Poisson, a ten wymaga parquetu (model_source=%s)",
                model_source,
            )

        # Podgląd selekcji single-leg — identyczny dobór jak build_single_leg_coupons,
        # ale bez zapisu i bez sprawdzania idempotencji (to wymaga Neon).
        from footstats.core.system_paper import najlepszy_typ
        from footstats.core.daily_filters import _pre_filtruj_ligi

        kandydaci = _pre_filtruj_ligi(wyniki)

        # Fallback nie ma kursów, a `najlepszy_typ` bez kursu zwraca None → zero
        # kuponów mimo poprawnych prob. Dociągamy je z AF po filtrze lig, żeby
        # ograniczony budżet szedł tylko na mecze, które faktycznie rozważamy.
        if fixtures_source != "bzzoiro" and kandydaci:
            from footstats.scrapers.fixtures_fallback import dolacz_kursy
            limit = int(os.getenv("FALLBACK_ODDS_LIMIT", "15"))
            uzupelnione = dolacz_kursy(kandydaci, limit=limit)
            log.info("fallback: kursy AF dociagniete dla %d/%d kandydatow (limit %d)",
                     uzupelnione, len(kandydaci), limit)

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

        # Niezależny punkt odniesienia: prognoza ClubElo (darmowa, bez klucza).
        # ŚWIADOMIE nie wpływa na selekcję ani na λ — to sygnał OBOK modelu, żeby dało
        # się porównać nasz typ z estymatorem ortogonalnym (Elo liczy siłę drużyn,
        # nasze λ liczy historię goli). Rozjazd = powód, by przyjrzeć się meczowi.
        elo_pokrycie = _dolacz_sygnal_elo(viable)

        if dry_run:
            return {
                "ok": True, "dry_run": True, "model_source": model_source,
                "fixtures_source": fixtures_source,
                "candidates": len(wyniki), "after_league_filter": len(kandydaci),
                "would_create": len(viable), "legs": viable[:50],
                "elo_pokrycie": elo_pokrycie,
                **_swiezosc_danych_system(),
            }

        from footstats.core.system_paper import build_single_leg_coupons
        created = build_single_leg_coupons(wyniki)
        # Sygnał świeżości PO zapisie: created>0 → stale_days=0; created=0 +
        # brak kuponu od >=prog_dni → STALE (rozróżnia benign vs starvation).
        fresh = _swiezosc_danych_system()
        if fresh.get("stale"):
            log.warning(
                "cloud_draft STALE: %s dni od ostatniego kuponu System "
                "(created=%d) — zbieranie danych moglo zamrzec",
                fresh.get("stale_days"), created,
            )
        return {
            "ok": True, "dry_run": False, "model_source": model_source,
            "fixtures_source": fixtures_source,
            "candidates": len(wyniki), "created": created, **fresh,
        }
    except Exception as e:  # noqa: BLE001 — endpoint musi być graceful (nigdy 500)
        log.error("generuj_system_draft błąd: %s", e, exc_info=True)
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
