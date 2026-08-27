"""
odds_store.py — zapis migawek kursow do `odds_snapshots`.

Idempotencja jest w obrebie DOBY: klucz unikalny to
(snapshot_date, event_id, market, line, outcome, bookmaker). Powtorne
uruchomienie tego samego dnia jest bezczynne, a jutrzejsza migawka tego samego
meczu wchodzi jako nowy wiersz — pilot narasta dzien po dniu.

Duplikaty odsiewamy WSTEPNYM ZAPYTANIEM, nie lapaniem wyjatku unikalnosci.
Powod jest praktyczny: w PostgreSQL `IntegrityError` przerywa cala transakcje,
wiec jeden duplikat wywalilby reszte partii — a migawka to ~3000 wierszy dziennie
i przy powtornym przebiegu duplikatem jest KAZDY z nich.

Spec: docs/superpowers/specs/2026-08-27-rozrzut-kursow-pilot-design.md
"""
from __future__ import annotations

import logging
from datetime import date

log = logging.getLogger(__name__)

# `commence_time` jest nullowalne, reszta wymagana. `line` moze byc 0.0, wiec
# sprawdzamy `is None`, a nie falsy — inaczej rynek h2h (linia 0) odpadalby
# jako "pusty" i do bazy nie trafiloby ani jedno kwotowanie 1X2.
_WYMAGANE = ("sport_key", "event_id", "team_home", "team_away",
             "market", "line", "outcome", "bookmaker", "price")

_INSERT = (
    "INSERT INTO odds_snapshots (snapshot_date, sport_key, event_id,"
    " commence_time, team_home, team_away, market, line, outcome,"
    " bookmaker, price) VALUES (?,?,?,?,?,?,?,?,?,?,?)"
)

_ISTNIEJACE = (
    "SELECT event_id, market, line, outcome, bookmaker FROM odds_snapshots"
    " WHERE snapshot_date = ?"
)


def _klucz(w: dict) -> tuple:
    """Klucz idempotencji — ten sam zestaw kolumn co indeks unikalny w migracji 16."""
    return (str(w["event_id"]), str(w["market"]), float(w["line"]),
            str(w["outcome"]), str(w["bookmaker"]))


def _brakujace_pola(w: dict) -> bool:
    return any(w.get(p) is None or w.get(p) == "" for p in _WYMAGANE)


def zapisz_migawke(
    wiersze: list[dict],
    conn=None,
    dzien: str | None = None,
    dry_run: bool = False,
) -> dict:
    """
    Zapisuje wiersze kolektora. Zwraca statystyki, nie rzuca na pojedynczym
    wierszu — eksperyment wpiety w potok produkcyjny musi umiec przezyc
    smieciowy rekord.

    `conn` podane → uzywa go (testy). `conn=None` → otwiera wlasne polaczenie.
    """
    stat = {"kandydaci": len(wiersze or []), "zapisane": 0,
            "pominiete": 0, "odrzucone": 0}
    if not wiersze:
        return stat

    dzien = dzien or date.today().isoformat()

    poprawne: list[dict] = []
    for w in wiersze:
        if _brakujace_pola(w):
            stat["odrzucone"] += 1
            continue
        poprawne.append(w)
    if not poprawne:
        log.warning("zapisz_migawke: wszystkie %d wierszy odrzucone jako niepelne",
                    stat["odrzucone"])
        return stat

    wlasne = conn is None
    kontekst = None
    if wlasne:
        from footstats.utils.db import connect
        kontekst = connect()
        conn = kontekst.__enter__()

    try:
        # Kolejnosc kolumn w `_ISTNIEJACE` odpowiada `_klucz`. Dostep po INDEKSIE,
        # bo `sqlite3.Row` i wiersz psycopg2 roznia sie interfejsem nazwowym,
        # a indeks dziala w obu.
        znane = {
            (str(r[0]), str(r[1]), float(r[2]), str(r[3]), str(r[4]))
            for r in conn.execute(_ISTNIEJACE, (dzien,)).fetchall()
        }

        for w in poprawne:
            if _klucz(w) in znane:
                stat["pominiete"] += 1
                continue
            znane.add(_klucz(w))
            if dry_run:
                stat["zapisane"] += 1
                continue
            conn.execute(_INSERT, (
                dzien, w["sport_key"], w["event_id"], w.get("commence_time"),
                w["team_home"], w["team_away"], w["market"], float(w["line"]),
                w["outcome"], w["bookmaker"], float(w["price"]),
            ))
            stat["zapisane"] += 1
    finally:
        if wlasne and kontekst is not None:
            kontekst.__exit__(None, None, None)

    log.info("zapisz_migawke(dry_run=%s, dzien=%s): %s", dry_run, dzien, stat)
    return stat
