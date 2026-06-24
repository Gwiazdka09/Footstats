"""Output formatting helpers for FootStats AI analyzer.

Extracted from analyzer.py — display/print functions.
"""
from __future__ import annotations


def wyswietl_analiza_ai(wynik: dict) -> None:
    """Wyświetla wynik analizy AI w czytelnym formacie."""
    g  = wynik.get("gospodarz", "")
    a  = wynik.get("goscie", "")
    t  = wynik.get("typ", "?")
    p  = wynik.get("pewnosc", 0)
    uz = wynik.get("uzasadnienie", "")
    vb = wynik.get("value_bet", False)
    vb_opis = wynik.get("value_bet_opis", "")
    alt = wynik.get("alternatywny_typ", "")
    ost = wynik.get("ostrzezenia", "")

    separator = "═" * 55
    print(f"\n{separator}")
    print(f"  AI ANALIZA: {g} vs {a}")
    print(separator)
    print(f"  TYP:      {t}")
    print(f"  PEWNOSC:  {p}%")
    print("\n  UZASADNIENIE:")
    print(f"  {uz}")

    if vb and vb_opis:
        print(f"\n  VALUE BET: {vb_opis}")

    if alt:
        print(f"\n  Alternatywny typ: {alt}")

    if ost:
        print(f"\n  Ostrzezenia: {ost}")

    k1 = wynik.get("k1")
    kx = wynik.get("kX")
    k2 = wynik.get("k2")
    if k1:
        print(f"\n  Kursy: 1={k1}  X={kx}  2={k2}")

    pw = wynik.get("p_wygrana", 0)
    pr = wynik.get("p_remis", 0)
    pp = wynik.get("p_przegrana", 0)
    print(f"  Model:    1={pw:.1f}%  X={pr:.1f}%  2={pp:.1f}%")
    print(separator)
