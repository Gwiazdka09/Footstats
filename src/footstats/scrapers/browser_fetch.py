"""
browser_fetch.py — pobieranie stron, które nie oddają danych zwykłym requestem.

Dlaczego istnieje (stan sprawdzony 2026-07-29):
  - **Understat** wraca HTTP 200, ale NIE embeduje już `matchesData`/`playersData`
    w HTML — dane wstrzykuje JS. Skutek: `understat_xg.fetch_team_xg` zwracał None
    dla każdej drużyny, więc 20% blend xG w `poisson.predict_match` **nigdy się nie
    odpalał** (cichy no-op, nie błąd).
  - **FBref** oddaje HTTP 403 nawet z przeglądarkowym User-Agentem (Cloudflare).

Oba potrzebują realnej przeglądarki. Obraz `footstats-jobs` ma już
`playwright install --with-deps chromium`, więc to działa w pipelinie chmurowym.
Obraz API (`Dockerfile.api`) jest lekki i Playwrighta nie ma — wtedy funkcje
zwracają pusto i reszta pipeline'u leci bez zmian.

Świadomie NIE robi retry/stealth: to ma być tani, przewidywalny fetcher.
Gdy strona nie odda danych, wyższa warstwa zostaje przy cache albo pomija xG.
"""
from __future__ import annotations

import logging
from typing import Any

from footstats.scrapers.base_playwright import (
    PLAYWRIGHT_OK,
    browser_context,
    page_context,
)

# Jawna lista błędów zamiast `except Exception` — gate broad-except w CI słusznie
# tego pilnuje. RuntimeError jest w zestawie, bo Playwright potrafi nim rzucić przy
# ubitym procesie przeglądarki, a fetcher danych nie może wywalić pipeline'u.
try:  # Playwright bywa nieobecny (lekki obraz API) — wtedy i tak nic nie robimy.
    from playwright.sync_api import Error as PWError, TimeoutError as PWTimeout
    _BLEDY_PRZEGLADARKI: tuple[type[BaseException], ...] = (
        PWError, PWTimeout, OSError, ValueError, RuntimeError,
    )
except ImportError:  # pragma: no cover — środowisko bez Playwrighta
    _BLEDY_PRZEGLADARKI = (OSError, ValueError, RuntimeError)

log = logging.getLogger(__name__)

_TIMEOUT_MS = 30_000
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


def pobierz_zmienne_js(
    url: str,
    nazwy: list[str],
    timeout_ms: int = _TIMEOUT_MS,
) -> dict[str, Any]:
    """
    Otwiera stronę i odczytuje zmienne z `window` po wyrenderowaniu.

    Przykład: Understat trzyma dane w `window.matchesData` / `window.playersData`.
    Zwraca tylko te zmienne, które faktycznie istnieją (None jest pomijane),
    więc wołający odróżnia „nie ma danych" od „jest None".

    Graceful: brak Playwrighta / błąd nawigacji / błąd pojedynczej zmiennej
    nie przerywa reszty i nigdy nie rzuca.
    """
    if not PLAYWRIGHT_OK:
        log.debug("browser_fetch: brak Playwrighta — pomijam %s", url)
        return {}

    wynik: dict[str, Any] = {}
    try:
        with browser_context(headless=True) as browser:
            with page_context(browser, user_agent=_UA) as page:
                page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
                for nazwa in nazwy:
                    try:
                        wartosc = page.evaluate(f"() => window.{nazwa}")
                    except _BLEDY_PRZEGLADARKI as e:
                        log.debug("browser_fetch: window.%s niedostępne (%s)", nazwa, e)
                        continue
                    if wartosc is not None:
                        wynik[nazwa] = wartosc
    except _BLEDY_PRZEGLADARKI as e:
        log.warning("browser_fetch: %s nieosiągalne: %s", url, e)
        return {}
    return wynik


def pobierz_html(
    url: str,
    czekaj_na: str | None = None,
    timeout_ms: int = _TIMEOUT_MS,
) -> str | None:
    """
    Zwraca HTML PO wyrenderowaniu (dla stron typu FBref, gdzie tabele dochodzą później).

    `czekaj_na` to opcjonalny selektor. Timeout na nim NIE kasuje wyniku — jeśli
    treść i tak przyszła, lepiej oddać ją częściową niż nic.
    """
    if not PLAYWRIGHT_OK:
        log.debug("browser_fetch: brak Playwrighta — pomijam %s", url)
        return None

    try:
        with browser_context(headless=True) as browser:
            with page_context(browser, user_agent=_UA) as page:
                page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
                if czekaj_na:
                    try:
                        page.wait_for_selector(czekaj_na, timeout=timeout_ms)
                    except _BLEDY_PRZEGLADARKI as e:  # brak selektora ≠ brak treści
                        log.debug("browser_fetch: selektor %s nie pojawił się (%s)",
                                  czekaj_na, e)
                return page.content()
    except _BLEDY_PRZEGLADARKI as e:
        log.warning("browser_fetch: %s nieosiągalne: %s", url, e)
        return None
