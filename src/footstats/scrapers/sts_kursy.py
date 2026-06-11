"""
sts_kursy.py – Scraper kursów 1X2 ze STS + porównanie z naszymi predykcjami
============================================================================
TD 15.3: Odds comparison. Pobiera kursy bukmacherskie 1X2 ze strony
STS /zaklady-bukmacherskie/pilka-nozna/1, dopasowuje je do naszych predykcji
(po nazwach drużyn) i liczy "value" (nasze prawdopodobieństwo vs implied STS).

Struktura strony (custom elements Angular):
    bo-one-ticket-match-tile
      bo-one-ticket-match-tile-prematch-header        -> "Kraj, Liga\\n+N"
      bo-one-ticket-match-tile-event-details-wrapper  -> drużyny + czas
      bo-one-ticket-match-tile-event-details-desktop  -> (wariant desktop)
      bo-one-ticket-match-tile-outcome (x3)           -> "1\\n2.02" / "X\\n4.00" / "2\\n2.85"

Użycie:
    python -m footstats.scrapers.sts_kursy             # pobierz i zapisz do cache
    python -m footstats.scrapers.sts_kursy --debug     # z widoczną przeglądarką
"""

from __future__ import annotations

import json
import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

try:
    from playwright.sync_api import Error as PWError
except ImportError:
    logger = logging.getLogger(__name__)
    logger.info("BŁĄD: pip install playwright  następnie  python -m playwright install chromium")
    sys.exit(1)

from footstats.scrapers.base_playwright import (
    STS_CONFIG as _CFG,
    browser_context,
    navigate_with_retry,
    page_context,
    zamknij_popup,
)

logger = logging.getLogger(__name__)

STS_URL   = "https://www.sts.pl"
ODDS_URL  = f"{STS_URL}/zaklady-bukmacherskie/pilka-nozna/1"
CACHE_DIR = Path("cache/sts_kursy")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

_CZAS_RE = re.compile(r"^(dzisiaj|jutro)?,?\s*(\d{1,2}\.\d{1,2}\.\d{4})?,?\s*\d{1,2}:\d{2}$", re.I)


# ── Parsowanie (czyste funkcje, testowalne bez Playwrighta) ───────────────────

def _parsuj_kurs(tekst: str) -> float | None:
    try:
        k = float(str(tekst).strip().replace(",", "."))
        return k if 1.01 <= k <= 1000 else None
    except (ValueError, AttributeError, TypeError):
        return None


def _jest_czasem(linia: str) -> bool:
    l = linia.strip().lower()
    if l in ("-", "–", ""):
        return True
    return bool(_CZAS_RE.match(l))


def _parsuj_mecz(header_txt: str, details_txt: str, outcome_txts: list[str]) -> dict | None:
    """Parsuje pojedynczy kafelek meczu na słownik z drużynami i kursami 1X2."""
    header_lines = [l.strip() for l in header_txt.split("\n") if l.strip()]
    liga = header_lines[0] if header_lines else "?"

    detail_lines = [l.strip() for l in details_txt.split("\n") if l.strip()]
    druzyny  = [l for l in detail_lines if not _jest_czasem(l)]
    czas_lin = [l for l in detail_lines if _jest_czasem(l) and l not in ("-", "–")]

    if len(druzyny) < 2:
        return None
    team1, team2 = druzyny[0], druzyny[1]
    czas = " ".join(czas_lin)

    kursy: dict[str, float | None] = {"1": None, "X": None, "2": None}
    for txt in outcome_txts:
        lines = [l.strip() for l in txt.split("\n") if l.strip()]
        if len(lines) < 2:
            continue
        label, kurs_txt = lines[0].upper(), lines[1]
        if label in kursy:
            kursy[label] = _parsuj_kurs(kurs_txt)

    return {
        "liga":    liga,
        "team1":   team1,
        "team2":   team2,
        "mecz":    f"{team1} - {team2}",
        "czas":    czas,
        "k1":      kursy["1"],
        "kx":      kursy["X"],
        "k2":      kursy["2"],
        "scraped": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def _match_score(mecz: dict, gosp: str, gosc: str) -> int:
    """Liczy podobieństwo nazw drużyn (nasze gosp/gosc vs team1/team2 ze STS)."""
    score = 0
    for nasze, ich in ((gosp, mecz.get("team1", "")), (gosc, mecz.get("team2", ""))):
        n = str(nasze).lower()
        i = str(ich).lower()
        for slowo in n.replace("-", " ").split():
            if len(slowo) > 3 and slowo in i:
                score += 1
    return score


def znajdz_kurs(gosp: str, gosc: str, oferta: list[dict], min_score: int = 2) -> dict | None:
    """Znajduje najlepiej pasujący mecz w ofercie STS po nazwach drużyn."""
    best, best_score = None, 0
    for m in oferta:
        s = _match_score(m, gosp, gosc)
        if s > best_score:
            best_score, best = s, m
    return best if best_score >= min_score else None


def oblicz_value(
    p_wygrana: float | None,
    p_remis: float | None,
    p_przegrana: float | None,
    k1: float | None,
    kx: float | None,
    k2: float | None,
    prog_ev: float = 5.0,
) -> dict[str, dict]:
    """
    Porównuje nasze prawdopodobieństwa (0-100, z predict_match) z implied
    probability kursów STS (100/kurs). Zwraca tylko typy z dodatnim EV.
    """
    wynik: dict[str, dict] = {}
    for typ, nasze, kurs in (("1", p_wygrana, k1), ("X", p_remis, kx), ("2", p_przegrana, k2)):
        if not kurs or kurs <= 1.0 or nasze is None:
            continue
        implied = round(100.0 / kurs, 1)
        ev = round(nasze - implied, 1)
        if ev >= prog_ev:
            wynik[typ] = {"kurs": kurs, "implied": implied, "nasze": nasze, "ev": ev}
    return wynik


# ── Scraping (Playwright) ──────────────────────────────────────────────────────

def _zbierz_kafelki(page, wyniki: list[dict], seen: set[str]) -> None:
    for tile in page.query_selector_all("bo-one-ticket-match-tile"):
        try:
            header  = tile.query_selector("bo-one-ticket-match-tile-prematch-header")
            details = tile.query_selector(
                "bo-one-ticket-match-tile-event-details-wrapper, "
                "bo-one-ticket-match-tile-event-details-desktop"
            )
            outcomes = tile.query_selector_all("bo-one-ticket-match-tile-outcome")
            if not details or len(outcomes) < 3:
                continue

            header_txt   = header.inner_text() if header else ""
            details_txt  = details.inner_text()
            outcome_txts = [o.inner_text() for o in outcomes[:3]]

            mecz = _parsuj_mecz(header_txt, details_txt, outcome_txts)
            if not mecz:
                continue

            klucz = f"{mecz['team1']}|{mecz['team2']}|{mecz['czas']}"
            if klucz not in seen:
                seen.add(klucz)
                wyniki.append(mecz)
        except (PWError, ValueError, AttributeError):
            continue


def pobierz_kursy_1x2(debug: bool = False, max_scroll: int = 20) -> list[dict]:
    """Pobiera kursy 1X2 dla nadchodzących meczów piłkarskich ze STS."""
    wyniki: list[dict] = []
    seen: set[str] = set()

    with browser_context(headless=not debug) as browser:
        with page_context(
            browser,
            extra_http_headers={"Accept-Language": "pl-PL,pl;q=0.9"},
            user_agent=USER_AGENT,
            viewport={"width": 1366, "height": 900},
        ) as page:
            navigate_with_retry(page, ODDS_URL)
            time.sleep(3)
            zamknij_popup(page, _CFG)
            time.sleep(1)

            for _ in range(max_scroll):
                _zbierz_kafelki(page, wyniki, seen)
                page.mouse.wheel(0, 1500)
                time.sleep(0.6)
            _zbierz_kafelki(page, wyniki, seen)

    logger.info("[STS-Kursy] Zebrano %d meczów", len(wyniki))
    return wyniki


# ── Porównanie z predykcjami ───────────────────────────────────────────────────

def porownaj_z_predykcjami(
    predykcje: list[dict],
    oferta: list[dict] | None = None,
    prog_ev: float = 5.0,
) -> list[dict]:
    """
    Dla każdej predykcji POISSON (z kluczami gosp/gosc/pred) dopasowuje kurs STS
    i zwraca listę meczów z dodatnim "value" (nasze prawdopodobieństwo > implied STS).
    """
    if oferta is None:
        oferta = pobierz_kursy_1x2()

    wyniki: list[dict] = []
    for w in predykcje:
        gosp, gosc = w.get("gosp"), w.get("gosc")
        if not gosp or not gosc:
            continue

        mecz = znajdz_kurs(gosp, gosc, oferta)
        if not mecz:
            continue

        pred = w.get("pred") or w
        value = oblicz_value(
            pred.get("p_wygrana"), pred.get("p_remis"), pred.get("p_przegrana"),
            mecz.get("k1"), mecz.get("kx"), mecz.get("k2"),
            prog_ev=prog_ev,
        )
        if value:
            wyniki.append({"gosp": gosp, "gosc": gosc, "sts": mecz, "value": value})

    return wyniki


# ── Zapis i CLI ─────────────────────────────────────────────────────────────────

def zapisz(oferta: list[dict]) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    sciezka = CACHE_DIR / f"kursy_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    sciezka.write_text(json.dumps(oferta, ensure_ascii=False, indent=2), encoding="utf-8")
    return sciezka


def main() -> None:
    debug = "--debug" in sys.argv

    print("=" * 60)
    logger.info("  STS — KURSY 1X2")
    print("=" * 60)

    oferta = pobierz_kursy_1x2(debug=debug)
    if not oferta:
        logger.info("[STS-Kursy] Brak danych")
        sys.exit(1)

    plik = zapisz(oferta)
    logger.info(f"[STS-Kursy] Zapisano: {plik}")

    for m in oferta[:30]:
        logger.info(f"{m['liga']}: {m['mecz']} ({m['czas']}) — 1={m['k1']} X={m['kx']} 2={m['k2']}")


if __name__ == "__main__":
    main()
