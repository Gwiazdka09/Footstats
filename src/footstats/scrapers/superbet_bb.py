"""
superbet_bb.py — Superbet BetBuilder market odds scraper.

Finds a match via /wyszukaj?query=, then calls getBetbuilderMarketsForMatch
API directly to get all BetBuilder odds without XHR interception guesswork.

Usage:
    from footstats.scrapers.superbet_bb import pobierz_bb_dla_meczow
    from footstats.betbuilder import generuj_kombinacje

    wyniki = pobierz_bb_dla_meczow([{"dom": "Aston Villa", "gost": "Nottingham Forest"}])
    typy   = wyniki.get("Aston Villa vs Nottingham Forest", [])
    combos = generuj_kombinacje(typy, kurs_rynkowy=3.50)

Requires: SUPERBET_LOGIN + SUPERBET_PASSWORD in .env
"""

from __future__ import annotations

import logging
import re
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page

from footstats.betbuilder import Typ
from footstats.scrapers.base_playwright import SUPERBET_CONFIG as _CFG, zamknij_popup

logger = logging.getLogger(__name__)

SUPERBET_URL  = "https://superbet.pl"
KURSY_BASE    = f"{SUPERBET_URL}/kursy/pilka-nozna"
BB_API        = "https://production-superbet-bmb.freetls.fastly.net/betbuilder/v2/getBetbuilderMarketsForMatch"

# Markets excluded from BetBuilder combinations
_SKIP_MARKETS = {
    "awans", "handicap azjatycki", "podwójna szansa",
}

# Prefixes that indicate player-specific markets (bloat: thousands of types)
_PLAYER_PREFIXES = (
    "zawodnik -",
    "strzelec",
    "asystent",
    "player -",
)


# ── Match ID extraction ───────────────────────────────────────────────────────

def _match_id_z_url(url: str) -> str | None:
    """Extracts numeric match ID from /kursy/pilka-nozna/{slug}-{id} URL."""
    m = re.search(r'-(\d{7,})(?:[/?]|$)', url)
    return m.group(1) if m else None


# ── API parser ────────────────────────────────────────────────────────────────

def _parsuj_markets_api(
    data: dict,
    filtruj_gracze: bool = True,
    min_kurs: float = 1.001,
) -> list[Typ]:
    """
    Parses getBetbuilderMarketsForMatch response into list of Typ.
    Format: {"matchId": "...", "markets": [{"name": "...", "odds": [...]}]}
    Typ.nazwa = "{market_name}: {selection_name}"

    Args:
        filtruj_gracze: Skip player-specific markets (reduces ~1400 → ~80 types).
        min_kurs:       Skip odds ≤ this value (near-certainties add no value).
    """
    typy: list[Typ] = []
    markets = data.get("markets", [])

    for market in markets:
        market_name = market.get("name", "").strip()
        if not market_name:
            continue
        name_lower = market_name.lower()
        if any(s in name_lower for s in _SKIP_MARKETS):
            continue
        if filtruj_gracze and any(name_lower.startswith(p) for p in _PLAYER_PREFIXES):
            continue

        for odd in market.get("odds", []):
            if odd.get("status") != "ACTIVE":
                continue
            sel_name = odd.get("name", "").strip()
            price    = odd.get("price")
            if not sel_name or price is None:
                continue
            try:
                kurs = round(float(price), 3)
            except (ValueError, TypeError):
                continue
            if kurs <= min_kurs:
                continue

            nazwa = f"{market_name}: {sel_name}"
            typy.append(Typ(nazwa=nazwa[:100], kurs=kurs))

    return typy


# ── Match search ──────────────────────────────────────────────────────────────

def _slugify(name: str) -> str:
    return name.lower().strip().replace(" ", "-").replace("_", "-")


def znajdz_url_meczu(page: Page, dom: str, gost: str) -> str | None:
    """
    Searches Superbet via /wyszukaj?query={dom}.
    Returns /kursy/pilka-nozna/{slug} URL matching both teams, or None.
    """
    query  = dom.replace(" ", "+")
    dom_s  = _slugify(dom)[:6]
    gost_s = _slugify(gost)[:6]
    src    = f"{SUPERBET_URL}/wyszukaj?query={query}"

    try:
        page.goto(src, wait_until="domcontentloaded", timeout=20000)
        time.sleep(3)
        zamknij_popup(page, _CFG)

        hrefs: list[str] = page.evaluate(
            "Array.from(document.querySelectorAll('a[href]'))"
            ".map(a => a.href)"
            ".filter(h => h.includes('/kursy/pilka-nozna/'))"
        )
        logger.info("[BB] Search '%s' → %d wyników", dom, len(hrefs))

        # Best: both teams in URL
        for href in hrefs:
            h = href.lower()
            if dom_s in h and gost_s in h:
                logger.info("[BB] Mecz (obie): %s", href)
                return href

        # Fallback: home team only
        for href in hrefs:
            if dom_s in href.lower():
                logger.info("[BB] Mecz (dom): %s", href)
                return href

        if hrefs:
            logger.info("[BB] Pierwszy wynik: %s", hrefs[0])
            return hrefs[0]

    except (RuntimeError, AttributeError) as e:
        logger.warning("[BB] Błąd search: %s", e)

    logger.warning("[BB] Nie znaleziono: %s vs %s", dom, gost)
    return None


# ── Core scraper ──────────────────────────────────────────────────────────────

def pobierz_kursy_bb(page: Page, match_url: str) -> list[Typ]:
    """
    Navigates to /kursy/ match page (to establish session), then calls
    getBetbuilderMarketsForMatch API directly with the extracted match_id.
    Returns list of Typ ready for betbuilder.generuj_kombinacje().
    """
    match_id = _match_id_z_url(match_url)
    if not match_id:
        logger.warning("[BB] Brak match_id w URL: %s", match_url)
        return []

    # Navigate to match page to warm up session/cookies
    try:
        page.goto(match_url, wait_until="domcontentloaded", timeout=20000)
        time.sleep(2)
        zamknij_popup(page, _CFG)
    except (RuntimeError, AttributeError, TimeoutError) as e:
        logger.warning("[BB] Nawigacja do kursy nieudana: %s", e)

    # Direct API call
    api_url = f"{BB_API}?match_id={match_id}&lang=pl-PL&target=SB_PL"
    try:
        resp = page.request.get(api_url, timeout=12000)
        if not resp.ok:
            logger.warning("[BB] API %d: %s", resp.status, api_url)
            return []
        data = resp.json()
    except (ValueError, RuntimeError) as e:
        logger.error("[BB] API call failed: %s", e)
        return []

    typy = _parsuj_markets_api(data)

    # Deduplicate: keep highest odds per name
    best: dict[str, float] = {}
    for t in typy:
        if t.nazwa not in best or t.kurs > best[t.nazwa]:
            best[t.nazwa] = t.kurs

    wynik = [Typ(nazwa=n, kurs=k) for n, k in best.items()]
    logger.info("[BB] match_id=%s → %d kursów BB (z %d markets)", match_id, len(wynik), len(data.get("markets", [])))
    return wynik


# ── Public batch API ──────────────────────────────────────────────────────────

def pobierz_bb_dla_meczow(
    mecze: list[dict],
    headless: bool = True,
) -> dict[str, list[Typ]]:
    """
    Batch: for each match dict {'dom': str, 'gost': str} fetches BetBuilder odds.

    Returns:
        {'Dom vs Gost': [Typ(...), ...], ...}

    Requires SUPERBET_LOGIN + SUPERBET_PASSWORD in .env.
    """
    from footstats.scrapers.superbet import zaloguj as _zaloguj

    wyniki: dict[str, list[Typ]] = {}

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        ctx = browser.new_context(
            extra_http_headers={"Accept-Language": "pl-PL,pl;q=0.9"},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
        )
        page = ctx.new_page()

        try:
            page.goto(SUPERBET_URL, wait_until="domcontentloaded", timeout=20000)
            time.sleep(2)
            zamknij_popup(page, _CFG)
            _zaloguj(page)
            time.sleep(2)

            for mecz in mecze:
                dom  = mecz.get("dom", "")
                gost = mecz.get("gost", "")
                if not dom or not gost:
                    continue

                klucz = f"{dom} vs {gost}"
                logger.info("[BB] Pobieram: %s", klucz)

                match_url = znajdz_url_meczu(page, dom, gost)
                if not match_url:
                    wyniki[klucz] = []
                    continue

                try:
                    wyniki[klucz] = pobierz_kursy_bb(page, match_url)
                    logger.info("[BB] %s → %d kursów", klucz, len(wyniki[klucz]))
                except (RuntimeError, AttributeError, ValueError, KeyError) as e:
                    logger.error("[BB] Błąd %s: %s", klucz, e)
                    wyniki[klucz] = []

        finally:
            browser.close()

    return wyniki


if __name__ == "__main__":
    import sys
    import json
    import logging

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    debug = "--debug" in sys.argv
    args  = [a for a in sys.argv[1:] if not a.startswith("--")]
    dom   = args[0] if len(args) > 0 else "Aston Villa"
    gost  = args[1] if len(args) > 1 else "Nottingham Forest"

    print(f"\n=== BetBuilder odds: {dom} vs {gost} ===\n")
    wyniki = pobierz_bb_dla_meczow([{"dom": dom, "gost": gost}], headless=not debug)

    for klucz, typy in wyniki.items():
        print(f"\n{klucz} — {len(typy)} kursów:")
        for t in sorted(typy, key=lambda x: x.kurs)[:30]:
            print(f"  {t.nazwa:<60} {t.kurs}")

    raw = {k: [(t.nazwa, t.kurs) for t in v[:20]] for k, v in wyniki.items()}
    print(f"\nRAW JSON (top 20):\n{json.dumps(raw, ensure_ascii=False, indent=2)}")
