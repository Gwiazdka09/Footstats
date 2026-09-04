#!/usr/bin/env python
"""ev_po_najlepszej_cenie.py — czy da się zarobić po cenie, po której się stawia.

===========================  PRE-REJESTRACJA  ===============================
Spisana 2026-09-04, PRZED zobaczeniem jakiejkolwiek liczby ROI z tych danych.

DLACZEGO TO OSOBNE PYTANIE, MIMO ŻE BRIER JUŻ ODPOWIEDZIAŁ „NIE".
Pomiar z 04.09 (n=120 351, 39 lig na 39) pokazał, że model jest gorszy od
zdewigowanej ceny. To zamyka pytanie „czy mamy więcej informacji niż rynek".
NIE zamyka pytania „czy da się zarobić", i to nie jest wykręt:

  * Brier porównuje nas ze ŚREDNIĄ (a właściwie: w 22 ligach z ceną
    przedmeczową, w 17 z zamknięciem — patrz `_wpisz_ostre_i_najlepsze`);
  * stawia się po cenie NAJLEPSZEJ z rynku, nie po średniej;
  * model gorszy od ceny ostrej może wciąż trafiać na kursy, w których
    KONKRETNA książka pomyliła się bardziej niż my. Tak wygląda realne
    obstawianie: nie bije się rynku, bije się najsłabszą ofertę w rynku.

To pytanie było dotąd NIEMIERZALNE, bo dataset niósł wyłącznie średnią.
`odds_*_max` (maksimum na zamknięciu) istnieje od 04.09.

REGUŁA ZAKŁADU — JEDNA, BEZ WOLNYCH PARAMETRÓW:
  Dla każdego meczu i każdego z trzech wyników liczymy EV = p * kurs_max − 1.
  Stawiamy PŁASKO jedną jednostkę na każdy zakład o EV > 0.

Próg zero nie jest strojony — to definicja dodatniej wartości oczekiwanej.
Każdy inny próg (EV>5%, EV>10%) byłby wolnym parametrem, a przy 39 ligach
wracamy prosto do 52 podzbiorów z 14.08, z których zero przeżyło holdout.
Krzywą ROI po progach raportujemy POGLĄDOWO, ale decyzja zapada na progu zero.

DWA ŹRÓDŁA PRAWDOPODOBIEŃSTWA, oba raportowane, żadne nie wybierane po fakcie:
  `model`     — czysty Poisson + siła ligowa (bez ensembla);
  `produkcja` — blend z ceną przy wadze rynku 0.7, czyli to, czym produkcja
                realnie by obstawiała.

PODATEK. W Polsce 12% od stawki (obrotu), potrącane przy zawarciu zakładu.
Raportujemy ROI brutto ORAZ po podatku — sam brutto systematycznie zawyża
i to jest dokładnie ta liczba, na którą łatwo się nabrać.

BŁĄD STANDARDOWY OBOWIĄZKOWY. ROI bez SE to liczba bez znaczenia: przy kilkuset
zakładach rozrzut sięga kilkunastu punktów procentowych, a `feedback_kubelki_bez_se`
zapisuje dwa fałszywe wnioski wyciągnięte jednego dnia z tabel bez SE.

REGUŁA DECYZYJNA, ZAMROŻONA:
  * ROI po podatku ujemne albo nieistotne (z < 2)  →  pytanie o obstawianie
    ZAMKNIĘTE. Nie szukamy progów, lig ani rynków, na których „jednak wyszło".
  * ROI po podatku dodatnie z z >= 2  →  to HIPOTEZA, nie zielone światło.
    Warunkiem jest holdout po dacie (trening < 2023-01-01), pre-rejestrowany
    osobno, ORAZ sprawdzenie, czy wynik nie stoi na jednej lidze.

CZEGO TEN POMIAR NIE OBEJMUJE, a co zmniejszyłoby realny wynik:
  * `MaxC` to najlepszy kurs U DOWOLNEJ książki w chwili zamknięcia. Konto
    trzeba mieć akurat tam, limit musi wystarczyć, a książki ograniczają
    wygrywających. Zmierzone ROI jest więc SUFITEM, nie prognozą;
  * `MaxC` istnieje od sezonu 1920, więc próba jest krótsza niż w pomiarze
    Brierowym.
=============================================================================

    python scripts/ev_po_najlepszej_cenie.py --zrzut sciezka/zrzut*.parquet
"""
from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

PODATEK = 0.12          # PL: 12% od stawki, potracane przy zawarciu zakladu
WAGA_RYNKU_PROD = 0.7   # ENSEMBLE_MARKET_WEIGHT na produkcji
PROGI_POGLADOWE = (0.0, 0.05, 0.10, 0.20)
WYNIK_NA_INDEKS = {"H": 0, "D": 1, "A": 2}
KOL_MAX = ("odds_h_max", "odds_d_max", "odds_a_max")


def wczytaj(wzorce: list[str]) -> pd.DataFrame:
    pliki: list[str] = []
    for w in wzorce:
        pliki += sorted(glob.glob(w))
    if not pliki:
        raise SystemExit(f"Zero plikow dla {wzorce}")
    df = pd.concat([pd.read_parquet(p) for p in pliki], ignore_index=True)
    df = df[df["actual_res"].isin(WYNIK_NA_INDEKS)]
    brak = [k for k in KOL_MAX if k not in df.columns]
    if brak:
        raise SystemExit(f"Zrzut bez kolumn najlepszej ceny: {brak}."
                         " Potrzebny przebieg po 2026-09-04.")
    df = df.dropna(subset=list(KOL_MAX))
    df["match_date"] = pd.to_datetime(df["match_date"], errors="coerce")
    return df.dropna(subset=["match_date"])


def prawdopodobienstwa(df: pd.DataFrame, zrodlo: str) -> np.ndarray | None:
    """Rozkład 1X2 w skali 0..1. `model` = czysty; `produkcja` = blend z ceną."""
    from footstats.core.wf_harness import devig_1x2

    model = df[["pw", "pr", "pp"]].to_numpy(dtype=float) / 100.0
    if zrodlo == "model":
        return model

    rynek = np.full_like(model, np.nan)
    for i, r in enumerate(df.itertuples(index=False)):
        p = devig_1x2(r.odds_h, r.odds_d, r.odds_a)
        if p is not None:
            rynek[i] = [p["pw"] / 100.0, p["pr"] / 100.0, p["pp"] / 100.0]
    # Mecz bez ceny nie ma z czym sie blendowac — zostaje czysty model, tak jak
    # robi to `predict_one` (flaga `no_odds`).
    brak = np.isnan(rynek).any(axis=1)
    mix = (1 - WAGA_RYNKU_PROD) * model + WAGA_RYNKU_PROD * rynek
    mix[brak] = model[brak]
    return mix


def rozlicz(p: np.ndarray, kursy: np.ndarray, y: np.ndarray,
            prog: float) -> dict:
    """Płaski zakład 1 jednostka na każdy wynik o EV > `prog`.

    Zwraca ROI brutto i po podatku, z błędem standardowym liczonym z rozkładu
    zwrotów POJEDYNCZYCH zakładów — nie z sumy, bo sumaryczne ROI bez SE nie
    pozwala odróżnić przewagi od kilkuset rzutów monetą.
    """
    ev = p * kursy - 1.0
    maska = ev > prog
    n = int(maska.sum())
    if n == 0:
        return {"n": 0, "roi": None, "roi_po": None, "se": None, "z": None,
                "trafione": 0}

    trafiony = np.zeros_like(kursy, dtype=bool)
    trafiony[np.arange(len(y)), y] = True

    # Zwrot z JEDNEJ jednostki: kurs-1 przy trafieniu, -1 przy pudle.
    zwroty = np.where(trafiony[maska], kursy[maska] - 1.0, -1.0)
    # Podatek od stawki: kazdy zaklad kosztuje 1+PODATEK, wygrana bez zmian.
    zwroty_po = zwroty - PODATEK

    sr = float(zwroty.mean())
    se = float(zwroty.std(ddof=1) / np.sqrt(n)) if n > 1 else None
    return {
        "n": n,
        "trafione": int(trafiony[maska].sum()),
        "roi": 100 * sr,
        "roi_po": 100 * float(zwroty_po.mean()),
        "se": 100 * se if se else None,
        "z": (float(zwroty_po.mean()) / se) if se else None,
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--zrzut", nargs="+", required=True)
    args = p.parse_args()

    df = wczytaj(args.zrzut)
    kursy = df[list(KOL_MAX)].to_numpy(dtype=float)
    y = df["actual_res"].map(WYNIK_NA_INDEKS).to_numpy(dtype=int)
    print(f"Zakladow mozliwych: {len(df)} meczow x 3 wyniki"
          f" | okres {df['match_date'].min():%Y-%m} .. {df['match_date'].max():%Y-%m}")

    for zrodlo in ("model", "produkcja"):
        pr = prawdopodobienstwa(df, zrodlo)
        if pr is None:
            continue
        print(f"\n{'=' * 88}")
        print(f"  ZRODLO PRAWDOPODOBIENSTWA: {zrodlo}"
              + ("  (blend z cena przy wadze rynku 0.7)" if zrodlo == "produkcja" else ""))
        print(f"{'=' * 88}")
        print(f"{'prog EV':>9}{'zakladow':>10}{'trafione':>10}{'ROI brutto':>12}"
              f"{'ROI po 12%':>12}{'SE':>9}{'z':>7}")
        for prog in PROGI_POGLADOWE:
            w = rozlicz(pr, kursy, y, prog)
            if not w["n"]:
                print(f"{prog:>9.0%}{'brak zakladow':>42}")
                continue
            gwiazdka = " <- DECYZJA" if prog == 0.0 else ""
            print(f"{prog:>9.0%}{w['n']:>10}{w['trafione']:>10}"
                  f"{w['roi']:>+11.2f}%{w['roi_po']:>+11.2f}%"
                  f"{w['se']:>8.2f}%{w['z']:>+7.2f}{gwiazdka}")

        decyzja = rozlicz(pr, kursy, y, 0.0)
        if decyzja["n"] and decyzja["z"] is not None:
            print(f"\n  REGULA DECYZYJNA (zamrozona przed przebiegiem), zrodlo `{zrodlo}`:")
            if decyzja["roi_po"] > 0 and decyzja["z"] >= 2:
                print(f"    ROI po podatku {decyzja['roi_po']:+.2f}% przy z={decyzja['z']:+.2f}")
                print("    -> HIPOTEZA, nie zielone swiatlo. Wymaga holdoutu po dacie")
                print("       i sprawdzenia, czy nie stoi na jednej lidze.")
            else:
                print(f"    ROI po podatku {decyzja['roi_po']:+.2f}% przy z={decyzja['z']:+.2f}")
                print("    -> pytanie o obstawianie ZAMKNIETE dla tego zrodla.")
                print("       Bez szukania progow, lig i rynkow, na ktorych 'jednak wyszlo'.")

    print("\n  SUFIT, NIE PROGNOZA: `MaxC` to najlepszy kurs u DOWOLNEJ ksiazki")
    print("  na zamknieciu. Trzeba tam miec konto, limit musi wystarczyc,")
    print("  a ksiazki ograniczaja wygrywajacych. Realny wynik bylby nizszy.")


if __name__ == "__main__":
    main()
