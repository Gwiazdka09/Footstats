"""
sklad.py — aktualny skład drużyny z FotMob (do filtrowania strzelców na kartach).

PO CO. `player_db.team_goal_shares_recent` sięga po ostatni PEŁNY sezon (2025),
więc karta pokazuje zawodników, którzy już odeszli (Lewandowski w Barcelonie po
transferze z lipca 2026). Skład z FotMob mówi, kto jest w klubie TERAZ.

Używa istniejącego klienta `fotmob._pobierz` (te same nagłówki i endpoint
`teams`), plus `search/suggest` do zamiany nazwy drużyny na id. Cache w pamięci
procesu (TTL 12 h); błąd = `None` = "nie wiemy" => wołający NIE filtruje.
Nie dotyka modelu (absencje/daily_phases) — to wyłącznie warstwa prezentacji.
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests

from footstats.scrapers.teamnews import fotmob
from footstats.scrapers.teamnews.base import klucz_gracza, klucz_skrocony
from footstats.utils.normalize import normalize_team_name, team_similarity

log = logging.getLogger(__name__)

_TTL_OK_S = 12 * 3600      # skład zmienia się rzadko
_TTL_BLAD_S = 15 * 60      # nieudane: nie młócimy FotMoba przy każdym odświeżeniu
_PROG_NAZW = 0.72
_MAX_WATKOW = 6            # równoległy prefetch składów (zimny cache)

_lock = threading.Lock()
_cache: dict[str, tuple[float, frozenset[str] | None]] = {}


def _znajdz_id(nazwa: str) -> int | None:
    """Nazwa drużyny → id FotMob przez search/suggest (najlepsze podobieństwo nazw)."""
    grupy: object = fotmob._pobierz("search/suggest", term=nazwa)
    cel = normalize_team_name(nazwa)
    najlepszy: tuple[float, int] | None = None
    for grupa in (grupy if isinstance(grupy, list) else []):
        for s in (grupa or {}).get("suggestions") or []:
            if not isinstance(s, dict) or s.get("type") != "team" or not s.get("id"):
                continue
            podobienstwo = team_similarity(cel, normalize_team_name(s.get("name") or ""))
            # `>` (nie `>=`): przy remisie wygrywa pierwszy = wyższy score FotMoba
            if podobienstwo >= _PROG_NAZW and (najlepszy is None or podobienstwo > najlepszy[0]):
                najlepszy = (podobienstwo, int(s["id"]))
    return najlepszy[1] if najlepszy else None


def _pobierz_sklad(nazwa: str) -> frozenset[str] | None:
    try:
        team_id = _znajdz_id(nazwa)
        if team_id is None:
            log.warning("FotMob: nie znaleziono druzyny %r — bez filtra skladu", nazwa)
            return None
        sklad = fotmob.parsuj_pozycje(fotmob._pobierz("teams", id=team_id))
    except (requests.RequestException, ValueError) as e:
        log.warning("FotMob: sklad %r niedostepny (%s: %s) — bez filtra",
                    nazwa, type(e).__name__, e)
        return None
    if not sklad:
        log.warning("FotMob: pusty sklad %r — bez filtra", nazwa)
        return None
    return frozenset(sklad)


def aktualny_sklad(nazwa: str) -> frozenset[str] | None:
    """Znormalizowane nazwiska zawodników drużyny albo `None` (nie wiemy)."""
    klucz = normalize_team_name(nazwa or "")
    if not klucz:
        return None
    teraz = time.monotonic()
    with _lock:
        wpis = _cache.get(klucz)
    if wpis and wpis[0] > teraz:
        return wpis[1]
    sklad = _pobierz_sklad(nazwa)
    with _lock:
        _cache[klucz] = (teraz + (_TTL_OK_S if sklad else _TTL_BLAD_S), sklad)
    return sklad


def przygotuj_sklady(nazwy: list[str]) -> None:
    """Równoległy prefetch (zimny cache: ~70 drużyn nie idzie szeregowo)."""
    teraz = time.monotonic()
    do_pobrania = sorted({
        n for n in nazwy
        if n and ((w := _cache.get(normalize_team_name(n))) is None or w[0] <= teraz)
    })
    if len(do_pobrania) > 1:
        with ThreadPoolExecutor(max_workers=_MAX_WATKOW) as ex:
            list(ex.map(aktualny_sklad, do_pobrania))


def _ten_gracz(baza: str, fotmob_klucz: str) -> bool:
    """Czy nazwa z bazy ("L. Yamal", "Mbappé") to gracz ze składu ("lamine yamal")."""
    a, b = klucz_gracza(baza).replace(".", ""), fotmob_klucz.replace(".", "")
    if not a or not b:
        return False
    if a == b:
        return True
    sa, sb = klucz_skrocony(a).split(), klucz_skrocony(b).split()
    krotszy, dluzszy = (sa, sb) if len(sa) <= len(sb) else (sb, sa)
    if len(krotszy) >= 2:
        return dluzszy[:len(krotszy)] == krotszy       # "l yamal" ~ "l yamal nasraoui"
    # jednoczłonowa nazwa ("Mbappé", "Pedri"): musi być członem nazwiska drugiej strony
    return krotszy[0] in a.split() and krotszy[0] in b.split()


def filtruj_strzelcow(
    gs: dict[str, float] | None, nazwa: str
) -> tuple[dict[str, float], bool]:
    """Udziały w golach zawężone do obecnego składu + flaga "zweryfikowano".

    Flaga True tylko, gdy skład był znany i filtr faktycznie zadziałał. Nieznany
    skład, albo zero trafień (podejrzane: raczej rozjazd zapisu niż wymiana całej
    kadry) => wejście bez zmian i False. Zwraca nowy słownik.
    """
    if not gs:
        return {}, False
    sklad = aktualny_sklad(nazwa)
    if sklad is None:
        return dict(gs), False
    zostaja = {n: v for n, v in gs.items() if any(_ten_gracz(n, k) for k in sklad)}
    if not zostaja:
        log.warning("FotMob: zaden strzelec %r nie pasuje do skladu — bez filtra", nazwa)
        return dict(gs), False
    return zostaja, True


def strzelcy_w_skladzie(gs: dict[str, float] | None, nazwa: str) -> dict[str, float]:
    """Sam słownik z `filtruj_strzelcow` (dla wywołujących bez potrzeby flagi)."""
    return filtruj_strzelcow(gs, nazwa)[0]
