"""
BetBuilder kombinacje z EV filtrowaniem.

Użycie (Superbet API data):
    typy = [Typ("1", 1.60), Typ("Over 1.5", 1.25), Typ("BTTS", 1.80)]
    combos = generuj_kombinacje(typy, kurs_rynkowy=3.20)

Użycie (Poisson suggestions → AI context):
    formatted = fmt_bb_sugestie(w["bet_builder"])
"""

import re
from dataclasses import dataclass
from itertools import combinations
from math import prod

_SPRZECZNE: list[frozenset[str]] = [
    frozenset({"1", "2"}),
    frozenset({"1", "X"}),
    frozenset({"X", "2"}),
    frozenset({"Over", "Under"}),
    frozenset({"BTTS_TAK", "BTTS_NIE"}),
    frozenset({"Over 2.5", "Under 2.5"}),
    frozenset({"Over 1.5", "Under 1.5"}),
]


@dataclass(frozen=True)
class Typ:
    nazwa: str
    kurs: float


@dataclass(frozen=True)
class Kombinacja:
    typy: tuple[Typ, ...]
    kurs_laczny: float
    ev: float | None  # None gdy brak kurs_rynkowy


def _sprzeczne(typy: tuple[Typ, ...]) -> bool:
    nazwy = {t.nazwa for t in typy}
    return any(para <= nazwy for para in _SPRZECZNE)


def generuj_kombinacje(
    typy: list[Typ],
    kurs_rynkowy: float | None = None,
    min_typy: int = 2,
    min_kurs: float = 1.60,
    min_ev: float = 0.10,
) -> list[Kombinacja]:
    """Generuje niesprzeczne kombinacje z filtrami kurs i EV."""
    if not typy:
        return []
    wyniki: list[Kombinacja] = []
    for r in range(min_typy, len(typy) + 1):
        for combo in combinations(typy, r):
            if _sprzeczne(combo):
                continue
            kurs_l = round(prod(t.kurs for t in combo), 3)
            if kurs_l < min_kurs:
                continue
            ev = round(kurs_l / kurs_rynkowy - 1, 4) if kurs_rynkowy else None
            if kurs_rynkowy and (ev is None or ev < min_ev):
                continue
            wyniki.append(Kombinacja(typy=combo, kurs_laczny=kurs_l, ev=ev))
    return sorted(wyniki, key=lambda k: k.ev or 0.0, reverse=True)


def _parsuj_prob(s: str) -> float | None:
    """Parsuje 'Szansa: 45%' → 0.45 z napisu Poisson sugestii."""
    m = re.search(r'Szansa:\s*(\d+)%', s)
    return int(m.group(1)) / 100.0 if m else None


def fmt_bb_sugestie(
    sugestie: list[str],
    kurs_rynkowy: float | None = None,
    max_items: int = 8,
) -> list[str]:
    """
    Konwertuje Poisson sugestie do formatu z kurs_fair dla kontekstu AI.
    Wejście: ["1 & Over 1.5 (Szansa: 45%)", ...]
    Wyjście: ["1 & Over 1.5 @2.22 (p=45%)", ...]
    """
    wyniki: list[str] = []
    for s in sugestie[:max_items]:
        prob = _parsuj_prob(s)
        nazwa = re.sub(r'\s*\(Szansa:.*?\)', '', s).strip()
        if prob and prob > 0:
            kurs_f = round(1.0 / prob, 2)
            ev_str = ""
            if kurs_rynkowy and kurs_rynkowy > 1.0:
                ev = kurs_f / kurs_rynkowy - 1.0
                ev_str = f" EV={ev * 100:+.0f}%"
            wyniki.append(f"{nazwa} @{kurs_f}{ev_str} (p={int(prob * 100)}%)")
        else:
            wyniki.append(nazwa)
    return wyniki
