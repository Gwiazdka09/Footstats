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


def domyslny_limit_kursow(budzet_dzienny: int | None = None) -> int:
    """Ile meczów dopytać o kursy, gdy Bzzoiro nie dało fixture'ów.

    Do 2026-09-03 stała 15 z jawnym uzasadnieniem w `dolacz_kursy`:
    „1 mecz = 2 zapytania AF przy dziennym limicie 100 — dlatego limit jest twardy".
    Oba człony są nieaktualne:

      * limit dzienny to 7500, nie 100 (plan Pro, zmierzone przez `/status`);
      * `znajdz_fixture_id` czyta `/fixtures?date=`, CACHE'OWANE na poziomie `_get`
        — jeden request na dzień dzielony przez wszystkie mecze, więc realny koszt
        to ~1 zapytanie na mecz, nie 2.

    Skutek starej wartości: przy nieczynnym Bzzoiro kursy dostawało 15 kandydatów,
    a reszta wypadała z typowania, bo `najlepszy_typ` pomija typ bez kursu. Przy
    48 kandydatach (draft 02.09) to dwie trzecie puli.

    Dzielnik 50 zostawia 98% budżetu na resztę dnia (rozliczenia, składy, sędzia)
    i sprowadza plan Free dokładnie do dawnych 15 — zejście z Pro nie może być
    regresją.
    """
    from footstats.utils.cache import AF_BUDGET_DAILY

    if budzet_dzienny is None:
        budzet_dzienny = AF_BUDGET_DAILY
    return max(15, budzet_dzienny // 50)


def limit_kursow_z_env() -> int:
    """`FALLBACK_ODDS_LIMIT` albo wartość wyliczona z budżetu.

    Śmieciowa wartość NIE wywraca draftu — to jest wyłącznik awaryjny, a literówka
    w zmiennej środowiskowej nie może ubić całego przebiegu.
    """
    surowa = os.getenv("FALLBACK_ODDS_LIMIT", "").strip()
    if not surowa:
        return domyslny_limit_kursow()
    try:
        return int(surowa)
    except ValueError:
        log.warning("FALLBACK_ODDS_LIMIT=%r nie jest liczba — biore wyliczone z budzetu",
                    surowa)
        return domyslny_limit_kursow()


def _zapisz_kupony_system(wyniki: list[dict]) -> tuple[int, int]:
    """Zapisuje kupony konta System. Zwraca `(single_leg, risk_*)`.

    DWIE sciezki, celowo rozdzielone:

    * `build_single_leg_coupons` — paper trading, 1 typ na mecz. To GLOWNY
      produkt: zbiera dane walidacyjne (326 wierszy) i na nim stoi pomiar ROI.
    * `generate_system_coupons` — propozycje dnia w koszykach low/medium/high,
      `shared=TRUE`, czyli widoczne na liscie "Najlepsi typerzy".

    Druga zyla dotad WYLACZNIE w lokalnym drafcie (`daily_agent.py`), wylaczonym
    przy migracji do Cloud Run — stad `kupon_type LIKE 'risk_%'` = 0 wierszy
    w calej historii i pusty leaderboard (`shared=TRUE` = 0 na 339 kuponow).

    Karmimy ja `na_ksztalt_pred_ml(wyniki)`, czyli NASZYM modelem, a nie
    `predykcje_tygodnia()` z Bzzoiro jak robil stary kod — produkcja gra
    Poisson-DC, wiec wersja z Bzzoiro wystawialaby na leaderboard typy z innego
    modelu niz mierzony.

    Awaria propozycji NIE moze zabic paper-tradingu: to dodatek, a tamto jest
    zrodlem danych. Stad osobny `try`.
    """
    from footstats.core.system_paper import build_single_leg_coupons

    created = build_single_leg_coupons(wyniki)

    risk_created = 0
    try:
        from footstats.core.system_coupons import (
            generate_system_coupons, na_ksztalt_pred_ml,
        )
        gotowe = na_ksztalt_pred_ml(wyniki)
        if gotowe:
            risk_created = len(generate_system_coupons(gotowe) or [])
        else:
            log.info("Propozycje ryzyka pominiete: zaden z %d meczow nie ma "
                     "kompletu prawdopodobienstw 1X2 z modelu", len(wyniki))
    except (OSError, RuntimeError, ValueError, KeyError, TypeError) as e:
        # GLOSNO, ale bez przerywania: brak tych kuponow oznacza pusty
        # leaderboard, co z zewnatrz wyglada jak "nikt jeszcze nic nie wystawil".
        log.warning("Propozycje ryzyka (risk_*) nie powstaly (%s: %s) — "
                    "lista 'Najlepsi typerzy' zostanie bez wpisow konta System",
                    type(e).__name__, e)

    return created, risk_created


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
            limit = limit_kursow_z_env()
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
                    # Bez godziny podglad nie pozwala zlozyc kuponu recznie —
                    # `data` mowi tylko "dzis", a po poludniu czesc meczow trwa.
                    "godzina": w.get("godzina") or "",
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

        created, risk_created = _zapisz_kupony_system(wyniki)
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
            "candidates": len(wyniki), "created": created,
            "risk_created": risk_created, **fresh,
        }
    except Exception as e:  # noqa: BLE001 — endpoint musi być graceful (nigdy 500)
        log.error("generuj_system_draft błąd: %s", e, exc_info=True)
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
