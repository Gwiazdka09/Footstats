"""
sts_inspiracje.py - Strefa Inspiracji STS: sygnal od top typerow + BetBuilder homepage (TD 15.7/15.8)
======================================================================================================
Parsuje "Popularne kupony" ze Strefy Inspiracji oraz karuzele "Popularne Bet Buildery"
ze strony glownej STS. Kazde zdarzenie BetBuildera (np. "Podwojna szansa: 1X",
"1. druzyna - strzeli gola: tak") jest normalizowane do formatu typu z betting.py
(oblicz_tip_correct), a nastepnie laczna kombinacja jest wyceniana modelem Poisson
(core.bet_builder.probability_matrix) i porownywana z realnym kursem STS (value/EV).

Struktura stron (Angular custom elements, stan na 2026-06-12):
    Strefa inspiracji -> "Popularne kupony":
        {nick}\n{skutecznosc}%\n...\n{team1} - {team2}\n{data}, {godzina}\n
        Bet Builder: {N} zdarzenia\n{kurs}\n{liga}\n{zdarzenie1}\n...\n{zdarzenieN}

    Strona glowna -> ".bet-builder-recommendation":
        {team1}\n{team2}\n{dzisiaj|jutro|data}\n{godzina}\n{zdarzenie1}\n...\n{kurs}

Uzycie:
    python -m footstats.scrapers.sts_inspiracje             # pobierz, dopasuj, zapisz sygnaly
    python -m footstats.scrapers.sts_inspiracje --debug     # z widoczna przegladarka
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
    logging.getLogger(__name__).info(
        "BŁĄD: pip install playwright  następnie  python -m playwright install chromium"
    )
    sys.exit(1)

from footstats.core.bet_builder import probability_matrix
from footstats.scrapers.base_playwright import (
    STS_CONFIG,
    browser_context,
    navigate_with_retry,
    page_context,
    zamknij_popup,
)
from footstats.scrapers.sts_kursy import USER_AGENT, _parsuj_kurs, znajdz_kurs
from footstats.utils.betting import oblicz_tip_correct

logger = logging.getLogger(__name__)

STS_URL   = "https://www.sts.pl"
CACHE_DIR = Path("cache/sts_inspiracje")

_TEAM_LINE_RE = re.compile(r"^(.+) - (.+)$")
_DATE_RE      = re.compile(r"^\d{1,2}\.\d{1,2}\.\d{4}, \d{1,2}:\d{2}$")
_BB_LICZBA_RE = re.compile(r"^Bet Builder:\s*(\d+)\s*zdarz", re.I)


# ── Normalizacja zdarzen BetBuildera -> format oblicz_tip_correct ────────────

def normalize_market_tip(label: str) -> str | None:
    """
    Mapuje opis zdarzenia BetBuildera ze STS na format typu z betting.oblicz_tip_correct.
    Zwraca None dla rynkow nieobslugiwanych przez model (rozne, kartki, polowy, zawodnicy).
    """
    label = label.strip()

    m = re.match(r"^Podwójna szansa:\s*(1X|X2|12)$", label, re.I)
    if m:
        return m.group(1).upper()

    m = re.match(r"^Mecz:\s*(1|X|2)$", label, re.I)
    if m:
        return m.group(1).upper()

    m = re.match(r"^Liczba goli:\s*([+-])(\d+(?:[.,]\d+)?)$", label)
    if m:
        kierunek = "OVER" if m.group(1) == "+" else "UNDER"
        return f"{kierunek} {m.group(2).replace(',', '.')}"

    m = re.match(r"^(1|2)\.\s*dru[zż]yna\s*-\s*liczba goli:\s*([+-])(\d+(?:[.,]\d+)?)$", label, re.I)
    if m:
        kierunek = "OVER" if m.group(2) == "+" else "UNDER"
        return f"{m.group(1)} {kierunek} {m.group(3).replace(',', '.')}"

    m = re.match(r"^(1|2)\.\s*dru[zż]yna\s*-\s*strzeli gola:\s*(tak|nie)$", label, re.I)
    if m:
        kierunek = "OVER" if m.group(2).lower() == "tak" else "UNDER"
        return f"{m.group(1)} {kierunek} 0.5"

    m = re.match(r"^(?:Oba zespo[lł]y|Obie dru[zż]yny) strzel[aą](?: gola)?:\s*(tak|nie)$", label, re.I)
    if m:
        return "BTTS" if m.group(1).lower() == "tak" else "BTTS NO"

    return None


# ── Parsowanie "Popularne kupony" (Strefa Inspiracji) ────────────────────────

def _parsuj_ticket(lines: list[str], i: int) -> tuple[dict | None, int]:
    m = _TEAM_LINE_RE.match(lines[i])
    if not m:
        return None, i + 1

    team1, team2 = m.group(1).strip(), m.group(2).strip()
    idx = i + 2  # lines[i+1] to data_godzina, juz zwalidowana przez wywolujacego

    n_zdarzenia = 0
    if idx < len(lines):
        bb = _BB_LICZBA_RE.match(lines[idx])
        if bb:
            n_zdarzenia = int(bb.group(1))
            idx += 1

    total_odds = _parsuj_kurs(lines[idx]) if idx < len(lines) else None
    idx += 1
    liga = lines[idx] if idx < len(lines) else "?"
    idx += 1

    zdarzenia = lines[idx:idx + n_zdarzenia]
    idx += n_zdarzenia

    ticket = {
        "team1":       team1,
        "team2":       team2,
        "mecz":        f"{team1} - {team2}",
        "data_godzina": lines[i + 1],
        "liga":        liga,
        "total_odds":  total_odds,
        "n_zdarzenia": n_zdarzenia,
        "zdarzenia":   zdarzenia,
        "typy":        [normalize_market_tip(z) for z in zdarzenia],
    }
    return ticket, idx


def parse_popular_tickets(text: str) -> list[dict]:
    """Parsuje surowy tekst sekcji 'Popularne kupony' na liste kuponow BetBuilder."""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    tickets: list[dict] = []

    i = 0
    while i < len(lines) - 1:
        if _TEAM_LINE_RE.match(lines[i]) and _DATE_RE.match(lines[i + 1]):
            ticket, next_i = _parsuj_ticket(lines, i)
            if ticket:
                tickets.append(ticket)
            i = max(next_i, i + 1)
        else:
            i += 1

    return tickets


# ── Parsowanie karuzeli BetBuilder na stronie glownej ────────────────────────

def parse_betbuilder_carousel(tile_texts: list[str]) -> list[dict]:
    """Parsuje teksty kafelkow '.bet-builder-recommendation' ze strony glownej STS."""
    tickets: list[dict] = []

    for txt in tile_texts:
        lines = [l.strip() for l in txt.split("\n") if l.strip()]
        if len(lines) < 5:
            continue

        team1, team2, data, godzina = lines[0], lines[1], lines[2], lines[3]
        *zdarzenia, kurs_txt = lines[4:]
        total_odds = _parsuj_kurs(kurs_txt)
        if not zdarzenia or total_odds is None:
            continue

        tickets.append({
            "team1":       team1,
            "team2":       team2,
            "mecz":        f"{team1} - {team2}",
            "data_godzina": f"{data}, {godzina}",
            "liga":        "?",
            "total_odds":  total_odds,
            "n_zdarzenia": len(zdarzenia),
            "zdarzenia":   zdarzenia,
            "typy":        [normalize_market_tip(z) for z in zdarzenia],
        })

    return tickets


# ── Wycena modelem Poisson + dopasowanie do predykcji ────────────────────────

def _joint_probability(typy: list[str], lh: float, la: float, max_goals: int = 7) -> float:
    """Sumuje P(wynik) macierzy Poissona dla wynikow spelniajacych WSZYSTKIE typy."""
    mat = probability_matrix(lh, la, max_goals=max_goals)
    total = 0.0
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            if all(oblicz_tip_correct(t, f"{h}-{a}") == 1 for t in typy):
                total += mat[h, a]
    return total


def ocen_sygnal(ticket: dict, lh: float | None, la: float | None) -> dict:
    """
    Ocenia kombo BetBuildera typera wzgledem modelu Poisson (lh/la = oczekiwane gole).
    signal: VALUE (model_p > implied), NO_VALUE, BRAK_MODELU (rynek poza zakresem modelu).
    """
    total_odds = ticket.get("total_odds")
    typy = ticket.get("typy") or []
    implied = round(100.0 / total_odds, 1) if total_odds else None

    if not typy or any(t is None for t in typy) or total_odds is None or lh is None or la is None:
        return {"signal": "BRAK_MODELU", "model_p": None, "implied": implied}

    model_p = round(_joint_probability(typy, lh, la) * 100, 1)
    signal = "VALUE" if model_p > implied else "NO_VALUE"
    return {"signal": signal, "model_p": model_p, "implied": implied}


def dopasuj_do_predykcji(tickets: list[dict], predykcje: list[dict]) -> list[dict]:
    """Dla kazdej predykcji dopasowuje kupon typera (po druzynach) i ocenia sygnal."""
    wyniki: list[dict] = []

    for w in predykcje:
        gosp, gosc = w.get("gosp"), w.get("gosc")
        if not gosp or not gosc:
            continue

        ticket = znajdz_kurs(gosp, gosc, tickets)
        if not ticket:
            continue

        pred = w.get("pred") or w
        lh = pred.get("expected_home_goals")
        la = pred.get("expected_away_goals")

        ocena = ocen_sygnal(ticket, lh, la)
        wyniki.append({"gosp": gosp, "gosc": gosc, "ticket": ticket, **ocena})

    return wyniki


# ── Scraping (Playwright) ────────────────────────────────────────────────────

def _usun_cookiebot(page) -> None:
    page.evaluate(
        "document.getElementById('CybotCookiebotDialogBodyUnderlay')?.remove();"
        "document.getElementById('CybotCookiebotDialog')?.remove();"
    )


def pobierz_popularne_kupony(debug: bool = False) -> str:
    """Pobiera surowy tekst sekcji 'Popularne kupony' ze Strefy Inspiracji."""
    with browser_context(headless=not debug) as browser:
        with page_context(
            browser,
            extra_http_headers={"Accept-Language": "pl-PL,pl;q=0.9"},
            user_agent=USER_AGENT,
            viewport={"width": 1366, "height": 900},
        ) as page:
            navigate_with_retry(page, f"{STS_URL}/strefa-inspiracji")
            time.sleep(3)
            _usun_cookiebot(page)
            time.sleep(0.5)

            for _ in range(5):
                page.mouse.wheel(0, 800)
                time.sleep(0.4)

            el = page.query_selector("[class*='inspiration-zone-content']")
            return el.inner_text() if el else page.inner_text("body")


def pobierz_betbuilder_carousel(debug: bool = False) -> list[str]:
    """Pobiera teksty kafelkow karuzeli 'Popularne Bet Buildery' ze strony glownej STS."""
    wyniki: list[str] = []

    with browser_context(headless=not debug) as browser:
        with page_context(
            browser,
            extra_http_headers={"Accept-Language": "pl-PL,pl;q=0.9"},
            user_agent=USER_AGENT,
            viewport={"width": 1366, "height": 900},
        ) as page:
            navigate_with_retry(page, STS_URL)
            time.sleep(3)
            zamknij_popup(page, STS_CONFIG)
            _usun_cookiebot(page)
            time.sleep(0.5)

            for _ in range(8):
                page.mouse.wheel(0, 800)
                time.sleep(0.4)

            for el in page.query_selector_all(".bet-builder-recommendation"):
                try:
                    wyniki.append(el.inner_text())
                except PWError:
                    continue

    return wyniki


# ── Zapis i CLI ───────────────────────────────────────────────────────────────

def zapisz_sygnaly(wyniki: list[dict], nazwa: str = "sygnaly") -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    sciezka = CACHE_DIR / f"{nazwa}_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    sciezka.write_text(json.dumps(wyniki, ensure_ascii=False, indent=2), encoding="utf-8")
    return sciezka


def main() -> None:
    debug = "--debug" in sys.argv

    from footstats.scrapers.bzzoiro import BzzoiroClient
    import os

    predykcje = BzzoiroClient(os.environ["BZZOIRO_KEY"]).predykcje_tygodnia()

    logger.info("[Inspiracje] Popularne kupony...")
    tickets = parse_popular_tickets(pobierz_popularne_kupony(debug=debug))
    logger.info("[Inspiracje] Bet Builder homepage...")
    tickets += parse_betbuilder_carousel(pobierz_betbuilder_carousel(debug=debug))

    wyniki = dopasuj_do_predykcji(tickets, predykcje)
    plik = zapisz_sygnaly(wyniki)
    logger.info("[Inspiracje] Zapisano %d sygnalow: %s", len(wyniki), plik)

    for w in wyniki:
        logger.info(
            "%s - %s: typy=%s kurs=%.2f implied=%.1f%% model=%s -> %s",
            w["gosp"], w["gosc"], w["ticket"]["typy"], w["ticket"]["total_odds"],
            w["implied"], w["model_p"], w["signal"],
        )


if __name__ == "__main__":
    main()
