"""
clubelo.py — ClubElo (http://api.clubelo.com) jako niezależny sygnał siły drużyn.

Darmowe, BEZ klucza i bez anti-bota, format CSV. Dwa użyteczne endpointy:

  `/<YYYY-MM-DD>` i `/<Klub>`
      Rankingi Elo. Każdy wiersz ma `From`/`To`, więc historia jest datowana —
      da się jej użyć w walk-forward bez lookaheadu (bierzemy stan na dzień
      PRZED meczem, nie dzisiejszy).

  `/Fixtures`
      Nadchodzące mecze wraz z ROZKŁADEM DOKŁADNYCH WYNIKÓW (kolumny `R:0-0`
      … `R:6-0`). Z tego wyliczamy 1X2 / BTTS / Over 2.5 — czyli dostajemy
      niezależny model do porównania z naszym Poissonem, za darmo.

Dlaczego to jest wartościowe: nasze λ liczy się z historii goli, więc Elo jest
estymatorem **ortogonalnym**. Nadaje się na cechę ensemble albo na sanity-check
("model daje 60% faworytowi, którego Elo jest niższe" = sygnał ostrzegawczy).

ŚWIADOMIE nie wpinamy tego w λ ani w selekcję. Zmiana modelu jest model-critical
i wymaga walk-forward + zgody usera (patrz reguły projektu). Na razie to sygnał
OBOK modelu, nie w jego środku.
"""
from __future__ import annotations

import csv
import io
import logging
import re
from datetime import date

import requests

log = logging.getLogger(__name__)

_BASE = "http://api.clubelo.com"
_TIMEOUT = 20
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

# Kolumny rozkładu wyników: dokładnie "R:<gole_gosp>-<gole_gosc>".
# GD<-5 / GD=0 itd. to rozkład RÓŻNICY bramek — nie wolno ich sumować razem z R:.
_WZOR_WYNIKU = re.compile(r"^R:(\d+)-(\d+)$")


def _pobierz_csv(url: str) -> str | None:
    """Surowy CSV spod URL. None przy dowolnym błędzie — źródło jest opcjonalne."""
    try:
        r = requests.get(url, headers={"User-Agent": _UA}, timeout=_TIMEOUT)
    except (OSError, ValueError) as e:
        log.warning("ClubElo %s nieosiągalne: %s", url, e)
        return None
    if r.status_code != 200:
        log.warning("ClubElo %s → HTTP %s", url, r.status_code)
        return None
    return r.text


def _wiersze(tekst: str) -> list[dict]:
    """CSV → lista dictów. Puste/uszkodzone wejście daje pustą listę."""
    try:
        return [w for w in csv.DictReader(io.StringIO(tekst)) if w]
    except (csv.Error, ValueError) as e:
        log.debug("ClubElo: błąd parsowania CSV: %s", e)
        return []


def pobierz_ranking(dzien: str | None = None) -> dict[str, dict]:
    """
    Ranking Elo na dany dzień: {nazwa_klubu: {elo, kraj, rank, poziom}}.

    `dzien` w formacie YYYY-MM-DD (domyślnie dziś). Brak danych → {}.
    """
    dzien = dzien or date.today().isoformat()
    tekst = _pobierz_csv(f"{_BASE}/{dzien}")
    if not tekst:
        return {}

    wynik: dict[str, dict] = {}
    for w in _wiersze(tekst):
        klub = (w.get("Club") or "").strip()
        if not klub:
            continue
        try:
            elo = float(w.get("Elo") or "")
        except (TypeError, ValueError):
            continue  # wiersz bez liczbowego Elo jest bezużyteczny
        try:
            rank = int(w.get("Rank") or 0)
        except (TypeError, ValueError):
            rank = 0
        wynik[klub] = {
            "elo": round(elo, 2),
            "kraj": (w.get("Country") or "").strip(),
            "rank": rank,
            "poziom": (w.get("Level") or "").strip(),
        }
    return wynik


def elo_druzyny(nazwa: str, dzien: str | None = None) -> float | None:
    """Elo pojedynczej drużyny z rankingu dnia. None gdy nie znaleziono."""
    ranking = pobierz_ranking(dzien)
    trafienie = ranking.get(nazwa.strip())
    return trafienie["elo"] if trafienie else None


def prob_z_rozkladu(wiersz: dict) -> dict | None:
    """
    Rozkład dokładnych wyników → {pw, pr, pp, bt, o25} w procentach.

    Bierze WYŁĄCZNIE kolumny `R:x-y` (kolumny `GD*` to rozkład różnicy bramek —
    zsumowanie ich razem policzyłoby to samo dwa razy).

    Normalizuje do 100%: kolumny urywają się na 6 bramkach, więc ogon rozkładu
    ucieka i surowa suma bywa < 1. None gdy nie ma z czego liczyć.
    """
    p_dom = p_remis = p_gosc = p_btts = p_over = suma = 0.0

    for klucz, surowa in (wiersz or {}).items():
        m = _WZOR_WYNIKU.match(str(klucz).strip())
        if not m:
            continue
        try:
            p = float(surowa)
        except (TypeError, ValueError):
            continue
        if p <= 0:
            continue

        gole_g, gole_a = int(m.group(1)), int(m.group(2))
        suma += p
        if gole_g > gole_a:
            p_dom += p
        elif gole_g == gole_a:
            p_remis += p
        else:
            p_gosc += p
        if gole_g > 0 and gole_a > 0:
            p_btts += p
        if gole_g + gole_a >= 3:
            p_over += p

    if suma <= 0:
        return None

    return {
        "pw": round(p_dom / suma * 100, 1),
        "pr": round(p_remis / suma * 100, 1),
        "pp": round(p_gosc / suma * 100, 1),
        "bt": round(p_btts / suma * 100, 1),
        "o25": round(p_over / suma * 100, 1),
    }


def pobierz_fixtures() -> list[dict]:
    """
    Nadchodzące mecze z prognozą ClubElo.

    Zwraca [{data, liga, gospodarz, goscie, prob}], gdzie `prob` to
    {pw, pr, pp, bt, o25}. Mecz bez użytecznego rozkładu jest pomijany —
    lepiej go nie mieć niż mieć z wyzerowaną prognozą.
    """
    tekst = _pobierz_csv(f"{_BASE}/Fixtures")
    if not tekst:
        return []

    mecze: list[dict] = []
    for w in _wiersze(tekst):
        gosp = (w.get("Home") or "").strip()
        gosc = (w.get("Away") or "").strip()
        if not gosp or not gosc:
            continue
        prob = prob_z_rozkladu(w)
        if not prob:
            continue
        mecze.append({
            "data": (w.get("Date") or "").strip(),
            "liga": (w.get("Country") or "").strip(),
            "gospodarz": gosp,
            "goscie": gosc,
            "prob": prob,
            "zrodlo": "clubelo",
        })
    return mecze
