"""
betbuilder_rules.py — FAZA 18.1: silnik reguł korelacji dla manualnego BetBuilder.

Każdy rynek to predykat na wyniku meczu (gole_gosp, gole_gosc). Reguły wynikają
z teorii zbiorów na siatce wyników 0..MAX_GOLI — bez ręcznych tabel sprzeczności:

- SPRZECZNE: brak wspólnego wyniku (np. "1" + "2") → blokada.
- TRYWIALNE/IMPLIKOWANE: każdy wynik dotychczasowego combo spełnia już nowy typ
  (np. "1" ⇒ "Over 0.5") → blokada (nie wnosi informacji, zero value).
- DOZWOLONE: nowy typ zawęża combo i jest osiągalny (np. "1" + "Over 1.5").
"""
from __future__ import annotations

from typing import Callable

_MAX_GOLI = 7
_SIATKA: list[tuple[int, int]] = [
    (h, a) for h in range(_MAX_GOLI + 1) for a in range(_MAX_GOLI + 1)
]

# Rynek → predykat (gole_gospodarza, gole_goscia) -> bool.
# Klucze = etykiety używane w GUI/bet_builder.
_PREDYKATY: dict[str, Callable[[int, int], bool]] = {
    # 1X2
    "1": lambda h, a: h > a,
    "X": lambda h, a: h == a,
    "2": lambda h, a: a > h,
    # Totals Over
    "Over 0.5": lambda h, a: h + a >= 1,
    "Over 1.5": lambda h, a: h + a >= 2,
    "Over 2.5": lambda h, a: h + a >= 3,
    "Over 3.5": lambda h, a: h + a >= 4,
    # Totals Under
    "Under 1.5": lambda h, a: h + a <= 1,
    "Under 2.5": lambda h, a: h + a <= 2,
    "Under 3.5": lambda h, a: h + a <= 3,
    # BTTS
    "BTTS": lambda h, a: h >= 1 and a >= 1,
    "BTTS NIE": lambda h, a: h == 0 or a == 0,
    # Gole drużyn
    "Gospodarz Over 0.5": lambda h, a: h >= 1,
    "Gospodarz Over 1.5": lambda h, a: h >= 2,
    "Gość Over 0.5": lambda h, a: a >= 1,
    "Gość Over 1.5": lambda h, a: a >= 2,
    # Handicapy
    "Handicap -1 Gospodarz": lambda h, a: (h - a) >= 2,
    "Handicap +1 Gość": lambda h, a: (a + 1) >= h,
}

WSZYSTKIE_RYNKI: tuple[str, ...] = tuple(_PREDYKATY.keys())


def _zbior_wynikow(rynek: str) -> frozenset[tuple[int, int]]:
    """Zbiór wyników (h,a) spełniających dany rynek."""
    pred = _PREDYKATY[rynek]
    return frozenset((h, a) for (h, a) in _SIATKA if pred(h, a))


# Cache zbiorów (predykaty stałe).
_CACHE: dict[str, frozenset[tuple[int, int]]] = {
    r: _zbior_wynikow(r) for r in WSZYSTKIE_RYNKI
}


def _wspolny_zbior(wybrane: list[str]) -> frozenset[tuple[int, int]]:
    """Przecięcie zbiorów wyników wybranych rynków (cała siatka gdy pusto)."""
    wynik: frozenset[tuple[int, int]] = frozenset(_SIATKA)
    for r in wybrane:
        if r in _CACHE:
            wynik &= _CACHE[r]
    return wynik


def czy_dozwolony(rynek: str, wybrane: list[str]) -> bool:
    """
    Czy `rynek` można dodać do `wybrane`?
    True gdy: wynik combo + rynek jest osiągalny (niesprzeczny) ORAZ rynek
    realnie zawęża combo (nie jest trywialnie implikowany).
    """
    if rynek in wybrane or rynek not in _CACHE:
        return False
    wspolny = _wspolny_zbior(wybrane)
    out_b = _CACHE[rynek]
    przeciecie = wspolny & out_b
    if not przeciecie:
        return False                      # sprzeczność — brak wspólnego wyniku
    if wspolny <= out_b:
        return False                      # trywialne — combo już implikuje rynek
    return True


def dozwolone_dodatki(wybrane: list[str]) -> list[str]:
    """Lista rynków, które legalnie można dodać do obecnego combo."""
    return [r for r in WSZYSTKIE_RYNKI if czy_dozwolony(r, wybrane)]


def powod_blokady(rynek: str, wybrane: list[str]) -> str | None:
    """Zwraca powód blokady rynku (do UI tooltipa) lub None gdy dozwolony."""
    if rynek in wybrane:
        return "już wybrany"
    if rynek not in _CACHE:
        return "nieznany rynek"
    wspolny = _wspolny_zbior(wybrane)
    out_b = _CACHE[rynek]
    if not (wspolny & out_b):
        return "sprzeczny z wybranymi typami"
    if wspolny <= out_b:
        return "trywialny — już wynika z wybranych typów"
    return None


def szansa_combo(wybrane: list[str], macierz) -> float:
    """
    Skorelowana szansa combo: suma prawdopodobieństw wyników (h,a) spełniających
    WSZYSTKIE wybrane rynki, wg macierzy Poissona (probability_matrix).
    Zwraca 0.0 gdy brak wybranych lub combo sprzeczne.
    """
    if not wybrane:
        return 0.0
    wspolny = _wspolny_zbior(wybrane)
    if not wspolny:
        return 0.0
    total = 0.0
    n = len(macierz)
    for (h, a) in wspolny:
        if h < n and a < len(macierz[h]):
            total += float(macierz[h][a])
    return total
