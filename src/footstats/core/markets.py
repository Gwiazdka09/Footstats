"""
markets.py — FAZA 20: katalog rynków bramkowych liczony z macierzy Poissona.

Z dwóch lambd (λ_dom, λ_gość) macierz daje dokładne prawdopodobieństwo KAŻDEGO
rynku bramkowego — jeden model, spójna pewność. Wszystkie tipy są w formacie
rozliczalnym przez `oblicz_tip_correct` (rozliczenie z wyniku końcowego).

Kurs: Bzzoiro gdy dostępny dla danego rynku, inaczej fair (1/prawdopodobieństwo).
Rynki zawodników/kartek/rożnych NIE są tu — brak danych do rozliczenia.
"""
from __future__ import annotations

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

    gole = []
    for linia in (0.5, 1.5, 2.5, 3.5, 4.5):
        gole.append(entry(f"Over {linia}", f"Over {linia}", _suma(mat, lambda h, a, L=linia: h + a > L)))
        gole.append(entry(f"Under {linia}", f"Under {linia}", _suma(mat, lambda h, a, L=linia: h + a < L)))
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

    return grupy
