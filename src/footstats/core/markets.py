"""
markets.py — FAZA 20: katalog rynków bramkowych liczony z macierzy Poissona.

Z dwóch lambd (λ_dom, λ_gość) macierz daje dokładne prawdopodobieństwo KAŻDEGO
rynku bramkowego — jeden model, spójna pewność. Wszystkie tipy są w formacie
rozliczalnym przez `oblicz_tip_correct` (rozliczenie z wyniku końcowego).

Kurs: Bzzoiro gdy dostępny dla danego rynku, inaczej fair (1/prawdopodobieństwo).
Rynki zawodników/kartek/rożnych NIE są tu — brak danych do rozliczenia.
"""
from __future__ import annotations

import math

from footstats.core.bet_builder import probability_matrix

# Mapowanie rynku → klucz kursu Bzzoiro (gdy bukmacher go ma)
_BZZ_KEY = {
    "1": "home", "X": "draw", "2": "away",
    "Over 2.5": "over_2_5", "Under 2.5": "under_2_5", "BTTS": "btts",
}


def _suma(mat, pred) -> float:
    n = len(mat)
    return sum(
        mat[h][a]
        for h in range(n)
        for a in range(len(mat[h]))
        if pred(h, a)
    )


def _fair(prob: float) -> float:
    """Fair odds = 1/prawdopodobieństwo (bez marży). Cap 1.01–99.0."""
    if prob <= 0.0101:
        return 99.0
    return max(1.01, round(1.0 / prob, 2))


def build_market_catalog(lh: float, la: float, bzz_odds: dict | None = None) -> list[dict]:
    """
    Zwraca listę grup rynków: [{grupa, rynki: [{rynek, tip, szansa, kurs, zrodlo}]}].
    tip — format rozliczalny przez oblicz_tip_correct.
    """
    mat = probability_matrix(lh, la)
    bzz = bzz_odds or {}

    def entry(rynek: str, tip: str, prob: float) -> dict:
        okey = _BZZ_KEY.get(tip)
        kurs_bzz = bzz.get(okey) if okey else None
        if kurs_bzz:
            kurs, zrodlo = round(float(kurs_bzz), 2), "bzzoiro"
        else:
            kurs, zrodlo = _fair(prob), "fair"
        return {
            "rynek": rynek, "tip": tip,
            "szansa": round(prob * 100, 1), "kurs": kurs, "zrodlo": zrodlo,
        }

    grupy: list[dict] = []

    grupy.append({"grupa": "Wynik meczu", "rynki": [
        entry("1", "1", _suma(mat, lambda h, a: h > a)),
        entry("X", "X", _suma(mat, lambda h, a: h == a)),
        entry("2", "2", _suma(mat, lambda h, a: a > h)),
    ]})

    grupy.append({"grupa": "Podwójna szansa", "rynki": [
        entry("1X", "1X", _suma(mat, lambda h, a: h >= a)),
        entry("X2", "X2", _suma(mat, lambda h, a: a >= h)),
        entry("12", "12", _suma(mat, lambda h, a: h != a)),
    ]})

    # Czytelność (06-22): wszystkie Over na górze (rosnąco), potem wszystkie Under — nie przeplatane.
    linie_gole = (0.5, 1.5, 2.5, 3.5, 4.5)
    gole = [entry(f"Over {L}", f"Over {L}", _suma(mat, lambda h, a, L=L: h + a > L)) for L in linie_gole]
    gole += [entry(f"Under {L}", f"Under {L}", _suma(mat, lambda h, a, L=L: h + a < L)) for L in linie_gole]
    grupy.append({"grupa": "Liczba goli", "rynki": gole})

    grupy.append({"grupa": "Gole gospodarza", "rynki": [
        entry(f"Gospodarz Over {L}", f"1 Over {L}", _suma(mat, lambda h, a, L=L: h > L))
        for L in (0.5, 1.5, 2.5)
    ]})
    grupy.append({"grupa": "Gole gościa", "rynki": [
        entry(f"Gość Over {L}", f"2 Over {L}", _suma(mat, lambda h, a, L=L: a > L))
        for L in (0.5, 1.5, 2.5)
    ]})

    grupy.append({"grupa": "Obie strzelą", "rynki": [
        entry("BTTS: tak", "BTTS", _suma(mat, lambda h, a: h >= 1 and a >= 1)),
        entry("BTTS: nie", "BTTS NIE", _suma(mat, lambda h, a: h == 0 or a == 0)),
    ]})

    grupy.append({"grupa": "Handicap", "rynki": [
        entry("1 (-0.5)", "1 (-0.5)", _suma(mat, lambda h, a: h > a)),
        entry("2 (+0.5)", "2 (+0.5)", _suma(mat, lambda h, a: a >= h)),
        entry("1 (-1.5)", "1 (-1.5)", _suma(mat, lambda h, a: (h - a) >= 2)),
        entry("2 (+1.5)", "2 (+1.5)", _suma(mat, lambda h, a: (h - a) <= 1)),
        entry("1 (-2.5)", "1 (-2.5)", _suma(mat, lambda h, a: (h - a) >= 3)),
        entry("2 (+2.5)", "2 (+2.5)", _suma(mat, lambda h, a: (h - a) <= 2)),
    ]})

    grupy.append({"grupa": "Inne", "rynki": [
        entry("Gospodarz do zera", "2 Under 0.5", _suma(mat, lambda h, a: a == 0)),
        entry("Gość do zera", "1 Under 0.5", _suma(mat, lambda h, a: h == 0)),
        entry("Parzysta liczba goli", "PARZYSTE", _suma(mat, lambda h, a: (h + a) % 2 == 0)),
        entry("Nieparzysta liczba goli", "NIEPARZYSTE", _suma(mat, lambda h, a: (h + a) % 2 == 1)),
    ]})

    # Multigoal — łączna liczba goli w przedziale (rozliczane "MULTIGOAL lo-hi").
    multigoal = []
    for lo, hi in ((0, 1), (1, 2), (2, 3), (3, 4), (1, 3), (2, 4), (4, 6)):
        multigoal.append(entry(
            f"Multigoal {lo}-{hi}", f"Multigoal {lo}-{hi}",
            _suma(mat, lambda h, a, L=lo, H=hi: L <= h + a <= H),
        ))
    grupy.append({"grupa": "Multigoal", "rynki": multigoal})

    # "Mecz & gol w każdej połowie" (jak Superbet): wybrany wynik 1X2 ORAZ ≥1 gol
    # (łącznie, dowolna drużyna) w 1. połowie ORAZ ≥1 gol w 2. połowie.
    # Model połów: μ = (lh+la)/2 — oczekiwana łączna liczba goli na połowę (Poisson
    # zakłada równy podział tempa strzeleckiego między połowy). P(gol w połowie)
    # = 1 - exp(-μ). Połowy przyjęto jako iid i niezależne od końcowego wyniku
    # (aproksymacja — uproszczenie, nie pełny model bivariate-Poisson per połowa).
    mu_polowa = (lh + la) / 2.0
    p_gol_w_polowie = 1.0 - math.exp(-mu_polowa)
    p_gg2h = p_gol_w_polowie ** 2
    p1 = _suma(mat, lambda h, a: h > a)
    px = _suma(mat, lambda h, a: h == a)
    p2 = _suma(mat, lambda h, a: a > h)
    grupy.append({"grupa": "Mecz & gol w każdej połowie", "rynki": [
        entry("1 & gol w każdej poł", "1 & GG2H", p1 * p_gg2h),
        entry("X & gol w każdej poł", "X & GG2H", px * p_gg2h),
        entry("2 & gol w każdej poł", "2 & GG2H", p2 * p_gg2h),
    ]})

    # Dokładny wynik — top-10 najbardziej prawdopodobnych wyników (rozliczane "Wynik h:a").
    n = len(mat)
    top_wyniki = sorted(
        ((mat[h][a], h, a) for h in range(n) for a in range(len(mat[h]))),
        key=lambda t: t[0], reverse=True,
    )[:10]
    grupy.append({"grupa": "Dokładny wynik", "rynki": [
        entry(f"Wynik {h}:{a}", f"Wynik {h}:{a}", prob) for prob, h, a in top_wyniki
    ]})

    return grupy
