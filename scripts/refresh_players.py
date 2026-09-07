#!/usr/bin/env python
"""
refresh_players.py — populacja bazy graczy (player_stats) z API-Football,
liga po lidze wg priorytetu (domyślnie: Liga Mistrzów → TOP5 → reszta).

Zasila goal_share dla Kontuzji v2 (`core.player_db`). Zapis do lokalnego SQLite
(`data/footstats_backtest.db`) — NIE prod Neon. Cache 24h + budżet klienta
APIFootball chronią przed przepalaniem limitu.

DOMYŚLNIE POBIERA PEŁNE KADRY (`/players`, stronami po 20), od 2026-09-07.
Wcześniej domyślny był `/players/topscorers`, który oddaje **20 nazwisk na CAŁĄ
ligę**, czyli 1-4 na drużynę — a `goal_share` dzieli gole przez sumę graczy
zapisanych, więc na takim mianowniku jeden zawodnik dostawał 100% ataku (62%
drużyn z realnego ruchu, pomiar w `docs/pomiary/goal_share_zmyslony_2026-09-07.md`).
Understat, jedyne dotychczasowe źródło pełnych składów, padł tego samego dnia.

KOSZT: ~34 strony na ligę, czyli około 550 zapytań na wszystkie 16 lig wobec
7500/dzień na planie Pro. Ekstraklasa 2025 zmierzona: 36 zapytań, 687 graczy.

KTÓRY SEZON. Ostatni PEŁNY, nie bieżący. `core/absencje.py` mówi wprost, czemu:
"Premier League po dwóch kolejkach dała 5 goli na dwie kadry, więc udział jednego
strzelca wyszedłby 0,4". Sprawdzone 07.09 na FotMobie: kadra Liverpoolu to 29
osób i 6 goli łącznie. `team_goal_shares_recent` cofa się do pełnego sezonu sama
(próg `player_db.MIN_SKLAD`).

Użycie:
  python scripts/refresh_players.py --season 2025   # pełne kadry ostatniego sezonu
  python scripts/refresh_players.py --only 2,39,140 # tylko wybrane api_id lig
  python scripts/refresh_players.py --topscorers    # stary, tani, bezużyteczny tryb

Po odświeżeniu: `python scripts/eksport_player_stats.py` → zrzut do obrazu.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from footstats.config import DB_PATH, ENV_APISPORTS  # noqa: E402
from footstats.scrapers.api_football import _APISPORTS_LIGI  # noqa: E402
from footstats.scrapers.player_stats import (  # noqa: E402
    refresh_league_players, refresh_league_squad,
)
from footstats.core.player_db import team_goal_shares_recent  # noqa: E402

# Priorytet lig (api_id) — Liga Mistrzów pierwsza, potem TOP5, potem reszta.
_PRIORYTET: tuple[int, ...] = (
    2,    # UEFA Champions League
    39,   # Premier League
    140,  # La Liga
    135,  # Serie A
    78,   # Bundesliga
    61,   # Ligue 1
    88,   # Eredivisie
    94,   # Primeira Liga
    106,  # Ekstraklasa
    40,   # Championship
    71,   # Brasileirao
    253,  # MLS
    307,  # Saudi Pro League
    262,  # Liga MX
    144,  # Belgia Pro League
    179,  # Scottish Premiership
)


# Ligi pobierane WYŁĄCZNIE po składy — świadomie osobno od `_APISPORTS_LIGI`.
#
# Tamta lista mówi, z jakich rozgrywek bierzemy MECZE. Ta mówi, dla jakich drużyn
# chcemy znać wagi zawodników — a to szersze pytanie, bo `goal_share` kluczuje po
# `team_norm`, nie po lidze. Pomiar `model_log` z 21 dni pokazuje, dlaczego to
# ma znaczenie: 58 lig w ruchu, rozkład płaski (największa 6%), a nasze 16 lig
# fixture'owych obejmuje tylko **21% ocen**.
#
# Puchary europejskie są tu najgęstszym źródłem: samo `id=2` (Liga Mistrzów)
# dało 69 drużyn z całej Europy jednym pobraniem, bo zawodnik zapisany przy
# drużynie jest tą samą drużyną niezależnie od rozgrywek. Z tego samego powodu
# mecz Ligi Konferencji czy Pucharu Polski dostaje wagi z ligi krajowej swoich
# uczestników i nie wymaga osobnego wpisu.
#
# ID SPRAWDZONE POJEDYNCZO przez `/leagues?search=`, zgodnie z ostrzeżeniem
# z `data/af_league_ids.json`: automatyczne dopasowanie po nazwie wybrałoby
# „National League" z Mjanmy zamiast angielskiej, a „Ligue 2" z Algierii zamiast
# francuskiej. Błędny wybór jest CICHY — statystyki z innych rozgrywek weszłyby
# w drużyny, których nie dotyczą.
_LIGI_SKLADOW: dict[int, str] = {
    3: "UEL",     # UEFA Europa League (World, Cup)
    848: "UECL",  # UEFA Europa Conference League (World, Cup)
    62: "FL2",    # Ligue 2 — Francja (NIE Algieria 187, NIE Tunezja 828)
    41: "EL1",    # League One — Anglia (NIE Szkocja 183, NIE Chiny 170)
    42: "EL2",    # League Two — Anglia (NIE Szkocja 184, NIE USL 256)
    43: "ENL",    # National League — Anglia (NIE Mjanma 588, NIE North 50)
    292: "KL1",   # K League 1 — Korea Poludniowa
    98: "J1",     # J1 League — Japonia (za `af_league_ids.json`)
    169: "CSL",   # Chinese Super League (za `af_league_ids.json`)
    119: "DSL",   # Superliga — Dania (za `af_league_ids.json`)
    103: "ELI",   # Eliteserien — Norwegia (za `af_league_ids.json`)
    283: "RO1",   # Liga I — Rumunia (za `af_league_ids.json`)
    218: "AUT",   # Bundesliga — Austria (za `af_league_ids.json`)
    128: "ARG",   # Liga Profesional — Argentyna (za `af_league_ids.json`)
    357: "IRL",   # Premier Division — Irlandia (za `af_league_ids.json`)
}


def _sezon_biezacy() -> int:
    now = datetime.now()
    return now.year if now.month > 6 else now.year - 1


def _kolejnosc(only: str | None) -> list[int]:
    if only:
        wybrane = [int(x) for x in only.split(",") if x.strip()]
        return [i for i in wybrane if i in _APISPORTS_LIGI]
    # priorytet najpierw, potem ewentualne nieujęte ligi z mapy
    reszta = [i for i in _APISPORTS_LIGI if i not in _PRIORYTET]
    return [i for i in _PRIORYTET if i in _APISPORTS_LIGI] + reszta


def _sanity(sezon_ref: int) -> None:
    """Wypis goal_share topowych zespołów (lookup jak pipeline: fallback sezonowy)."""
    print("\nSanity goal_share:")
    for team in ("Real Madrid", "Liverpool", "Bayern Munich", "Paris Saint Germain", "Inter"):
        sh = team_goal_shares_recent(team, sezon_ref, lookback=2)
        if sh:
            top = sorted(sh.items(), key=lambda kv: kv[1], reverse=True)[:3]
            print(f"  {team:<20} {len(sh):>2} graczy | " + ", ".join(f"{n} {s:.0%}" for n, s in top))
        else:
            print(f"  {team:<20} BRAK")


def main() -> int:
    ap = argparse.ArgumentParser(description="Populacja bazy graczy (goal_share) z API-Football.")
    ap.add_argument("--season", type=int, default=None, help="sezon (domyślnie bieżący)")
    ap.add_argument("--only", type=str, default=None, help="lista api_id po przecinku")
    ap.add_argument("--understat", action="store_true",
                    help="scraper Understat TOP5 (pełen skład, bez klucza/budżetu) zamiast API-Football"
                         " — UWAGA: źródło padło 07.09.2026, oddaje HTTP 200 i pustą stronę")
    ap.add_argument("--topscorers", action="store_true",
                    help="stary tryb: 1 req/liga, ale TYLKO ~20 nazwisk na całą ligę."
                         " Domyślnie pobierane są PEŁNE kadry (`/players`, ~34 strony/liga),"
                         " bo goal_share liczony na czołówce strzelców daje jednemu"
                         " zawodnikowi 100%% ataku drużyny.")
    ap.add_argument("--rozszerz", action="store_true",
                    help="dolicz ligi z `_LIGI_SKLADOW` — rozgrywki, z których NIE bierzemy"
                         " meczów, ale których drużyny oceniamy (puchary europejskie,"
                         " niższe klasy angielskie, Azja, Skandynawia). Nasze 16 lig"
                         " fixture'owych pokrywa tylko 21%% ocen w `model_log`.")
    args = ap.parse_args()

    sezon = args.season if args.season is not None else _sezon_biezacy()

    # Tryb scraper Understat — pełne składy TOP5, prawdziwy denominator goal_share
    if args.understat:
        from footstats.scrapers.player_stats import refresh_understat_leagues
        only = [x.strip() for x in args.only.split(",")] if args.only else None
        print(f"Sezon {sezon} | Understat scraper TOP5 | DB {DB_PATH}\n")
        n = refresh_understat_leagues(sezon, only=only)
        print(f"\nRazem (Understat): {n} graczy")
        _sanity(sezon)
        return 0

    key = (os.environ.get(ENV_APISPORTS) or "").strip()
    if not key:
        print(f"BŁĄD: brak {ENV_APISPORTS} w środowisku.", file=sys.stderr)
        return 1
    ligi = _kolejnosc(args.only)
    kody = {i: _APISPORTS_LIGI[i]["kod"] for i in ligi}
    nazwy = {i: _APISPORTS_LIGI[i]["nazwa"] for i in ligi}
    if args.rozszerz and not args.only:
        for api_id, kod in _LIGI_SKLADOW.items():
            if api_id not in kody:
                ligi.append(api_id)
                kody[api_id] = kod
                nazwy[api_id] = kod
    tryb = "topscorers (~20 nazwisk/liga)" if args.topscorers else "PELNE kadry (/players)"
    print(f"Sezon {sezon} | DB {DB_PATH} | ligi: {len(ligi)} | tryb: {tryb}\n")

    pobierz = refresh_league_players if args.topscorers else refresh_league_squad

    total = 0
    ok = puste = 0
    for api_id in ligi:
        etykieta = f"{nazwy[api_id]} [{kody[api_id]}]"
        n = pobierz(api_id, sezon, key, league_code=kody[api_id])
        total += n
        if n:
            ok += 1
            print(f"  ✓ {etykieta:<34} +{n} graczy")
        else:
            puste += 1
            print(f"  · {etykieta:<34} 0 (pusto / 429 / brak sezonu)")

    print(f"\nRazem: {total} graczy | {ok} lig OK, {puste} pustych")
    _kompletnosc(sezon)
    _sanity(sezon)
    return 0


def _kompletnosc(sezon: int) -> None:
    """Ile drużyn ma skład NA TYLE pełny, żeby `goal_share` coś znaczył.

    Sam licznik graczy tego nie mówi: `/players/topscorers` potrafi zwrócić
    setki wierszy w skali ligi i zero użytecznych drużyn, bo rozkłada je po
    1-4 na zespół. Bez tej linii oba tryby wyglądają na wyjściu identycznie.
    """
    import sqlite3

    from footstats.core.player_db import MIN_SKLAD

    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        wiersze = con.execute(
            "SELECT team_norm, COUNT(*) n FROM player_stats"
            " WHERE season = ? AND goals IS NOT NULL AND goals > 0"
            " GROUP BY team_norm", (int(sezon),)).fetchall()
    finally:
        con.close()

    if not wiersze:
        print(f"\nKompletnosc {sezon}: brak druzyn ze strzelcami")
        return
    ile = [n for _, n in wiersze]
    pelne = sum(1 for n in ile if n >= MIN_SKLAD)
    print(f"\nKompletnosc {sezon}: {pelne}/{len(ile)} druzyn ma >= {MIN_SKLAD}"
          f" strzelcow (mediana {sorted(ile)[len(ile) // 2]})")


if __name__ == "__main__":
    raise SystemExit(main())
