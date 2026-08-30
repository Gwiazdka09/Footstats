"""
base.py — wspólny interfejs źródeł team-news (przewidywany skład, absencje, sędzia).

Bliźniak `scrapers/sources/base.py`, ale dla danych PRZEDmeczowych. Implementacje
są graceful (błąd → pusta lista), lecz NIE ciche: awaria źródła musi zostawić log
na ERROR, bo dla nieoficjalnego API to jedyny sygnał, że przestało istnieć.
"""
from __future__ import annotations

import typing
import unicodedata
from dataclasses import dataclass, field


def klucz_gracza(nazwisko: str) -> str:
    """
    Nazwisko do porownania miedzy zrodlami: bez diakrytykow, casefold,
    pojedyncze spacje.

    JEDNA definicja dla calego projektu. Dwie kopie tej normalizacji rozjechalyby
    sie po cichu, a objawem byloby "gracz nie znaleziony" — czyli brak korekty
    lambda, nie blad.
    """
    bez_znakow = unicodedata.normalize("NFKD", nazwisko or "")
    bez_znakow = "".join(c for c in bez_znakow if not unicodedata.combining(c))
    return " ".join(bez_znakow.casefold().split())

# Wartości `expectedReturn`, które znaczą "może zagra". Zbiór, nie pojedyncza
# stała, bo źródło używa też innych wariantów pisowni.
_NIEPEWNE = frozenset({"doubtful", "questionable", "50/50"})


def absencja_pewna(powrot: str | None) -> bool:
    """
    Czy absencja jest TWARDA (zawodnik na pewno nie zagra).

    Trzy stany wejściowe, dwa wyjściowe — i to jest celowe:

        "Mid September 2026" → True   nie zagra
        "Doubtful"           → False  może zagrać
        None / ""            → False  NIE WIADOMO, źródło nie podało

    Dwa ostatnie dają `False` z tego samego powodu: do korekty λ wolno wziąć
    wyłącznie absencję potwierdzoną. Rozróżnia je pole `Absencja.powrot`, żeby
    log mógł powiedzieć, czy źródło milczało, czy powiedziało "wątpliwy".
    """
    if not powrot or not powrot.strip():
        return False
    return powrot.strip().casefold() not in _NIEPEWNE


@dataclass(frozen=True)
class Absencja:
    """Zawodnik niedostępny na mecz."""

    nazwisko: str
    typ: str                        # "injury" / "suspension" / "unknown"
    powrot: str | None = None       # "Doubtful" | "Mid September 2026" | None
    pewna: bool = False             # patrz `absencja_pewna`
    gole_sezon: int | None = None   # performance.seasonGoals
    # "G"/"D"/"M"/"F" ze skladu druzyny; None = zrodlo nie podalo. Pozycja jest
    # WARUNKIEM dwustronnej korekty lambda: `injury_lambda_factors` klasyfikuje
    # po niej, wiec bez niej absencja nie robi nic. `unavailable[]` w matchDetails
    # jej NIE ma (positionId to None albo sentinel 1000) — przychodzi z osobnego
    # zapytania o sklad druzyny.
    pozycja: str | None = None


@dataclass(frozen=True)
class TeamNews:
    """
    Znormalizowane dane przedmeczowe z jednego źródła.

    `typ_skladu` jest osobnym polem CELOWO: "lastStarting11" to ostatni skład,
    nie prognoza na ten mecz. Zlanie go z "predicted" w jedno pole to ten sam
    błąd, co mieszanie zmierzonych procentów z domyślnymi 50/50/50
    w `scrapers/api_football.py` (naprawione 29.08) — odbiorca dostaje dane
    i nie widzi, że to nie pomiar.
    """

    source: str
    home: str
    away: str
    date: str                                       # YYYY-MM-DD
    typ_skladu: str | None = None                   # "predicted" | "lastStarting11"
    xi_home: tuple[str, ...] = ()
    xi_away: tuple[str, ...] = ()
    absencje_home: tuple[Absencja, ...] = ()
    absencje_away: tuple[Absencja, ...] = ()
    sedzia: str | None = None
    sedzia_stats: dict[str, float | None] = field(default_factory=dict)

    @property
    def sklad_jest_prognoza(self) -> bool:
        """True tylko dla realnej prognozy — nie dla ostatniej jedenastki."""
        return self.typ_skladu == "predicted"


@typing.runtime_checkable
class TeamNewsSource(typing.Protocol):
    """Adapter źródła team-news. Graceful, ale nie cichy (patrz docstring modułu)."""

    name: str

    def fetch(self, date: str) -> list[TeamNews]:
        """Zwraca dane przedmeczowe dla meczów danego dnia (YYYY-MM-DD)."""
        ...
